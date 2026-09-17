"""
The prompt texts W6 sends to the summary service (:8825).

One file per prompt, right next to this module::

    src/prompts/summary.txt      -> the narrative summary
    src/prompts/entities.txt     -> one `TYPE: value` entity per line
    src/prompts/sentiment.txt    -> a single word, POSITIVE/NEGATIVE/NEUTRAL

The service does NOT load these itself: `/summarize` takes the prompt *text* in
the request body (`prompt_text`), so the pipeline owns the wording and a prompt
can be edited without touching the AI host. `Config.SUMMARY_PROMPT` and friends
name the file; `load()` turns that name into the text `ai_client.summarize()`
posts.

Files are read once and cached — editing one takes effect on the next restart.
`load()` raises `PromptError` when a prompt is missing or empty, which is a
configuration mistake, not a service failure: it is better to hear about it at
startup (see `preload()`, called from `main.py`) than to discover it on the
first video.
"""

import os
import threading
from typing import Dict, List, Optional

from config import Config
from framework.commons.logger import logger


class PromptError(RuntimeError):
    """A prompt file is missing, unreadable, or empty."""


_cache: Dict[str, str] = {}
_lock = threading.Lock()


def path(name: str) -> str:
    """The absolute path of prompt file `name` inside `Config.PROMPTS_DIR`."""
    return os.path.join(Config.PROMPTS_DIR, name)


def load(name: str) -> str:
    """The prompt text for file `name` — the database's copy, or the file's.

    `name` is a bare file name (`summary.txt`) resolved inside
    `Config.PROMPTS_DIR`; anything else is refused so a stray env var cannot
    make the pipeline read an arbitrary file.

    When the prompt has been edited in the UI (`PROMPTS_FROM_DB`, the default)
    the stored wording wins. The file is what ships, what seeds the table and
    what is used whenever the database has nothing to say — including when it
    is down, which is why a prompt outage cannot stop a video being analysed.
    Use `from_file()` for the shipped text specifically.
    """
    stored = _stored(name)
    if stored is not None:
        return stored
    return from_file(name)


def _stored(name: str) -> Optional[str]:
    """The database's copy of this prompt, or None. Never raises."""
    try:
        from client import prompt_store
    except Exception:  # pragma: no cover - the client package is optional
        return None

    kind = prompt_store.kind_of(name)
    if kind is None:
        return None
    answer = prompt_store.text_for(kind)
    return answer[0] if answer else None


def from_file(name: str) -> str:
    """The shipped text of prompt file `name`, read once and cached."""
    if name != os.path.basename(name):
        raise PromptError(f"prompt {name!r} must be a file name inside {Config.PROMPTS_DIR}")

    cached = _cache.get(name)
    if cached is not None:
        return cached

    with _lock:
        if name in _cache:
            return _cache[name]

        target = path(name)
        try:
            with open(target, "r", encoding="utf-8") as handle:
                text = handle.read().strip()
        except OSError as exc:
            raise PromptError(f"cannot read prompt {name!r} at {target}: {exc}") from exc

        if not text:
            raise PromptError(f"prompt {name!r} at {target} is empty")

        _cache[name] = text
        return text


def preload() -> List[str]:
    """Read the three configured prompts at startup and log their sizes.

    Returns the names that loaded. A broken prompt raises here, at boot, rather
    than mid-pipeline on the first video.
    """
    names = [Config.SUMMARY_PROMPT, Config.ENTITIES_PROMPT, Config.SENTIMENT_PROMPT]
    for name in names:
        # The *file*, deliberately: this is the check that the shipped default
        # is readable, and it runs before the database is known to be there.
        text = from_file(name)
        logger.info(f"[prompts] {name:<16} {len(text)} chars from {path(name)}")
    return names
