"""
The client app's HTTP layer — `/client/...`, registered in maps/endpoint.json.

Handlers follow this app's existing convention (see `src/api/__init__.py`):
they are called as `fn(app=..., operation=..., request=..., **path_params)` and
return a plain dict or a `(dict, status)` tuple, which Flask-RESTX serialises.

Two shapes of question, deliberately:

  * `GET  /client/records?...`   the filter bar and a bookmarkable URL — every
                                 narrowing is a query-string parameter;
  * `POST /client/records/search` the same engine, with the advanced builder's
                                 nested condition tree in the body, which does
                                 not fit in a URL.

Both compile to the same SQL, because both go through `client.explorer`.

Failures answer with the error envelope from `client.errors`
(`{error, message, details}`) and the matching status code, so the frontend has
one exception type to handle rather than a body per endpoint.
"""

from typing import Any, Dict, Tuple

from flask import request as flask_request

from framework.commons.logger import logger

from client import dashboard as dashboard_service
from client import db
from client import explorer as explorer_service
from client import export as export_module
from client import saved_searches as saved_search_service
from client import statistics as statistics_service
from client.errors import ApiError, ServiceUnavailableError
from client.resources import FIELDS, SENTIMENTS, SERVICES, STATUSES

Answer = Tuple[Dict[str, Any], int]


# ---------------------------------------------------------------------------
# Plumbing
# ---------------------------------------------------------------------------

def _body() -> Dict[str, Any]:
    payload = flask_request.get_json(force=True, silent=True)
    return payload if isinstance(payload, dict) else {}


def _args() -> Dict[str, Any]:
    """The query string as a plain dict — `apply_filters` reads it like a body."""
    return {key: value for key, value in flask_request.args.items()}


def _answer(fn, *args, **kwargs):
    """Run one handler inside a session, turning domain errors into HTTP.

    A dead database is a 503 rather than a 500: it is a dependency being down,
    not a bug, and the UI says so differently.
    """
    try:
        with db.session_scope() as session:
            return fn(session, *args, **kwargs), 200
    except ApiError as exc:
        return exc.to_dict(), exc.status_code
    except db.DatabaseUnavailable as exc:
        return ServiceUnavailableError(str(exc)).to_dict(), 503
    except Exception as exc:  # pragma: no cover - the catch-all a UI relies on
        logger.exception(f"[client] {fn.__name__} failed: {exc}")
        from sqlalchemy.exc import SQLAlchemyError

        if isinstance(exc, SQLAlchemyError):
            return (
                ServiceUnavailableError(
                    "the records database is unavailable", details={"detail": db._short(exc)}
                ).to_dict(),
                503,
            )
        return {"error": "internal_error", "message": str(exc)}, 500


# ---------------------------------------------------------------------------
# Records — the explorer
# ---------------------------------------------------------------------------

def records_list(app, operation, request, **kwargs) -> Answer:
    """GET /client/records — the table, from query-string parameters."""
    args = _args()
    payload = {
        "filters": {k: v for k, v in args.items()
                    if k not in ("page", "page_size", "sort", "order", "q", "facets", "columns")},
        "query_text": args.get("q", ""),
        "columns": args.get("columns"),
        "facets": str(args.get("facets", "")).lower() in ("1", "true", "yes"),
        "page": args.get("page", 1),
        "page_size": args.get("page_size", 25),
        "sort": args.get("sort"),
        "order": args.get("order"),
    }
    return _answer(explorer_service.search, payload)


def records_search(app, operation, request, **kwargs) -> Answer:
    """POST /client/records/search — the same engine, with a condition tree."""
    return _answer(explorer_service.search, _body())


def record_detail(app, operation, request, record_id=None, **kwargs) -> Answer:
    """GET /client/records/{record_id} — one record and its document."""
    return _answer(explorer_service.detail, str(record_id))


def record_related(app, operation, request, record_id=None, **kwargs) -> Answer:
    """GET /client/records/{record_id}/related — videos sharing an entity."""
    return _answer(explorer_service.neighbours, str(record_id))


def records_export(app, operation, request, **kwargs):
    """POST /client/records/export — the current question as a download.

    Returns a streamed Flask response rather than a dict: the rows are read
    from a generator that owns its own session, so the first byte leaves before
    the last row is fetched.
    """
    payload = _body()
    fmt = export_module.parse_format(payload.get("format"), default="csv")
    columns = explorer_service.export_columns(payload.get("columns"))
    statement = explorer_service.export_statement(payload)

    try:
        export_module.refuse_if_truncated(statement, fmt=fmt, what="records")
        rows = export_module.stream_rows(statement, limit=export_module.limit_for(fmt))
        return export_module.response(rows, columns, fmt=fmt, stem="video-records")
    except ApiError as exc:
        return exc.to_dict(), exc.status_code
    except db.DatabaseUnavailable as exc:
        return ServiceUnavailableError(str(exc)).to_dict(), 503


# ---------------------------------------------------------------------------
# Dashboard, statistics
# ---------------------------------------------------------------------------

def dashboard(app, operation, request, **kwargs) -> Answer:
    args = _args()
    return _answer(
        dashboard_service.overview,
        preset=args.get("range"),
        frm=args.get("from"),
        to=args.get("to"),
    )


def statistics(app, operation, request, **kwargs) -> Answer:
    args = _args()
    return _answer(
        statistics_service.services,
        preset=args.get("range"),
        frm=args.get("from"),
        to=args.get("to"),
    )


# ---------------------------------------------------------------------------
# Saved searches
# ---------------------------------------------------------------------------

def saved_searches_list(app, operation, request, **kwargs) -> Answer:
    return _answer(saved_search_service.listing, _args())


def saved_search_create(app, operation, request, **kwargs) -> Answer:
    body, status = _answer(saved_search_service.create, _body())
    return body, (201 if status == 200 else status)


def saved_search_update(app, operation, request, search_id=None, **kwargs) -> Answer:
    return _answer(saved_search_service.update, str(search_id), _body())


def saved_search_delete(app, operation, request, search_id=None, **kwargs) -> Answer:
    return _answer(saved_search_service.delete, str(search_id))


def saved_search_run(app, operation, request, search_id=None, **kwargs) -> Answer:
    """POST /client/searches/{id}/run — count the run and answer it.

    The stored question is merged *under* whatever the caller sends, so a saved
    search can be opened and then paged or re-sorted without being edited.
    """
    overrides = _body()

    def run(session):
        stored = saved_search_service.resolve(session, str(search_id))
        saved_search_service.mark_run(session, str(search_id))
        return explorer_service.search(session, {**stored, **overrides})

    return _answer(run)


# ---------------------------------------------------------------------------
# Meta — what the UI builds itself from
# ---------------------------------------------------------------------------

def meta(app, operation, request, **kwargs) -> Answer:
    """GET /client/meta — the field catalogue, the vocabularies, the ranges.

    The advanced query builder is generated from this rather than from a copy
    of the field list maintained in TypeScript: two lists that must agree and
    are edited separately eventually do not.
    """
    return {
        "fields": FIELDS.describe(),
        "searchable": [field.name for field in FIELDS.searchable],
        "facets": [field.name for field in FIELDS.facets],
        "sentiments": list(SENTIMENTS),
        "statuses": list(STATUSES),
        "services": list(SERVICES),
        "ranges": [
            "today", "yesterday", "last_7_days", "last_30_days", "last_90_days",
            "current_month", "previous_month", "current_year", "custom",
        ],
        "export_formats": list(export_module.FORMATS),
        "page_sizes": [10, 25, 50, 100, 200],
    }, 200


def health(app, operation, request, **kwargs) -> Answer:
    """GET /client/health — is the database there, and how much is in it?"""
    state = db.health()
    if state.get("status") != "ok":
        return state, 503

    from sqlalchemy import func, select

    from client.models import RecordCall, SavedSearch, VideoRecord

    try:
        with db.session_scope() as session:
            state["records"] = session.scalar(select(func.count(VideoRecord.id))) or 0
            state["calls"] = session.scalar(select(func.count(RecordCall.id))) or 0
            state["saved_searches"] = session.scalar(select(func.count(SavedSearch.id))) or 0
            state["latest"] = session.scalar(select(func.max(VideoRecord.analysed_at)))
            state["latest"] = state["latest"].isoformat() if state["latest"] else None
    except Exception as exc:  # pragma: no cover - reported, not raised
        state["status"] = "degraded"
        state["error"] = str(exc)[:200]
        return state, 503
    return state, 200
