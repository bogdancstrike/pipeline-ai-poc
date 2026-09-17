#!/usr/bin/env python3
"""
Submit one video to the pipeline from the command line.

Publishes straight to `video.in` (the same topic the API writes to), so it works
without the HTTP layer:

    python tools/submit_video.py /video/migrants.mp4
    python tools/submit_video.py /video/1.mp4 --id vid-demo-1
    python tools/submit_video.py /audio/input.mp4 --language ro --task transcribe

Run it from the project root with src/ importable — `pip install -r
requirements.txt` in the venv, or `docker compose exec app python
tools/submit_video.py ...` inside the container.
"""

import argparse
import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BASE_DIR / ".env")

import publisher  # noqa: E402
import utils  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Submit one video to the analysis pipeline")
    parser.add_argument("path", help="Video path, as the AI services will open it")
    parser.add_argument("--id", dest="video_id", help="Message id (generated when omitted)")
    parser.add_argument("--name", help="Name of the output record (defaults to the file name)")
    parser.add_argument("--language", help="transcribe: source language, e.g. ar")
    parser.add_argument("--task", choices=["transcribe", "translate"], help="transcribe: task")
    parser.add_argument("--format", dest="fmt", help="transcribe: output format, e.g. dialog")
    parser.add_argument(
        "--level", dest="transcription_level", help="transcribe: transcription_level, e.g. word"
    )
    args = parser.parse_args()

    options = {
        k: v
        for k, v in {
            "language": args.language,
            "task": args.task,
            "format": args.fmt,
            "transcription_level": args.transcription_level,
        }.items()
        if v is not None
    }

    try:
        path = utils.resolve_video_path(args.path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    result = publisher.publish_video(
        path=path,
        video_id=args.video_id,
        name=args.name or utils.video_name(path),
        options=options,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nwatch it run:  docker compose logs -f app", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
