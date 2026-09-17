"""
The SQLAlchemy engine, the session scope, and the schema.

One engine per process, created lazily — importing a model must not open a
socket, or a mocked unit test would need PostgreSQL to import a worker.

`available()` is the reason the pipeline survives a database outage: it answers
"can I reach it?" once, cheaply, and `store.save_record()` uses it to decide
between writing and logging. Everything else here assumes a working connection
and raises if there is not one, because a *read* endpoint that silently answers
`[]` when the database is down is worse than one that says so.
"""

import threading
from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from config import Config
from framework.commons.logger import logger

_engine = None
_maker: Optional[sessionmaker] = None
#: Re-entrant on purpose. `create_schema()` and `_sessions()` both take this
#: lock and then call `engine()`, which takes it again to build the engine on
#: first use. With a plain Lock that is a deadlock, and it is not hypothetical:
#: whichever of the three runs first in a cold process hangs its thread for
#: ever. Today `main.py` calls `available()` — and so `engine()` — at boot,
#: which fills `_engine` and makes every later re-entry short-circuit before
#: the lock; a worker process that skipped that step would simply stop.
_lock = threading.RLock()
_schema_ready = False


class DatabaseUnavailable(RuntimeError):
    """The database is turned off (`DB_ENABLED=false`) or cannot be reached."""


def engine():
    """The process-wide engine, built on first use."""
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                _engine = create_engine(
                    Config.DATABASE_URL,
                    pool_size=Config.DB_POOL_SIZE,
                    max_overflow=Config.DB_MAX_OVERFLOW,
                    pool_timeout=Config.DB_POOL_TIMEOUT,
                    # A pooled connection that a restarted PostgreSQL has
                    # already forgotten is the classic "first request after a
                    # compose restart fails"; this trades a ping for that.
                    pool_pre_ping=True,
                    echo=Config.DB_ECHO,
                    future=True,
                )
    return _engine


def _sessions() -> sessionmaker:
    global _maker
    if _maker is None:
        with _lock:
            if _maker is None:
                _maker = sessionmaker(bind=engine(), expire_on_commit=False, future=True)
    return _maker


@contextmanager
def session_scope() -> Iterator[Session]:
    """Commit on success, roll back on error, always close."""
    if not Config.DB_ENABLED:
        raise DatabaseUnavailable("DB_ENABLED=false — the client app has no database")

    session = _sessions()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_schema() -> None:
    """Create the tables and indexes when they are missing; idempotent.

    Called once at boot from `main.py` and again, lazily, by the first write —
    the API and the ETL start in the same process here, but a worker running on
    its own would otherwise have no schema.
    """
    global _schema_ready
    if _schema_ready or not Config.DB_CREATE_ALL:
        return

    from client import models

    with _lock:
        if _schema_ready:
            return
        models.Base.metadata.create_all(engine())
        _schema_ready = True
        logger.info(
            f"[db] schema ready — {len(models.Base.metadata.tables)} tables at "
            f"{safe_url()}"
        )


def available() -> bool:
    """Can a record be written right now? Never raises.

    A failure here is logged once per call and answered as False, so the caller
    (`store.save_record`) can keep the pipeline moving.
    """
    if not Config.DB_ENABLED:
        return False
    try:
        with engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError as exc:
        logger.warning(f"[db] unavailable at {safe_url()}: {_short(exc)}")
        return False


def health() -> dict:
    """`{status, url, tables?, error?}` — what `/client/health` reports."""
    if not Config.DB_ENABLED:
        return {"status": "disabled", "url": safe_url()}
    try:
        with engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        from client import models

        return {
            "status": "ok",
            "url": safe_url(),
            "tables": sorted(models.Base.metadata.tables),
        }
    except SQLAlchemyError as exc:
        return {"status": "unreachable", "url": safe_url(), "error": _short(exc)}


def safe_url() -> str:
    """The connection URL with the password removed — safe to log or serve."""
    try:
        from sqlalchemy.engine import make_url

        return make_url(Config.DATABASE_URL).render_as_string(hide_password=True)
    except Exception:  # pragma: no cover - a malformed URL is reported elsewhere
        return "<unparseable DATABASE_URL>"


def _short(exc: Exception) -> str:
    """The first line of a SQLAlchemy error — the rest is a stack of drivers."""
    return str(exc).strip().splitlines()[0][:200]
