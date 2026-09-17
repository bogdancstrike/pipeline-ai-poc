"""
Application entry point — starts the Kafka ETL (7 workers) and the HTTP API
in a single process, using the QF framework's one-call bootstrap.

  - ETL runs in a background thread (consumes the pipeline topics).
  - Flask dev server blocks the main thread and serves the pipeline API.

The five AI services are NOT started here and are not part of docker-compose —
they run on their own host (172.17.12.80:8821-8825 by default). Set
MOCK_WORKER_<NAME>=True in .env to run the whole pipeline without them.

Env vars of interest (see .env / src/config.py for the full list):
  KAFKA_BOOTSTRAP_SERVERS, REDIS_HOST, API_PORT, AI_*_URL, MOCK_WORKER_*,
  PROMPTS_DIR (the summary prompts W6 posts to :8825)
"""

import sys
from pathlib import Path

# ---- Path setup ----
# The framework ETL does `from config import Config`, so src/ (which holds
# config.py, workers/, ai_client.py, mock/, publisher.py) must be importable as
# top-level names.
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "src"))

# Load .env before importing config, so Config picks up the values.
from dotenv import load_dotenv  # noqa: E402
load_dotenv(BASE_DIR / ".env")

from config import Config  # noqa: E402
from framework.app import FrameworkApp, FrameworkSettings  # noqa: E402
from framework.commons.logger import logger  # noqa: E402


def _log_wiring():
    """One boot line per AI service, saying where it points and whether it is mocked."""
    services = {
        "face-match-main": (Config.AI_FACE_MATCH_URL + "/match", Config.MOCK_WORKER_FACE_MATCH),
        "video-describe-354b": (Config.AI_DESCRIBE_URL + "/describe", Config.MOCK_WORKER_DESCRIBE),
        "video-ocr": (Config.AI_OCR_URL + "/ocr", Config.MOCK_WORKER_OCR),
        "transcribe": (Config.AI_TRANSCRIBE_URL + "/transcribe", Config.MOCK_WORKER_TRANSCRIBE),
        "summarize:summary": (Config.AI_SUMMARIZE_URL + "/summarize", Config.MOCK_WORKER_SUMMARY),
        "summarize:entities": (Config.AI_SUMMARIZE_URL + "/summarize", Config.MOCK_WORKER_ENTITIES),
        "summarize:sentiment": (Config.AI_SUMMARIZE_URL + "/summarize", Config.MOCK_WORKER_SENTIMENT),
    }
    for name, (url, mocked) in services.items():
        logger.info(f"[ai] {name:<20} {'MOCKED' if mocked else url}")

    # :8825 takes the prompt TEXT in the request body, so the three prompt
    # files are ours to ship. Read them now: a missing one is a boot error,
    # not a surprise on the first video.
    import prompts  # noqa: PLC0415 — src/ is only on sys.path from here down

    try:
        prompts.preload()
    except prompts.PromptError as exc:
        logger.error(f"[prompts] {exc}")
        raise


def main():
    logger.info(
        f"[pipeline] starting — kafka={Config.KAFKA_BOOTSTRAP_SERVERS} "
        f"redis={Config.REDIS_HOST}:{Config.REDIS_PORT} "
        f"api_port={Config.API_PORT} output_format={Config.OUTPUT_FORMAT}"
    )
    _log_wiring()

    settings = FrameworkSettings(
        enable_etl=True,
        enable_api=True,
        enable_dynamic_endpoints=True,

        api_host=Config.API_HOST,
        api_port=Config.API_PORT,
        api_version="1.0",
        api_title="Video Analysis Pipeline API",
        api_description=(
            "One video path -> face match / description / transcript / OCR -> "
            "aggregate + prompt the summary service -> aggregated record"
        ),

        endpoint_json_path="maps/endpoint.json",

        # ETL: scan this module for @kafka_handler / @kafka_aggregator workers.
        worker_modules=["workers.pipeline"],
        kafka_bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS,
        consumer_name=Config.WORKER_NAME,

        # Tracing off by default for the PoC.
        enable_tracing=False,
        service_name=Config.WORKER_NAME,
    )

    fw = FrameworkApp(settings, app_root=BASE_DIR)
    handles = fw.run()

    if handles.app:
        logger.info(f"[pipeline] API listening on {Config.API_HOST}:{Config.API_PORT}")
        handles.app.run(host=Config.API_HOST, port=Config.API_PORT, debug=False)


if __name__ == "__main__":
    main()
