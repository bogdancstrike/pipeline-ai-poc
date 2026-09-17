"""
A corpus of W7-shaped records, built to be *varied* rather than plentiful.

Every suite below the unit tests needs records to ask questions of, and the
questions are only worth asking if the answers differ: a hundred copies of one
record proves a filter returns rows, not that it filters. So the generator
walks deterministic cycles of sentiment, model, entities, persons, failure and
date — one seed, one corpus, the same one on every machine, which is what lets
an end-to-end test assert a number instead of "more than zero".

The records are the pipeline's own shape (`enrichment.<branch>.text`, `errors`,
`submitted_at`/`analysed_at`), so they go in through `client.store.save_record`
— the writer W7 uses — rather than through hand-written INSERTs. A seeded row
is therefore a row the pipeline could have produced, and a change to the
flattening is caught here instead of in production.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterator, List

#: Every seeded id starts with this, and nothing else in the database does.
#: It is what makes seeding idempotent without touching a real record.
PREFIX = "qa-"

SENTIMENTS = ("NEGATIVE", "POSITIVE", "NEUTRAL")
MODELS = ("phi4:14b-q8_0", "llama3.3:70b", "qwen2.5:32b")
TRANSCRIBE_MODELS = ("large-v3", "medium")

#: Each entry is (type, value). The cycle length is coprime with the sentiment
#: and model cycles, so the combinations do not line up into a pattern that a
#: filter could satisfy by accident.
ENTITIES = (
    ("LOCATION", "Ceuta"),
    ("LOCATION", "Melilla"),
    ("LOCATION", "Morocco"),
    ("LOCATION", "Tarajal"),
    ("NAME", "Red Cross"),
    ("NAME", "Guardia Civil"),
    ("ORG", "Frontex"),
    ("DATE", "2026-05-18"),
    ("LOCATION", "Algeciras"),
    ("NAME", "Salvamento Maritimo"),
    ("ORG", "UNHCR"),
)

PERSONS = ("222", "417", "903", "1180")

TOPICS = (
    "migrants crossing the breakwater at dawn",
    "a crowd pressed against the border fence",
    "rescue boats returning to the harbour",
    "a queue forming at the processing tent",
    "drone footage of the coastal road",
)

#: One record in six is short of a service, which is what makes `status`
#: worth filtering on and gives the Statistics page failures to draw.
FAILING = {
    3: ("face-match-main", "path /video/missing.mp4 does not exist"),
    9: ("transcribe", "read timeout after 600s"),
    15: ("video-ocr", "CUDA out of memory"),
}


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def record(index: int, *, now: datetime | None = None, prefix: str = PREFIX) -> Dict[str, Any]:
    """One record, fully determined by `index`.

    `index` also fixes the moment: record 0 is the most recent and each one
    after it is six hours older, so a 120-record corpus spans thirty days and
    every range preset on the dashboard has something to show.
    """
    now = now or datetime.now(timezone.utc)
    analysed = now - timedelta(hours=6 * index, minutes=index % 7)
    submitted = analysed - timedelta(seconds=12 + (index % 17) * 3)

    sentiment = SENTIMENTS[index % len(SENTIMENTS)]
    model = MODELS[index % len(MODELS)]
    topic = TOPICS[index % len(TOPICS)]
    person_count = index % 3          # 0, 1 or 2 people
    entity_count = 2 + (index % 4)    # 2..5 entities

    entities = [ENTITIES[(index + step) % len(ENTITIES)] for step in range(entity_count)]
    entity_lines = [f"{kind}: {value}" for kind, value in entities]
    persons = [PERSONS[(index + step) % len(PERSONS)] for step in range(person_count)]

    video_id = f"{prefix}{index:04d}"
    name = f"{video_id}.mp4"

    errors: Dict[str, str] = {}
    failure = FAILING.get(index % 18)
    if failure:
        errors[failure[0]] = failure[1]

    summary = (
        f"Record {index}: {topic}. The footage was analysed by {model} and reads as "
        f"{sentiment.lower()}. Locations named include "
        f"{', '.join(value for kind, value in entities if kind == 'LOCATION') or 'none'}."
    )
    prompt_hash = _hash(f"summary.txt::{index % 3}")

    enrichment: Dict[str, Any] = {
        "face_match": {
            "persons": persons,
            "message": "The following persons identified in this video",
        },
        "description": {
            "text": f"A wide shot of {topic}; the camera holds steady for most of the clip.",
            "metadata": {
                "model": "Qwen/Qwen3.5-4B",
                "device": "cuda",
                "frames_sampled": 20 + index % 15,
                "processing_time_seconds": round(18.0 + (index % 23) * 0.9, 3),
            },
        },
        "transcript": {
            "text": f"00: Speaker one describes {topic}.\n01: Speaker two answers briefly.",
            "format": "dialog",
            "metadata": {
                "model": TRANSCRIBE_MODELS[index % len(TRANSCRIBE_MODELS)],
                "device": "cuda",
                "total_speakers": 1 + index % 3,
                "requested_language": "ar",
                "detected_language": "ar",
                "audio_duration_seconds": round(20.0 + (index % 40) * 1.5, 3),
                "processing_time_seconds": round(1.2 + (index % 9) * 0.4, 3),
            },
        },
        "ocr": {
            "text": f"BREAKING {index}\n{entities[0][1].upper()}\nLIVE",
            "frames_count": 4 + index % 9,
            "metadata": {
                "model": "easyocr:en",
                "device": "cuda",
                "frames_sampled": 4 + index % 9,
                "processing_time_seconds": round(0.8 + (index % 11) * 0.3, 3),
            },
        },
        "summary": {
            "text": summary,
            "prompt": "summary.txt",
            "metadata": {
                "model": model,
                "provider": "openai-compatible",
                "prompt_hash": prompt_hash,
                "input_tokens": 900 + index * 7,
                "output_tokens": 120 + index * 3,
                "duration_seconds": round(2.0 + (index % 13) * 0.55, 3),
            },
        },
        "entities": {
            "list": entity_lines,
            "text": "\n".join(entity_lines),
            "prompt": "entities.txt",
            "metadata": {
                "model": model,
                "provider": "openai-compatible",
                "prompt_hash": _hash("entities.txt"),
                "input_tokens": 850 + index * 5,
                "output_tokens": 40 + index,
                "duration_seconds": round(1.4 + (index % 8) * 0.4, 3),
            },
        },
        "sentiment": {
            "text": sentiment,
            "prompt": "sentiment.txt",
            "metadata": {
                "model": model,
                "provider": "openai-compatible",
                "prompt_hash": _hash("sentiment.txt"),
                "input_tokens": 830 + index * 4,
                "output_tokens": 3,
                "duration_seconds": round(0.9 + (index % 6) * 0.3, 3),
            },
        },
    }

    # A failed branch produced nothing — the record says so in `errors` and
    # leaves the text empty, which is exactly what AI_FAIL_FAST=false does.
    for service in errors:
        branch = {
            "face-match-main": "face_match",
            "transcribe": "transcript",
            "video-ocr": "ocr",
            "video-describe-354b": "description",
        }.get(service)
        if branch == "face_match":
            enrichment["face_match"] = {"persons": [], "message": ""}
        elif branch:
            enrichment[branch] = {"text": "", "metadata": {}}

    return {
        "id": video_id,
        "name": name,
        "path": f"/app/videos/qa/{name}",
        "submitted_at": submitted.isoformat(),
        "analysed_at": analysed.isoformat(),
        "enrichment": enrichment,
        "errors": errors,
    }


def calls(index: int) -> Dict[str, Any]:
    """W6's per-call provenance for `record(index)`.

    Every fourth record is a *live* run, so the Statistics page has real
    latencies to take a median of; the rest are mocked, which is what a
    developer's corpus actually looks like.
    """
    live = index % 4 == 0
    base = 40.0 if not live else 900.0 + (index % 31) * 120.0
    services = {
        "face-match-main": ":8821/match",
        "video-describe-354b": ":8822/describe",
        "transcribe": ":8824/transcribe",
        "video-ocr": ":8823/ocr",
        "summary": ":8825/summarize",
        "entities": ":8825/summarize",
        "sentiment": ":8825/summarize",
    }
    errors = record(index).get("errors") or {}

    out: Dict[str, Any] = {}
    for position, (service, suffix) in enumerate(services.items()):
        out[service] = {
            "service": service,
            "mocked": not live,
            "endpoint": None if not live else f"http://172.17.12.80{suffix}",
            "duration_ms": round(base + position * (7.0 if not live else 95.0), 1),
            "error": errors.get(service, ""),
        }
    return out


def records(count: int, *, now: datetime | None = None, prefix: str = PREFIX) -> Iterator[Dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    for index in range(count):
        yield record(index, now=now, prefix=prefix)


def expected(count: int) -> Dict[str, Any]:
    """What the corpus of `count` records adds up to.

    Computed from the same cycles the records are built from, so a test can
    assert a total instead of a shape — and so a change to the generator can
    never quietly agree with a change to the app.
    """
    rows = [record(index) for index in range(count)]
    sentiments: Dict[str, int] = {}
    statuses: Dict[str, int] = {}
    models: Dict[str, int] = {}
    persons = 0
    entities = 0
    for index, row in enumerate(rows):
        sentiment = row["enrichment"]["sentiment"]["text"]
        sentiments[sentiment] = sentiments.get(sentiment, 0) + 1
        status = "partial" if row["errors"] else "analysed"
        statuses[status] = statuses.get(status, 0) + 1
        model = row["enrichment"]["summary"]["metadata"]["model"]
        models[model] = models.get(model, 0) + 1
        persons += len(row["enrichment"]["face_match"]["persons"])
        entities += len(row["enrichment"]["entities"]["list"])
    return {
        "total": count,
        "sentiments": sentiments,
        "statuses": statuses,
        "models": models,
        "person_mentions": persons,
        "entity_mentions": entities,
    }


def ids(count: int, *, prefix: str = PREFIX) -> List[str]:
    return [f"{prefix}{index:04d}" for index in range(count)]
