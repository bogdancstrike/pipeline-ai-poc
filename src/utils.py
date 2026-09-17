"""
Helpers for the pipeline workers — everything that is not a Kafka worker.

`workers/pipeline.py` holds ONLY the @kafka_handler / @kafka_aggregator
functions — the workers per se. Every piece of plumbing they call lives here:

  * worker plumbing — START/DONE logging, timing, and the AI call that survives
                      a dead service (`call_ai`)
  * path handling   — turn a submitted video path into one the services can use
  * branch context  — the fields every branch echoes so the aggregators can merge
  * `video_description` — the titled, concatenated string W6 posts to :8825
  * entity parsing  — the entities prompt answers with text; normalise it
  * record building — `build_record`, the one JSON object W7 produces
  * console output  — how W7 renders that record

W7's *file* output lives in its own module, `record_writer.py`.
"""

import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from config import Config
from framework.commons.logger import logger

import ai_client
import prompts

# Workers run in a thread pool — keep console output from interleaving.
_print_lock = threading.Lock()

# Fields every branch echoes, so `deep_merge` in W6/W7 reconstructs the whole
# record (the video's identity + whatever that branch produced).
_CONTEXT_KEYS = ("id", "path", "name", "options", "submitted_at")


def console(text: str) -> None:
    """Print one record to stdout without interleaving worker threads."""
    with _print_lock:
        print(text, flush=True)


# ---------------------------------------------------------------------------
# Worker plumbing — timestamps, START/DONE logging, one resilient AI call
#
# Every worker in `workers/pipeline.py` is built out of these three, which is
# why that module holds nothing but the decorated functions themselves.
# ---------------------------------------------------------------------------

def now_iso() -> str:
    """UTC, to the second — `submitted_at` and `analysed_at`."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def response_envelope(raw: Optional[dict]) -> dict:
    """`{"response": <the service's full body>}`, or nothing when turned off."""
    return {"response": raw or {}} if Config.OUTPUT_INCLUDE_RAW else {}


def worker_start(label: str, video_id: str, detail: str) -> float:
    """Log a worker picking up a message; return the clock to measure it with."""
    logger.info(f"[{label}] id={video_id} START {detail}")
    return time.monotonic()


def worker_done(label: str, video_id: str, detail: str, started: float) -> None:
    """Log a worker finishing, with how long the whole step took."""
    elapsed = round((time.monotonic() - started) * 1000, 1)
    logger.info(f"[{label}] id={video_id} DONE  {detail} in {elapsed}ms")


def call_ai(label: str, video_id: str, fn) -> Tuple[dict, dict]:
    """Run one AI call and return `(data, meta)`, surviving a dead service.

    A 4-way fan-in only completes when all four branches arrive, so an
    extraction worker that raises would leave the video buffered in Redis until
    the aggregator timeout — no record, no error in the output, nothing to look
    at but the DLQ. Instead the failure is recorded on the branch and published,
    the aggregators fire normally, and W7 writes a record that names what broke.

    `AI_FAIL_FAST=true` restores the strict behaviour: re-raise and let the
    framework's retry/DLQ policy own it. A synchronous `/workers/...` call has
    no DLQ behind it, so there the raised error becomes the HTTP 502.

    An unreadable prompt file (`PromptError`) is recorded the same way: W6 sends
    the prompt text, so a missing `src/prompts/*.txt` stops that one call, not
    the record. `main.py` reads all three at boot, so normally it never gets here.
    """
    try:
        answer = fn()
    except (ai_client.AIServiceError, prompts.PromptError) as exc:
        if Config.AI_FAIL_FAST:
            raise
        logger.error(f"[{label}] id={video_id} BRANCH FAILED — recording the error: {exc}")
        return {}, {"service": label, "mocked": False, "error": str(exc)}
    return answer["data"], answer["meta"]


# ---------------------------------------------------------------------------
# Video path — W1 / the API
# ---------------------------------------------------------------------------

def resolve_video_path(path: str) -> str:
    """Return the path the AI services should be asked about.

    The services resolve the path on *their own* filesystem, so a submitted path
    is normally passed straight through. When the same file happens to be
    mounted here (`VIDEO_SEARCH_DIRS`, e.g. `./videos` -> `/app/videos`) it is
    resolved locally first, purely so an obvious typo becomes a 400 at submit
    time instead of a failed HTTP call two workers later.

    `VIDEO_PATH_PASSTHROUGH=false` makes a path that cannot be found locally a
    hard error — use it when the app and the AI host share a mount.
    """
    if not path or not str(path).strip():
        raise ValueError("no video path given")

    path = str(path).strip()
    if os.path.isfile(path):
        return os.path.abspath(path)

    name = os.path.basename(path)
    tried = []
    for directory in Config.VIDEO_SEARCH_DIRS:
        candidate = os.path.join(directory, name)
        tried.append(candidate)
        if os.path.isfile(candidate):
            return candidate

    if Config.VIDEO_PATH_PASSTHROUGH:
        logger.debug(
            f"[path] {path!r} is not readable here — forwarding it to the AI "
            f"services as-is (VIDEO_PATH_PASSTHROUGH=true)"
        )
        return path

    raise FileNotFoundError(
        f"video not found: {path!r}" + (f" — also tried {tried}" if tried else "")
    )


def video_name(path: str) -> str:
    """`/video/migrants.mp4` -> `migrants.mp4` — names W7's output file."""
    return os.path.basename(str(path or "")) or "video"


# ---------------------------------------------------------------------------
# Branch context — W2..W5
# ---------------------------------------------------------------------------

def branch_context(message: dict) -> dict:
    """The shared fields a branch echoes alongside its own result key."""
    return {key: message.get(key) for key in _CONTEXT_KEYS if message.get(key) is not None}


# ---------------------------------------------------------------------------
# The `inputs` payload — W6
# ---------------------------------------------------------------------------

def _section(heading: str, body: Optional[str]) -> Optional[str]:
    """One titled block, or None when there is nothing to show and no placeholder."""
    text = (body or "").strip()
    if not text:
        if not Config.SECTION_EMPTY_PLACEHOLDER:
            return None
        text = Config.SECTION_EMPTY_PLACEHOLDER
    return f"{heading}\n{text}"


def persons_text(persons: Optional[List[str]]) -> str:
    """The identified persons as one line: `222, 481` — or empty when none."""
    if not persons:
        return ""
    return ", ".join(str(p).strip() for p in persons if str(p).strip())


def build_video_description(
    description: Optional[str],
    ocr_text: Optional[str],
) -> str:
    """Everything visible in the video, as ONE titled string.

        VIDEO DESCRIPTION
        <what :8822 described>

        ON SCREEN TEXT
        <what :8823 read off the frames>

    This is the value of the `video_description` key W6 posts to :8825. The
    headings are configurable (`SECTION_DESCRIPTION` / `SECTION_OCR`), and a
    branch that produced nothing shows `SECTION_EMPTY_PLACEHOLDER` — set it
    empty to drop the whole section.

    The identified persons are NOT part of this string: face matching bypasses
    W6 and goes straight to the final record (see `Topics` in config.py).
    """
    blocks = [
        _section(Config.SECTION_DESCRIPTION, description),
        _section(Config.SECTION_OCR, ocr_text),
    ]
    return "\n\n".join(block for block in blocks if block)


def build_inputs(
    description: Optional[str],
    ocr_text: Optional[str],
    transcript: Optional[str],
) -> Dict[str, str]:
    """The `inputs` dict for :8825 — what is seen, and what is heard."""
    return {
        Config.SUMMARIZE_KEY_DESCRIPTION: build_video_description(description, ocr_text),
        Config.SUMMARIZE_KEY_TRANSCRIPT: (transcript or "").strip(),
    }


# ---------------------------------------------------------------------------
# Answer normalisation — W6
# ---------------------------------------------------------------------------

_JSON_ARRAY = re.compile(r"\[.*]", re.DOTALL)


def parse_entities(text: Optional[str]) -> List[str]:
    """The entities prompt answers with text; give the record a list.

    Handles the three shapes a prompted model realistically returns:
      '["Ceuta", "Red Cross"]'        -> ["Ceuta", "Red Cross"]   (JSON, possibly fenced)
      'Ceuta, Red Cross, Morocco'     -> ["Ceuta", "Red Cross", "Morocco"]
      '- Ceuta\\n- Red Cross'          -> ["Ceuta", "Red Cross"]

    The raw answer is always kept alongside the list (see `worker_ai_caller`),
    so nothing is lost when the parse guesses wrong.
    """
    text = (text or "").strip()
    if not text:
        return []

    match = _JSON_ARRAY.search(text)
    if match:
        try:
            loaded = json.loads(match.group(0))
        except ValueError:
            pass
        else:
            if isinstance(loaded, list):
                return [str(item).strip() for item in loaded if str(item).strip()]

    if "\n" in text:
        lines = [line.strip().lstrip("-*•").strip() for line in text.splitlines()]
        items = [line for line in lines if line]
        if len(items) > 1:
            return items

    return [part.strip() for part in text.split(",") if part.strip()]


# ---------------------------------------------------------------------------
# The final record — W7
# ---------------------------------------------------------------------------

def build_record(merged: dict) -> dict:
    """The final record — one video in, one JSON object out.

    `merged` is the face branch (W2) deep-merged with the AI caller's output
    (W6). Everything the AI services produced lives under `enrichment`, one
    entry per call, each with the parsed value, the service's own metadata and
    (unless `OUTPUT_INCLUDE_RAW=false`) its complete response body:

        enrichment.face_match   persons                 <- W2  :8821 /match
        enrichment.description  text                    <- W3  :8822 /describe
        enrichment.transcript   text                    <- W4  :8824 /transcribe
        enrichment.ocr          text                    <- W5  :8823 /ocr
        enrichment.summary      text                    <- W6  :8825 summary.txt
        enrichment.entities     list + text             <- W6  :8825 entities.txt
        enrichment.sentiment    text                    <- W6  :8825 sentiment.txt

    Around it sits only the identity of the run (`id`, `name`, `path`,
    timestamps) and `errors`, naming any service that would not answer.

    Two things deliberately stay OUT of the record: the `inputs` posted to
    :8825 and the per-call `calls` metadata (mocked or live, which URL, how
    long). Both still travel on the branch messages — visible in kafka-ui and
    in the response of `POST /workers/aggregator-ai-caller/run` — and the
    timings are in the `[ai]` log lines. Each `enrichment` entry also keeps the
    service's own `metadata` and, unless turned off, its full `response` body.
    """
    face = merged.get("face") or {}

    enrichment = {
        # W2's branch arrives here directly — it never passes through W6.
        "face_match": {
            "persons": face.get("persons") or [],
            "message": face.get("message"),
            **response_envelope(face.get("raw")),
        },
        **(merged.get("enrichment") or {}),
    }

    return {
        "id": merged.get("id"),
        "name": merged.get("name"),
        "path": merged.get("path"),
        "submitted_at": merged.get("submitted_at"),
        "analysed_at": now_iso(),

        # Everything the AI services answered.
        "enrichment": enrichment,

        # Only what did NOT answer; `{}` on a clean run.
        "errors": _errors(merged),
    }


def _errors(merged: dict) -> Dict[str, str]:
    """`{service: message}` for every branch whose AI call would not answer.

    Read off the `source` metadata the branches carry, which is why that
    metadata is merged here and dropped from the record itself.
    """
    sources = {
        "face-match-main": (merged.get("face") or {}).get("source"),
        **(merged.get("calls") or {}),
    }
    return {
        name: meta["error"]
        for name, meta in sources.items()
        if (meta or {}).get("error")
    }


# ---------------------------------------------------------------------------
# Console rendering — W7
# ---------------------------------------------------------------------------

def format_record(record: dict) -> str:
    """Render one aggregated record per Config.OUTPUT_FORMAT."""
    if Config.OUTPUT_FORMAT == "json":
        return json.dumps(record, ensure_ascii=False, indent=Config.OUTPUT_JSON_INDENT)
    if Config.OUTPUT_FORMAT == "line":
        return _format_line(record)
    return _format_block(record)


def _preview(text: Optional[Any], limit: Optional[int] = None) -> str:
    flat = " ".join(str(text or "").split())
    limit = Config.OUTPUT_TEXT_PREVIEW_CHARS if limit is None else limit
    return flat[:limit] + ("…" if len(flat) > limit else "")


def _enrichment(record: dict) -> Dict[str, dict]:
    return record.get("enrichment") or {}


def _entry(record: dict, key: str) -> dict:
    return _enrichment(record).get(key) or {}


def _format_line(record: dict) -> str:
    return (
        f"[video] {record.get('name', '?'):<28} "
        f"persons={len(_entry(record, 'face_match').get('persons') or [])} "
        f"entities={len(_entry(record, 'entities').get('list') or [])} "
        f"sentiment={_entry(record, 'sentiment').get('text', '?')} "
        f":: {_preview(_entry(record, 'summary').get('text'), 120)!r}"
    )


def _format_block(record: dict) -> str:
    errors = record.get("errors") or {}

    lines = [
        "─" * 78,
        f" VIDEO       : {record.get('name', '?')}  ({record.get('path', '?')})",
        f" id          : {record.get('id')}",
        f" analysed_at : {record.get('analysed_at', '?')}",
        "─" * 78,
        f" PERSONS     : {persons_text(_entry(record, 'face_match').get('persons')) or '-'}",
        f" DESCRIPTION : {_preview(_entry(record, 'description').get('text'))}",
        f" ON SCREEN   : {_preview(_entry(record, 'ocr').get('text'), 160)}",
        f" TRANSCRIPT  : {_preview(_entry(record, 'transcript').get('text'), 160)}",
        "─" * 78,
        f" SUMMARY     : {_preview(_entry(record, 'summary').get('text'))}",
        f" ENTITIES    : {', '.join(_entry(record, 'entities').get('list') or []) or '-'}",
        f" SENTIMENT   : {_entry(record, 'sentiment').get('text') or '-'}",
        "─" * 78,
    ]
    if errors:
        lines.append(f" errors      : {'; '.join(f'{k}: {v}' for k, v in errors.items())}")
    return "\n".join(lines)
