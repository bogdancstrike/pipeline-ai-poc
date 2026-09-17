# Video Analysis Pipeline — QF Framework

A **7-worker** pipeline built on the **QF Framework** (`dist/qf-1.0.5`). It takes
one **video path**, fans it out to four AI services in parallel (face matching,
description, transcription, on-screen OCR), folds what is visible into a single
titled string, prompts a summary service three times with it, and writes one
enriched JSON record per video.

Any single worker can also be run on its own from Swagger — synchronously, with
the answer in the HTTP response and nothing published to Kafka. See
**[`../docs/call_ai_individually.md`](../docs/call_ai_individually.md)**.

![Worker topology](../docs/diagram-1-worker-topology.svg)

**The five AI services are not part of docker-compose.** They live on their own
host (`172.17.12.80:8821-8825` by default) and are reached over HTTP. Every AI
call has its own `MOCK_WORKER_<NAME>` switch, so the whole pipeline runs end to
end without them — same topics, same message shapes, same code path.

For the full reference — every worker, every topic, every message shape, the AI
contracts, failure behaviour and how to extend it — see
**[`../docs/architecture.md`](../docs/architecture.md)**.

---

## Pipeline at a glance

| # | Worker | Kind | Consumes | Produces | Job |
|---|--------|------|----------|----------|-----|
| 1 | `splitter` | handler | `video.in` | `video.{face,describe,transcribe,ocr}.in` | one path → four parallel branches |
| 2 | `face-match-main` | handler | `video.face.in` | `video.agg.face` | `:8821/match` — who is in it |
| 3 | `video-describe-354b` | handler | `video.describe.in` | `video.merge.describe` | `:8822/describe` — what happens |
| 4 | `transcribe` | handler | `video.transcribe.in` | `video.merge.transcribe` | `:8824/transcribe` — what is said |
| 5 | `video-ocr` | handler | `video.ocr.in` | `video.merge.ocr` | `:8823/ocr` — what is written |
| 6 | `aggregator-ai-caller` | **aggregator** | the three `video.merge.*` | `video.agg.ai` | merge 3, build the payload, `:8825/summarize` **×3** |
| 7 | `aggregator` | **aggregator** | `video.agg.face` + `video.agg.ai` | `video.done` | assemble the record, print it, write it |

**W2 skips W6.** The other three branches produce *content* — prose, speech and
on-screen text — so they meet in W6 and become the payload the summary prompts
read. Face matching produces *identity*: structured data for the record, not
prose for a model. It therefore publishes to `video.agg.face` only and lands in
the record as `enrichment.face_match`, which also means a slow or dead `:8821`
no longer holds up the summary, the entities or the sentiment.

Both aggregators are Redis-backed and regroup their branches by the message
`id` — 3 branches for W6, 2 for W7.

---

## Quick start

```bash
docker compose up -d --build     # kafka + kafka-ui + redis + redis-insight + app
docker compose logs -f app       # this is where the analysis is printed
```

| Service | URL |
|---------|-----|
| Swagger — `pipeline` (submit) and `workers` (run one) | <http://localhost:5000> |
| kafka-ui — browse the 11 topics | <http://localhost:8081> |
| RedisInsight — watch the aggregator keys | <http://localhost:5540> |

Submit one video — this is what starts W1:

```bash
curl -X POST http://localhost:5000/pipeline/analyze \
     -H 'Content-Type: application/json' \
     -d '{"path": "/video/migrants.mp4"}'
```

…or open <http://localhost:5000>, expand **pipeline → POST /pipeline/analyze**,
and *Try it out*. The response tells you where the record will land:

```json
{
  "id": "vid-3f2a91c4e0b7",
  "topic": "video.in",
  "path": "/video/migrants.mp4",
  "output_file": "/app/output/migrants_analysis.json",
  "status": "submitted",
  "mocked_workers": ["face-match-main", "video-describe-354b", "…"]
}
```

`./output` is bind-mounted and the container runs as your uid, so the record
shows up as `app/output/migrants_analysis.json`, owned by you.

From the command line instead:

```bash
python tools/submit_video.py /video/migrants.mp4
python tools/submit_video.py /audio/input.mp4 --language ro --task transcribe
```

---

## The `path` — read this first

`path` is opened by the **AI services**, not by this container. They run on
their own host, so it is normally *their* path, and it is forwarded untouched.

**The five services do not share a filesystem.** `/video/1.mp4` exists for
`:8821` but not for `:8823`; `/video/sna.mp4` the other way round. A live run
needs a path all four extraction services can open — give them a common mount,
or every service that cannot see the file records an error.

`./videos`, `../VIDEOS` and `./data` are mounted into the container so a
submitted path can be checked locally before it travels; set
`VIDEO_PATH_PASSTHROUGH=false` to make that check mandatory.

---

## Mocking

Seven switches in `.env`, one per AI call:

```bash
MOCK_WORKER_FACE_MATCH=True     # :8821
MOCK_WORKER_DESCRIBE=True       # :8822
MOCK_WORKER_OCR=True            # :8823
MOCK_WORKER_TRANSCRIBE=True     # :8824
MOCK_WORKER_SUMMARY=True        # :8825 summary.txt
MOCK_WORKER_ENTITIES=True       # :8825 entities.txt
MOCK_WORKER_SENTIMENT=True      # :8825 sentiment.txt
```

`True` returns the canned body from [`src/mock/mock_responses.py`](src/mock/mock_responses.py)
without opening a socket. Mix freely — mock the slow describe service and call
the rest for real. `GET /pipeline/health` lists what is mocked and what is live.

---

## What the summary service receives

W6 folds what is **visible** into one titled string and leaves what is
**audible** in another:

```json
{
  "inputs": {
    "video_description": "VIDEO DESCRIPTION\n<describe>\n\nON SCREEN TEXT\n<ocr>",
    "transcription": "<transcript>"
  },
  "prompt_text": "<the text of src/prompts/summary.txt>",
  "options": { "num_predict": 2048 }
}
```

and gets back the same envelope every time:

```json
{
  "output": "The source is a video featuring people walking on the streets…",
  "metadata": {
    "prompt_hash": "34f899…", "provider": "openai-compatible", "model": "phi4:14b-q8_0",
    "generated_at": "2026-09-17T07:30:43+00:00", "options": { "num_predict": 2048 },
    "input_tokens": 61, "output_tokens": 48, "duration_seconds": 7.307
  }
}
```

That same `inputs` dict is posted three times, once per prompt — the service
takes the prompt **text**, not a file name, so the wording lives here:

| call | file | asks for |
|------|------|----------|
| summary | `src/prompts/summary.txt` | a plain-text summary |
| entities | `src/prompts/entities.txt` | one `TYPE: value` per line |
| sentiment | `src/prompts/sentiment.txt` | a single word — `POSITIVE`/`NEGATIVE`/`NEUTRAL` |

Edit a `.txt` and restart (`docker compose restart app`) — the files are read
once at boot, and a missing or empty one fails the boot rather than the video.
`GET /pipeline/config` reports the resolved file, its size and whether it loads.
Both headings and both `inputs` key names are `.env` settings.

The identified persons are **not** in here: that branch goes straight to the
record. To see the exact payload for a given video without running the pipeline,
call `POST /workers/aggregator-ai-caller/run` and read `result.inputs`.

![Message shape](../docs/diagram-2-message-shape.svg)

---

## The output

### File — `output/<video name>_analysis.json`

Everything the AI services produced lives under `enrichment`, one entry per call:

```json
{
  "id": "vid-demo-1",
  "name": "migrants.mp4",
  "path": "/video/migrants.mp4",
  "submitted_at": "2026-09-16T12:04:19+00:00",
  "analysed_at": "2026-09-16T12:04:46+00:00",

  "enrichment": {
    "face_match":  { "persons": ["222"], "message": "…", "response": {} },
    "description": { "text": "The video captures…", "metadata": {}, "response": {} },
    "transcript":  { "text": "00: Hello.\n", "format": "dialog", "metadata": {}, "response": {} },
    "ocr":         { "text": "Reaction\n88886F…", "frames_count": 9, "metadata": {}, "response": {} },
    "summary":     { "text": "Migrants are filmed…", "prompt": "summary.txt", "metadata": {}, "response": {} },
    "entities":    { "list": ["LOCATION: Morocco", "LOCATION: Ceuta"], "text": "LOCATION: Morocco\nLOCATION: Ceuta", "prompt": "entities.txt", "metadata": {}, "response": {} },
    "sentiment":   { "text": "NEGATIVE", "prompt": "sentiment.txt", "metadata": {}, "response": {} }
  },

  "errors": {}
}
```

- `.text` / `.list` / `.persons` — the parsed value, what you normally read
- `.metadata` — the service's own metadata (model, device, timings)
- `.response` — its **complete** body, verbatim (`OUTPUT_INCLUDE_RAW=false` drops it)
- `errors` — only services that would not answer; `{}` on a clean run

The payload posted to `:8825` and the per-call provenance (mocked or live, which
URL, how long) are **not** in the record. They still travel on the branch
messages — visible in kafka-ui and in `POST /workers/{worker}/run` — and the
timings are in the `[ai]` log lines.

Written atomically, so a reader never sees half a record.

### Console

```
──────────────────────────────────────────────────────────────────────────────
 VIDEO       : migrants.mp4  (/video/migrants.mp4)
 id          : vid-demo-1
──────────────────────────────────────────────────────────────────────────────
 PERSONS     : 222
 DESCRIPTION : The video captures a dramatic and intense scene of migrants…
 ON SCREEN   : Reaction 88886F HUDDER MbA BHM @1 ADMiSSiOMS C OPENFor I n…
 TRANSCRIPT  : 00: Hello.
──────────────────────────────────────────────────────────────────────────────
 SUMMARY     : Migrants are filmed crossing from Morocco into Ceuta by sea…
 ENTITIES    : LOCATION: Morocco, LOCATION: Spain, LOCATION: Ceuta, NAME: Red Cross
 SENTIMENT   : NEGATIVE
──────────────────────────────────────────────────────────────────────────────
```

### Logs — every call, both halves

```
[W2 face-match-main] id=demo-1 START path='/video/migrants.mp4'
[ai] id=demo-1 face-match-main      --> POST http://172.17.12.80:8821/match {"path": "/video/migrants.mp4"}
[ai] id=demo-1 face-match-main      <-- 200 in 1843.2ms {"message": "…", "persons": ["222"]}
[W2 face-match-main] id=demo-1 DONE  persons=1 ['222'] in 1844.0ms
```

Bodies truncate at `AI_LOG_BODY_CHARS`; `AI_LOG_BODIES=False` keeps timings only.
A `/summarize` request logs its prompt as `<summary.txt, 1362 chars>` rather than
the whole file, so the `inputs` stay readable.

### Logs — every byte, at `LOGGING_LEVEL=DEBUG`

The two INFO lines are a readable trace. DEBUG adds, for **every** call to
**every** AI service (mocked ones included), the complete request body and the
complete response body — uncut:

```
[ai] id=demo-1 summarize:summary    --> POST http://172.17.12.80:8825/summarize {"inputs": {…}, "prompt_text": "<summary.txt, 1362 chars>", …}
[ai] id=demo-1 summarize:summary    REQUEST  POST http://172.17.12.80:8825/summarize {"inputs": {"video_description": "VIDEO DESCRIPTION\nThe video captures…", "transcription": "00: Hello."}, "prompt_text": "# OBJECTIVES\nYou are an OSINT analyst…", "options": {"num_predict": 2048}}
[ai] id=demo-1 summarize:summary    <-- 200 in 7307.0ms {"output": "Migrants are filmed…", "metadata": {…}}
[ai] id=demo-1 summarize:summary    RESPONSE 200 in 7307.0ms {"output": "Migrants are filmed crossing from Morocco into Ceuta by sea…", "metadata": {"prompt_hash": "34f899…", "model": "phi4:14b-q8_0", "input_tokens": 61, "output_tokens": 48, "duration_seconds": 7.307}}
```

So the exact prompt that produced an answer, the full transcript that went in
and every OCR frame that came back can all be read out of the log. DEBUG also
logs one line per HTTP attempt, which is where a retry becomes visible:

```
[ai] video-ocr POST http://172.17.12.80:8823/ocr attempt 1/3 timeout=600s
[ai] video-ocr http://172.17.12.80:8823/ocr attempt 1/3 -> HTTP 200 (31482 bytes)
```

`AI_LOG_DEBUG_BODY_CHARS` caps these lines (`0`, the default, means uncut) and
`AI_LOG_BODIES=False` drops payloads at every level.

---

## When a service will not answer

A four-way fan-in is only as available as its slowest branch, so by default
(`AI_FAIL_FAST=false`) a failing call is **recorded on its branch and published
anyway**: the missing section shows `(none)`, W7 still writes a record, and
`errors` names what broke. Set `AI_FAIL_FAST=true` to re-raise instead and let
the framework's retry/DLQ policy own it.

---

## HTTP API

| Method | Path | Body | Response |
|--------|------|------|----------|
| POST | `/pipeline/analyze` | `{"path"}` + optional `id`, `name`, `options` | `202 {id, topic, path, output_file, …}` |
| GET | `/pipeline/health` | — | `200 {status, kafka, workers_mocked, workers_live}` |
| GET | `/pipeline/config` | — | `200 {ai_services, mocked, prompts, topics, …}` |
| GET | `/workers/list` | — | `200 {workers: [{worker, kind, topics_in, topics_out, runs_first, mocked}], …}` |
| POST | `/workers/{worker}/run` | `{"path"}` + optional `id`, `name`, `options`, `chain`, `persist`, `message` | `200 {worker, ran_first, would_publish_to, published: false, consumed, result}` |

`options` is forwarded to the transcribe service — `language`, `task`, `format`,
`transcription_level`, `dialog_timestamps`. Anything else is ignored; omitted
keys fall back to `.env`.

The pipeline has no "get result" endpoint — its output is the console and the
record file, whose path the submit response already gives you. When you want the
answer *in* the response, call the worker directly:

```bash
# one service, on its own
curl -X POST http://localhost:5000/workers/video-ocr/run \
     -H 'Content-Type: application/json' -d '{"path": "/video/migrants.mp4"}'

# the whole pipeline, synchronously — the record comes back in the response
curl -X POST http://localhost:5000/workers/aggregator/run \
     -H 'Content-Type: application/json' -d '{"path": "/video/migrants.mp4"}'
```

Neither publishes anything to Kafka. A worker whose `MOCK_WORKER_*` flag is on
answers with its canned body here exactly as it does in the pipeline. Full
reference, with a request and a response per worker:
[`../docs/call_ai_individually.md`](../docs/call_ai_individually.md).

![Two front doors](../docs/diagram-4-two-front-doors.svg)

---

## Running locally (infra in Docker, app in your shell)

```bash
docker compose up -d kafka kafka-ui redis redis-insight
python -m venv venv && source venv/bin/activate
pip install ./dist/qf-1.0.5-py3-none-any.whl -r requirements.txt
python app.py                      # reads .env (KAFKA_BOOTSTRAP_SERVERS=localhost:9094)
```

Stop the `app` container first — both processes share the consumer group
`video-pipeline` and would split the partitions between them.

---

## Tests

```bash
pytest -m "not integration"        # 41 unit tests — no infra, no AI host
pytest -m integration              # needs kafka + redis (auto-skips otherwise)
tests/e2e/e2e_test.sh              # HTTP submit -> record, then all 7 workers directly
```

The unit suite forces every worker into mock mode, drives all seven directly and
checks the topology (one worker per topic, W2 bypassing W6, both aggregators
keyed by `id`), the titled string, the entity parsing, the record shape and the
degraded path. `tests/test_direct_workers.py` covers the `/workers/...` route:
the catalog, the upstream chaining, and that a direct run publishes nothing and
writes no file. `tests/e2e/e2e_test.sh` submits through the API and waits for a
record carrying *its own* id.

> Stop the `app` container before `pytest -m integration` — same consumer group.

---

## Configuration

Everything is env-driven (`.env`, `src/config.py`), passed to the container with
`env_file`. `GET /pipeline/config` serves the resolved values. The full table is
in [`../docs/architecture.md`](../docs/architecture.md#configuration); the knobs
you are most likely to touch:

| Var | Default | Meaning |
|-----|---------|---------|
| `MOCK_WORKER_*` | `True` | seven switches, one per AI call |
| `AI_*_URL` | `http://172.17.12.80:882x` | where each service lives |
| `AI_TIMEOUT_SEC` | `600` | a cold model on a long video |
| `AI_FAIL_FAST` | `False` | `True` = raise instead of recording the error |
| `AI_LOG_BODIES` | `True` | log request/response bodies |
| `AI_LOG_DEBUG_BODY_CHARS` | `0` | cap on the DEBUG full bodies (0 = uncut) |
| `SECTION_*` | `VIDEO DESCRIPTION` … | the three headings in `video_description` |
| `PROMPTS_DIR` | `src/prompts` | where the three prompt files are read from |
| `SUMMARY_PROMPT` / `ENTITIES_PROMPT` / `SENTIMENT_PROMPT` | `*.txt` | which prompt file each call sends |
| `TRANSCRIBE_LANGUAGE` / `_TASK` | `ar` / `translate` | transcribe defaults |
| `OUTPUT_FORMAT` | `block` | `block` \| `line` \| `json` |
| `OUTPUT_INCLUDE_RAW` | `True` | keep each service's full response body |
| `OCR_KEEP_FRAMES` | `False` | keep the per-frame OCR array |
| `AGGREGATOR_TIMEOUT_SEC` | `3600` | how long a branch waits for its siblings |
| `LOGGING_LEVEL` | `INFO` | `DEBUG` adds every AI request/response in full, plus framework dispatch traces |
| `PORT_API` / `PORT_KAFKA` / `PORT_KAFKA_UI` / `PORT_REDIS` / `PORT_REDIS_INSIGHT` | `5000` / `9094` / `8081` / `6379` / `5540` | host side of each published port — change one if it clashes |

---

## Troubleshooting

### `bind: address already in use`

```
Error response from daemon: driver failed programming external connectivity on
endpoint video-kafka-ui: Error starting userland proxy:
listen tcp4 0.0.0.0:8082: bind: address already in use
```

Something on the **host** already owns that port. Find it:

```bash
sudo ss -lptn 'sport = :8082'        # which process holds it
docker ps -a --filter publish=8082   # ...or which container
```

Then either stop that process, or move this stack's port — every host port is
an `.env` setting, and nothing inside the containers moves with it:

```bash
# app/.env
PORT_API=5000
PORT_KAFKA=9094
PORT_KAFKA_UI=8081
PORT_REDIS=6379
PORT_REDIS_INSIGHT=5540
```

```bash
docker compose up -d      # re-reads .env, no rebuild needed
```

> If you change `PORT_KAFKA`, also change the host-side
> `KAFKA_BOOTSTRAP_SERVERS=localhost:<new port>` — it is only used when you run
> the app **outside** Docker. Inside compose it is overridden to `kafka:9092`.

**The most likely cause on a server that ran an earlier version of this
project:** the containers used to be named `pipe-kafka`, `pipe-kafka-ui`,
`pipe-redis`, `pipe-redis-insight`, `pipe-app`. They are now `video-*`. If the
old ones are still up they keep holding the host ports, and compose will not
touch them because it only manages containers carrying its own project label:

```bash
docker ps -a --filter name=pipe-          # the old stack, if it is still there
docker rm -f pipe-kafka pipe-kafka-ui pipe-redis pipe-redis-insight pipe-app
docker compose down --remove-orphans      # then bring this one up cleanly
docker compose up -d --build
```

Also worth a look if two checkouts of this project exist on the machine —
compose derives its project name from the **directory name**, so
`~/a/app` and `~/b/app` are two separate stacks that will fight over the same
host ports.

### The stack is up but `/pipeline/health` says `degraded`

The app cannot reach Kafka. Check the broker is healthy and that the app is
using the in-network address:

```bash
docker compose ps                                  # kafka should be (healthy)
docker compose exec app printenv KAFKA_BOOTSTRAP_SERVERS   # must be kafka:9092
docker compose logs kafka | tail -20
```

### A video is submitted but no record appears

Both aggregators wait for **all** their branches. Follow one id through the log:

```bash
docker compose logs -f app | grep 'id=<your id>'
```

- Four `W2..W5 … DONE` lines but no `W6 … START` → a branch never arrived; look
  for `BRANCH FAILED` or check `video.dlq` in kafka-ui.
- `W6 … DONE` but no `W7` → the `video.agg.face` branch is missing, i.e. W2
  never published.
- Nothing after `W1` → the consumer is not assigned; make sure a second copy of
  the app (a local `python app.py`) is not sharing the `video-pipeline`
  consumer group.

### Errors in the record

`errors` names every service that would not answer, with its own message —
`path … does not exist` means that service cannot see the file on **its**
filesystem. See [Known constraints](../docs/architecture.md#known-constraints).

---

## Layout

```
main.py / app.py            entry point (ETL + API in one process)
src/config.py               settings + Topics
src/workers/pipeline.py     the 7 workers — nothing else
src/workers/registry.py     run any one of them directly, without Kafka
src/ai_client.py            the only module that talks to the AI services
src/mock/mock_responses.py  the canned bodies used when a worker is mocked
src/utils.py                worker plumbing, path handling, the titled string,
                              entity parsing, the record, console rendering
src/record_writer.py        W7's file sink
src/publisher.py            Kafka producer used by the API and the CLI
src/api/pipeline_endpoints.py  POST /pipeline/analyze, /health, /config
src/api/worker_endpoints.py    GET /workers/list, POST /workers/{worker}/run
maps/endpoint.json          wires both endpoint modules into Flask-RESTX + Swagger
tools/submit_video.py       submit a video from the command line
videos/                     drop a video here to mount it at /app/videos
output/                     W7's records — <video name>_analysis.json
../docs/                    architecture.md, call_ai_individually.md + 4 diagrams
```

![Deployment](../docs/diagram-3-deployment.svg)
