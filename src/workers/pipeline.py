"""
The video analysis pipeline — 7 QF-framework workers.

This module contains NOTHING but the seven decorated functions. Every helper
they use (logging, timing, the resilient AI call, string assembly, the record)
lives in `utils.py`; the HTTP calls live in `ai_client.py` and the file sink in
`record_writer.py`.

Flow (see ../../../docs/diagram-1-worker-topology.svg):

    W1 splitter              video.in              -> video.{face,describe,transcribe,ocr}.in
    W2 face-match-main       video.face.in         -> video.agg.face
    W3 video-describe-354b   video.describe.in     -> video.merge.describe
    W4 transcribe            video.transcribe.in   -> video.merge.transcribe
    W5 video-ocr             video.ocr.in          -> video.merge.ocr
    W6 aggregator-ai-caller  video.merge.*         -> video.agg.ai        (3 calls to :8825)
    W7 aggregator            video.agg.face
                             + video.agg.ai        -> video.done          (console + JSON file)

W1 receives one submitted video path and fans it out to the four extraction
workers, which each call one AI service and republish what it answered.

The four branches then part ways:

  * W3, W4 and W5 produce *content* — prose, speech and on-screen text. They
    meet in W6, which folds what was seen into a single titled
    `video_description` string, pairs it with what was heard (the transcript),
    and posts that dict to the summary service three times, once per prompt
    file (`summary.txt`, `entities.txt`, `sentiment.txt` under `src/prompts/`,
    sent as `prompt_text`).
  * W2 produces *identity* — who is in the video. That is structured data, not
    something to paraphrase, so it skips W6 entirely and goes straight to W7,
    which files it under `enrichment.face_match` in the record.

W7 is the second aggregator: it joins W2's person list with W6's three answers,
assembles the final record, prints it and writes it to
`<OUTPUT_DIR>/<video name>_analysis.json` **and** to PostgreSQL
(`src/client/store.py`), which is what the client app searches and charts. The
file is the pipeline's product; the database is the read side, and a database
that is down costs the row, never the record.

Logging
-------
Every worker logs three things, so a `docker compose logs -f app` is enough to
see the pipeline work:

    [W2 face-match-main] id=vid-1 START path=/video/1.mp4
    [ai] id=vid-1 face-match-main      --> POST http://172.17.12.80:8821/match {"path": "/video/1.mp4"}
    [ai] id=vid-1 face-match-main      <-- 200 in 1843.2ms {"message": "...", "persons": ["222"]}
    [W2 face-match-main] id=vid-1 DONE  persons=1 in 1844.0ms

The two `[ai]` lines come from `src/ai_client.py` and carry the full request and
response bodies (truncated to `AI_LOG_BODY_CHARS`).

Framework mechanics used here
-----------------------------
* A handler's return value is published to EVERY topic in `topics_out` — that
  is how W1 fans one message out to four branches.
* The message `id` is preserved through every worker; both
  `@kafka_aggregator(aggregate_by="id")` stages regroup their branches by it and
  `deep_merge` them into one dict before the worker body runs.
* Every worker MUST declare a non-empty `topics_out`; W7 emits a terminal
  `video.done` event even though nothing consumes it here.
* A failing AI call is recorded on its branch rather than raised, so one dead
  service cannot leave a video buffered in Redis forever (see `utils.call_ai`
  and `AI_FAIL_FAST`).
* `metadatas` is whatever the caller passes. The ETL passes the decorator's
  dict; `workers/registry.py` adds `persist: False` when a worker is invoked
  straight from Swagger, so a trial run does not overwrite a record on disk.

Every AI call can be mocked independently with `MOCK_WORKER_<NAME>=True`
(see .env and src/mock/mock_responses.py). Mocked or live, the message shapes,
the topics and the code path are identical — including when a worker is called
directly through `POST /workers/{worker}/run`.
"""

from typing import Dict, List

from config import Config, Topics
from framework.commons.logger import logger
from framework.decorators import kafka_handler, kafka_aggregator

import ai_client
import record_writer
import utils
from client import store


# ============================================================
# Worker 1 — Splitter (one video path -> four extraction branches)
# ============================================================
@kafka_handler(
    name="splitter",
    topics_in=[Topics.VIDEO_IN],
    topics_out=[Topics.FACE_IN, Topics.DESCRIBE_IN, Topics.TRANSCRIBE_IN, Topics.OCR_IN],
    max_workers=2,
    metadatas={"worker": "splitter", "step": 1},
)
def worker_split(message: dict, consumer_name: str, metadatas: dict) -> dict:
    """Start the pipeline for one video.

    The returned dict is published to all four extraction topics, so face
    matching, description, transcription and OCR run in parallel on the same
    path. Nothing is read or downloaded here — only the path travels.
    """
    video_id = str(message["id"])
    started = utils.worker_start("W1 splitter", video_id, f"submitted={message.get('path')!r}")

    path = utils.resolve_video_path(message.get("path") or message.get("file") or "")
    name = message.get("name") or utils.video_name(path)

    item = {
        "id": video_id,
        "path": path,
        "name": name,
        # Per-submit overrides for the transcribe service (language, task, ...).
        "options": message.get("options") or {},
        "submitted_at": message.get("submitted_at") or utils.now_iso(),
    }

    utils.worker_done(
        "W1 splitter",
        video_id,
        f"name={name!r} -> {Topics.FACE_IN} / {Topics.DESCRIBE_IN} / "
        f"{Topics.TRANSCRIBE_IN} / {Topics.OCR_IN}",
        started,
    )
    utils.console(f"[video] {video_id}: {name} — fanned out to 4 extraction workers")
    return item


# ============================================================
# Worker 2 — face-match-main (:8821 /match)
# ============================================================
@kafka_handler(
    name="face-match-main",
    topics_in=[Topics.FACE_IN],
    # Straight to the final aggregator. The persons are structured data for the
    # record, not prose for the summary prompts, so this branch skips W6.
    topics_out=[Topics.AGG_FACE],
    max_workers=4,
    metadatas={"worker": "face-match-main", "step": 2, "service": "8821",
               "ai_calls": ["face-match-main"]},
)
def worker_face_match(message: dict, consumer_name: str, metadatas: dict) -> dict:
    """Identify the persons appearing in the video."""
    video_id = str(message["id"])
    label = "W2 face-match-main"
    started = utils.worker_start(label, video_id, f"path={message['path']!r}")

    data, meta = utils.call_ai(
        label, video_id, lambda: ai_client.face_match(message["path"], video_id=video_id)
    )
    persons: List[str] = [str(p) for p in (data.get("persons") or [])]

    utils.worker_done(label, video_id, f"persons={len(persons)} {persons}", started)
    return {
        **utils.branch_context(message),
        "face": {
            "persons": persons,
            "message": data.get("message"),
            "source": meta,
            "raw": data,
        },
    }


# ============================================================
# Worker 3 — video-describe-354b (:8822 /describe)
# ============================================================
@kafka_handler(
    name="video-describe-354b",
    topics_in=[Topics.DESCRIBE_IN],
    topics_out=[Topics.MERGE_DESCRIBE],
    max_workers=4,
    metadatas={"worker": "video-describe-354b", "step": 3, "service": "8822",
               "ai_calls": ["video-describe-354b"]},
)
def worker_describe(message: dict, consumer_name: str, metadatas: dict) -> dict:
    """Describe what happens in the video, in prose."""
    video_id = str(message["id"])
    label = "W3 video-describe-354b"
    started = utils.worker_start(label, video_id, f"path={message['path']!r}")

    data, meta = utils.call_ai(
        label, video_id, lambda: ai_client.describe(message["path"], video_id=video_id)
    )
    description = data.get("description") or ""
    model = (data.get("metadata") or {}).get("model", "?")

    utils.worker_done(label, video_id, f"description={len(description)} chars model={model}", started)
    return {
        **utils.branch_context(message),
        "describe": {
            "description": description,
            "metadata": data.get("metadata") or {},
            "source": meta,
            "raw": data,
        },
    }


# ============================================================
# Worker 4 — transcribe (:8824 /transcribe)
# ============================================================
@kafka_handler(
    name="transcribe",
    topics_in=[Topics.TRANSCRIBE_IN],
    topics_out=[Topics.MERGE_TRANSCRIBE],
    max_workers=4,
    metadatas={"worker": "transcribe", "step": 4, "service": "8824",
               "ai_calls": ["transcribe"]},
)
def worker_transcribe(message: dict, consumer_name: str, metadatas: dict) -> dict:
    """Turn the audio track into text (optionally translated — see .env)."""
    video_id = str(message["id"])
    label = "W4 transcribe"
    params = ai_client.transcribe_params(message.get("options"))
    started = utils.worker_start(label, video_id, f"path={message['path']!r} params={params}")

    data, meta = utils.call_ai(
        label,
        video_id,
        lambda: ai_client.transcribe(message["path"], message.get("options"), video_id=video_id),
    )
    transcription = data.get("transcription") or ""
    metadata = data.get("metadata") or {}

    utils.worker_done(
        label,
        video_id,
        f"transcript={len(transcription)} chars "
        f"lang={metadata.get('detected_language', '?')}->{metadata.get('output_language', '?')} "
        f"speakers={metadata.get('total_speakers', '?')}",
        started,
    )
    return {
        **utils.branch_context(message),
        "transcribe": {
            "transcription": transcription,
            "format": data.get("format"),
            "metadata": metadata,
            "source": meta,
            "raw": data,
        },
    }


# ============================================================
# Worker 5 — video-ocr (:8823 /ocr)
# ============================================================
@kafka_handler(
    name="video-ocr",
    topics_in=[Topics.OCR_IN],
    topics_out=[Topics.MERGE_OCR],
    max_workers=4,
    metadatas={"worker": "video-ocr", "step": 5, "service": "8823",
               "ai_calls": ["video-ocr"]},
)
def worker_ocr(message: dict, consumer_name: str, metadatas: dict) -> dict:
    """Read the text burnt into the frames.

    The per-frame `frames` array is bulky and nothing downstream reads it, so it
    is dropped unless `OCR_KEEP_FRAMES=true`; `full_text` is what W6 uses.
    """
    video_id = str(message["id"])
    label = "W5 video-ocr"
    started = utils.worker_start(label, video_id, f"path={message['path']!r}")

    data, meta = utils.call_ai(
        label, video_id, lambda: ai_client.ocr(message["path"], video_id=video_id)
    )
    full_text = data.get("full_text") or ""
    frames = data.get("frames") or []

    utils.worker_done(label, video_id, f"text={len(full_text)} chars over {len(frames)} frame(s)", started)

    result = {
        "full_text": full_text,
        "frames_count": len(frames),
        "metadata": data.get("metadata") or {},
        "source": meta,
        # The full body, minus the per-frame array unless OCR_KEEP_FRAMES — it
        # is by far the bulkiest thing in the pipeline and would ride through
        # Kafka twice on its way to the record.
        "raw": data if Config.OCR_KEEP_FRAMES else {k: v for k, v in data.items() if k != "frames"},
    }
    if Config.OCR_KEEP_FRAMES:
        result["frames"] = frames

    return {**utils.branch_context(message), "ocr": result}


# ============================================================
# Worker 6 — Aggregator + AI caller (:8825 /summarize, three prompts)
# ============================================================
@kafka_aggregator(
    name="aggregator-ai-caller",
    topics_in=[Topics.MERGE_DESCRIBE, Topics.MERGE_TRANSCRIBE, Topics.MERGE_OCR],
    topics_out=[Topics.AGG_AI],
    aggregate_by="id",
    aggregator_timeout_sec=Config.AGGREGATOR_TIMEOUT_SEC,
    max_workers=4,
    metadatas={"worker": "aggregator-ai-caller", "step": 6, "service": "8825",
               "ai_calls": ["summary", "entities", "sentiment"]},
)
def worker_ai_caller(merged: dict, consumer_name: str, metadatas: dict) -> dict:
    """Merge the three content branches, then prompt the summary service 3×.

    `merged` is what the framework produced by deep-merging the three branch
    messages that share this `id`, so `describe`, `transcribe` and `ocr` are all
    present. `face` is NOT — that branch goes straight to W7.

    Everything visible becomes ONE titled string under `video_description`:

        VIDEO DESCRIPTION
        ...
        ON SCREEN TEXT
        ...

    and the transcript stays separate under `transcription`. That dict is posted
    to :8825 three times, each with the text of one prompt file as `prompt_text`
    — the endpoint returns the same `{"output", "metadata"}` envelope every
    time, and the prompt decides what the text inside means.
    """
    video_id = str(merged.get("id"))
    label = "W6 aggregator-ai-caller"

    description = (merged.get("describe") or {}).get("description") or ""
    ocr_text = (merged.get("ocr") or {}).get("full_text") or ""
    transcript = (merged.get("transcribe") or {}).get("transcription") or ""

    started = utils.worker_start(
        label,
        video_id,
        f"3 branches merged — description={len(description)} ocr={len(ocr_text)} "
        f"transcript={len(transcript)}",
    )

    inputs = utils.build_inputs(description, ocr_text, transcript)
    logger.info(
        f"[{label}] id={video_id} inputs built: "
        f"{Config.SUMMARIZE_KEY_DESCRIPTION}={len(inputs[Config.SUMMARIZE_KEY_DESCRIPTION])} chars "
        f"({Config.SECTION_DESCRIPTION} + {Config.SECTION_OCR}), "
        f"{Config.SUMMARIZE_KEY_TRANSCRIPT}={len(inputs[Config.SUMMARIZE_KEY_TRANSCRIPT])} chars"
    )

    calls = (
        ("summary", Config.SUMMARY_PROMPT),
        ("entities", Config.ENTITIES_PROMPT),
        ("sentiment", Config.SENTIMENT_PROMPT),
    )

    answers: Dict[str, dict] = {}
    for kind, prompt_file in calls:
        data, meta = utils.call_ai(
            f"{label}:{kind}",
            video_id,
            lambda kind=kind, prompt_file=prompt_file: ai_client.summarize(
                kind, inputs, prompt_file, video_id=video_id
            ),
        )
        answers[kind] = {
            "text": ai_client.summarize_output(data),
            "metadata": data.get("metadata") or {},
            "source": meta,
            "raw": data,
        }

    entities = utils.parse_entities(answers["entities"]["text"])

    utils.worker_done(
        label,
        video_id,
        f"3 prompts answered — summary={len(answers['summary']['text'])} chars, "
        f"entities={len(entities)}, sentiment={answers['sentiment']['text']!r}",
        started,
    )

    return {
        **utils.branch_context(merged),
        # Exactly what was posted to :8825 — kept so a record is reproducible.
        "inputs": inputs,
        # One entry per AI answer this worker can account for: the three texts
        # it merged, and the three prompts it ran. W7 adds `face_match` from
        # W2's own branch and writes the lot out under `enrichment`.
        "enrichment": {
            "description": {
                "text": description,
                "metadata": (merged.get("describe") or {}).get("metadata") or {},
                **utils.response_envelope((merged.get("describe") or {}).get("raw")),
            },
            "transcript": {
                "text": transcript,
                "format": (merged.get("transcribe") or {}).get("format"),
                "metadata": (merged.get("transcribe") or {}).get("metadata") or {},
                **utils.response_envelope((merged.get("transcribe") or {}).get("raw")),
            },
            "ocr": {
                "text": ocr_text,
                "frames_count": (merged.get("ocr") or {}).get("frames_count", 0),
                "metadata": (merged.get("ocr") or {}).get("metadata") or {},
                **utils.response_envelope((merged.get("ocr") or {}).get("raw")),
            },
            "summary": {
                "text": answers["summary"]["text"],
                "prompt": Config.SUMMARY_PROMPT,
                "metadata": answers["summary"]["metadata"],
                **utils.response_envelope(answers["summary"]["raw"]),
            },
            "entities": {
                # The prompt answers with text; the record carries both the
                # parsed list and the raw answer, so a bad parse loses nothing.
                "list": entities,
                "text": answers["entities"]["text"],
                "prompt": Config.ENTITIES_PROMPT,
                "metadata": answers["entities"]["metadata"],
                **utils.response_envelope(answers["entities"]["raw"]),
            },
            "sentiment": {
                "text": answers["sentiment"]["text"],
                "prompt": Config.SENTIMENT_PROMPT,
                "metadata": answers["sentiment"]["metadata"],
                **utils.response_envelope(answers["sentiment"]["raw"]),
            },
        },
        # How each answer was produced: mocked or live, which URL, how long,
        # and the error when a service would not answer.
        "calls": {
            "video-describe-354b": (merged.get("describe") or {}).get("source"),
            "transcribe": (merged.get("transcribe") or {}).get("source"),
            "video-ocr": (merged.get("ocr") or {}).get("source"),
            "summary": answers["summary"]["source"],
            "entities": answers["entities"]["source"],
            "sentiment": answers["sentiment"]["source"],
        },
    }


# ============================================================
# Worker 7 — Aggregator (final record: console + JSON file)
# ============================================================
@kafka_aggregator(
    name="aggregator",
    topics_in=[Topics.AGG_FACE, Topics.AGG_AI],
    topics_out=[Topics.DONE],
    aggregate_by="id",
    aggregator_timeout_sec=Config.AGGREGATOR_TIMEOUT_SEC,
    max_workers=2,
    metadatas={"worker": "aggregator", "step": 7},
)
def worker_aggregate(merged: dict, consumer_name: str, metadatas: dict) -> dict:
    """Assemble, print and write the one record that holds every worker's result.

    `merged` is W2's person list deep-merged with W6's three answers — the two
    halves of the pipeline meeting for the first time. This worker does no I/O
    with the AI host: it flattens them into the record the pipeline exists to
    produce, prints it and writes it to disk.

    `metadatas["persist"]` is False when the worker was invoked straight from
    Swagger, so a trial run prints the record without overwriting the file.
    """
    video_id = str(merged.get("id"))
    label = "W7 aggregator"
    started = utils.worker_start(label, video_id, "2 branches merged (face + ai)")

    record = utils.build_record(merged)

    utils.console(utils.format_record(record))
    persist = metadatas.get("persist", True)
    written = record_writer.write(record) if persist else None
    # The same record, into PostgreSQL, for the client app to search and chart.
    # `merged["calls"]` is W6's per-call provenance (mocked or live, which URL,
    # how long) — the record deliberately leaves it out, and the statistics
    # page is built from it. A database that is down is logged and skipped:
    # the record is the pipeline's product and it is already on disk.
    stored = store.save_record(record, merged.get("calls")) if persist else None

    failed = sorted(record["errors"])
    utils.worker_done(
        label,
        video_id,
        f"persons={len(record['enrichment']['face_match']['persons'])} "
        f"entities={len(record['enrichment']['entities']['list'])} "
        f"sentiment={record['enrichment']['sentiment']['text']!r} "
        f"failed={failed or 'none'} written={written} stored={stored or '-'}",
        started,
    )
    if written:
        utils.console(f"[video] {video_id}: record written to {written}")

    # The terminal event: a summary line for a consumer that only wants to know
    # a video finished, plus the record itself, so `video.done` — and the
    # response of `POST /workers/aggregator/run` — is self-contained.
    return {
        "id": record["id"],
        "name": record["name"],
        "path": record["path"],
        "status": "analysed",
        "persons": len(record["enrichment"]["face_match"]["persons"]),
        "entities": len(record["enrichment"]["entities"]["list"]),
        "sentiment": record["enrichment"]["sentiment"]["text"],
        "failed_services": failed,
        "output_file": written,
        "stored": bool(stored),
        "record": record,
    }
