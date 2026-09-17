"""
`utils.resolve_video_path` — the one place a submitted path is interpreted.

This is the function behind the single most common way a live run fails, so
its three behaviours are pinned separately: a path that exists here is made
absolute, a path that does not is looked for by file name in the search dirs,
and a path found nowhere is either forwarded (the default) or refused.
"""

import os

import pytest

from config import Config
from utils import branch_context, resolve_video_path, video_name


# ── a path that exists here ──────────────────────────────────────────────


def test_an_existing_file_is_returned_absolute(tmp_path, monkeypatch):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00")
    monkeypatch.chdir(tmp_path)

    assert resolve_video_path("clip.mp4") == str(video)


def test_a_relative_path_is_expanded_against_the_working_directory(tmp_path, monkeypatch):
    """The reason a host path can reach the AI services: `..` is resolved here.

    Submitting `../VIDEOS/x.mp4` from the app directory sends the *host's*
    absolute path to services that resolve it on their own filesystem.
    """
    corpus = tmp_path / "VIDEOS" / "Inmigracion"
    corpus.mkdir(parents=True)
    video = corpus / "1abe.mp4"
    video.write_bytes(b"\x00")
    workdir = tmp_path / "app"
    workdir.mkdir()
    monkeypatch.chdir(workdir)

    resolved = resolve_video_path("../VIDEOS/Inmigracion/1abe.mp4")

    assert resolved == str(video)
    assert os.path.isabs(resolved)


# ── a path that is only mounted here under another root ──────────────────


def test_a_file_name_is_looked_for_in_each_search_directory(tmp_path, monkeypatch):
    first = tmp_path / "a"
    second = tmp_path / "b"
    first.mkdir()
    second.mkdir()
    (second / "clip.mp4").write_bytes(b"\x00")
    monkeypatch.setattr(Config, "VIDEO_SEARCH_DIRS", [str(first), str(second)])

    assert resolve_video_path("/somewhere/else/clip.mp4") == str(second / "clip.mp4")


def test_the_first_search_directory_holding_the_name_wins(tmp_path, monkeypatch):
    first = tmp_path / "a"
    second = tmp_path / "b"
    first.mkdir()
    second.mkdir()
    (first / "clip.mp4").write_bytes(b"\x00")
    (second / "clip.mp4").write_bytes(b"\x00")
    monkeypatch.setattr(Config, "VIDEO_SEARCH_DIRS", [str(first), str(second)])

    assert resolve_video_path("/elsewhere/clip.mp4") == str(first / "clip.mp4")


def test_the_lookup_is_by_file_name_so_a_subdirectory_is_not_reconstructed(tmp_path, monkeypatch):
    """Documenting a real limit: only the basename is tried, never the tail.

    `/app/videos/Inmigracion/x.mp4` cannot resolve to `<dir>/Inmigracion/x.mp4`
    — the subdirectory is dropped. `client/media.py` does match on the tail,
    for streaming; this side deliberately does not.
    """
    root = tmp_path / "corpus"
    (root / "Inmigracion").mkdir(parents=True)
    (root / "Inmigracion" / "x.mp4").write_bytes(b"\x00")
    monkeypatch.setattr(Config, "VIDEO_SEARCH_DIRS", [str(root)])
    monkeypatch.setattr(Config, "VIDEO_PATH_PASSTHROUGH", True)

    # Forwarded untouched rather than found.
    assert resolve_video_path("/app/videos/Inmigracion/x.mp4") == "/app/videos/Inmigracion/x.mp4"


# ── a path found nowhere ─────────────────────────────────────────────────


def test_an_unknown_path_is_forwarded_when_passthrough_is_on(monkeypatch):
    monkeypatch.setattr(Config, "VIDEO_SEARCH_DIRS", [])
    monkeypatch.setattr(Config, "VIDEO_PATH_PASSTHROUGH", True)

    assert resolve_video_path("/video/on-the-ai-host.mp4") == "/video/on-the-ai-host.mp4"


def test_an_unknown_path_is_refused_when_passthrough_is_off(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "VIDEO_SEARCH_DIRS", [str(tmp_path)])
    monkeypatch.setattr(Config, "VIDEO_PATH_PASSTHROUGH", False)

    with pytest.raises(FileNotFoundError) as caught:
        resolve_video_path("/video/nope.mp4")

    # The message has to name what was tried, or it cannot be acted on.
    assert "nope.mp4" in str(caught.value)
    assert str(tmp_path) in str(caught.value)


@pytest.mark.parametrize("empty", ["", "   ", None])
def test_an_empty_path_is_a_value_error(empty):
    with pytest.raises(ValueError):
        resolve_video_path(empty)


def test_surrounding_whitespace_is_stripped(monkeypatch):
    monkeypatch.setattr(Config, "VIDEO_SEARCH_DIRS", [])
    monkeypatch.setattr(Config, "VIDEO_PATH_PASSTHROUGH", True)

    assert resolve_video_path("  /video/x.mp4  ") == "/video/x.mp4"


# ── the record's name ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/video/migrants.mp4", "migrants.mp4"),
        ("/a/b/c/1abe85d1.mp4", "1abe85d1.mp4"),
        ("migrants.mp4", "migrants.mp4"),
        ("", "video"),
        (None, "video"),
    ],
)
def test_video_name_is_the_file_name(path, expected):
    assert video_name(path) == expected


# ── what a branch echoes ─────────────────────────────────────────────────


def test_branch_context_carries_the_shared_fields_only():
    message = {
        "id": "vid-1",
        "path": "/video/x.mp4",
        "name": "x.mp4",
        "submitted_at": "2026-09-17T10:00:00+00:00",
        "face": {"persons": []},
    }

    context = branch_context(message)

    assert context["id"] == "vid-1"
    assert context["path"] == "/video/x.mp4"
    # A branch's own answer is not context; echoing it would make the
    # aggregator merge one branch's result into another's message.
    assert "face" not in context


def test_branch_context_drops_keys_that_are_absent():
    assert branch_context({"id": "vid-1"}) == {"id": "vid-1"}
