"""
Publishing helper for the ingest topic (`video.in`).

Used by the HTTP API and by `tools/submit_video.py`. Only a *path* travels
through Kafka — never the video itself — so messages are small; the producer
still raises `max_request_size` to `Config.KAFKA_MAX_MESSAGE_BYTES` because the
same broker settings carry the fat OCR and transcript branch messages later in
the pipeline.

The framework's own `KafkaClient` is not used here: it builds its producer with
a fixed config, and the pipeline needs the larger limit.
"""

import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

from kafka import KafkaProducer

from config import Config, Topics
from framework.commons.logger import logger
import record_writer

_producer: Optional[KafkaProducer] = None
_lock = threading.Lock()


def get_producer() -> KafkaProducer:
    """Lazily create the producer (so importing never needs a broker)."""
    global _producer
    if _producer is None:
        with _lock:
            if _producer is None:
                _producer = KafkaProducer(
                    bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS.split(","),
                    value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
                    key_serializer=lambda k: k.encode("utf-8") if k else None,
                    max_request_size=Config.KAFKA_MAX_MESSAGE_BYTES,
                    buffer_memory=max(32 * 1024 * 1024, Config.KAFKA_MAX_MESSAGE_BYTES * 2),
                    acks=1,
                    retries=3,
                    request_timeout_ms=60_000,
                )
                logger.info(
                    f"[publisher] producer ready servers={Config.KAFKA_BOOTSTRAP_SERVERS} "
                    f"max_request_size={Config.KAFKA_MAX_MESSAGE_BYTES}"
                )
    return _producer


def publish_video(
    *,
    path: str,
    video_id: Optional[str] = None,
    name: Optional[str] = None,
    options: Optional[dict] = None,
    timeout_sec: float = 30.0,
) -> dict:
    """Publish one video to `video.in` and wait for the broker ack.

    `video_id` becomes the message `id` — the key BOTH aggregators regroup their
    branches by, so it must be unique per submission. One is generated when it
    is not given.

    `options` is forwarded untouched to the transcribe worker (language, task,
    format, transcription_level, dialog_timestamps); anything else is ignored.
    """
    video_id = video_id or f"vid-{uuid.uuid4().hex[:12]}"
    envelope = {
        "id": video_id,
        "path": path,
        "source": "api",
        "submitted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if name:
        envelope["name"] = name
    if options:
        envelope["options"] = options

    future = get_producer().send(Topics.VIDEO_IN, value=envelope, key=video_id)
    future.get(timeout=timeout_sec)

    logger.info(f"[publisher] id={video_id} path={path} -> {Topics.VIDEO_IN}")
    return {
        "id": video_id,
        "topic": Topics.VIDEO_IN,
        "path": path,
        "name": name,
        "options": options or {},
        "output_file": record_writer.output_path(name or path, video_id),
    }
