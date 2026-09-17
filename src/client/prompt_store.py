"""
The prompts, in the database — read by W6, edited from /pipeline.

`src/prompts/*.txt` is still where the wording *ships*: it is the default a
fresh database is seeded from, and the fallback whenever PostgreSQL is not
there. A row in `prompts` overrides its file.

The cache is what makes this cheap enough to sit in the pipeline's path. W6
asks for three prompts per video, so a query per call would be three round
trips per video; a cache with no invalidation would mean an edit not taking
effect until a restart. Both are avoided the same way: cache with a short TTL,
and drop the entry the moment this process writes one. The ETL and the API are
the same process here, so an edit is live immediately; a second process picks
it up within `PROMPT_CACHE_SECONDS`.

Nothing here raises into a worker: `text_for()` falls back to the file, and the
file is validated at boot (`prompts.preload()`), so a database outage costs the
*edits*, never the pipeline.
"""

import threading
import time
from typing import Dict, Optional, Tuple

from config import Config
from framework.commons.logger import logger

#: `kind` -> the file its default lives in. The kinds are W6's three calls.
FILES = {
    "summary": Config.SUMMARY_PROMPT,
    "entities": Config.ENTITIES_PROMPT,
    "sentiment": Config.SENTIMENT_PROMPT,
}

KINDS = tuple(FILES)

#: How long a cached prompt is trusted. Short, because the cost of being wrong
#: is an analyst editing a prompt and not seeing it apply.
TTL_SECONDS = float(Config.PROMPT_CACHE_SECONDS)

_cache: Dict[str, Tuple[float, str, int]] = {}
_lock = threading.Lock()


def kind_of(prompt_file: str) -> Optional[str]:
    """`summary.txt` -> `summary`; anything unrecognised -> None."""
    for kind, name in FILES.items():
        if name == prompt_file:
            return kind
    return None


def text_for(kind: str) -> Optional[Tuple[str, int]]:
    """`(text, version)` from the database, or None to use the file.

    Never raises: a database that is down, a missing table on a first run, a
    row that has not been created yet — all of them mean "the file is the
    prompt", which is exactly what the pipeline did before this existed.
    """
    if not Config.DB_ENABLED or not Config.PROMPTS_FROM_DB:
        return None

    now = time.monotonic()
    cached = _cache.get(kind)
    if cached and cached[0] > now:
        return cached[1], cached[2]

    try:
        from client import db
        from client.models import Prompt

        with db.session_scope() as session:
            row = session.get(Prompt, kind)
            if row is None or not (row.text or "").strip():
                return None
            answer = (row.text.strip(), int(row.version or 1))
    except Exception as exc:  # the pipeline must not stop for this
        logger.debug(f"[prompts] database copy unavailable for {kind!r}: {exc}")
        return None

    with _lock:
        _cache[kind] = (now + TTL_SECONDS, answer[0], answer[1])
    return answer


def invalidate(kind: Optional[str] = None) -> None:
    """Forget the cached copy — called by every write in this process."""
    with _lock:
        if kind is None:
            _cache.clear()
        else:
            _cache.pop(kind, None)


# ---------------------------------------------------------------------------
# The editing side — what /client/prompts serves
# ---------------------------------------------------------------------------

def seed(session) -> int:
    """Create a row per prompt from its file, for the ones with no row yet.

    Runs at boot. It never overwrites an existing row: the file is the default,
    and a default does not get to undo somebody's edit.
    """
    import prompts as prompt_files
    from client.models import Prompt

    created = 0
    for kind, file_name in FILES.items():
        if session.get(Prompt, kind) is not None:
            continue
        try:
            text = prompt_files.load(file_name)
        except prompt_files.PromptError as exc:
            logger.warning(f"[prompts] {file_name} could not be read, not seeded: {exc}")
            continue
        session.add(Prompt(name=kind, text=text, default_text=text, version=1, updated_by="file"))
        created += 1
    if created:
        logger.info(f"[prompts] seeded {created} prompt(s) into the database from src/prompts/")
    return created


def listing(session) -> Dict[str, object]:
    """Every prompt, with where its text is coming from right now."""
    import prompts as prompt_files
    from client.models import Prompt

    items = []
    for kind, file_name in FILES.items():
        row = session.get(Prompt, kind)
        try:
            file_text = prompt_files.load(file_name)
        except prompt_files.PromptError:
            file_text = ""
        items.append(
            {
                "name": kind,
                "file": file_name,
                "text": (row.text if row else file_text) or "",
                "default_text": (row.default_text if row else file_text) or "",
                "version": int(row.version) if row else 0,
                "updated_by": row.updated_by if row else "",
                "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
                # False means the file is in use — either nothing has been saved
                # yet or PROMPTS_FROM_DB is off.
                "from_db": bool(row and Config.PROMPTS_FROM_DB),
                "modified": bool(row and (row.text or "").strip() != (row.default_text or "").strip()),
            }
        )
    return {"items": items, "from_db": Config.PROMPTS_FROM_DB, "dir": Config.PROMPTS_DIR}


def save(session, kind: str, text: str, *, updated_by: str = "") -> Dict[str, object]:
    """Store a new wording for one prompt and return the stored row."""
    from client.errors import NotFoundError, ValidationError
    from client.models import Prompt

    if kind not in FILES:
        raise NotFoundError(f"{kind!r} is not a prompt; use one of {', '.join(KINDS)}")

    body = (text or "").strip()
    if not body:
        raise ValidationError("a prompt cannot be empty")

    row = session.get(Prompt, kind)
    if row is None:
        row = Prompt(name=kind, default_text=body, version=0)
        session.add(row)

    if body != (row.text or ""):
        row.version = int(row.version or 0) + 1
    row.text = body
    row.updated_by = str(updated_by or "")[:128]
    session.flush()
    invalidate(kind)

    logger.info(f"[prompts] {kind} saved (v{row.version}, {len(body)} chars) by {row.updated_by or 'anonymous'}")
    return {
        "name": row.name,
        "text": row.text,
        "version": row.version,
        "updated_by": row.updated_by,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def reset(session, kind: str) -> Dict[str, object]:
    """Put the shipped wording back — the file's text, as first seeded."""
    from client.errors import NotFoundError
    from client.models import Prompt

    if kind not in FILES:
        raise NotFoundError(f"{kind!r} is not a prompt; use one of {', '.join(KINDS)}")

    row = session.get(Prompt, kind)
    default = (row.default_text if row else "") or ""
    if not default:
        import prompts as prompt_files

        default = prompt_files.load(FILES[kind])
    return save(session, kind, default, updated_by="reset")
