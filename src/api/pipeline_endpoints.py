"""
The pipeline endpoints — submit a video and let the seven workers run.

  POST /pipeline/analyze  — publish one video path to `video.in`; W1 picks it
                            up and the pipeline runs asynchronously
  GET  /pipeline/health   — Kafka reachability + which workers are mocked
  GET  /pipeline/config   — the resolved AI endpoints, prompts and mock flags

There is no "get result" endpoint: the pipeline's output is the console (W7
prints the aggregated record) and a JSON file whose path the submit response
already tells you (`output_file`).

To run a single worker instead — synchronously, with the answer in the HTTP
response and nothing published to Kafka — see `worker_endpoints.py`.
"""

import socket

from config import Config, Topics
from framework.commons.logger import logger
import ai_client
import prompts
import publisher
import utils

from . import json_body

# Only these are forwarded to the transcribe service; anything else in
# `options` is ignored rather than silently changing the request shape.
_TRANSCRIBE_OPTION_KEYS = (
    "language", "task", "format", "transcription_level", "dialog_timestamps",
)


def pipeline_analyze(app, operation, request, **kwargs):
    """POST /pipeline/analyze — submit one video and start the pipeline.

    Body:
        {"path": "/video/1.mp4"}                       ← the Swagger default
        {"id": "vid-demo-1", "path": "/video/1.mp4"}   named run
        {"path": "...", "options": {"language": "ro", "task": "transcribe"}}

    `path` is the path the **AI services** will open. They run on their own host
    (172.17.12.80 by default, not in docker-compose), so the path is normally
    theirs, not this container's — it is forwarded untouched. When the same file
    is also mounted here (`./videos` → `/app/videos`) it is resolved locally
    first so a typo is a 400 now instead of a failed call two workers later; set
    `VIDEO_PATH_PASSTHROUGH=false` to make that check mandatory.

    `id` is optional and becomes the message id every branch is regrouped by.
    Left out — which is what the UI does — it is **the video's file name**
    (`1abe85d1-….mp4`), so the log lines, the record, the JSON file and the
    database row all name the same thing. Re-submitting a file therefore
    replaces its record; pass an explicit `id` to keep both.
    """
    payload = json_body()

    path = payload.get("path") or payload.get("file") or payload.get("uri")
    if not path or not str(path).strip():
        return {"error": '"path" is required — e.g. {"path": "/video/1.mp4"}'}, 400

    try:
        path = utils.resolve_video_path(str(path))
    except (FileNotFoundError, ValueError) as exc:
        logger.error(f"[api] {exc}")
        return {
            "error": str(exc),
            "search_dirs": Config.VIDEO_SEARCH_DIRS,
            "hint": "set VIDEO_PATH_PASSTHROUGH=true to forward unknown paths to the AI services",
        }, 400

    raw_options = payload.get("options") or {}
    if not isinstance(raw_options, dict):
        return {"error": '"options" must be an object'}, 400
    options = {k: v for k, v in raw_options.items() if k in _TRANSCRIBE_OPTION_KEYS and v is not None}

    try:
        result = publisher.publish_video(
            path=path,
            video_id=payload.get("id") or None,
            name=payload.get("name") or utils.video_name(path),
            options=options,
        )
    except Exception as exc:  # noqa: BLE001 — brokers unavailable, serialisation, ...
        logger.error(f"[api] publish failed: {exc}")
        return {"error": f"failed to publish video: {exc}"}, 502

    return {
        **result,
        "status": "submitted",
        "transcribe_params": ai_client.transcribe_params(options),
        "mocked_workers": [name for name, on in Config.mock_flags().items() if on],
    }, 202


def pipeline_health(app, operation, request, **kwargs):
    """GET /pipeline/health — can we reach Kafka, and what is mocked?"""
    reachable = []
    for server in Config.KAFKA_BOOTSTRAP_SERVERS.split(","):
        host, _, port = server.strip().partition(":")
        try:
            with socket.create_connection((host, int(port or 9092)), timeout=2):
                reachable.append(server.strip())
        except OSError:
            pass

    ok = bool(reachable)
    flags = Config.mock_flags()
    return {
        "status": "ok" if ok else "degraded",
        "kafka": reachable or Config.KAFKA_BOOTSTRAP_SERVERS,
        "input_topic": Topics.VIDEO_IN,
        "workers_mocked": [name for name, on in flags.items() if on],
        "workers_live": [name for name, on in flags.items() if not on],
    }, (200 if ok else 503)


def _prompts_config() -> dict:
    """Which prompt file each call sends, and whether it can actually be read.

    The prompt text travels in the request body now, so a missing file is a
    pipeline problem, not an AI-host one — say so here rather than at the first
    video.
    """
    entry = {}
    for kind, name in (
        ("summary", Config.SUMMARY_PROMPT),
        ("entities", Config.ENTITIES_PROMPT),
        ("sentiment", Config.SENTIMENT_PROMPT),
    ):
        try:
            entry[kind] = {"file": name, "chars": len(prompts.load(name)), "loaded": True}
        except prompts.PromptError as exc:
            entry[kind] = {"file": name, "loaded": False, "error": str(exc)}
    return {"dir": Config.PROMPTS_DIR, **entry}


def pipeline_config(app, operation, request, **kwargs):
    """GET /pipeline/config — the resolved wiring, without restarting to read logs."""
    return {
        "ai_services": {
            "face-match-main": f"{Config.AI_FACE_MATCH_URL}/match",
            "video-describe-354b": f"{Config.AI_DESCRIBE_URL}/describe",
            "video-ocr": f"{Config.AI_OCR_URL}/ocr",
            "transcribe": f"{Config.AI_TRANSCRIBE_URL}/transcribe",
            "summarize": f"{Config.AI_SUMMARIZE_URL}/summarize",
        },
        "mocked": Config.mock_flags(),
        "prompts": _prompts_config(),
        "summarize_inputs": {
            "description_key": Config.SUMMARIZE_KEY_DESCRIPTION,
            "transcript_key": Config.SUMMARIZE_KEY_TRANSCRIPT,
            # Face matching bypasses W6, so the persons are not a section here.
            "sections": [Config.SECTION_DESCRIPTION, Config.SECTION_OCR],
        },
        "transcribe_defaults": ai_client.transcribe_params(),
        "output": {
            "dir": Config.OUTPUT_DIR,
            "suffix": Config.OUTPUT_FILE_SUFFIX,
            "write_file": Config.OUTPUT_WRITE_FILE,
            "format": Config.OUTPUT_FORMAT,
        },
        "topics": {
            name: value for name, value in vars(Topics).items() if not name.startswith("_")
        },
    }, 200
