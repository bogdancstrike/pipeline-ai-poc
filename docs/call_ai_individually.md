# Calling one AI service on its own

The pipeline has two front doors, and this page is about the second one.

| | `POST /pipeline/analyze` | `POST /workers/{worker}/run` |
|---|---|---|
| What it does | publishes the path to `video.in` | runs one worker inside the HTTP request |
| When you get the answer | later, on the console and in `output/` | immediately, in the response body |
| Kafka | every worker, every topic | **nothing is published** |
| Redis | both aggregations buffer there | not used |
| Good for | the real thing | trying one service, debugging a prompt, checking a payload |

Everything below is on the Swagger UI at <http://localhost:5000> under the
**workers** namespace, so none of it needs `curl`.

---

## Contents

1. [Why a worker can be called directly](#why-a-worker-can-be-called-directly)
2. [The request body](#the-request-body)
3. [The response envelope](#the-response-envelope)
4. [`GET /workers/list`](#get-workerslist)
5. **One section per worker** — [W1](#w1--splitter) · [W2](#w2--face-match-main-8821-match) ·
   [W3](#w3--video-describe-354b-8822-describe) · [W4](#w4--transcribe-8824-transcribe) ·
   [W5](#w5--video-ocr-8823-ocr) · [W6](#w6--aggregator-ai-caller-8825-summarize--3) ·
   [W7](#w7--aggregator-the-whole-pipeline-synchronously)
6. [Driving a worker with your own message](#driving-a-worker-with-your-own-message)
7. [Mocking](#mocking)
8. [Errors](#errors)

---

## Why a worker can be called directly

`@kafka_handler` and `@kafka_aggregator` do **not** wrap the function they
decorate. They register a `WorkerSpec` — which keeps a reference to the function
— and return the function unchanged. Publishing a worker's return value to its
`topics_out` happens in the framework's ETL runtime *around* that call, never
inside it.

So running the worker body is just:

```python
spec.fn(message, consumer_name, metadatas)
```

That is the one line behind this endpoint (`app/src/workers/registry.py`). It
runs the same code the pipeline runs, and its return value is an ordinary dict.
Nothing is produced to Kafka, nothing is buffered in Redis, no downstream worker
is triggered. The framework is used exactly as shipped.

### How the input message is built

Each worker expects the message *its own* topic carries — which is the output of
the worker upstream of it. Rather than hard-coding those shapes, the endpoint
reads the topic graph out of the registry: for every topic in `topics_in` it
finds the worker that publishes to it, runs that one first, recursively, and
deep-merges the branches exactly as the aggregator runtime would.

```
POST /workers/video-ocr/run    ->  W1, then W5
POST /workers/aggregator/run   ->  W1, W2, W3, W4, W5, W6, then W7
```

Each worker runs **at most once per request**, so the splitter is not re-run for
every branch. `"chain": false` turns all of it off and hands the worker your
body untouched.

---

## The request body

Every field is optional, but you must give either `path` or `message`.

```jsonc
{
  "path": "/video/migrants.mp4",   // the video to run on
  "id": "try-1",                   // labels every log line; generated when omitted
  "name": "migrants.mp4",          // defaults to the file name in `path`
  "options": {"language": "ro"},   // transcribe overrides: language, task, format,
                                   //   transcription_level, dialog_timestamps
  "chain": true,                   // default: run the upstream workers first
  "persist": false,                // default: W7 does not write its record file
  "message": {}                    // feed the worker this exact message (implies chain=false)
}
```

The smallest useful call is therefore:

```json
{"path": "/video/migrants.mp4"}
```

`path` is resolved the same way `/pipeline/analyze` resolves it: looked up in
`VIDEO_SEARCH_DIRS` when the file is mounted here, otherwise forwarded to the AI
service untouched (`VIDEO_PATH_PASSTHROUGH`).

---

## The response envelope

Every worker answers with the same wrapper:

```jsonc
{
  "worker": "video-ocr",
  "kind": "handler",                         // handler | aggregator
  "chained": true,
  "ran_first": ["splitter"],                 // run to build the input, in order
  "duration_ms": 0.2,                        // the target worker only
  "would_publish_to": ["video.merge.ocr"],   // where the pipeline would send this
  "published": false,                        // it did not go there
  "consumed": { },                           // the message the worker received
  "result": { }                              // what the worker returned
}
```

`consumed` and `result` are the two halves worth reading: the message the
worker's topic would have carried, and the message it would have published.

---

## `GET /workers/list`

The catalog — every registered worker, its wiring, and whether its AI calls are
mocked right now.

```jsonc
{
  "workers": [
    {
      "worker": "video-ocr",
      "step": 5,
      "kind": "handler",
      "topics_in": ["video.ocr.in"],
      "topics_out": ["video.merge.ocr"],
      "aggregate_by": null,
      "runs_first": ["splitter"],
      "mocked": {"video-ocr": true},
      "run": "POST /workers/video-ocr/run"
    }
  ],
  "run": "POST /workers/{worker}/run",
  "note": "a direct run publishes nothing to Kafka — the answer is the HTTP response"
}
```

`mocked` is keyed by AI call, not by worker, because W6 makes three
(`summary`, `entities`, `sentiment`). `{}` means the worker calls no service at
all — W1 and W7.

---

## W1 — `splitter`

Calls no AI service. Normalises one submitted message into the item the four
extraction branches receive — useful for checking how a path is resolved.

**Request** — `POST /workers/splitter/run`

```json
{"id": "doc-splitter", "path": "/video/migrants.mp4"}
```

**Response**

```jsonc
{
  "worker": "splitter",
  "kind": "handler",
  "chained": true,
  "ran_first": [],
  "duration_ms": 0.1,
  "would_publish_to": [
    "video.face.in", "video.describe.in", "video.transcribe.in", "video.ocr.in"
  ],
  "published": false,
  "consumed": {
    "id": "doc-splitter", "path": "/video/migrants.mp4",
    "name": "migrants.mp4", "options": {}, "submitted_at": "2026-09-16T13:27:26+00:00"
  },
  "result": {
    "id": "doc-splitter",
    "path": "/video/migrants.mp4",
    "name": "migrants.mp4",
    "options": {},
    "submitted_at": "2026-09-16T13:27:26+00:00"
  }
}
```

---

## W2 — `face-match-main` (`:8821 /match`)

Who appears in the video. This branch goes **straight to the final aggregator**
— it never reaches the summary prompts.

**Request** — `POST /workers/face-match-main/run`

```json
{"id": "doc-face", "path": "/video/migrants.mp4"}
```

**What it sends to `:8821`**

```json
{"path": "/video/migrants.mp4"}
```

**Response** (`result`, the rest of the envelope omitted)

```jsonc
{
  "id": "doc-face",
  "path": "/video/migrants.mp4",
  "name": "migrants.mp4",
  "options": {},
  "submitted_at": "2026-09-16T13:27:26+00:00",
  "face": {
    "persons": ["222"],
    "message": "The following persons identified in this video",
    "source": {
      "service": "face-match-main",
      "mocked": true,          // false + an endpoint URL on a live call
      "endpoint": null,
      "duration_ms": 0.0
    },
    "raw": {                   // the service's complete response body
      "message": "The following persons identified in this video",
      "persons": ["222"]
    }
  }
}
```

`would_publish_to` is `["video.agg.face"]`.

---

## W3 — `video-describe-354b` (`:8822 /describe`)

What happens in the video, in prose.

**Request** — `POST /workers/video-describe-354b/run`

```json
{"id": "doc-describe", "path": "/video/migrants.mp4"}
```

**What it sends to `:8822`**

```json
{"path": "/video/migrants.mp4"}
```

**Response** (`result`)

```jsonc
{
  "id": "doc-describe",
  "path": "/video/migrants.mp4",
  "name": "migrants.mp4",
  "options": {},
  "submitted_at": "2026-09-16T13:27:26+00:00",
  "describe": {
    "description": "The video captures a dramatic and intense scene of migrants from Morocco attempting to cross the border into Spain's Ceuta. …",
    "metadata": {
      "model": "Qwen/Qwen3.5-4B",
      "fps": 0.5,
      "frames_sampled": 31,
      "processing_time_seconds": 26.429
    },
    "source": {"service": "video-describe-354b", "mocked": true, "endpoint": null, "duration_ms": 0.0},
    "raw": { }
  }
}
```

`would_publish_to` is `["video.merge.describe"]`.

---

## W4 — `transcribe` (`:8824 /transcribe`)

The audio as text. This is the one worker `options` changes.

**Request** — `POST /workers/transcribe/run`

```json
{
  "id": "doc-transcribe",
  "path": "/video/migrants.mp4",
  "options": {"language": "ar", "task": "translate"}
}
```

**What it sends to `:8824`** — the `.env` defaults with your overrides applied:

```json
{
  "path": "/video/migrants.mp4",
  "language": "ar",
  "task": "translate",
  "format": "dialog",
  "transcription_level": "word",
  "dialog_timestamps": false
}
```

**Response** (`result`)

```jsonc
{
  "id": "doc-transcribe",
  "path": "/video/migrants.mp4",
  "name": "migrants.mp4",
  "options": {"language": "ar", "task": "translate"},
  "submitted_at": "2026-09-16T13:27:26+00:00",
  "transcribe": {
    "transcription": "00: Hello.\n",
    "format": "dialog",
    "metadata": {
      "processing_time_seconds": 1.54,
      "audio_duration_seconds": 24.105,
      "realtime_factor": 0.064,
      "model": "large-v3",
      "device": "cuda",
      "total_speakers": 2,
      "requested_language": "ar",
      "detected_language": "ar",
      "output_language": "en",
      "transcription_level": "word",
      "dialog_timestamps": false
    },
    "source": {"service": "transcribe", "mocked": true, "endpoint": null, "duration_ms": 0.0},
    "raw": { }
  }
}
```

`GET /pipeline/config` shows the resolved defaults under `transcribe_defaults`.
`would_publish_to` is `["video.merge.transcribe"]`.

---

## W5 — `video-ocr` (`:8823 /ocr`)

The text burnt into the frames.

**Request** — `POST /workers/video-ocr/run`

```json
{"id": "doc-ocr", "path": "/video/migrants.mp4"}
```

**What it sends to `:8823`**

```json
{"path": "/video/migrants.mp4"}
```

**Response** (`result`)

```jsonc
{
  "id": "doc-ocr",
  "path": "/video/migrants.mp4",
  "name": "migrants.mp4",
  "options": {},
  "submitted_at": "2026-09-16T13:27:26+00:00",
  "ocr": {
    "full_text": "Reaction\n88886F\nHUDDER\nMbA\nBHM @1\nADMiSSiOMS C\n…",
    "frames_count": 9,
    "metadata": {
      "model": "easyocr:en",
      "fps": 1.0,
      "frames_sampled": 9,
      "frames_returned": 9,
      "device": "cuda",
      "processing_time_seconds": 1.777
    },
    "source": {"service": "video-ocr", "mocked": true, "endpoint": null, "duration_ms": 0.0},
    "raw": { }
  }
}
```

> The per-frame `frames` array is dropped — it is the bulkiest thing in the
> pipeline and nothing downstream reads it. `OCR_KEEP_FRAMES=true` keeps it, in
> this response as well as in the pipeline.

`would_publish_to` is `["video.merge.ocr"]`.

---

## W6 — `aggregator-ai-caller` (`:8825 /summarize` × 3)

The interesting one. A chained call runs W1, W3, W4 and W5 first, merges them,
builds the payload and posts it to the summary service three times.

**Request** — `POST /workers/aggregator-ai-caller/run`

```json
{"id": "doc-ai", "path": "/video/migrants.mp4"}
```

`ran_first` comes back as `["splitter", "video-describe-354b", "transcribe", "video-ocr"]`
— note that `face-match-main` is **not** there.

**What it sends to `:8825`** — the same body three times, only `prompt` changes:

```jsonc
{
  "inputs": {
    "video_description": "VIDEO DESCRIPTION\nThe video captures a dramatic and intense scene…\n\nON SCREEN TEXT\nReaction\n88886F\n…",
    "transcription": "00: Hello."
  },
  "prompt": "summary.txt",        // then entities.txt, then sentiment.txt
  "options": {"num_predict": 2048}
}
```

**Response** (`result`)

```jsonc
{
  "id": "doc-ai",
  "path": "/video/migrants.mp4",
  "name": "migrants.mp4",
  "options": {},
  "submitted_at": "2026-09-16T13:27:26+00:00",

  // exactly what was posted to :8825 — this is the field to read when you are
  // tuning a prompt
  "inputs": {
    "video_description": "VIDEO DESCRIPTION\n…\n\nON SCREEN TEXT\n…",
    "transcription": "00: Hello."
  },

  "enrichment": {
    "description": {"text": "The video captures…", "metadata": { }, "response": { }},
    "transcript":  {"text": "00: Hello.\n", "format": "dialog", "metadata": { }, "response": { }},
    "ocr":         {"text": "Reaction\n88886F\n…", "frames_count": 9, "metadata": { }, "response": { }},
    "summary": {
      "text": "Migrants are filmed crossing from Morocco into Ceuta by sea, climbing border barriers while Red Cross staff assist them on the shoreline. …",
      "prompt": "summary.txt",
      "metadata": {"provider": "ollama", "model": "phi4:14b-q8_0", "duration_seconds": 3.127},
      "response": { }
    },
    "entities": {
      "list": ["Morocco", "Spain", "Ceuta", "Red Cross", "Huddersfield"],
      "text": "[\"Morocco\", \"Spain\", \"Ceuta\", \"Red Cross\", \"Huddersfield\"]",
      "prompt": "entities.txt",
      "metadata": { },
      "response": { }
    },
    "sentiment": {"text": "negative", "prompt": "sentiment.txt", "metadata": { }, "response": { }}
  },

  // how each answer was produced
  "calls": {
    "video-describe-354b": {"service": "video-describe-354b", "mocked": true, "endpoint": null, "duration_ms": 0.0},
    "transcribe":          { },
    "video-ocr":           { },
    "summary":             {"service": "summarize:summary",   "mocked": true, "endpoint": null, "duration_ms": 0.0},
    "entities":            { },
    "sentiment":           { }
  }
}
```

To try a different prompt, point `SUMMARY_PROMPT` / `ENTITIES_PROMPT` /
`SENTIMENT_PROMPT` at another file on the AI host and call this endpoint again —
no restart of the pipeline is needed to see the new payload, only of the app.

`would_publish_to` is `["video.agg.ai"]`.

---

## W7 — `aggregator` (the whole pipeline, synchronously)

Calls no AI service itself, but a chained call pulls in every worker before it —
so this is how you run the complete analysis and get the finished record back in
one HTTP response.

**Request** — `POST /workers/aggregator/run`

```json
{"id": "doc-aggregator", "path": "/video/migrants.mp4"}
```

`ran_first` comes back as
`["splitter", "face-match-main", "video-describe-354b", "transcribe", "video-ocr", "aggregator-ai-caller"]`.

**Response** (`result`)

```jsonc
{
  "id": "doc-aggregator",
  "name": "migrants.mp4",
  "path": "/video/migrants.mp4",
  "status": "analysed",
  "persons": 1,
  "entities": 5,
  "sentiment": "negative",
  "failed_services": [],
  "output_file": null,          // null because persist defaults to false
  "record": {
    "id": "doc-aggregator",
    "name": "migrants.mp4",
    "path": "/video/migrants.mp4",
    "submitted_at": "2026-09-16T13:27:26+00:00",
    "analysed_at": "2026-09-16T13:27:26+00:00",
    "enrichment": {
      "face_match":  {"persons": ["222"], "message": "The following persons identified in this video", "response": { }},
      "description": {"text": "The video captures…", "metadata": { }, "response": { }},
      "transcript":  {"text": "00: Hello.\n", "format": "dialog", "metadata": { }, "response": { }},
      "ocr":         {"text": "Reaction\n…", "frames_count": 9, "metadata": { }, "response": { }},
      "summary":     {"text": "Migrants are filmed crossing…", "prompt": "summary.txt", "metadata": { }, "response": { }},
      "entities":    {"list": ["Morocco", "Spain", "Ceuta", "Red Cross", "Huddersfield"], "text": "…", "prompt": "entities.txt", "metadata": { }, "response": { }},
      "sentiment":   {"text": "negative", "prompt": "sentiment.txt", "metadata": { }, "response": { }}
    },
    "errors": {}
  }
}
```

The record is also printed to the console, exactly as in a pipeline run.

**It is not written to disk.** `persist` defaults to `false` so a trial run
cannot overwrite `output/<video>_analysis.json`. Add `"persist": true` to write
it, and `output_file` comes back with the path.

---

## Driving a worker with your own message

`chain: false` skips the upstream workers and hands the worker exactly what you
supply, so you can test one branch in isolation — including an aggregator, with
branches you assembled yourself.

```jsonc
// POST /workers/video-ocr/run
{
  "chain": false,
  "message": {
    "id": "hand-made-1",
    "path": "/video/some-other.mp4",
    "name": "some-other.mp4"
  }
}
```

The response then shows `"chained": false`, `"ran_first": []`, and `consumed`
equal to what you sent.

The same trick feeds W6 a description you wrote yourself, to see how a prompt
reacts without running the describe service at all:

```jsonc
// POST /workers/aggregator-ai-caller/run
{
  "chain": false,
  "message": {
    "id": "prompt-test-1",
    "name": "test.mp4",
    "describe":   {"description": "Two people argue in a car park at night."},
    "ocr":        {"full_text": "CCTV 03:14"},
    "transcribe": {"transcription": "00: Give me the keys."}
  }
}
```

---

## Mocking

`MOCK_WORKER_<NAME>=True` is checked inside `ai_client`, *below* the worker, so
a mocked call answers from `app/src/mock/mock_responses.py` here exactly as it
does in the pipeline — same shapes, same code path, no socket opened. That is
what makes this endpoint usable while the AI host (`172.17.12.80:8821-8825`) is
out of reach.

```bash
MOCK_WORKER_FACE_MATCH=True
MOCK_WORKER_DESCRIBE=True
MOCK_WORKER_OCR=True
MOCK_WORKER_TRANSCRIBE=True
MOCK_WORKER_SUMMARY=True
MOCK_WORKER_ENTITIES=True
MOCK_WORKER_SENTIMENT=True
```

A mocked answer is labelled in the response: `source.mocked` is `true` and
`source.endpoint` is `null`. On a live call, `endpoint` is the URL that was
posted to and `duration_ms` is the real round trip.

Mocking is per service, so mixing is the point: mock the slow describe service
and call OCR for real.

---

## Errors

| Status | When | Body |
|---|---|---|
| `400` | no `path` and no `message` | `{"error": "give a \"path\" to run on, or a \"message\" to feed the worker verbatim", "example": { }}` |
| `400` | `path` not found and `VIDEO_PATH_PASSTHROUGH=false` | `{"error": "video not found: …", "search_dirs": [ ]}` |
| `400` | a field has the wrong type | Flask-RESTX validation: `{"errors": {"options": "'nope' is not of type 'object'"}}` |
| `404` | no such worker | `{"error": "unknown worker 'nope' — known: [ … ]", "hint": "GET /workers/list for the registered names"}` |
| `502` | an AI service would not answer, with `AI_FAIL_FAST=true` | `{"error": "… at http://172.17.12.80:8821/match rejected the request (400): …", "worker": "face-match-main"}` |
| `500` | the worker raised on a hand-written `message` | `{"error": "KeyError: 'path'", "worker": "video-ocr"}` |

With the default `AI_FAIL_FAST=false` a dead service is **not** a 502: the
failure is recorded on the branch and the worker returns `200` normally, with
`source.error` set and the parsed value empty — the same behaviour that keeps
one dead service from stranding a video in the pipeline. Look at
`result.<branch>.source.error`, or at `result.record.errors` when calling W7.

---

## See also

- [`architecture.md`](architecture.md) — the pipeline itself, topic by topic
- `app/src/workers/registry.py` — the 40 lines this endpoint is built on
- `app/src/api/worker_endpoints.py` — the HTTP layer
- `app/tests/test_direct_workers.py` — the behaviour above, asserted
