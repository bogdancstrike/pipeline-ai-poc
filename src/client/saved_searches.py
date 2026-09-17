"""
A search somebody named, so it can be asked again.

What is stored is the explorer's own request body — the filters, the free text,
the condition tree, the columns and the sort — not a rendered SQL string. That
is what lets a saved search survive a new field being added to the resource,
and what lets "run" mean *the same question asked now* rather than a snapshot
of the answer it gave last week.

There is no auth in this app yet, so `owner` is a label somebody typed rather
than a principal: a shared PoC instance with three analysts on it can still
tell whose search is whose, and the column is ready for a real identity when
one arrives.
"""

import uuid
from typing import Any, Dict, Optional

from sqlalchemy import select

from client.clock import iso, now
from client.errors import NotFoundError, ValidationError
from client.models import SavedSearch
from client.pagination import envelope, parse_page

MAX_NAME = 200

#: The keys of the explorer body that are worth keeping. Anything else a client
#: sends is dropped rather than stored: a saved search is a question, and a
#: page number is not part of one.
PAYLOAD_KEYS = ("filters", "query_text", "condition_tree", "columns", "sort", "order", "page_size")


def listing(session, args) -> Dict[str, Any]:
    page = parse_page(args, default_sort="updated_at")
    statement = select(SavedSearch)

    owner = str(args.get("owner") or "").strip()
    if owner:
        statement = statement.where(SavedSearch.owner == owner)
    text = str(args.get("q") or "").strip()
    if text:
        statement = statement.where(SavedSearch.name.ilike(f"%{text}%"))

    total = len(session.scalars(statement).all())
    column = getattr(SavedSearch, page.sort, SavedSearch.updated_at)
    statement = statement.order_by(
        SavedSearch.pinned.desc(),
        column.desc() if page.order == "desc" else column.asc(),
    )
    rows = session.scalars(statement.offset(page.offset).limit(page.page_size)).all()
    return envelope([_serialise(row) for row in rows], total, page)


def create(session, body: Dict[str, Any]) -> Dict[str, Any]:
    name = str(body.get("name") or "").strip()
    if not name:
        raise ValidationError("a saved search needs a name")

    row = SavedSearch(
        id=uuid.uuid4().hex,
        name=name[:MAX_NAME],
        description=str(body.get("description") or "").strip(),
        owner=str(body.get("owner") or "").strip()[:128],
        payload=_payload(body.get("payload") or body),
        pinned=bool(body.get("pinned")),
    )
    session.add(row)
    session.flush()
    return _serialise(row)


def update(session, search_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    row = _get(session, search_id)
    if "name" in body:
        name = str(body.get("name") or "").strip()
        if not name:
            raise ValidationError("a saved search needs a name")
        row.name = name[:MAX_NAME]
    if "description" in body:
        row.description = str(body.get("description") or "").strip()
    if "owner" in body:
        row.owner = str(body.get("owner") or "").strip()[:128]
    if "pinned" in body:
        row.pinned = bool(body.get("pinned"))
    if "payload" in body or any(key in body for key in PAYLOAD_KEYS):
        row.payload = _payload(body.get("payload") or body)
    session.flush()
    return _serialise(row)


def delete(session, search_id: str) -> Dict[str, Any]:
    row = _get(session, search_id)
    session.delete(row)
    return {"deleted": search_id}


def mark_run(session, search_id: str) -> Dict[str, Any]:
    """Count a run. What makes a "recently used" list honest."""
    row = _get(session, search_id)
    row.run_count = int(row.run_count or 0) + 1
    row.last_run_at = now()
    session.flush()
    return _serialise(row)


def _get(session, search_id: str) -> SavedSearch:
    row = session.get(SavedSearch, str(search_id))
    if row is None:
        raise NotFoundError(f"no saved search with id {search_id!r}")
    return row


def _payload(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValidationError("payload must be an object")
    return {key: raw[key] for key in PAYLOAD_KEYS if key in raw}


def _serialise(row: SavedSearch) -> Dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "owner": row.owner,
        "payload": row.payload or {},
        "pinned": row.pinned,
        "run_count": row.run_count,
        "last_run_at": iso(row.last_run_at),
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }


def resolve(session, search_id: Optional[str]) -> Dict[str, Any]:
    """The stored question, ready to be merged into an explorer request."""
    if not search_id:
        return {}
    return dict(_get(session, search_id).payload or {})
