"""
W7's file sink — the aggregated record for one video.

Unlike a batch pipeline, one submitted video produces exactly one record, so
there is nothing to buffer: W7 hands the finished record here and it is written
straight out, atomically.

    <Config.OUTPUT_DIR>/<video name without extension><Config.OUTPUT_FILE_SUFFIX>
    /video/migrants.mp4  ->  output/migrants_analysis.json

A second submission of the same video overwrites the previous record unless
`OUTPUT_UNIQUE_NAMES=true`, which appends the message id instead.
"""

import json
import os
from typing import Optional

from config import Config
from framework.commons.logger import logger


def output_path(video_name: str, record_id: Optional[str] = None) -> str:
    """`migrants.mp4` -> `<OUTPUT_DIR>/migrants_analysis.json`."""
    stem = os.path.splitext(os.path.basename(video_name or "video"))[0] or "video"
    if record_id and os.getenv("OUTPUT_UNIQUE_NAMES", "false").strip().lower() in ("1", "true", "yes", "on"):
        stem = f"{stem}-{record_id}"
    return os.path.join(Config.OUTPUT_DIR, f"{stem}{Config.OUTPUT_FILE_SUFFIX}")


def write(record: dict) -> Optional[str]:
    """Serialise one aggregated record; return the path, or None when disabled."""
    if not Config.OUTPUT_WRITE_FILE:
        return None

    path = output_path(record.get("name") or record.get("path") or "video", record.get("id"))
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    # Write beside the target and rename, so a reader never sees half a file.
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(record, fh, ensure_ascii=False, indent=Config.OUTPUT_JSON_INDENT)
        fh.write("\n")
    os.replace(tmp, path)

    logger.info(f"[sink] id={record.get('id')} wrote record -> {path}")
    return path
