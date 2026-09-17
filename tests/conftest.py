"""
Shared pytest setup.

Forces every worker into mock mode BEFORE any pipeline module imports config,
so the unit tests never touch the AI host at 172.17.12.80 (which is not part of
docker-compose and is normally unreachable from CI). `pytest.ini` already puts
src/ on the path.
"""

import os

os.environ.setdefault("LOGGING_LEVEL", "WARNING")
os.environ.setdefault("MOCK_LATENCY_MS", "0")
os.environ.setdefault("OUTPUT_FORMAT", "line")
os.environ.setdefault("VIDEO_PATH_PASSTHROUGH", "true")

for _worker in (
    "FACE_MATCH", "DESCRIBE", "OCR", "TRANSCRIBE", "SUMMARY", "ENTITIES", "SENTIMENT",
):
    os.environ.setdefault(f"MOCK_WORKER_{_worker}", "True")

# W7 writes every record to PostgreSQL as well as to disk. A unit test has no
# PostgreSQL, and `store.save_record` swallows that by design — but it would
# still try to connect, once per test, with the pool timeout that implies. Off
# by default here; `test_client.py` turns it back on against SQLite.
os.environ.setdefault("DB_ENABLED", "false")

import pytest  # noqa: E402

from framework.commons.utils import deep_merge  # noqa: E402


@pytest.fixture()
def video_message():
    """What lands on `video.in` — one path plus the id both aggregators key on."""
    return {
        "id": "test-video-1",
        "path": "/video/migrants.mp4",
        "source": "api",
        "submitted_at": "2026-09-16T10:00:00+00:00",
    }


@pytest.fixture()
def merge():
    """Emulate the framework's aggregator: deep-merge the branch messages."""

    def _merge(messages):
        out = {}
        for message in messages:
            out = deep_merge(out, message)
        return out

    return _merge


@pytest.fixture()
def branches(video_message):
    """Run W1..W5 and hand back every message, the way the runtime would."""
    from workers import pipeline

    item = pipeline.worker_split(video_message, "test", {})
    return {
        "item": item,
        "face": pipeline.worker_face_match(item, "test", {}),
        "describe": pipeline.worker_describe(item, "test", {}),
        "transcribe": pipeline.worker_transcribe(item, "test", {}),
        "ocr": pipeline.worker_ocr(item, "test", {}),
    }
