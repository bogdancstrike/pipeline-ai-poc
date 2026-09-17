"""
The record list, one record, and the export.

Every narrowing happens in PostgreSQL. A client that filtered a page it had
already downloaded would be filtering 25 of 20,000 rows while presenting the
answer as if it covered all of them — so `q`, the filter bar, the advanced
condition tree, the sort and the facet counts are all one statement, and the
page comes back with the total the footer needs.

    POST /client/records/search   {filters, query_text, condition_tree, page…}
    GET  /client/records          the same thing from query-string parameters
    GET  /client/records/{id}     one record, with its document
    POST /client/records/export   the same question, as a CSV or JSON download
"""

from typing import Any, Dict, List, Optional

from sqlalchemy import select

from client import export as export_module
from client.clock import iso
from client.errors import NotFoundError, ValidationError
from client.models import RecordCall, RecordEntity, VideoRecord
from client.pagination import envelope, parse_page
from client.query import apply_filters, apply_sort, count_of, facets_for
from client.resources import (
    DEFAULT_COLUMNS,
    DEFAULT_SORT,
    EXPORT_COLUMNS,
    FIELDS,
)
from client.rules import compile_tree, describe_tree, rule_count

#: Text columns a list row truncates. The table shows a line of the summary;
#: the drawer shows all of it, and the document has every word either way.
PREVIEW_CHARS = 280


# ---------------------------------------------------------------------------
# The list
# ---------------------------------------------------------------------------

def search(session, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Run one explorer question and return the page, the total and the facets."""
    if not isinstance(payload, dict):
        raise ValidationError("The query must be a JSON object.")

    tree = payload.get("condition_tree")
    if tree is not None and not isinstance(tree, dict):
        raise ValidationError("condition_tree must be an object or null")

    page = parse_page(payload, default_sort=DEFAULT_SORT)
    statement = apply_filters(select(VideoRecord), _filter_args(payload), FIELDS)

    predicate = compile_tree(tree, FIELDS)
    if predicate is not None:
        statement = statement.where(predicate)

    total = count_of(session, statement)
    # One GROUP BY per faceted column, and only when asked: computing menus
    # nobody renders is work the reader waits for.
    facets = facets_for(session, statement, FIELDS) if payload.get("facets") else {}

    statement = apply_sort(statement, page, FIELDS, default=DEFAULT_SORT)
    rows = session.scalars(
        statement.offset(page.offset).limit(page.page_size)
    ).unique().all()

    columns = _columns(payload.get("columns"))
    return envelope(
        [row_of(row, columns) for row in rows],
        total,
        page,
        columns=columns,
        fields=FIELDS.describe(),
        facets=facets,
        condition_text=describe_tree(tree, FIELDS),
        rule_count=rule_count(tree),
        # Echoed so the table highlights the term that was actually searched
        # for, not the one currently in the box: the two differ for as long as
        # the request is in flight.
        query_text=str(payload.get("query_text") or "").strip(),
        searchable=[field.name for field in FIELDS.searchable],
    )


def _filter_args(payload: Dict[str, Any]) -> Dict[str, Any]:
    """The subset of the body `apply_filters` reads: the declared fields, their
    `__operator` spellings, and `q`."""
    args: Dict[str, Any] = {}
    filters = payload.get("filters")
    if filters is not None and not isinstance(filters, dict):
        raise ValidationError("filters must be an object")
    for key, value in (filters or {}).items():
        args[str(key)] = value
    text = str(payload.get("query_text") or payload.get("q") or "").strip()
    if text:
        args["q"] = text
    return args


def _columns(raw: Any) -> List[str]:
    """The columns to serialise — declared ones only, in the order asked for."""
    if not raw:
        return list(DEFAULT_COLUMNS)
    if isinstance(raw, str):
        raw = [part.strip() for part in raw.split(",")]
    if not isinstance(raw, (list, tuple)):
        raise ValidationError("columns must be a list of field names")

    chosen = [str(name) for name in raw if str(name) in FIELDS.by_name]
    if not chosen:
        raise ValidationError(
            "none of those columns exist",
            details={"available": sorted(FIELDS.by_name)},
        )
    return chosen


def row_of(row: VideoRecord, columns: List[str]) -> Dict[str, Any]:
    """One table row: the identity every row carries, plus the chosen columns.

    `id` and `name` are always present whatever the column choice, because the
    table has to be able to open a record the reader did not ask to see the id
    of.
    """
    body: Dict[str, Any] = {"id": row.id, "name": row.name}
    for column in columns:
        body[column] = _value(row, column)
    # A line of prose, so a result is recognisable without opening it.
    body.setdefault("summary_preview", _clip(row.summary))
    body["sentiment"] = row.sentiment
    body["status"] = row.status
    body["analysed_at"] = iso(row.analysed_at)
    return body


def _value(row: VideoRecord, column: str) -> Any:
    spec = FIELDS.by_name.get(column)
    value = getattr(row, spec.column.key if spec is not None else column, None)
    if spec is not None and spec.kind == "datetime":
        return iso(value)
    if spec is not None and spec.kind == "text" and isinstance(value, str):
        return _clip(value)
    return value


def _clip(text: Optional[str]) -> str:
    text = (text or "").strip()
    return text if len(text) <= PREVIEW_CHARS else f"{text[:PREVIEW_CHARS]}…"


# ---------------------------------------------------------------------------
# One record
# ---------------------------------------------------------------------------

def detail(session, record_id: str) -> Dict[str, Any]:
    """Everything about one video: the columns, the children, the document."""
    row = session.get(VideoRecord, str(record_id))
    if row is None:
        raise NotFoundError(f"no record with id {record_id!r}")

    return {
        "id": row.id,
        "name": row.name,
        "path": row.path,
        "status": row.status,
        "submitted_at": iso(row.submitted_at),
        "analysed_at": iso(row.analysed_at),
        "processing_seconds": row.processing_seconds,
        "sentiment": row.sentiment,
        "summary": row.summary,
        "entities_text": row.entities_text,
        "description": row.description,
        "transcript": row.transcript,
        "transcript_format": row.transcript_format,
        "ocr_text": row.ocr_text,
        "ocr_frames_count": row.ocr_frames_count,
        "persons": row.persons or [],
        "model": row.model,
        "prompt_hash": row.prompt_hash,
        "mocked": row.mocked,
        "errors": row.errors or {},
        "failed_services": row.failed_services or [],
        "entities": [
            {"type": e.type, "value": e.value, "raw": e.raw, "position": e.position}
            for e in sorted(row.entities, key=lambda e: e.position)
        ],
        "calls": [
            {
                "service": c.service,
                "mocked": c.mocked,
                "endpoint": c.endpoint,
                "duration_ms": c.duration_ms,
                "ok": c.ok,
                "error": c.error,
                "model": c.model,
                "provider": c.provider,
                "input_tokens": c.input_tokens,
                "output_tokens": c.output_tokens,
                "service_seconds": c.service_seconds,
            }
            for c in sorted(row.calls, key=lambda c: c.service)
        ],
        # Is the file readable from here? The player is only rendered when it
        # is — a <video> pointing at a 404 is a black box with no explanation.
        "video": _video_of(row),
        # W7's record, verbatim — what the JSON file on disk holds.
        "document": row.document or {},
    }


def _video_of(row: VideoRecord) -> Dict[str, Any]:
    from client import media

    playable, local, size = media.describe(row.path)
    return {
        "playable": playable,
        "url": f"/client/records/{row.id}/video" if playable else None,
        "size_bytes": size,
        "local_path": local,
    }


def raw(session, record_id: str) -> VideoRecord:
    """The row itself — for a caller that needs a column, not a document."""
    row = session.get(VideoRecord, str(record_id))
    if row is None:
        raise NotFoundError(f"no record with id {record_id!r}")
    return row


def neighbours(session, record_id: str) -> Dict[str, Any]:
    """The records that share an entity or a person with this one.

    Cheap relatedness, and honest about being that: two videos that both name
    Ceuta are related in the only way this data can prove.
    """
    row = session.get(VideoRecord, str(record_id))
    if row is None:
        raise NotFoundError(f"no record with id {record_id!r}")

    keys = [e.value_key for e in row.entities if e.value_key]
    if not keys:
        return {"items": [], "shared_on": []}

    statement = (
        select(RecordEntity.record_id, VideoRecord.name, RecordEntity.value)
        .join(VideoRecord, VideoRecord.id == RecordEntity.record_id)
        .where(RecordEntity.value_key.in_(keys), RecordEntity.record_id != row.id)
    )
    seen: Dict[str, Dict[str, Any]] = {}
    for other_id, name, value in session.execute(statement).all():
        entry = seen.setdefault(
            other_id, {"id": other_id, "name": name, "shared": [], "count": 0}
        )
        if value not in entry["shared"]:
            entry["shared"].append(value)
        entry["count"] += 1

    items = sorted(seen.values(), key=lambda e: (-e["count"], e["name"]))
    return {"items": items[:25], "shared_on": sorted({v for e in items for v in e["shared"]})}


# ---------------------------------------------------------------------------
# The export
# ---------------------------------------------------------------------------

def export_columns(raw: Any) -> List[export_module.Column]:
    names = _columns(raw) if raw else list(EXPORT_COLUMNS)
    # `Column.title` is derived from `label`; passing it directly is a
    # TypeError on a frozen slots dataclass.
    return [
        export_module.Column(name=name, label=FIELDS.by_name[name].title)
        for name in names
        if name in FIELDS.by_name
    ]


def export_statement(payload: Dict[str, Any]):
    """The same question the list answers, without the page — for a download."""
    statement = apply_filters(select(VideoRecord), _filter_args(payload), FIELDS)
    predicate = compile_tree(payload.get("condition_tree"), FIELDS)
    if predicate is not None:
        statement = statement.where(predicate)
    page = parse_page(payload, default_sort=DEFAULT_SORT)
    return apply_sort(statement, page, FIELDS, default=DEFAULT_SORT)


def call_rows(session, record_id: str) -> List[RecordCall]:
    return list(session.scalars(select(RecordCall).where(RecordCall.record_id == record_id)))
