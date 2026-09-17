"""
`mock.mock_responses` — the canned answers a mocked worker returns.

Every worker is mocked by default, so these ARE the pipeline for most runs:
a mock whose shape drifts from the real service's makes the whole suite green
against something that cannot happen. Each answer is therefore checked against
the shape `ai_client` and the workers actually read.
"""

import pytest

from mock import mock_responses


def test_face_match_answers_persons_and_a_message():
    answer = mock_responses.face_match("/video/x.mp4")
    assert isinstance(answer["persons"], list)
    assert all(isinstance(person, str) for person in answer["persons"])
    assert answer["message"]


def test_describe_answers_a_description_and_its_metadata():
    answer = mock_responses.describe("/video/x.mp4")
    assert answer["description"]
    assert answer["metadata"]["model"]
    assert answer["metadata"]["processing_time_seconds"] > 0


def test_transcribe_answers_a_transcription_in_the_requested_format():
    answer = mock_responses.transcribe("/video/x.mp4", format="dialog")
    assert answer["format"] == "dialog"
    assert answer["transcription"]


def test_transcribe_echoes_the_language_that_was_asked_for():
    """The real service reports what it was told and what it detected."""
    answer = mock_responses.transcribe("/video/x.mp4", language="ro")
    assert answer["metadata"]["requested_language"] == "ro"


def test_ocr_answers_the_full_text_and_one_entry_per_frame():
    answer = mock_responses.ocr("/video/x.mp4")

    assert answer["full_text"]
    assert len(answer["frames"]) == answer["metadata"]["frames_returned"]
    for frame in answer["frames"]:
        assert {"frame_index", "timestamp_ms", "text"} <= set(frame)


def test_the_ocr_frames_are_copies_so_a_worker_cannot_mutate_the_mock():
    first = mock_responses.ocr("/video/x.mp4")["frames"][0]
    first["text"] = "tampered"
    assert mock_responses.ocr("/video/x.mp4")["frames"][0]["text"] != "tampered"


def summarised(prompt_file, prompt_text="the prompt"):
    return mock_responses.summarize({}, prompt_file, prompt_text, {})


def test_the_summary_prompt_answers_prose():
    assert len(summarised("summary.txt")["output"].split()) > 5


def test_the_entities_prompt_answers_typed_lines():
    answer = summarised("entities.txt")
    lines = [line for line in answer["output"].splitlines() if line.strip()]
    assert lines
    for line in lines:
        assert ":" in line, f"{line!r} is not a TYPE: value line"


def test_the_sentiment_prompt_answers_one_word_in_capitals():
    word = summarised("sentiment.txt")["output"].strip()
    assert word == word.upper()
    assert len(word.split()) == 1
    # The three the prompt asks for; the column takes anything, the charts
    # bucket on these.
    assert word in ("POSITIVE", "NEUTRAL", "NEGATIVE")


def test_a_summary_answer_carries_the_provenance_the_statistics_page_needs():
    metadata = summarised("summary.txt")["metadata"]
    assert metadata["model"]
    assert metadata["provider"]
    assert metadata["input_tokens"] > 0
    assert metadata["output_tokens"] > 0


def test_an_unknown_prompt_still_answers_rather_than_raising():
    """A new prompt file must not take the mocked pipeline down."""
    assert summarised("something-new.txt")["output"]


def test_the_prompt_hash_follows_the_prompt_text_not_the_file_name():
    """It is how you tell that the wording changed underneath a corpus."""
    one = summarised("summary.txt", "wording A")["metadata"]["prompt_hash"]
    two = summarised("summary.txt", "wording B")["metadata"]["prompt_hash"]
    assert one != two


def test_the_mocks_are_deterministic():
    """Two runs of a mocked pipeline have to produce the same record."""
    assert mock_responses.face_match("/video/x.mp4") == mock_responses.face_match("/video/x.mp4")
    assert mock_responses.describe("/video/x.mp4") == mock_responses.describe("/video/x.mp4")
    assert summarised("summary.txt") == summarised("summary.txt")


def test_the_mocks_touch_no_filesystem():
    """Which is why a mocked transcribe 'works' for a path that does not exist."""
    import inspect

    source = inspect.getsource(mock_responses)
    assert "open(" not in source
    assert "os.path" not in source
