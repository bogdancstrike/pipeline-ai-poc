"""
W7's database sink — one record in, one row (plus its children) out.

This is the only module a worker imports from `src/client`, and
`save_record()` is the only function it calls. Everything it can go wrong with
is caught here: a database that is down, a record shaped unexpectedly, a
duplicate id. The pipeline's product is the record, and the record is already
on disk by the time this runs — so a failure here is logged and swallowed, and
the video still counts as analysed.

Re-submitting the same video id **replaces** its row. The alternative is a
table with six copies of one video and no way to say which is current; the
JSON file behaves the same way (`OUTPUT_UNIQUE_NAMES=false`).
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.exc import SQLAlchemyError

from config import Config
from framework.commons.logger import logger

from client import db
from client.models import RecordCall, RecordEntity, RecordPerson, VideoRecord

#: `LOCATION: Ceuta` -> ("LOCATION", "Ceuta"). A bare value keeps `UNTYPED`.
_TYPED_ENTITY = re.compile(r"^\s*([A-Za-z][A-Za-z _/-]{1,40}?)\s*:\s*(.+?)\s*$")


# ---------------------------------------------------------------------------
# The public entry point
# ---------------------------------------------------------------------------

def save_record(record: dict, calls: Optional[dict] = None) -> Optional[str]:
    """Write one W7 record to PostgreSQL. Returns the row id, or None.

    `calls` is W6's per-call provenance (mocked or live, which URL, how long),
    which the record itself does not carry. Passing it is what makes the
    statistics page possible; omitting it costs only that.

    Never raises: the caller is a Kafka worker whose job is already done.
    """
    if not Config.DB_ENABLED:
        return None

    video_id = str(record.get("id") or "").strip()
    if not video_id:
        logger.warning("[db] record with no id — not stored")
        return None

    try:
        db.create_schema()
        with db.session_scope() as session:
            row = session.get(VideoRecord, video_id)
            if row is None:
                row = VideoRecord(id=video_id)
                session.add(row)
            else:
                # Replace the children wholesale rather than diffing them: a
                # re-analysis is a new answer, not an edit of the old one.
                row.entities.clear()
                row.people.clear()
                row.calls.clear()
                session.flush()

            _fill(row, record)
            _fill_children(row, record, calls or {})

        logger.info(
            f"[db] id={video_id} stored — entities={len(record.get('enrichment', {}).get('entities', {}).get('list') or [])} "
            f"persons={len(record.get('enrichment', {}).get('face_match', {}).get('persons') or [])}"
        )
        return video_id
    except SQLAlchemyError as exc:
        logger.error(f"[db] id={video_id} NOT stored: {db._short(exc)}")
        return None
    except Exception as exc:  # pragma: no cover - defensive; W7 must not die
        logger.error(f"[db] id={video_id} NOT stored: {exc}")
        return None


# ---------------------------------------------------------------------------
# record -> columns
# ---------------------------------------------------------------------------

def _entry(record: dict, name: str) -> dict:
    entry = (record.get("enrichment") or {}).get(name)
    return entry if isinstance(entry, dict) else {}


def _fill(row: VideoRecord, record: dict) -> None:
    enrichment = record.get("enrichment") or {}
    summary = _entry(record, "summary")
    entities = _entry(record, "entities")
    sentiment = _entry(record, "sentiment")
    description = _entry(record, "description")
    transcript = _entry(record, "transcript")
    ocr = _entry(record, "ocr")
    face = _entry(record, "face_match")

    errors = record.get("errors") or {}
    submitted = _moment(record.get("submitted_at"))
    analysed = _moment(record.get("analysed_at"))

    row.name = str(record.get("name") or "")[:512]
    row.path = str(record.get("path") or "")[:1024]
    row.submitted_at = submitted
    row.analysed_at = analysed
    row.processing_seconds = (
        round((analysed - submitted).total_seconds(), 3)
        if submitted and analysed and analysed >= submitted
        else None
    )

    row.status = "partial" if errors else "analysed"
    row.failed_services = sorted(errors)
    row.errors = errors
    row.error_count = len(errors)

    row.summary = _text(summary.get("text"))
    # The sentiment prompt answers with one word; normalise the case so
    # POSITIVE and positive are one bucket in every chart.
    row.sentiment = _text(sentiment.get("text")).upper()[:32]
    row.entities_text = _text(entities.get("text"))
    row.description = _text(description.get("text"))
    row.transcript = _text(transcript.get("text"))
    row.transcript_format = str(transcript.get("format") or "")[:32]
    row.ocr_text = _text(ocr.get("text"))

    persons = [str(p) for p in (face.get("persons") or [])]
    row.persons = persons
    row.person_count = len(persons)
    row.entity_count = len(entities.get("list") or [])
    row.ocr_frames_count = int(ocr.get("frames_count") or 0)

    row.summary_chars = len(row.summary)
    row.transcript_chars = len(row.transcript)
    row.description_chars = len(row.description)
    row.ocr_chars = len(row.ocr_text)

    meta = summary.get("metadata") or {}
    row.model = str(meta.get("model") or "")[:128]
    row.prompt_hash = str(meta.get("prompt_hash") or "")[:64]

    row.search_text = "\n".join(
        part for part in (row.summary, row.entities_text, row.transcript,
                          row.description, row.ocr_text, row.name) if part
    )
    row.document = record


def _fill_children(row: VideoRecord, record: dict, calls: dict) -> None:
    entities = _entry(record, "entities")
    for position, raw in enumerate(entities.get("list") or []):
        kind, value = _split_entity(str(raw))
        row.entities.append(
            RecordEntity(
                type=kind[:64],
                value=value[:512],
                value_key=value.strip().lower()[:512],
                raw=str(raw),
                position=position,
            )
        )

    for person in row.persons:
        row.people.append(RecordPerson(person=str(person)[:128]))

    analysed = row.analysed_at
    mocked_any = False
    for service, source in _call_sources(record, calls):
        mocked = bool(source.get("mocked"))
        mocked_any = mocked_any or mocked
        meta = source.get("metadata") or {}
        row.calls.append(
            RecordCall(
                service=service[:64],
                mocked=mocked,
                endpoint=str(source.get("endpoint") or "")[:512],
                duration_ms=_number(source.get("duration_ms")),
                ok=not source.get("error"),
                error=str(source.get("error") or ""),
                model=str(meta.get("model") or "")[:128],
                provider=str(meta.get("provider") or "")[:64],
                input_tokens=_int(meta.get("input_tokens")),
                output_tokens=_int(meta.get("output_tokens")),
                service_seconds=_number(
                    meta.get("duration_seconds") or meta.get("processing_time_seconds")
                ),
                metadata_json=meta if isinstance(meta, dict) else {},
                analysed_at=analysed,
            )
        )
    row.mocked = mocked_any


def _call_sources(record: dict, calls: dict) -> List[Tuple[str, Dict[str, Any]]]:
    """One `(service, provenance)` pair per AI call this record can account for.

    `calls` is W6's provenance when W7 passed it on. What it cannot cover is
    face matching — that branch never passes through W6 — so the record's own
    `enrichment` fills in the rest, and a service named in `errors` gets a row
    even though it produced no answer. The point is that a failed call is
    visible in the statistics, not absent from them.
    """
    named: Dict[str, Dict[str, Any]] = {}

    for service, source in (calls or {}).items():
        if isinstance(source, dict):
            named[str(service)] = dict(source)

    # The metadata lives on the record even when the provenance did not travel.
    for entry_name, service in (
        ("face_match", "face-match-main"),
        ("description", "video-describe-354b"),
        ("transcript", "transcribe"),
        ("ocr", "video-ocr"),
        ("summary", "summary"),
        ("entities", "entities"),
        ("sentiment", "sentiment"),
    ):
        entry = _entry(record, entry_name)
        if not entry and service not in named:
            continue
        source = named.setdefault(service, {})
        source.setdefault("metadata", entry.get("metadata") or {})

    for service, message in (record.get("errors") or {}).items():
        named.setdefault(str(service), {})["error"] = str(message)

    return sorted(named.items())


def _split_entity(raw: str) -> Tuple[str, str]:
    """`LOCATION: Ceuta` -> ("LOCATION", "Ceuta"); `Ceuta` -> ("UNTYPED", "Ceuta")."""
    match = _TYPED_ENTITY.match(raw)
    if not match:
        return "UNTYPED", raw.strip()
    return match.group(1).strip().upper().replace(" ", "_"), match.group(2).strip()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _moment(value: Any) -> Optional[datetime]:
    """An ISO timestamp from the record -> an aware datetime, or None."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
