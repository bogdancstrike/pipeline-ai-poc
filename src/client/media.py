"""
Serving the video itself, so a record can be watched next to its analysis.

The pipeline never opens the video — it forwards a path and the AI services
resolve it on *their* filesystem. The browser cannot do that, so this module
answers one question: is the file this record names also readable here, under
one of `VIDEO_SEARCH_DIRS`? If it is, it is streamed; if it is not, the UI is
told plainly rather than shown a player that will not play.

The two filesystems rarely agree on the root — the services say
`/video/Inmigracion/x.mp4`, compose mounts the same tree at `/app/videos` — so
the match is on the path's **tail**, not on its file name alone.

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
from typing import List, Optional, Tuple

from config import Config
from framework.commons.logger import logger

#: What a browser can be expected to play, and what we are willing to open.
VIDEO_SUFFIXES = (".mp4", ".webm", ".mkv", ".mov", ".m4v", ".avi", ".ogg", ".ogv")

DEFAULT_TYPE = "application/octet-stream"


def candidates_for(path: str) -> List[str]:
    """Every local path a record's `path` could mean, best first.

    The path in a record is the one the AI services opened, on *their*
    filesystem — `/video/Inmigracion/1abe….mp4`. The same file is usually
    mounted here under a different root, so the search is by **path suffix**:
    the whole thing first, then progressively shorter tails joined onto each
    search directory.

        /video/Inmigracion/1abe….mp4
          -> /video/Inmigracion/1abe….mp4            (as given)
          -> /app/videos/video/Inmigracion/1abe….mp4
          -> /app/videos/Inmigracion/1abe….mp4       ← the one that hits
          -> /app/videos/1abe….mp4

    Matching only the file name — which is what this did first — finds a video
    sitting directly in ./videos and misses every one in a subdirectory, which
    is how the corpus is actually organised.
    """
    raw = str(path or "").strip()
    if not raw:
        return []

    parts = [part for part in raw.replace("\\", "/").split("/") if part and part != "."]
    if not parts:
        return []

    found = [raw]
    for directory in Config.VIDEO_SEARCH_DIRS:
        # Longest tail first: `Inmigracion/x.mp4` is a better answer than
        # `x.mp4`, which could be a different file of the same name.
        for start in range(len(parts)):
            found.append(os.path.join(directory, *parts[start:]))

    seen = set()
    ordered = []
    for candidate in found:
        if candidate not in seen:
            seen.add(candidate)
            ordered.append(candidate)
    return ordered


def locate(path: str) -> Optional[str]:
    """The local file for a record's `path`, or None when there is not one."""
    for candidate in candidates_for(path):
        resolved = os.path.realpath(candidate)
        if not os.path.isfile(resolved):
            continue
        if not _inside_a_search_dir(resolved):
            logger.debug(f"[media] {resolved} exists but is outside VIDEO_SEARCH_DIRS")
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
