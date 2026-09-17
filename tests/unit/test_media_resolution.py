"""
`client.media` — turning a record's stored path into a file this host can serve.

The pipeline and the browser do not share a filesystem: a record says
`/video/Inmigracion/x.mp4` because that is where :8821 opened it, and the same
file is mounted here as `/app/videos/Inmigracion/x.mp4`. So the match is on the
path's *tail*. This is also the one endpoint that turns a stored string into a
file read, which makes the traversal tests here the security ones.
"""

import pytest

from config import Config
from client import media


@pytest.fixture()
def corpus(tmp_path, monkeypatch):
    """`<tmp>/videos/Inmigracion/clip.mp4`, with `<tmp>/videos` searchable."""
    root = tmp_path / "videos"
    (root / "Inmigracion").mkdir(parents=True)
    (root / "Inmigracion" / "clip.mp4").write_bytes(b"\x00" * 32)
    (root / "loose.mp4").write_bytes(b"\x00" * 16)
    monkeypatch.setattr(Config, "VIDEO_SEARCH_DIRS", [str(root)])
    return root


# ── which local paths a record's path could mean ─────────────────────────


def test_the_candidates_start_with_the_path_as_given(corpus):
    assert media.candidates_for("/video/x.mp4")[0] == "/video/x.mp4"


def test_the_candidates_try_the_longest_tail_before_the_bare_name(corpus):
    """`Inmigracion/clip.mp4` is a better answer than `clip.mp4`."""
    candidates = media.candidates_for("/video/Inmigracion/clip.mp4")
    with_folder = str(corpus / "Inmigracion" / "clip.mp4")
    bare = str(corpus / "clip.mp4")

    assert with_folder in candidates and bare in candidates
    assert candidates.index(with_folder) < candidates.index(bare)


def test_the_candidates_carry_no_duplicates(corpus):
    candidates = media.candidates_for("/video/Inmigracion/clip.mp4")
    assert len(candidates) == len(set(candidates))


@pytest.mark.parametrize("nothing", ["", "   ", None, "/"])
def test_a_path_with_no_parts_has_no_candidates(corpus, nothing):
    assert media.candidates_for(nothing) == [] or media.candidates_for(nothing) == [nothing]


def test_a_windows_style_separator_is_understood(corpus):
    candidates = media.candidates_for(r"C:\video\Inmigracion\clip.mp4")
    assert str(corpus / "Inmigracion" / "clip.mp4") in candidates


# ── finding the file ─────────────────────────────────────────────────────


def test_a_video_in_a_subdirectory_is_found_by_its_tail(corpus):
    """The bug this module was rewritten for: matching only the file name
    finds a video sitting directly in ./videos and misses every one in a
    subdirectory, which is how the corpus is actually organised."""
    assert media.locate("/video/Inmigracion/clip.mp4") == str(corpus / "Inmigracion" / "clip.mp4")


def test_a_video_directly_in_a_search_directory_is_found(corpus):
    assert media.locate("/elsewhere/loose.mp4") == str(corpus / "loose.mp4")


def test_a_video_that_is_not_mounted_here_is_not_found(corpus):
    assert media.locate("/video/never-seen.mp4") is None


def test_describe_answers_playable_with_the_size(corpus):
    playable, local, size = media.describe("/video/Inmigracion/clip.mp4")
    assert playable is True
    assert local.endswith("clip.mp4")
    assert size == 32


def test_describe_says_so_when_the_file_is_elsewhere(corpus):
    assert media.describe("/video/absent.mp4") == (False, None, None)


# ── the two rules that make this safe to point at a path from a row ──────


def test_a_file_outside_every_search_directory_is_refused(tmp_path, monkeypatch):
    """Existing is not enough — it has to be inside a directory we published."""
    outside = tmp_path / "secrets"
    outside.mkdir()
    secret = outside / "private.mp4"
    secret.write_bytes(b"\x00")
    inside = tmp_path / "videos"
    inside.mkdir()
    monkeypatch.setattr(Config, "VIDEO_SEARCH_DIRS", [str(inside)])

    assert media.locate(str(secret)) is None


def test_a_traversal_out_of_a_search_directory_is_refused(corpus, tmp_path):
    escape = tmp_path / "escape.mp4"
    escape.write_bytes(b"\x00")

    assert media.locate("../escape.mp4") is None
    assert media.locate("/videos/../../escape.mp4") is None


def test_a_symlink_pointing_out_of_a_search_directory_is_refused(corpus, tmp_path):
    """Checked after realpath, so a link cannot be used as a door."""
    target = tmp_path / "outside.mp4"
    target.write_bytes(b"\x00")
    (corpus / "link.mp4").symlink_to(target)

    assert media.locate("/video/link.mp4") is None


def test_a_sibling_directory_with_the_same_prefix_is_not_inside(tmp_path, monkeypatch):
    """`/app/videos-secret/x.mp4` starts with `/app/videos` as a *string*."""
    allowed = tmp_path / "videos"
    allowed.mkdir()
    sneaky = tmp_path / "videos-secret"
    sneaky.mkdir()
    (sneaky / "x.mp4").write_bytes(b"\x00")
    monkeypatch.setattr(Config, "VIDEO_SEARCH_DIRS", [str(allowed)])

    assert media.locate(str(sneaky / "x.mp4")) is None


@pytest.mark.parametrize("name", ["notes.txt", "archive.zip", "script.sh", "record.json"])
def test_only_a_known_video_extension_is_served(corpus, name):
    (corpus / name).write_bytes(b"\x00")
    assert media.locate(f"/video/{name}") is None


@pytest.mark.parametrize("suffix", [".mp4", ".webm", ".mkv", ".mov", ".m4v"])
def test_the_formats_a_browser_can_play_are_served(corpus, suffix):
    (corpus / f"clip{suffix}").write_bytes(b"\x00")
    assert media.locate(f"/video/clip{suffix}") is not None


def test_the_extension_check_ignores_case(corpus):
    (corpus / "SHOUTED.MP4").write_bytes(b"\x00")
    assert media.locate("/video/SHOUTED.MP4") is not None


# ── what the browser is told the file is ─────────────────────────────────


def test_a_content_type_is_guessed_from_the_name(corpus):
    assert "video" in media.content_type(str(corpus / "Inmigracion" / "clip.mp4"))


def test_an_unguessable_name_falls_back_to_octet_stream(tmp_path):
    assert media.content_type(str(tmp_path / "file.unknownext")) == media.DEFAULT_TYPE
