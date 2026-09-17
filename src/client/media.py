"""
Serving the video itself, so a record can be watched next to its analysis.

The pipeline never opens the video — it forwards a path and the AI services
resolve it on *their* filesystem. The browser cannot do that, so this module
answers one question: is the file this record names also readable here, under
one of `VIDEO_SEARCH_DIRS`? If it is, it is streamed; if it is not, the UI is
told plainly rather than shown a player that will not play.

Two rules, because this is the one endpoint that turns a stored string into a
file read:

  * the path must resolve **inside** a configured search directory, checked
    after `realpath` so a symlink cannot lead out of one;
  * only known video extensions are served.

A record's path comes from the pipeline rather than from a request, but that is
an argument for validating it anyway: the day something else writes a record,
this is what stops a path traversal being a file disclosure.
"""

import mimetypes
import os
from typing import Optional, Tuple

from config import Config

#: What a browser can be expected to play, and what we are willing to open.
VIDEO_SUFFIXES = (".mp4", ".webm", ".mkv", ".mov", ".m4v", ".avi", ".ogg", ".ogv")

DEFAULT_TYPE = "application/octet-stream"


def locate(path: str) -> Optional[str]:
    """The local file for a record's `path`, or None when there is not one.

    Tries the path itself, then the same *file name* inside each search
    directory — which is the case that matters in compose, where the AI host
    says `/video/x.mp4` and the same file is mounted at `/app/videos/x.mp4`.
    """
    raw = str(path or "").strip()
    if not raw:
        return None

    candidates = [raw]
    name = os.path.basename(raw)
    if name:
        candidates.extend(os.path.join(directory, name) for directory in Config.VIDEO_SEARCH_DIRS)

    for candidate in candidates:
        resolved = os.path.realpath(candidate)
        if not os.path.isfile(resolved):
            continue
        if not _inside_a_search_dir(resolved):
            continue
        if os.path.splitext(resolved)[1].lower() not in VIDEO_SUFFIXES:
            continue
        return resolved
    return None


def _inside_a_search_dir(resolved: str) -> bool:
    """True when `resolved` is under one of VIDEO_SEARCH_DIRS.

    `commonpath` rather than `startswith`: `/app/videos-secret/x.mp4` starts
    with `/app/videos` as a string and is not inside it as a directory.
    """
    for directory in Config.VIDEO_SEARCH_DIRS:
        root = os.path.realpath(directory)
        if not root:
            continue
        try:
            if os.path.commonpath([resolved, root]) == root:
                return True
        except ValueError:
            # Different drives on Windows; not the same tree either way.
            continue
    return False


def describe(path: str) -> Tuple[bool, Optional[str], Optional[int]]:
    """`(playable, local_path, size_bytes)` — what the detail endpoint reports."""
    local = locate(path)
    if local is None:
        return False, None, None
    try:
        return True, local, os.path.getsize(local)
    except OSError:  # pragma: no cover - raced with a deletion
        return False, None, None


def content_type(local_path: str) -> str:
    guessed, _ = mimetypes.guess_type(local_path)
    return guessed or DEFAULT_TYPE
