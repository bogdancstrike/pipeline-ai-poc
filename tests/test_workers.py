"""
Unit tests for the 7 workers — no Kafka, no Redis, no AI host.

Every worker is called directly with the message its topic would carry, and the
two aggregators are fed a deep-merge of their input branches, exactly as the
framework runtime does before invoking them.
"""

import contextlib
import json
import logging

import pytest

from config import Config, Topics
from mock import mock_responses
from workers import pipeline
import utils


# ---------------------------------------------------------------- topology --

def test_every_topic_has_exactly_one_worker():
    """The framework refuses two workers on one topic — assert the wiring holds."""
    from framework.decorators.kafka_workers import all_workers

    workers = {w.name: w for w in all_workers()}
    assert set(workers) == {
        "splitter",
        "face-match-main",
        "video-describe-354b",
        "transcribe",
        "video-ocr",
        "aggregator-ai-caller",
        "aggregator",
    }

    seen = {}
    for worker in workers.values():
        for topic in worker.topics_in:
            assert topic not in seen, f"{topic} consumed by both {seen[topic]} and {worker.name}"
            seen[topic] = worker.name


def test_splitter_fans_out_to_four_extraction_topics():
    spec = next(w for w in _specs() if w.name == "splitter")
    assert spec.topics_out == [
        Topics.FACE_IN, Topics.DESCRIBE_IN, Topics.TRANSCRIBE_IN, Topics.OCR_IN
    ]


def test_face_match_goes_straight_to_the_final_aggregator():
    """Identity is structured data for the record, not prose for the prompts."""
    spec = next(w for w in _specs() if w.name == "face-match-main")
    assert spec.topics_out == [Topics.AGG_FACE]

    ai_caller = next(w for w in _specs() if w.name == "aggregator-ai-caller")
    assert Topics.AGG_FACE not in ai_caller.topics_in


def test_aggregators_group_by_id():
    for name, topics in (
        ("aggregator-ai-caller", 3),
        ("aggregator", 2),
    ):
        spec = next(w for w in _specs() if w.name == name)
        assert spec.kind == "aggregator"
        assert spec.aggregate_by == "id"
        assert len(spec.topics_in) == topics


def _specs():
    from framework.decorators.kafka_workers import all_workers

    return all_workers()


# ------------------------------------------------------------------- W1..W5 --

def test_splitter_normalises_the_message(video_message):
    item = pipeline.worker_split(video_message, "test", {})
    assert item["id"] == "test-video-1"
    assert item["path"] == "/video/migrants.mp4"
    assert item["name"] == "migrants.mp4"
    assert item["options"] == {}
    assert item["submitted_at"] == "2026-09-16T10:00:00+00:00"


def test_splitter_rejects_an_empty_path(video_message):
    with pytest.raises(ValueError):
        pipeline.worker_split({**video_message, "path": "  "}, "test", {})


def test_extraction_workers_return_the_service_payload(branches):
    assert branches["face"]["face"]["persons"] == mock_responses.MOCK_PERSONS
    assert branches["describe"]["describe"]["description"] == mock_responses.MOCK_DESCRIPTION
    assert branches["transcribe"]["transcribe"]["transcription"] == mock_responses.MOCK_TRANSCRIPTION
    assert branches["ocr"]["ocr"]["full_text"] == mock_responses.MOCK_OCR_FULL_TEXT


def test_every_branch_echoes_the_id_so_the_aggregators_can_regroup(branches):
    for key in ("face", "describe", "transcribe", "ocr"):
        assert branches[key]["id"] == "test-video-1"
        assert branches[key]["path"] == "/video/migrants.mp4"


def test_ocr_drops_the_bulky_frame_array_by_default(branches):
    ocr = branches["ocr"]["ocr"]
    assert "frames" not in ocr
    assert ocr["frames_count"] == len(mock_responses.MOCK_OCR_FRAMES)


def test_every_extraction_result_records_that_it_was_mocked(branches):
    for key in ("face", "describe", "transcribe", "ocr"):
        payload = next(v for k, v in branches[key].items() if isinstance(v, dict) and "source" in v)
        assert payload["source"]["mocked"] is True
        assert payload["source"]["endpoint"] is None


# ---------------------------------------------------------------------- W6 --

def test_ai_caller_builds_the_titled_video_description(branches, merge):
    result = pipeline.worker_ai_caller(
        merge([branches["describe"], branches["transcribe"], branches["ocr"]]),
        "test",
        {},
    )

    inputs = result["inputs"]
    assert set(inputs) == {"video_description", "transcription"}

    description = inputs["video_description"]
    # Two sections, in order, each under its heading.
    assert description.index("VIDEO DESCRIPTION") < description.index("ON SCREEN TEXT")
    assert mock_responses.MOCK_DESCRIPTION in description
    assert mock_responses.MOCK_OCR_FULL_TEXT in description

    # The identified persons never reach the summary payload — W2 skips W6.
    assert "PERSONS" not in description
    assert mock_responses.MOCK_PERSONS[0] not in description

    # What is heard stays separate.
    assert inputs["transcription"] == mock_responses.MOCK_TRANSCRIPTION.strip()


def test_ai_caller_makes_one_call_per_prompt(branches, merge):
    result = pipeline.worker_ai_caller(
        merge([branches["describe"], branches["transcribe"], branches["ocr"]]),
        "test",
        {},
    )
    enrichment = result["enrichment"]
    assert enrichment["summary"]["prompt"] == "summary.txt"
    assert enrichment["entities"]["prompt"] == "entities.txt"
    assert enrichment["sentiment"]["prompt"] == "sentiment.txt"
    assert enrichment["summary"]["text"] == mock_responses.MOCK_SUMMARIES["summary.txt"]
    assert enrichment["sentiment"]["text"] == mock_responses.MOCK_SUMMARIES["sentiment.txt"]


def test_ai_caller_parses_the_entities_answer_into_a_list(branches, merge):
    result = pipeline.worker_ai_caller(
        merge([branches["describe"], branches["transcribe"], branches["ocr"]]),
        "test",
        {},
    )
    entities = result["enrichment"]["entities"]
    # entities.txt asks for one `TYPE: value` per line.
    assert entities["list"] == mock_responses.MOCK_SUMMARIES["entities.txt"].splitlines()
    # The raw answer is kept, so a bad parse loses nothing.
    assert entities["text"] == mock_responses.MOCK_SUMMARIES["entities.txt"]


# ---------------------------------------------------------------------- W7 --

def test_final_record_holds_every_worker_result(branches, merge, tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(Config, "OUTPUT_WRITE_FILE", True)

    ai = pipeline.worker_ai_caller(
        merge([branches["describe"], branches["transcribe"], branches["ocr"]]),
        "test",
        {},
    )
    event = pipeline.worker_aggregate(merge([branches["face"], ai]), "test", {})

    assert event["status"] == "analysed"
    assert event["persons"] == 1
    assert event["entities"] == 5
    assert event["sentiment"] == "NEGATIVE"

    written = tmp_path / "migrants_analysis.json"
    assert event["output_file"] == str(written)
    record = json.loads(written.read_text(encoding="utf-8"))

    # Every AI answer lives under `enrichment`, one entry per call.
    enrichment = record["enrichment"]
    assert set(enrichment) == {
        "face_match", "description", "transcript", "ocr",
        "summary", "entities", "sentiment",
    }

    # W2 + W3 + W4 + W5 results.
    assert enrichment["face_match"]["persons"] == mock_responses.MOCK_PERSONS
    assert enrichment["description"]["text"] == mock_responses.MOCK_DESCRIPTION
    assert enrichment["ocr"]["text"] == mock_responses.MOCK_OCR_FULL_TEXT
    assert enrichment["transcript"]["text"] == mock_responses.MOCK_TRANSCRIPTION

    # W6 results.
    assert enrichment["summary"]["text"]
    assert enrichment["entities"]["list"]
    assert enrichment["sentiment"]["text"] == "NEGATIVE"

    # Each entry also carries the service's complete response body.
    for entry in enrichment.values():
        assert isinstance(entry["response"], dict) and entry["response"]

    # Only the run's identity, the enrichment and the failures — the payload
    # posted to :8825 and the per-call provenance stay off the record.
    assert set(record) == {
        "id", "name", "path", "submitted_at", "analysed_at", "enrichment", "errors",
    }
    assert record["errors"] == {}


def test_raw_bodies_can_be_left_out(branches, merge, tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(Config, "OUTPUT_INCLUDE_RAW", False)

    ai = pipeline.worker_ai_caller(
        merge([branches["describe"], branches["transcribe"], branches["ocr"]]),
        "test",
        {},
    )
    pipeline.worker_aggregate(merge([branches["face"], ai]), "test", {})

    record = json.loads((tmp_path / "migrants_analysis.json").read_text(encoding="utf-8"))
    for entry in record["enrichment"].values():
        assert "response" not in entry
    # The parsed values survive.
    assert record["enrichment"]["sentiment"]["text"] == "negative"


def test_a_failing_service_still_produces_a_record(branches, merge, tmp_path, monkeypatch):
    """One dead branch must not strand the video in Redis (AI_FAIL_FAST=false)."""
    import ai_client

    monkeypatch.setattr(Config, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(Config, "AI_FAIL_FAST", False)

    def boom(*args, **kwargs):
        raise ai_client.AIServiceError("face-match-main at :8821 rejected the request (400)")

    monkeypatch.setattr(ai_client, "face_match", boom)
    face = pipeline.worker_face_match(branches["item"], "test", {})
    assert face["face"]["persons"] == []
    assert face["face"]["source"]["error"]

    # W6 never sees the face branch, so its payload is unaffected by the failure.
    ai = pipeline.worker_ai_caller(
        merge([branches["describe"], branches["transcribe"], branches["ocr"]]),
        "test",
        {},
    )

    event = pipeline.worker_aggregate(merge([face, ai]), "test", {})
    assert event["failed_services"] == ["face-match-main"]

    record = json.loads((tmp_path / "migrants_analysis.json").read_text(encoding="utf-8"))
    assert "face-match-main" in record["errors"]
    # Everything that did work is still there.
    assert record["enrichment"]["summary"]["text"]


def test_fail_fast_reraises_instead(branches, monkeypatch):
    import ai_client

    monkeypatch.setattr(Config, "AI_FAIL_FAST", True)

    def boom(*args, **kwargs):
        raise ai_client.AIServiceError("unreachable")

    monkeypatch.setattr(ai_client, "face_match", boom)
    with pytest.raises(ai_client.AIServiceError):
        pipeline.worker_face_match(branches["item"], "test", {})


def test_output_file_can_be_turned_off(branches, merge, monkeypatch):
    monkeypatch.setattr(Config, "OUTPUT_WRITE_FILE", False)
    ai = pipeline.worker_ai_caller(
        merge([branches["describe"], branches["transcribe"], branches["ocr"]]),
        "test",
        {},
    )
    event = pipeline.worker_aggregate(merge([branches["face"], ai]), "test", {})
    assert event["output_file"] is None


# ------------------------------------------------------------------- utils --

@pytest.mark.parametrize(
    "answer,expected",
    [
        ('["Ceuta", "Red Cross"]', ["Ceuta", "Red Cross"]),
        ('```json\n["Ceuta", "Morocco"]\n```', ["Ceuta", "Morocco"]),
        ("Ceuta, Red Cross, Morocco", ["Ceuta", "Red Cross", "Morocco"]),
        ("- Ceuta\n- Red Cross", ["Ceuta", "Red Cross"]),
        ("LOCATION: Ceuta\nNAME: John", ["LOCATION: Ceuta", "NAME: John"]),
        ("", []),
    ],
)
def test_parse_entities_handles_what_a_prompted_model_returns(answer, expected):
    assert utils.parse_entities(answer) == expected


def test_a_section_with_no_content_shows_the_placeholder():
    description = utils.build_video_description("a description", "")
    assert "ON SCREEN TEXT\n(none)" in description


def test_an_empty_placeholder_drops_the_section(monkeypatch):
    monkeypatch.setattr(Config, "SECTION_EMPTY_PLACEHOLDER", "")
    description = utils.build_video_description("a description", "")
    assert "ON SCREEN TEXT" not in description
    assert description == "VIDEO DESCRIPTION\na description"


def test_unknown_paths_are_forwarded_to_the_ai_services(monkeypatch):
    monkeypatch.setattr(Config, "VIDEO_PATH_PASSTHROUGH", True)
    assert utils.resolve_video_path("/video/on-the-ai-host.mp4") == "/video/on-the-ai-host.mp4"


def test_unknown_paths_are_rejected_when_passthrough_is_off(monkeypatch):
    monkeypatch.setattr(Config, "VIDEO_PATH_PASSTHROUGH", False)
    with pytest.raises(FileNotFoundError):
        utils.resolve_video_path("/video/nowhere.mp4")


# --------------------------------------------------------------- mocking --

def test_mock_flags_cover_every_ai_call():
    assert set(Config.mock_flags()) == {
        "face-match-main", "video-describe-354b", "video-ocr", "transcribe",
        "summary", "entities", "sentiment",
    }


def test_a_live_worker_would_call_the_documented_endpoint(monkeypatch):
    """With the flag off, the client posts the documented body to the real URL."""
    import ai_client

    seen = {}

    def fake_post(service, base_url, path, payload):
        seen.update(service=service, url=f"{base_url}{path}", payload=payload)
        return {"message": "ok", "persons": []}

    monkeypatch.setattr(Config, "MOCK_WORKER_FACE_MATCH", False)
    monkeypatch.setattr(ai_client, "_post", fake_post)

    ai_client.face_match("/video/1.mp4")
    assert seen["url"] == f"{Config.AI_FACE_MATCH_URL}/match"
    assert seen["payload"] == {"path": "/video/1.mp4"}


def test_a_live_summarize_call_posts_the_prompt_text(monkeypatch):
    """:8825 takes the prompt TEXT, not the file name — and answers `output`."""
    import ai_client
    import prompts

    seen = {}

    def fake_post(service, base_url, path, payload):
        seen.update(service=service, url=f"{base_url}{path}", payload=payload)
        return {"output": "  a summary  ", "metadata": {"model": "phi4:14b-q8_0"}}

    monkeypatch.setattr(Config, "MOCK_WORKER_SUMMARY", False)
    monkeypatch.setattr(ai_client, "_post", fake_post)

    inputs = {"video_description": "people walking", "transcription": "hello"}
    answer = ai_client.summarize("summary", inputs, "summary.txt")

    assert seen["url"] == f"{Config.AI_SUMMARIZE_URL}/summarize"
    assert set(seen["payload"]) == {"inputs", "prompt_text", "options"}
    assert seen["payload"]["inputs"] == inputs
    assert seen["payload"]["prompt_text"] == prompts.load("summary.txt")
    assert seen["payload"]["options"] == {"num_predict": Config.SUMMARIZE_NUM_PREDICT}

    # The worker reads the answer through this one accessor.
    assert ai_client.summarize_output(answer["data"]) == "a summary"


def test_a_missing_prompt_file_is_reported_as_such(monkeypatch, tmp_path):
    import prompts

    monkeypatch.setattr(Config, "PROMPTS_DIR", str(tmp_path))
    monkeypatch.setattr(prompts, "_cache", {})
    with pytest.raises(prompts.PromptError):
        prompts.load("summary.txt")

    (tmp_path / "summary.txt").write_text("  Summarize the source.  ", encoding="utf-8")
    assert prompts.load("summary.txt") == "Summarize the source."


def test_the_shipped_prompts_are_readable():
    import prompts

    assert prompts.preload() == ["summary.txt", "entities.txt", "sentiment.txt"]


@contextlib.contextmanager
def captured_ai_logs(level=logging.DEBUG):
    """Every record `src/ai_client.py` emits, at `level` and above.

    A handler on the framework's own logger rather than pytest's `caplog`,
    which only sees what propagates to the root logger.
    """
    from framework.commons.logger import logger as ai_logger

    records = []
    handler = logging.Handler()
    handler.emit = records.append
    previous = ai_logger.level
    ai_logger.addHandler(handler)
    ai_logger.setLevel(level)
    try:
        yield records
    finally:
        ai_logger.removeHandler(handler)
        ai_logger.setLevel(previous)


def test_debug_logs_the_whole_request_and_response(monkeypatch):
    """DEBUG carries every input and output in full — the INFO line truncates."""
    import ai_client
    import prompts

    monkeypatch.setattr(Config, "AI_LOG_BODY_CHARS", 60)
    monkeypatch.setattr(Config, "AI_LOG_DEBUG_BODY_CHARS", 0)

    inputs = {"video_description": "a" * 500, "transcription": "hello"}
    with captured_ai_logs() as records:
        ai_client.summarize("summary", inputs, "summary.txt", video_id="vid-1")

    messages = [r.getMessage() for r in records]
    debug = [r.getMessage() for r in records if r.levelno == logging.DEBUG]
    request = next(m for m in debug if "REQUEST" in m)
    response = next(m for m in debug if "RESPONSE" in m)

    # The whole prompt and the whole input, not the INFO line's stand-in.
    assert "<summary.txt" not in request
    assert json.dumps(prompts.load("summary.txt"))[1:-1] in request
    assert "a" * 500 in request
    # The whole answer.
    assert mock_responses.MOCK_SUMMARIES["summary.txt"] in response

    # The INFO line is still the short one.
    info = [m for m in messages if "-->" in m or "<--" in m]
    assert info and all("chars)" in m for m in info)


def test_debug_bodies_can_be_capped_and_silenced(monkeypatch):
    import ai_client

    inputs = {"video_description": "a" * 500, "transcription": "hello"}

    monkeypatch.setattr(Config, "AI_LOG_DEBUG_BODY_CHARS", 100)
    with captured_ai_logs() as records:
        ai_client.summarize("summary", inputs, "summary.txt")
    assert any(
        "REQUEST" in r.getMessage() and "chars)" in r.getMessage() for r in records
    )

    # AI_LOG_BODIES=False means no payloads at any level.
    monkeypatch.setattr(Config, "AI_LOG_BODIES", False)
    with captured_ai_logs() as records:
        ai_client.summarize("summary", inputs, "summary.txt")
    assert not [
        r for r in records
        if "REQUEST" in r.getMessage() or "RESPONSE" in r.getMessage()
    ]
