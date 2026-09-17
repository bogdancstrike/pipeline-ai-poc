"""
The only module that talks to the AI services.

Five services, one function each. Every function:

  1. checks its `MOCK_WORKER_<NAME>` flag — when set, returns the canned body
     from `src/mock/mock_responses.py` and never opens a socket;
  2. otherwise POSTs the documented JSON body and returns the parsed response;
  3. logs the request and the response, with the elapsed time (see below);
  4. wraps the answer in `{"data": <body>, "meta": {...}}` so a worker always
     learns how the answer was produced (mocked or live, which URL, how long).

The AI services are NOT part of docker-compose — they run on their own host
(default `172.17.12.80`, ports 8821-8825, see `.env`). That is the whole reason
the mock switches exist: the pipeline, Kafka and Redis come up and run a video
end to end with no access to that host.

Logging
-------
Every call produces two INFO lines, so a `docker compose logs -f app` shows
exactly what each worker asked for and what came back::

    [ai] id=vid-1 face-match-main      --> POST http://172.17.12.80:8821/match {"path": "/video/1.mp4"}
    [ai] id=vid-1 face-match-main      <-- 200 in 1843.2ms {"message": "The following persons...", "persons": ["222"]}

Bodies are truncated to `AI_LOG_BODY_CHARS`; `AI_LOG_BODIES=False` keeps the
timings and drops the payloads. A failure logs the same shape with the error.

With `LOGGING_LEVEL=DEBUG` each of those lines is followed by the COMPLETE body
— every input sent to an AI service and every output it returned, uncut::

    [ai] id=vid-1 summarize:summary    --> POST http://172.17.12.80:8825/summarize {"inputs": {...}, "prompt_text": "<summary.txt, 1362 chars>", ...}
    [ai] id=vid-1 summarize:summary    REQUEST  POST http://172.17.12.80:8825/summarize {"inputs": {...}, "prompt_text": "# OBJECTIVES\nYou are an OSINT analyst...", "options": {...}}
    [ai] id=vid-1 summarize:summary    <-- 200 in 7307.0ms {"output": "The source is a video featuring people...", "metadata": {...}}
    [ai] id=vid-1 summarize:summary    RESPONSE 200 in 7307.0ms {"output": "The source is a video featuring people walking on the streets...", "metadata": {...}}

The INFO line is the readable trace (truncated, and a prompt shows by name);
the DEBUG line is the wire body, so a prompt, a transcript or every OCR frame
can be read back in full. `AI_LOG_DEBUG_BODY_CHARS` caps them (0 = uncut), and
mocked calls log both halves the same way. DEBUG also logs one line per HTTP
attempt, which is where a retry becomes visible.

Errors are raised as `AIServiceError`. The *workers* decide what to do with one
(see `_call` in workers/pipeline.py) — by default they record it on the branch
so the aggregation still completes.
"""

import json
import logging
import time
from typing import Any, Dict, Optional

import requests

import prompts
from config import Config
from framework.commons.logger import logger
from mock import mock_responses


class AIServiceError(RuntimeError):
    """A service was unreachable, timed out, or answered with a non-2xx."""


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _render(value: Any, limit: int) -> str:
    """`value` as one line of JSON, cut to `limit` chars (0 = no limit)."""
    try:
        text = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        text = repr(value)
    if limit and len(text) > limit:
        return f"{text[:limit]}… (+{len(text) - limit} chars)"
    return text


def _body(value: Any) -> str:
    """A log-safe rendering of a request or response body, for the INFO line."""
    if not Config.AI_LOG_BODIES:
        return ""
    return _render(value, Config.AI_LOG_BODY_CHARS)


def _tag(video_id: Optional[str], service: str) -> str:
    return f"[ai] id={video_id or '-'} {service:<20}"


def _log_full(video_id: Optional[str], service: str, direction: str, context: str, body: Any) -> None:
    """DEBUG: the COMPLETE body of one AI request or response.

    The INFO lines above are a readable trace — truncated, and a summarize
    request shows its prompt by name. These are the whole thing: every field of
    every request to an AI service and every field of its answer, uncut unless
    AI_LOG_DEBUG_BODY_CHARS says otherwise. `LOGGING_LEVEL=DEBUG` turns them on.
    """
    if not logger.isEnabledFor(logging.DEBUG) or not Config.AI_LOG_BODIES:
        return
    rendered = _render(body, Config.AI_LOG_DEBUG_BODY_CHARS)
    logger.debug(f"{_tag(video_id, service)} {direction:<8} {context} {rendered}".rstrip())


def _log_request(
    video_id: Optional[str],
    service: str,
    target: str,
    payload: Dict[str, Any],
    full_payload: Optional[Dict[str, Any]] = None,
) -> None:
    logger.info(f"{_tag(video_id, service)} --> {target} {_body(payload)}".rstrip())
    _log_full(video_id, service, "REQUEST", target,
              payload if full_payload is None else full_payload)


def _log_response(
    video_id: Optional[str], service: str, status: str, elapsed_ms: float, body: Any
) -> None:
    logger.info(f"{_tag(video_id, service)} <-- {status} in {elapsed_ms}ms {_body(body)}".rstrip())
    _log_full(video_id, service, "RESPONSE", f"{status} in {elapsed_ms}ms", body)


def _log_failure(video_id: Optional[str], service: str, elapsed_ms: float, error: Any) -> None:
    logger.error(f"{_tag(video_id, service)} <-- FAILED after {elapsed_ms}ms: {error}")


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------

def _mock_latency() -> None:
    """Pretend the remote call took a moment (0 ms by default)."""
    if Config.MOCK_LATENCY_MS > 0:
        time.sleep(Config.MOCK_LATENCY_MS / 1000.0)


def _post(service: str, base_url: str, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """POST `payload` to `base_url + path`, with transport-level retries.

    Retries cover connection errors and 5xx — a model that is still loading, a
    reset connection, a restarted container. A 4xx is a bad request on our side
    and fails immediately.
    """
    url = f"{base_url.rstrip('/')}{path}"
    attempts = max(1, Config.AI_RETRIES + 1)
    last_error: Optional[Exception] = None

    for attempt in range(1, attempts + 1):
        logger.debug(
            f"[ai] {service} POST {url} attempt {attempt}/{attempts} "
            f"timeout={Config.AI_TIMEOUT_SEC}s"
        )
        try:
            response = requests.post(
                url,
                json=payload,
                headers={"content-type": "application/json"},
                timeout=Config.AI_TIMEOUT_SEC,
            )
        except requests.RequestException as exc:
            last_error = exc
            logger.warning(f"[ai] {service} {url} attempt {attempt}/{attempts} failed: {exc}")
        else:
            logger.debug(
                f"[ai] {service} {url} attempt {attempt}/{attempts} -> HTTP "
                f"{response.status_code} ({len(response.content)} bytes)"
            )
            if response.status_code < 400:
                try:
                    return response.json()
                except ValueError as exc:
                    raise AIServiceError(
                        f"{service} at {url} returned {response.status_code} "
                        f"with a non-JSON body: {response.text[:200]!r}"
                    ) from exc

            if response.status_code < 500:
                raise AIServiceError(
                    f"{service} at {url} rejected the request "
                    f"({response.status_code}): {response.text[:200]!r}"
                )

            last_error = AIServiceError(
                f"{service} at {url} returned {response.status_code}: {response.text[:200]!r}"
            )
            logger.warning(f"[ai] {service} attempt {attempt}/{attempts}: {last_error}")

        if attempt < attempts:
            time.sleep(Config.AI_RETRY_BACKOFF_SEC * attempt)

    raise AIServiceError(f"{service} at {url} failed after {attempts} attempt(s): {last_error}")


def _call(
    service: str,
    *,
    video_id: Optional[str],
    mocked: bool,
    base_url: str,
    path: str,
    payload: Dict[str, Any],
    mock_fn,
    log_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run one service call — mocked or live — logging both halves and the time.

    `log_payload` stands in for `payload` in the log line when the real body is
    not worth reading back — a summarize request carries a whole prompt file,
    which would eat the truncation budget and hide the inputs.
    """
    endpoint = f"{base_url.rstrip('/')}{path}"
    target = "MOCK" if mocked else f"POST {endpoint}"

    _log_request(
        video_id,
        service,
        target,
        log_payload if log_payload is not None else payload,
        # DEBUG always gets the body as sent, stand-in or not.
        full_payload=payload,
    )
    started = time.monotonic()

    try:
        if mocked:
            _mock_latency()
            data = mock_fn()
        else:
            data = _post(service, base_url, path, payload)
    except Exception as exc:
        _log_failure(video_id, service, round((time.monotonic() - started) * 1000, 1), exc)
        raise

    elapsed_ms = round((time.monotonic() - started) * 1000, 1)

    if not isinstance(data, dict):
        _log_failure(video_id, service, elapsed_ms, f"expected a JSON object, got {type(data).__name__}")
        raise AIServiceError(f"{service} returned {type(data).__name__}, expected a JSON object")

    _log_response(video_id, service, "MOCK" if mocked else "200", elapsed_ms, data)

    return {
        "data": data,
        "meta": {
            "service": service,
            "mocked": mocked,
            "endpoint": None if mocked else endpoint,
            "duration_ms": elapsed_ms,
        },
    }


# ---------------------------------------------------------------------------
# :8821  face-match-main      POST /match
# ---------------------------------------------------------------------------

def face_match(path: str, video_id: Optional[str] = None) -> Dict[str, Any]:
    """-> {"message": str, "persons": [str, ...]}"""
    return _call(
        "face-match-main",
        video_id=video_id,
        mocked=Config.MOCK_WORKER_FACE_MATCH,
        base_url=Config.AI_FACE_MATCH_URL,
        path="/match",
        payload={"path": path},
        mock_fn=lambda: mock_responses.face_match(path),
    )


# ---------------------------------------------------------------------------
# :8822  video-describe-354b  POST /describe
# ---------------------------------------------------------------------------

def describe(path: str, video_id: Optional[str] = None) -> Dict[str, Any]:
    """-> {"description": str, "metadata": {...}}"""
    return _call(
        "video-describe-354b",
        video_id=video_id,
        mocked=Config.MOCK_WORKER_DESCRIBE,
        base_url=Config.AI_DESCRIBE_URL,
        path="/describe",
        payload={"path": path},
        mock_fn=lambda: mock_responses.describe(path),
    )


# ---------------------------------------------------------------------------
# :8823  video-ocr            POST /ocr
# ---------------------------------------------------------------------------

def ocr(path: str, video_id: Optional[str] = None) -> Dict[str, Any]:
    """-> {"frames": [...], "full_text": str, "metadata": {...}}"""
    return _call(
        "video-ocr",
        video_id=video_id,
        mocked=Config.MOCK_WORKER_OCR,
        base_url=Config.AI_OCR_URL,
        path="/ocr",
        payload={"path": path},
        mock_fn=lambda: mock_responses.ocr(path),
    )


# ---------------------------------------------------------------------------
# :8824  transcribe           POST /transcribe
# ---------------------------------------------------------------------------

def transcribe_params(overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The request body minus `path` — .env defaults, overridable per submit."""
    params = {
        "language": Config.TRANSCRIBE_LANGUAGE,
        "task": Config.TRANSCRIBE_TASK,
        "format": Config.TRANSCRIBE_FORMAT,
        "transcription_level": Config.TRANSCRIBE_LEVEL,
        "dialog_timestamps": Config.TRANSCRIBE_DIALOG_TIMESTAMPS,
    }
    for key, value in (overrides or {}).items():
        if key in params and value is not None:
            params[key] = value
    return params


def transcribe(
    path: str, overrides: Optional[Dict[str, Any]] = None, video_id: Optional[str] = None
) -> Dict[str, Any]:
    """-> {"format": str, "transcription": str, "metadata": {...}}"""
    params = transcribe_params(overrides)
    return _call(
        "transcribe",
        video_id=video_id,
        mocked=Config.MOCK_WORKER_TRANSCRIBE,
        base_url=Config.AI_TRANSCRIBE_URL,
        path="/transcribe",
        payload={"path": path, **params},
        mock_fn=lambda: mock_responses.transcribe(path, **params),
    )


# ---------------------------------------------------------------------------
# :8825  summarize            POST /summarize
# ---------------------------------------------------------------------------
#
# The service does not know the prompt files — the request carries the prompt
# TEXT and the answer comes back under `output`:
#
#   --> {"inputs": {"video_description": "...", "transcription": "..."},
#        "prompt_text": "Summarize the source.",
#        "options": {"num_predict": 2048}}
#   <-- {"output": "The source is a video featuring...",
#        "metadata": {"prompt_hash": "34f899...", "provider": "openai-compatible",
#                     "model": "phi4:14b-q8_0", "generated_at": "...", "options": {...},
#                     "input_tokens": 61, "output_tokens": 48, "duration_seconds": 7.307}}

# Which mock flag guards which prompt — W6 makes all three calls.
_SUMMARIZE_MOCK_FLAGS = {
    "summary": lambda: Config.MOCK_WORKER_SUMMARY,
    "entities": lambda: Config.MOCK_WORKER_ENTITIES,
    "sentiment": lambda: Config.MOCK_WORKER_SENTIMENT,
}


def summarize(
    kind: str, inputs: Dict[str, str], prompt_file: str, video_id: Optional[str] = None
) -> Dict[str, Any]:
    """One prompted call to the summary service.

    `kind` is `summary` | `entities` | `sentiment` — it picks the mock flag and
    labels the call in the logs. `prompt_file` names a file under
    `Config.PROMPTS_DIR` (`summary.txt`, `entities.txt`, `sentiment.txt`); its
    text is read by `src/prompts` and posted as `prompt_text`.

    -> {"output": str, "metadata": {...}}  — the envelope is the same for every
    prompt; the prompt decides what the text inside means.

    A missing or empty prompt file raises `prompts.PromptError`; W6 records it
    on the branch exactly like a dead service (see `utils.call_ai`).
    """
    mocked = _SUMMARIZE_MOCK_FLAGS.get(kind, lambda: False)()
    prompt_text = prompts.load(prompt_file)
    options = {"num_predict": Config.SUMMARIZE_NUM_PREDICT}
    payload = {"inputs": inputs, "prompt_text": prompt_text, "options": options}
    return _call(
        f"summarize:{kind}",
        video_id=video_id,
        mocked=mocked,
        base_url=Config.AI_SUMMARIZE_URL,
        path="/summarize",
        payload=payload,
        mock_fn=lambda: mock_responses.summarize(inputs, prompt_file, prompt_text, options),
        # The prompt is a file on disk, not a per-video value: log which one and
        # how long it is, and keep the truncation budget for the inputs.
        log_payload={
            **payload,
            "prompt_text": f"<{prompt_file}, {len(prompt_text)} chars>",
        },
    )


def summarize_output(data: Dict[str, Any]) -> str:
    """The generated text of a `/summarize` answer — the `output` field."""
    return (data.get("output") or "").strip()
