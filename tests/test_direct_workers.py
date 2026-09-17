"""
Calling a worker directly — `workers/registry.py` and `POST /workers/...`.

These assert the property the feature exists for: the worker body runs, its
answer comes back, and **nothing is published to Kafka**. No broker is running
during these tests, so any attempt to produce would fail loudly.
"""

import pytest

from config import Topics
from mock import mock_responses
from workers import registry


# ------------------------------------------------------------------ catalog --

def test_catalog_lists_every_worker_in_pipeline_order():
    names = [w["worker"] for w in registry.catalog()]
    assert names == [
        "splitter",
        "face-match-main",
        "video-describe-354b",
        "transcribe",
        "video-ocr",
        "aggregator-ai-caller",
        "aggregator",
    ]


def test_catalog_reports_which_ai_calls_are_mocked():
    by_name = {w["worker"]: w for w in registry.catalog()}

    # conftest turns every MOCK_WORKER_* on.
    assert by_name["video-ocr"]["mocked"] == {"video-ocr": True}
    assert by_name["aggregator-ai-caller"]["mocked"] == {
        "summary": True, "entities": True, "sentiment": True,
    }
    # W1 and W7 call no AI service at all.
    assert by_name["splitter"]["mocked"] == {}
    assert by_name["aggregator"]["mocked"] == {}


def test_catalog_says_what_a_chained_call_runs_first():
    by_name = {w["worker"]: w for w in registry.catalog()}
    assert by_name["splitter"]["runs_first"] == []
    assert by_name["video-ocr"]["runs_first"] == ["splitter"]
    # The final aggregator pulls in the whole pipeline, each worker once.
    assert by_name["aggregator"]["runs_first"] == [
        "splitter", "face-match-main", "video-describe-354b",
        "transcribe", "video-ocr", "aggregator-ai-caller",
    ]


def test_an_unknown_worker_is_reported_not_raised_blindly():
    with pytest.raises(registry.UnknownWorker):
        registry.run("nope", {"id": "x", "path": "/video/1.mp4"})


# ------------------------------------------------------------------ running --

@pytest.fixture()
def seed():
    return {
        "id": "direct-1",
        "path": "/video/migrants.mp4",
        "name": "migrants.mp4",
        "options": {},
    }


def test_running_one_handler_returns_its_branch_message(seed):
    out = registry.run("video-ocr", seed)

    assert out["worker"] == "video-ocr"
    assert out["published"] is False
    assert out["would_publish_to"] == [Topics.MERGE_OCR]
    assert out["ran_first"] == ["splitter"]
    assert out["result"]["ocr"]["full_text"] == mock_responses.MOCK_OCR_FULL_TEXT


def test_a_chained_call_feeds_the_worker_the_message_its_topic_would_carry(seed):
    """W5 never sees the raw body — it sees what the splitter produced."""
    consumed = registry.run("video-ocr", seed)["consumed"]
    assert set(consumed) == {"id", "path", "name", "options", "submitted_at"}
    assert consumed["submitted_at"]  # added by W1, absent from the request


def test_chain_false_hands_the_body_over_untouched(seed):
    out = registry.run("video-ocr", seed, chain=False)
    assert out["ran_first"] == []
    assert "submitted_at" not in out["consumed"]
    assert out["result"]["ocr"]["full_text"] == mock_responses.MOCK_OCR_FULL_TEXT


def test_running_the_ai_caller_merges_the_three_content_branches(seed):
    out = registry.run("aggregator-ai-caller", seed)

    assert out["ran_first"] == [
        "splitter", "video-describe-354b", "transcribe", "video-ocr",
    ]
    # The face branch is not one of its inputs.
    assert "face" not in out["consumed"]
    assert set(out["result"]["enrichment"]) == {
        "description", "transcript", "ocr", "summary", "entities", "sentiment",
    }


def test_running_the_final_aggregator_runs_the_whole_pipeline(seed):
    out = registry.run("aggregator", seed)

    record = out["result"]["record"]
    assert set(record) == {
        "id", "name", "path", "submitted_at", "analysed_at", "enrichment", "errors",
    }
    assert record["enrichment"]["face_match"]["persons"] == mock_responses.MOCK_PERSONS
    assert record["enrichment"]["sentiment"]["text"] == "NEGATIVE"
    assert record["errors"] == {}


def test_each_worker_runs_once_even_when_several_branches_need_it(seed, monkeypatch):
    """Five of the six upstream workers descend from W1 — it must run once.

    W1 announces itself on the console, so counting that line counts the runs.
    """
    import utils

    printed = []
    monkeypatch.setattr(utils, "console", printed.append)

    registry.run("aggregator", seed)

    assert len([line for line in printed if "fanned out" in line]) == 1


# ------------------------------------------------------- no file, no Kafka --

def test_a_direct_run_does_not_write_the_record_file(seed, tmp_path, monkeypatch):
    from config import Config

    monkeypatch.setattr(Config, "OUTPUT_DIR", str(tmp_path))
    out = registry.run("aggregator", seed)

    assert out["result"]["output_file"] is None
    assert list(tmp_path.iterdir()) == []


def test_persist_true_writes_it_as_the_pipeline_would(seed, tmp_path, monkeypatch):
    from config import Config

    monkeypatch.setattr(Config, "OUTPUT_DIR", str(tmp_path))
    out = registry.run("aggregator", seed, persist=True)

    assert out["result"]["output_file"] == str(tmp_path / "migrants_analysis.json")
    assert (tmp_path / "migrants_analysis.json").is_file()
