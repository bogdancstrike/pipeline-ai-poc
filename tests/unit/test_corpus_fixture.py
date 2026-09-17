"""
The QA corpus generator tests itself.

Everything below the unit suite asserts against numbers this module computes,
so a generator that drifted from its own `expected()` would make a broken
application look correct. These are the tests that stop the fixture from
becoming the thing under test.
"""

import pytest

from support import corpus


COUNT = 120


def test_a_record_is_fully_determined_by_its_index():
    from datetime import UTC, datetime

    moment = datetime(2026, 5, 18, tzinfo=UTC)
    assert corpus.record(7, now=moment) == corpus.record(7, now=moment)


def test_two_indexes_are_two_different_records():
    assert corpus.record(1)["id"] != corpus.record(2)["id"]


def test_every_id_carries_the_prefix_that_makes_seeding_reversible():
    for record in corpus.records(20):
        assert record["id"].startswith(corpus.PREFIX)


def test_the_ids_are_the_ones_the_helper_predicts():
    assert [record["id"] for record in corpus.records(5)] == corpus.ids(5)


def test_a_record_has_the_shape_w7_writes():
    record = corpus.record(0)
    assert set(record) == {
        "id", "name", "path", "submitted_at", "analysed_at", "enrichment", "errors",
    }
    assert set(record["enrichment"]) == {
        "face_match", "description", "transcript", "ocr", "summary", "entities", "sentiment",
    }


def test_record_zero_is_the_newest_and_they_run_backwards():
    newest = corpus.record(0)["analysed_at"]
    older = corpus.record(1)["analysed_at"]
    assert newest > older


def test_the_corpus_spans_a_month_so_every_range_preset_has_something():
    from client.clock import parse

    span = parse(corpus.record(0)["analysed_at"]) - parse(corpus.record(COUNT - 1)["analysed_at"])
    assert 29 <= span.days <= 31


def test_a_record_is_analysed_after_it_was_submitted():
    for record in corpus.records(30):
        assert record["analysed_at"] > record["submitted_at"]


# ── the variety that makes a filter worth testing ────────────────────────


def test_all_three_sentiments_appear_in_equal_parts():
    assert corpus.expected(COUNT)["sentiments"] == {"NEGATIVE": 40, "POSITIVE": 40, "NEUTRAL": 40}


def test_some_records_are_partial_and_most_are_not():
    statuses = corpus.expected(COUNT)["statuses"]
    assert statuses["partial"] > 0
    assert statuses["analysed"] > statuses["partial"]
    assert statuses["analysed"] + statuses["partial"] == COUNT


def test_three_models_appear_so_the_model_facet_has_choices():
    assert len(corpus.expected(COUNT)["models"]) == 3


def test_a_failed_branch_produced_no_text():
    """Which is what AI_FAIL_FAST=false actually leaves behind."""
    failing = next(record for record in corpus.records(COUNT) if record["errors"])
    service = next(iter(failing["errors"]))
    branch = {"face-match-main": "face_match", "transcribe": "transcript", "video-ocr": "ocr"}[service]

    if branch == "face_match":
        assert failing["enrichment"]["face_match"]["persons"] == []
    else:
        assert failing["enrichment"][branch]["text"] == ""


def test_some_records_have_nobody_in_them_and_some_have_two():
    counts = {len(record["enrichment"]["face_match"]["persons"]) for record in corpus.records(COUNT)}
    assert 0 in counts and 2 in counts


def test_entity_counts_vary():
    counts = {len(record["enrichment"]["entities"]["list"]) for record in corpus.records(COUNT)}
    assert len(counts) > 1


def test_every_entity_line_is_typed():
    for record in corpus.records(30):
        for line in record["enrichment"]["entities"]["list"]:
            assert ": " in line


def test_each_record_is_findable_by_a_word_only_it_carries():
    """The free-text sweep needs a term that matches exactly one record."""
    summaries = [record["enrichment"]["summary"]["text"] for record in corpus.records(COUNT)]
    assert sum("Record 7:" in summary for summary in summaries) == 1


# ── the provenance the statistics page reads ─────────────────────────────


def test_every_service_gets_a_call_row():
    assert set(corpus.calls(0)) == {
        "face-match-main", "video-describe-354b", "transcribe", "video-ocr",
        "summary", "entities", "sentiment",
    }


def test_some_runs_are_live_so_latency_has_something_to_measure():
    live = [index for index in range(COUNT) if not corpus.calls(index)["summary"]["mocked"]]
    assert 0 < len(live) < COUNT


def test_a_live_call_carries_an_endpoint_and_a_mocked_one_does_not():
    live = next(corpus.calls(i) for i in range(COUNT) if not corpus.calls(i)["summary"]["mocked"])
    mocked = next(corpus.calls(i) for i in range(COUNT) if corpus.calls(i)["summary"]["mocked"])

    assert live["summary"]["endpoint"]
    assert mocked["summary"]["endpoint"] is None


def test_a_live_call_is_slower_than_a_mocked_one():
    live = next(corpus.calls(i) for i in range(COUNT) if not corpus.calls(i)["summary"]["mocked"])
    mocked = next(corpus.calls(i) for i in range(COUNT) if corpus.calls(i)["summary"]["mocked"])

    assert live["summary"]["duration_ms"] > mocked["summary"]["duration_ms"]


def test_the_call_rows_agree_with_the_records_errors():
    for index in range(30):
        errors = corpus.record(index)["errors"]
        calls = corpus.calls(index)
        for service, message in errors.items():
            assert calls[service]["error"] == message


def test_the_expected_totals_are_computed_from_the_records_themselves():
    expected = corpus.expected(10)
    assert expected["total"] == 10
    assert sum(expected["sentiments"].values()) == 10
    assert sum(expected["statuses"].values()) == 10
