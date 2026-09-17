"""
Central configuration for the video analysis pipeline.

Loaded by the QF framework at two points:
  - framework.etl.framework_etl does `from config import Config` at import time,
    so this module MUST be importable as the top-level name `config`
    (main.py inserts src/ onto sys.path to make that work).
  - framework.api.server does `app.config.from_object('config.Config')`.

Every value has an env-var override so the same code runs unchanged on a laptop
(docker-compose) or in a cluster. See `.env` for the shipped values.
"""

import os

from framework.commons.logger import logger

# Project root (src/..) — used to locate the bundled sample videos.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _flag(name: str, default: str = "false") -> bool:
    """Read a boolean env var. Accepts True/true/1/yes/on."""
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


class Config:
    # ------------------------------------------------------------------ Kafka
    WORKER_NAME = os.getenv("WORKER_NAME", "video-pipeline")
    KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9094")
    ERROR_TOPIC = os.getenv("ERROR_TOPIC", "video.dlq")

    # An OCR response carries one text block per sampled frame and a transcript
    # can be long, so branch messages are well above Kafka's 1 MB default.
    # The broker is configured to match in docker-compose.yml.
    KAFKA_MAX_MESSAGE_BYTES = int(os.getenv("KAFKA_MAX_MESSAGE_BYTES", str(20 * 1024 * 1024)))

    # Offset commit semantics: before | after_success
    KAFKA_COMMIT_STRATEGY = os.getenv("KAFKA_COMMIT_STRATEGY", "before")

    # ETL loop tuning — low-latency defaults suitable for an interactive PoC.
    KAFKA_POLL_TIMEOUT_MS = int(os.getenv("KAFKA_POLL_TIMEOUT_MS", "50"))
    KAFKA_POLL_MAX_RECORDS = int(os.getenv("KAFKA_POLL_MAX_RECORDS", "200"))
    KAFKA_IDLE_SLEEP_SEC = float(os.getenv("KAFKA_IDLE_SLEEP_SEC", "0.01"))
    KAFKA_COMMIT_TICK_SEC = float(os.getenv("KAFKA_COMMIT_TICK_SEC", "0.2"))
    KAFKA_PENDING_MAX_PER_TP = int(os.getenv("KAFKA_PENDING_MAX_PER_TP", "500"))
    KAFKA_MAX_JOBS_PER_TP_PER_TICK = int(os.getenv("KAFKA_MAX_JOBS_PER_TP_PER_TICK", "100"))

    # ------------------------------------------------------------------ Redis
    # Used by the framework aggregators (W6 and W7) to buffer partial results.
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = os.getenv("REDIS_PORT", "6379")
    REDIS_DB = os.getenv("REDIS_DB", "0")
    REDIS_MAX_CONNECTIONS = os.getenv("REDIS_MAX_CONNECTIONS", "50")
    REDIS_SOCKET_TIMEOUT = os.getenv("REDIS_SOCKET_TIMEOUT", "5.0")
    REDIS_CONNECT_TIMEOUT = os.getenv("REDIS_CONNECT_TIMEOUT", "5.0")
    REDIS_RETRY_ON_TIMEOUT = os.getenv("REDIS_RETRY_ON_TIMEOUT", "true")

    # How long a half-analysed video may wait in Redis for its other branches.
    # Transcription of a long video can take minutes, so this is generous.
    AGGREGATOR_TIMEOUT_SEC = int(os.getenv("AGGREGATOR_TIMEOUT_SEC", "3600"))

    # =========================================================== AI SERVICES ==
    # Every worker that talks to a model calls exactly one of these. The URLs
    # are full origins — the path (/match, /describe, ...) is appended by
    # src/ai_client.py, so a service can be moved to another host or port
    # without touching any code.
    AI_FACE_MATCH_URL = os.getenv("AI_FACE_MATCH_URL", "http://172.17.12.80:8821")
    AI_DESCRIBE_URL = os.getenv("AI_DESCRIBE_URL", "http://172.17.12.80:8822")
    AI_OCR_URL = os.getenv("AI_OCR_URL", "http://172.17.12.80:8823")
    AI_TRANSCRIBE_URL = os.getenv("AI_TRANSCRIBE_URL", "http://172.17.12.80:8824")
    AI_SUMMARIZE_URL = os.getenv("AI_SUMMARIZE_URL", "http://172.17.12.80:8825")

    # A cold model plus a long video easily runs into minutes.
    AI_TIMEOUT_SEC = float(os.getenv("AI_TIMEOUT_SEC", "600"))
    # Transport-level retries (connection reset / 5xx), not model retries.
    AI_RETRIES = int(os.getenv("AI_RETRIES", "2"))
    AI_RETRY_BACKOFF_SEC = float(os.getenv("AI_RETRY_BACKOFF_SEC", "2.0"))

    # ---- Call logging ----
    # Every worker logs the request it sends and the response it got back, with
    # the elapsed time. Bodies are truncated to AI_LOG_BODY_CHARS so a 30 kB OCR
    # answer does not flood the log; set AI_LOG_BODIES=False for timings only.
    AI_LOG_BODIES = _flag("AI_LOG_BODIES", "true")
    AI_LOG_BODY_CHARS = int(os.getenv("AI_LOG_BODY_CHARS", "400"))

    # At LOGGING_LEVEL=DEBUG each of those two lines is followed by the COMPLETE
    # body — every input sent to an AI service and every output it returned,
    # untruncated (a summarize request then shows the whole prompt text, an OCR
    # answer every frame). 0 = no limit; set a number of chars to cap them.
    # AI_LOG_BODIES=False silences these too — it means "no payloads, ever".
    AI_LOG_DEBUG_BODY_CHARS = int(os.getenv("AI_LOG_DEBUG_BODY_CHARS", "0"))

    # What an extraction worker does when its service will not answer.
    #
    #   false (default) — record the error on that branch and publish it anyway,
    #                     so the two aggregators still fire and W7 writes a
    #                     record naming what failed. A 4-way fan-in is only as
    #                     available as its slowest branch: without this, ONE
    #                     unreachable service means the video never completes
    #                     and its Redis key just expires.
    #   true            — re-raise, so the framework's retry/DLQ policy owns it
    #                     and no partial record is ever produced.
    AI_FAIL_FAST = _flag("AI_FAIL_FAST")

    # ------------------------------------------------------- Mocked workers --
    # MOCK_WORKER_<NAME>=True makes that worker skip its HTTP call entirely and
    # return the canned answer from src/mock/mock_responses.py instead. The
    # worker code, the message shapes and the topics are identical either way,
    # so a mocked run exercises the whole pipeline without the AI host.
    MOCK_WORKER_FACE_MATCH = _flag("MOCK_WORKER_FACE_MATCH")
    MOCK_WORKER_DESCRIBE = _flag("MOCK_WORKER_DESCRIBE")
    MOCK_WORKER_OCR = _flag("MOCK_WORKER_OCR")
    MOCK_WORKER_TRANSCRIBE = _flag("MOCK_WORKER_TRANSCRIBE")
    MOCK_WORKER_SUMMARY = _flag("MOCK_WORKER_SUMMARY")
    MOCK_WORKER_ENTITIES = _flag("MOCK_WORKER_ENTITIES")
    MOCK_WORKER_SENTIMENT = _flag("MOCK_WORKER_SENTIMENT")

    # Fake per-call latency in ms for a mocked worker — 0 keeps runs instant,
    # a few hundred ms makes the fan-out visible in the logs.
    MOCK_LATENCY_MS = float(os.getenv("MOCK_LATENCY_MS", "0"))

    # -------------------------------------------------- Per-service payloads --
    # transcribe (:8824) — everything the endpoint accepts besides `path`.
    TRANSCRIBE_LANGUAGE = os.getenv("TRANSCRIBE_LANGUAGE", "ar")
    TRANSCRIBE_TASK = os.getenv("TRANSCRIBE_TASK", "translate")
    TRANSCRIBE_FORMAT = os.getenv("TRANSCRIBE_FORMAT", "dialog")
    TRANSCRIBE_LEVEL = os.getenv("TRANSCRIBE_LEVEL", "word")
    TRANSCRIBE_DIALOG_TIMESTAMPS = _flag("TRANSCRIBE_DIALOG_TIMESTAMPS")

    # video-ocr (:8823) — a frame-by-frame `frames` array rides along with
    # `full_text`. It is bulky and nothing downstream reads it, so it is
    # dropped before the message is republished unless this is turned on.
    OCR_KEEP_FRAMES = _flag("OCR_KEEP_FRAMES")

    # summarize (:8825) — W6 calls it three times, once per prompt file.
    #
    # The service takes the prompt TEXT in the request body (`prompt_text`), so
    # these name files under PROMPTS_DIR that `src/prompts/__init__.py` reads
    # and `ai_client.summarize()` posts. The wording lives here, not on the AI
    # host: editing summary.txt and restarting is the whole change.
    PROMPTS_DIR = os.getenv("PROMPTS_DIR", os.path.join(BASE_DIR, "src", "prompts"))
    SUMMARY_PROMPT = os.getenv("SUMMARY_PROMPT", "summary.txt")
    ENTITIES_PROMPT = os.getenv("ENTITIES_PROMPT", "entities.txt")
    SENTIMENT_PROMPT = os.getenv("SENTIMENT_PROMPT", "sentiment.txt")
    SUMMARIZE_NUM_PREDICT = int(os.getenv("SUMMARIZE_NUM_PREDICT", "2048"))

    # The two keys of the `inputs` dict W6 posts to :8825 — the exact shape the
    # service documents. What the eye can see in the video (the description and
    # the on-screen text) is folded into ONE string under
    # SUMMARIZE_KEY_DESCRIPTION, as titled sections:
    #
    #     VIDEO DESCRIPTION
    #     <what :8822 described>
    #
    #     ON SCREEN TEXT
    #     <what :8823 read off the frames>
    #
    # What the ear hears stays separate, under SUMMARIZE_KEY_TRANSCRIPT.
    #
    # The identified persons are deliberately NOT here: face matching is a
    # branch of its own that goes straight to the final record (W2 -> W7), so
    # the summary prompts never see it. See Topics below.
    SUMMARIZE_KEY_DESCRIPTION = os.getenv("SUMMARIZE_KEY_DESCRIPTION", "video_description")
    SUMMARIZE_KEY_TRANSCRIPT = os.getenv("SUMMARIZE_KEY_TRANSCRIPT", "transcription")

    SECTION_DESCRIPTION = os.getenv("SECTION_DESCRIPTION", "VIDEO DESCRIPTION")
    SECTION_OCR = os.getenv("SECTION_OCR", "ON SCREEN TEXT")
    # Printed under a heading whose worker returned nothing. Set empty to drop
    # the section entirely instead.
    SECTION_EMPTY_PLACEHOLDER = os.getenv("SECTION_EMPTY_PLACEHOLDER", "(none)")

    # ------------------------------------------------------------ Video input
    # A submitted path (`{"path": "/video/1.mp4"}`) is forwarded to the AI
    # services untouched — they resolve it on their own filesystem. When the
    # same file is also mounted here it is resolved locally first, purely so an
    # obvious typo is a 400 at submit time instead of a failed HTTP call later.
    VIDEO_SEARCH_DIRS = [
        d for d in os.getenv(
            "VIDEO_SEARCH_DIRS",
            os.pathsep.join([os.path.join(BASE_DIR, "videos"), os.path.join(BASE_DIR, "data")]),
        ).split(os.pathsep) if d
    ]
    # false = reject a path that cannot be found in VIDEO_SEARCH_DIRS.
    # true (default) = accept it and let the AI services resolve it.
    VIDEO_PATH_PASSTHROUGH = _flag("VIDEO_PATH_PASSTHROUGH", "true")

    # ---------------------------------------------------------- Console output
    # W7 prints the aggregated record for every video.
    # block = human-readable paragraph | line = one compact line | json = the raw record
    OUTPUT_FORMAT = os.getenv("OUTPUT_FORMAT", "block").strip().lower()
    OUTPUT_TEXT_PREVIEW_CHARS = int(os.getenv("OUTPUT_TEXT_PREVIEW_CHARS", "400"))

    # ------------------------------------------------------------- File output
    # W7 also writes the aggregated record as JSON:
    #   <OUTPUT_DIR>/<video file name without extension><OUTPUT_FILE_SUFFIX>
    #   /video/migrants.mp4  ->  output/migrants_analysis.json
    OUTPUT_DIR = os.getenv("OUTPUT_DIR", os.path.join(BASE_DIR, "output"))
    OUTPUT_FILE_SUFFIX = os.getenv("OUTPUT_FILE_SUFFIX", "_analysis.json")
    OUTPUT_WRITE_FILE = _flag("OUTPUT_WRITE_FILE", "true")
    OUTPUT_JSON_INDENT = int(os.getenv("OUTPUT_JSON_INDENT", "2"))
    # Also store every AI service's COMPLETE response body under `raw`, so the
    # file is the full record of the run and not just the fields the pipeline
    # happens to read. The OCR frame array follows OCR_KEEP_FRAMES.
    OUTPUT_INCLUDE_RAW = _flag("OUTPUT_INCLUDE_RAW", "true")

    # ------------------------------------------------------------------- API
    API_HOST = os.getenv("API_HOST", "0.0.0.0")
    API_PORT = int(os.getenv("API_PORT", "5000"))

    SECRET_KEY = os.getenv("SECRET_KEY", "video-pipeline-secret")

    logger.setLevel(os.getenv("LOGGING_LEVEL", "INFO"))

    # ------------------------------------------------------------- Introspection
    @classmethod
    def mock_flags(cls) -> dict:
        """{worker name: is mocked} — logged at boot and served on /pipeline/health."""
        return {
            "face-match-main": cls.MOCK_WORKER_FACE_MATCH,
            "video-describe-354b": cls.MOCK_WORKER_DESCRIBE,
            "video-ocr": cls.MOCK_WORKER_OCR,
            "transcribe": cls.MOCK_WORKER_TRANSCRIBE,
            "summary": cls.MOCK_WORKER_SUMMARY,
            "entities": cls.MOCK_WORKER_ENTITIES,
            "sentiment": cls.MOCK_WORKER_SENTIMENT,
        }


# ---------------------------------------------------------------------------
# Topic names — single source of truth shared by workers, API and tests.
#
#   video.in ─W1─┬─> video.face.in ──────W2───> video.agg.face ───────────┐
#                ├─> video.describe.in ──W3───> video.merge.describe ──┐  │
#                ├─> video.transcribe.in W4───> video.merge.transcribe─┤  │
#                └─> video.ocr.in ───────W5───> video.merge.ocr ───────┤  │
#                                                                      ▼  │
#                              W6  aggregate 3 branches + call :8825 ×3   │
#                                        └─> video.agg.ai ────────────┐   │
#                                                                     ▼   ▼
#                                        W7  aggregate 2 ──────> video.done
#
# Face matching is a branch of its own: W2 publishes ONLY to `video.agg.face`,
# which the final aggregator consumes. The identified persons therefore reach
# the record as structured data and never enter the summary payload — W6
# aggregates the three *content* branches (description, transcript, OCR).
# ---------------------------------------------------------------------------
class Topics:
    VIDEO_IN = "video.in"                       # W1 in — the submitted video path lands here

    FACE_IN = "video.face.in"                   # W1 -> W2
    DESCRIBE_IN = "video.describe.in"           # W1 -> W3
    TRANSCRIBE_IN = "video.transcribe.in"       # W1 -> W4
    OCR_IN = "video.ocr.in"                     # W1 -> W5

    AGG_FACE = "video.agg.face"                 # W2 -> W7  (skips W6 entirely)
    MERGE_DESCRIBE = "video.merge.describe"     # W3 -> W6
    MERGE_TRANSCRIBE = "video.merge.transcribe" # W4 -> W6
    MERGE_OCR = "video.merge.ocr"               # W5 -> W6

    AGG_AI = "video.agg.ai"                     # W6 -> W7
    DONE = "video.done"                         # W7 -> terminal per-video event
