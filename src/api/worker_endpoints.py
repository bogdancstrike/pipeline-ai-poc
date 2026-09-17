"""
The worker endpoints — run ONE worker on demand, without Kafka.

  GET  /workers/list           every registered worker and how to call it
  POST /workers/{worker}/run   run that worker here and now

`POST /pipeline/analyze` publishes to `video.in` and returns immediately: the
seven workers then run across Kafka topics and you read the result from the
console or the record file. These two endpoints are the other way round — the
worker body runs inside the HTTP request and its return value **is** the
response. Nothing is produced to Kafka, nothing is buffered in Redis, and no
downstream worker is triggered.

`workers/registry.py` explains why that is possible and how the input message
is built. The short version:

    POST /workers/video-ocr/run  {"path": "/video/1.mp4"}
        -> runs W1 (to build the message W5's topic would carry), then W5
        -> responds with what W5 returned

    POST /workers/video-ocr/run  {"chain": false, "message": {...}}
        -> runs W5 alone, on the message you supplied

A worker whose `MOCK_WORKER_*` flag is on answers with its canned body here
exactly as it does in the pipeline — which is what makes this usable with the
AI services offline.
"""

import uuid

from config import Config
from framework.commons.logger import logger
import ai_client
import utils
from workers import registry

from . import json_body


def workers_list(app, operation, request, **kwargs):
    """GET /workers/list — every worker, its topics, and how to call it."""
    return {
        "workers": registry.catalog(),
        "run": "POST /workers/{worker}/run",
        "note": "a direct run publishes nothing to Kafka — the answer is the HTTP response",
    }, 200


def worker_run(app, operation, request, worker=None, **kwargs):
    """POST /workers/{worker}/run — run one worker and return what it produced.

    Body (every field optional but one of `path` / `message` is required):

        {"path": "/video/1.mp4"}                    run the worker on this video
        {"path": "...", "id": "try-1"}              name the run (appears in the logs)
        {"path": "...", "options": {"language": "ro"}}   transcribe overrides
        {"chain": false, "message": {...}}          feed the worker a message verbatim
        {"path": "...", "persist": true}            let W7 write its record file

    `chain` (default true) runs the upstream workers first, so the worker
    receives the message its own topic would have carried — calling
    `aggregator` therefore runs the whole pipeline synchronously and answers
    with the finished record. `persist` (default false) is what keeps a trial
    run from overwriting `output/<video>_analysis.json`.
    """
    payload = json_body()

    message = payload.get("message")
    if message is not None and not isinstance(message, dict):
        return {"error": '"message" must be an object'}, 400

    options = payload.get("options") or {}
    if not isinstance(options, dict):
        return {"error": '"options" must be an object'}, 400

    run_id = str(payload.get("id") or f"api-{uuid.uuid4().hex[:8]}")

    if message:
        # An explicit message is used as-is; chaining would overwrite it.
        seed = {"id": run_id, **message}
        chain = False
    else:
        path = payload.get("path")
        if not path or not str(path).strip():
            return {
                "error": 'give a "path" to run on, or a "message" to feed the worker verbatim',
                "example": {"path": "/video/migrants.mp4"},
            }, 400
        try:
            path = utils.resolve_video_path(str(path))
        except (FileNotFoundError, ValueError) as exc:
            logger.error(f"[api] {exc}")
            return {"error": str(exc), "search_dirs": Config.VIDEO_SEARCH_DIRS}, 400

        seed = {
            "id": run_id,
            "path": path,
            "name": payload.get("name") or utils.video_name(path),
            "options": options,
            "submitted_at": utils.now_iso(),
        }
        chain = payload.get("chain", True) is not False

    logger.info(f"[api] id={run_id} running worker {worker!r} directly (chain={chain})")

    try:
        return registry.run(
            worker,
            seed,
            chain=chain,
            persist=bool(payload.get("persist")),
        ), 200
    except registry.UnknownWorker as exc:
        return {
            "error": str(exc),
            "hint": "GET /workers/list for the registered names",
        }, 404
    except ai_client.AIServiceError as exc:
        # Only reachable with AI_FAIL_FAST=true; otherwise the failure is
        # recorded on the branch and the worker returns normally.
        logger.error(f"[api] id={run_id} worker {worker!r} failed: {exc}")
        return {"error": str(exc), "worker": worker}, 502
    except Exception as exc:  # noqa: BLE001 — a bad hand-written `message`, mostly
        logger.exception(f"[api] id={run_id} worker {worker!r} raised")
        return {"error": f"{type(exc).__name__}: {exc}", "worker": worker}, 500
