"""
`prompts` — the wording W6 posts to :8825 as `prompt_text`.

Two things are load-bearing: the database's copy wins over the file so an edit
in the UI reaches the next video without a restart, and a prompt outage cannot
stop a video being analysed — the shipped file is always there to fall back to.
"""

import pytest

from config import Config
import prompts


@pytest.fixture(autouse=True)
def isolated_prompts(tmp_path, monkeypatch):
    """A prompts directory of our own, and a cold cache."""
    monkeypatch.setattr(Config, "PROMPTS_DIR", str(tmp_path))
    monkeypatch.setattr(prompts, "_cache", {})
    (tmp_path / "summary.txt").write_text("Summarise the video.\n", encoding="utf-8")
    (tmp_path / "entities.txt").write_text("List entities.\n", encoding="utf-8")
    (tmp_path / "sentiment.txt").write_text("One word.\n", encoding="utf-8")
    return tmp_path


@pytest.fixture()
def no_database(monkeypatch):
    """`_stored` answers None — the file is the only source."""
    monkeypatch.setattr(prompts, "_stored", lambda name: None)


# ── reading a prompt file ────────────────────────────────────────────────


def test_a_prompt_is_the_text_of_its_file(isolated_prompts, no_database):
    assert prompts.load("summary.txt").strip() == "Summarise the video."


def test_the_file_is_read_once_and_cached(isolated_prompts, no_database):
    first = prompts.from_file("summary.txt")
    (isolated_prompts / "summary.txt").write_text("changed on disk", encoding="utf-8")

    assert prompts.from_file("summary.txt") == first, "an edit takes effect on restart"


def test_the_path_is_inside_the_prompts_directory(isolated_prompts):
    assert prompts.path("summary.txt") == str(isolated_prompts / "summary.txt")


# ── refusals ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("escape", ["../secrets.txt", "/etc/passwd", "a/b.txt"])
def test_a_prompt_name_that_is_not_a_bare_file_name_is_refused(isolated_prompts, escape):
    """A stray env var must not make the pipeline read an arbitrary file."""
    with pytest.raises(prompts.PromptError):
        prompts.from_file(escape)


def test_a_missing_prompt_file_is_a_configuration_error(isolated_prompts, no_database):
    with pytest.raises(prompts.PromptError) as caught:
        prompts.from_file("absent.txt")
    assert "absent.txt" in str(caught.value)


def test_an_empty_prompt_file_is_a_configuration_error(isolated_prompts, no_database):
    (isolated_prompts / "blank.txt").write_text("   \n", encoding="utf-8")
    with pytest.raises(prompts.PromptError):
        prompts.from_file("blank.txt")


# ── the database's copy ──────────────────────────────────────────────────


def test_the_stored_wording_wins_over_the_file(isolated_prompts, monkeypatch):
    monkeypatch.setattr(prompts, "_stored", lambda name: "edited in the UI")
    assert prompts.load("summary.txt") == "edited in the UI"


def test_the_file_is_used_when_the_database_has_nothing_to_say(isolated_prompts, monkeypatch):
    monkeypatch.setattr(prompts, "_stored", lambda name: None)
    assert prompts.load("summary.txt").strip() == "Summarise the video."


def test_a_database_outage_cannot_stop_a_video_being_analysed(isolated_prompts, monkeypatch):
    """The shipped wording runs when PostgreSQL does not answer.

    The guard lives in `prompt_store.text_for`, which swallows everything —
    a dead database, a missing table on a first run, a row nobody created —
    because all three mean "the file is the prompt".
    """
    from client import db, prompt_store

    monkeypatch.setattr(Config, "DB_ENABLED", True)
    monkeypatch.setattr(Config, "PROMPTS_FROM_DB", True)
    monkeypatch.setattr(prompt_store, "_cache", {})

    def dead(*_args, **_kwargs):
        raise db.DatabaseUnavailable("postgres is down")

    monkeypatch.setattr(db, "session_scope", dead)

    assert prompts.load("summary.txt").strip() == "Summarise the video."


def test_stored_answers_none_when_the_client_package_cannot_be_reached(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "client.prompt_store", None)
    assert prompts._stored("summary.txt") is None


# ── the boot check ───────────────────────────────────────────────────────


def test_preload_reads_every_configured_prompt(isolated_prompts, no_database):
    loaded = prompts.preload()
    assert set(loaded) >= {Config.SUMMARY_PROMPT, Config.ENTITIES_PROMPT, Config.SENTIMENT_PROMPT}


def test_preload_fails_at_boot_rather_than_on_the_first_video(isolated_prompts, no_database, monkeypatch):
    (isolated_prompts / "summary.txt").unlink()
    monkeypatch.setattr(prompts, "_cache", {})

    with pytest.raises(prompts.PromptError):
        prompts.preload()


def test_the_three_configured_names_are_the_ones_w6_posts():
    assert Config.SUMMARY_PROMPT.endswith(".txt")
    assert Config.ENTITIES_PROMPT.endswith(".txt")
    assert Config.SENTIMENT_PROMPT.endswith(".txt")
