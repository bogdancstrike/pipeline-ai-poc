"""
`client.store` — W7's record, flattened into the columns the explorer filters on.

The record is the product; these columns are a *view* of it built for
questions. Every one of them is a small transformation that can silently be
wrong — a sentiment stored in the case the model happened to use, an entity
line that never got split, a person count off by the number of empty strings —
and none of those show up until somebody filters and gets the wrong rows.

No database here: `_fill` is exercised against a bare row object.
"""

import pytest

from client.models import VideoRecord
from client.store import _fill, _fill_children, _split_entity


def flattened(record: dict) -> VideoRecord:
    row = VideoRecord(id=record.get("id", "x"))
    _fill(row, record)
    return row


def base(**enrichment) -> dict:
    return {
        "id": "vid-1",
        "name": "migrants.mp4",
        "path": "/video/migrants.mp4",
        "submitted_at": "2026-05-18T09:00:00+00:00",
        "analysed_at": "2026-05-18T09:00:42+00:00",
        "enrichment": enrichment,
        "errors": {},
    }


# ── identity and timing ──────────────────────────────────────────────────


def test_the_name_and_path_are_carried_across():
    row = flattened(base())
    assert row.name == "migrants.mp4"
    assert row.path == "/video/migrants.mp4"


def test_processing_time_is_wall_clock_including_the_queue():
    assert flattened(base()).processing_seconds == 42.0


def test_processing_time_is_absent_rather_than_negative_when_the_clocks_disagree():
    record = base()
    record["analysed_at"] = "2026-05-18T08:00:00+00:00"
    assert flattened(record).processing_seconds is None


def test_processing_time_is_absent_when_a_moment_is_missing():
    record = base()
    record.pop("submitted_at")
    assert flattened(record).processing_seconds is None


# ── outcome ──────────────────────────────────────────────────────────────


def test_a_record_with_no_errors_is_analysed():
    row = flattened(base())
    assert row.status == "analysed"
    assert row.failed_services == []
    assert row.error_count == 0


def test_a_record_with_one_failed_service_is_partial():
    record = base()
    record["errors"] = {"transcribe": "read timeout"}
    row = flattened(record)

    assert row.status == "partial"
    assert row.failed_services == ["transcribe"]
    assert row.error_count == 1
    assert row.errors["transcribe"] == "read timeout"


def test_the_failed_services_are_sorted_so_two_records_compare():
    record = base()
    record["errors"] = {"video-ocr": "boom", "face-match-main": "boom"}
    assert flattened(record).failed_services == ["face-match-main", "video-ocr"]


# ── the sentiment case, which every chart buckets on ─────────────────────


@pytest.mark.parametrize("answered", ["NEGATIVE", "negative", "Negative", " negative "])
def test_the_sentiment_is_stored_in_capitals_however_the_model_answered(answered):
    row = flattened(base(sentiment={"text": answered}))
    assert row.sentiment == "NEGATIVE"


def test_a_missing_sentiment_is_empty_not_null():
    assert flattened(base()).sentiment == ""


# ── entities ─────────────────────────────────────────────────────────────


def test_the_entity_count_is_the_number_of_lines_the_model_returned():
    row = flattened(base(entities={"list": ["LOCATION: Ceuta", "NAME: Red Cross"]}))
    assert row.entity_count == 2


@pytest.mark.parametrize(
    ("line", "kind", "value"),
    [
        ("LOCATION: Ceuta", "LOCATION", "Ceuta"),
        ("NAME: Red Cross", "NAME", "Red Cross"),
        ("  DATE :  2026-05-18 ", "DATE", "2026-05-18"),
        ("Ceuta", "UNTYPED", "Ceuta"),
        ("", "UNTYPED", ""),
    ],
)
def test_a_typed_entity_line_is_split_and_a_bare_one_is_kept(line, kind, value):
    assert _split_entity(line) == (kind, value)


def test_the_raw_line_is_kept_beside_the_split_parts():
    """A model that answers `Ceuta` must be distinguishable from a parse bug."""
    record = base(entities={"list": ["Ceuta"]})
    row = VideoRecord(id="vid-1")
    _fill(row, record)
    _fill_children(row, record, {})

    assert row.entities[0].raw == "Ceuta"
    assert row.entities[0].type == "UNTYPED"


def test_entity_values_are_case_folded_for_grouping():
    """So `Ceuta` and `ceuta` are one entity in a top-ten."""
    record = base(entities={"list": ["LOCATION: Ceuta", "LOCATION: ceuta"]})
    row = VideoRecord(id="vid-1")
    _fill(row, record)
    _fill_children(row, record, {})

    assert {entity.value_key for entity in row.entities} == {"ceuta"}


def test_entity_position_records_the_order_the_model_answered_in():
    record = base(entities={"list": ["LOCATION: A", "LOCATION: B", "LOCATION: C"]})
    row = VideoRecord(id="vid-1")
    _fill(row, record)
    _fill_children(row, record, {})

    assert [entity.position for entity in row.entities] == [0, 1, 2]


# ── persons ──────────────────────────────────────────────────────────────


def test_persons_are_stored_as_text_whatever_the_service_answered():
    row = flattened(base(face_match={"persons": [222, "417"]}))
    assert row.persons == ["222", "417"]
    assert row.person_count == 2


def test_no_persons_is_a_count_of_zero_not_a_null():
    assert flattened(base(face_match={"persons": []})).person_count == 0


def test_a_missing_face_branch_is_the_same_as_no_persons():
    assert flattened(base()).person_count == 0


# ── the sizes that make "videos with no speech" a filter ─────────────────


def test_the_character_counts_follow_the_texts():
    row = flattened(
        base(
            summary={"text": "12345"},
            transcript={"text": "123", "format": "dialog"},
            description={"text": "1234567"},
            ocr={"text": "1"},
        )
    )
    assert (row.summary_chars, row.transcript_chars, row.description_chars, row.ocr_chars) == (
        5, 3, 7, 1,
    )


def test_the_transcript_format_is_carried_for_the_panel_heading():
    assert flattened(base(transcript={"text": "x", "format": "srt"})).transcript_format == "srt"


def test_the_ocr_frame_count_is_carried():
    assert flattened(base(ocr={"text": "x", "frames_count": 9})).ocr_frames_count == 9


# ── the free-text sweep ──────────────────────────────────────────────────


def test_the_search_text_is_every_produced_text_at_once():
    row = flattened(
        base(
            summary={"text": "a summary"},
            entities={"list": [], "text": "LOCATION: Ceuta"},
            transcript={"text": "spoken words"},
            description={"text": "a wide shot"},
            ocr={"text": "ON SCREEN"},
        )
    )

    for fragment in ("a summary", "Ceuta", "spoken words", "a wide shot", "ON SCREEN", "migrants.mp4"):
        assert fragment in row.search_text


def test_an_absent_branch_leaves_no_blank_line_in_the_search_text():
    assert "\n\n" not in flattened(base(summary={"text": "only this"})).search_text


# ── provenance ───────────────────────────────────────────────────────────


def test_the_model_and_prompt_hash_come_from_the_summary_metadata():
    row = flattened(
        base(summary={"text": "s", "metadata": {"model": "phi4:14b-q8_0", "prompt_hash": "abc"}})
    )
    assert row.model == "phi4:14b-q8_0"
    assert row.prompt_hash == "abc"


def test_the_whole_record_is_kept_verbatim_beside_the_columns():
    """The answer to a question these columns did not anticipate."""
    record = base(summary={"text": "s"})
    assert flattened(record).document == record


# ── the call rows the statistics page is built from ──────────────────────


def test_a_call_row_is_produced_per_service():
    record = base(summary={"text": "s"})
    row = VideoRecord(id="vid-1")
    calls = {
        "face-match-main": {"mocked": True, "duration_ms": 50.0, "endpoint": None},
        "summary": {"mocked": False, "duration_ms": 900.0, "endpoint": "http://x:8825/summarize"},
    }
    _fill(row, record)
    _fill_children(row, record, calls)

    by_service = {call.service: call for call in row.calls}
    assert by_service["face-match-main"].mocked is True
    assert by_service["summary"].mocked is False
    assert by_service["summary"].endpoint.endswith("/summarize")


def test_a_call_that_reported_an_error_is_not_ok():
    record = base(summary={"text": ""})
    record["errors"] = {"summary": "read timeout"}
    row = VideoRecord(id="vid-1")
    _fill(row, record)
    _fill_children(row, record, {"summary": {"mocked": False, "error": "read timeout"}})

    call = {c.service: c for c in row.calls}["summary"]
    assert call.ok is False
    assert call.error == "read timeout"


def test_a_record_is_mocked_when_any_call_was():
    record = base(summary={"text": "s"})
    row = VideoRecord(id="vid-1")
    _fill(row, record)
    _fill_children(row, record, {"summary": {"mocked": True}})
    assert row.mocked is True


# ── the long values a column has to survive ──────────────────────────────


def test_an_overlong_name_is_truncated_to_the_column_rather_than_raising():
    record = base()
    record["name"] = "x" * 900
    assert len(flattened(record).name) == 512


def test_an_overlong_path_is_truncated_to_the_column():
    record = base()
    record["path"] = "/" + "x" * 2000
    assert len(flattened(record).path) == 1024
