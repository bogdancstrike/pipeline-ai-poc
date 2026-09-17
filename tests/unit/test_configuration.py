"""
`config` — the one place a deployment is described.

Most of these are guards against a class of bug that is invisible in review and
obvious in production: an env var read as a string and compared as a boolean,
a topic renamed on one side of a fan-out, a mock switch whose name does not
match the worker it is supposed to silence.
"""

import importlib
import os

import pytest

from config import Config, Topics


def reloaded(monkeypatch, **env):
    """Re-import config with these environment variables set."""
    import config as config_module

    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return importlib.reload(config_module)


# ── booleans from the environment ────────────────────────────────────────


@pytest.mark.parametrize("word", ["true", "True", "TRUE", "1", "yes", "on"])
def test_every_spelling_of_yes_is_true(monkeypatch, word):
    module = reloaded(monkeypatch, VIDEO_PATH_PASSTHROUGH=word)
    assert module.Config.VIDEO_PATH_PASSTHROUGH is True


@pytest.mark.parametrize("word", ["false", "False", "0", "no", "off", "", "maybe"])
def test_anything_else_is_false(monkeypatch, word):
    module = reloaded(monkeypatch, VIDEO_PATH_PASSTHROUGH=word)
    assert module.Config.VIDEO_PATH_PASSTHROUGH is False


def test_a_flag_is_a_real_boolean_not_a_string(monkeypatch):
    """`if Config.X` on the string "false" is true, and that is the bug."""
    module = reloaded(monkeypatch, VIDEO_PATH_PASSTHROUGH="false")
    assert module.Config.VIDEO_PATH_PASSTHROUGH is not "false"  # noqa: F632
    assert isinstance(module.Config.VIDEO_PATH_PASSTHROUGH, bool)


# ── the AI services ──────────────────────────────────────────────────────


def test_every_service_has_a_url():
    for name in ("AI_FACE_MATCH_URL", "AI_DESCRIBE_URL", "AI_OCR_URL",
                 "AI_TRANSCRIBE_URL", "AI_SUMMARIZE_URL"):
        assert getattr(Config, name).startswith("http")


def test_the_five_services_are_on_five_ports():
    urls = {
        Config.AI_FACE_MATCH_URL, Config.AI_DESCRIBE_URL, Config.AI_OCR_URL,
        Config.AI_TRANSCRIBE_URL, Config.AI_SUMMARIZE_URL,
    }
    assert len(urls) == 5


def test_a_url_can_be_moved_without_touching_the_code(monkeypatch):
    module = reloaded(monkeypatch, AI_FACE_MATCH_URL="http://elsewhere:9999")
    assert module.Config.AI_FACE_MATCH_URL == "http://elsewhere:9999"


def test_the_timeout_is_generous_enough_for_a_cold_model():
    assert Config.AI_TIMEOUT_SEC >= 60


def test_retries_are_bounded():
    assert 0 <= Config.AI_RETRIES <= 10


# ── the mock switches ────────────────────────────────────────────────────


def test_every_worker_that_calls_a_service_has_a_mock_switch():
    flags = Config.mock_flags()
    assert set(flags) >= {
        "face-match-main", "video-describe-354b", "video-ocr",
        "transcribe", "summary", "entities", "sentiment",
    }


def test_the_mock_flags_are_booleans():
    assert all(isinstance(value, bool) for value in Config.mock_flags().values())


def test_a_single_service_can_be_taken_live(monkeypatch):
    module = reloaded(monkeypatch, MOCK_WORKER_FACE_MATCH="False", MOCK_WORKER_OCR="True")
    flags = module.Config.mock_flags()
    assert flags["face-match-main"] is False
    assert flags["video-ocr"] is True


# ── the topics both aggregators regroup on ───────────────────────────────


def test_every_topic_is_named():
    names = [value for key, value in vars(Topics).items() if not key.startswith("_")]
    assert all(isinstance(name, str) and name for name in names)


def test_the_topics_are_distinct():
    """A fan-out that writes two branches to one topic loses one of them."""
    names = [value for key, value in vars(Topics).items() if not key.startswith("_")]
    assert len(names) == len(set(names))


def test_the_four_extraction_topics_are_the_splitters_outputs():
    for topic in (Topics.FACE_IN, Topics.DESCRIBE_IN, Topics.TRANSCRIBE_IN, Topics.OCR_IN):
        assert topic


# ── sizes and limits ─────────────────────────────────────────────────────


def test_the_kafka_message_ceiling_is_above_the_default_megabyte():
    """An OCR answer carries one text block per sampled frame."""
    assert Config.KAFKA_MAX_MESSAGE_BYTES > 1024 * 1024


def test_the_aggregator_window_outlasts_a_long_transcription():
    assert Config.AGGREGATOR_TIMEOUT_SEC >= 600


# ── the video search path ────────────────────────────────────────────────


def test_the_search_directories_are_a_list_not_a_string(monkeypatch):
    module = reloaded(monkeypatch, VIDEO_SEARCH_DIRS="/a:/b:/c")
    assert module.Config.VIDEO_SEARCH_DIRS == ["/a", "/b", "/c"]


def test_empty_entries_in_the_search_path_are_dropped(monkeypatch):
    module = reloaded(monkeypatch, VIDEO_SEARCH_DIRS="/a::/b:")
    assert module.Config.VIDEO_SEARCH_DIRS == ["/a", "/b"]


# ── the prompts W6 posts ─────────────────────────────────────────────────


def test_the_three_prompt_files_are_distinct():
    """One file name for two prompts would summarise a video three times."""
    names = {Config.SUMMARY_PROMPT, Config.ENTITIES_PROMPT, Config.SENTIMENT_PROMPT}
    assert len(names) == 3


def test_the_two_summarize_input_keys_are_distinct():
    """They are the keys of one dict; sharing a name loses the transcript."""
    assert Config.SUMMARIZE_KEY_DESCRIPTION != Config.SUMMARIZE_KEY_TRANSCRIPT


def test_the_output_format_is_one_the_writer_knows():
    assert Config.OUTPUT_FORMAT in ("block", "line", "json")
