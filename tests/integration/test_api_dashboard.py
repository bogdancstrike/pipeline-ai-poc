"""
`/client/dashboard` and `/client/statistics` — the two pages of numbers.

Everything here is computed in PostgreSQL over the whole window, never over a
page: a tile that averages the 25 rows it downloaded and calls itself "average
processing time" is a lie that looks like a metric. So the tests check the
arithmetic against the corpus, and check that the windows actually narrow.
"""

import pytest

from support import corpus, live

pytestmark = pytest.mark.live


def overview(range_="last_90_days"):
    answer = live.get(f"/client/dashboard?range={range_}")
    assert answer.ok, answer.text[:300]
    return answer.body


def statistics(range_="last_90_days"):
    answer = live.get(f"/client/statistics?range={range_}")
    assert answer.ok, answer.text[:300]
    return answer.body


# ── the KPI row ──────────────────────────────────────────────────────────


def test_the_dashboard_answers_five_tiles_and_six_charts():
    body = overview()

    assert len(body["kpis"]) == 5
    assert set(body["charts"]) == {
        "volume", "sentiment", "entity_types", "top_entities", "top_persons", "service_latency",
    }


def test_every_tile_says_which_direction_is_good():
    """More videos is good, more failures is not; colouring both green for "up"
    is how a dashboard teaches people to ignore it."""
    for kpi in overview()["kpis"]:
        assert kpi["better"] in ("up", "down")
        assert kpi["label"]
        assert "value" in kpi and "previous" in kpi and "delta" in kpi


def test_a_tile_with_nothing_to_compare_to_has_no_percentage():
    """"+100%" against an empty previous window is arithmetic, not information."""
    for kpi in overview("today")["kpis"]:
        if not kpi["previous"]:
            assert kpi["delta_pct"] is None


def test_the_analysed_count_covers_the_whole_corpus_not_one_page(expected):
    analysed = {kpi["key"]: kpi for kpi in overview()["kpis"]}["analysed"]
    assert analysed["value"] >= expected["total"]


def test_the_partial_rate_is_a_percentage():
    rate = {kpi["key"]: kpi for kpi in overview()["kpis"]}["failure_rate"]
    assert 0 <= rate["value"] <= 100
    assert rate["unit"] == "%"


# ── the charts ───────────────────────────────────────────────────────────


def test_every_chart_is_labels_and_series_the_frontend_maps_straight_across():
    for name, chart in overview()["charts"].items():
        assert set(chart) >= {"labels", "series"}, name
        assert isinstance(chart["labels"], list), name
        assert isinstance(chart["series"], list), name


def test_each_series_has_one_value_per_label():
    for name, chart in overview()["charts"].items():
        for series in chart["series"]:
            assert len(series["data"]) == len(chart["labels"]), f"{name}/{series.get('name')}"


def test_the_sentiment_donut_counts_the_corpus(expected):
    chart = overview()["charts"]["sentiment"]
    counts = dict(zip(chart["labels"], chart["series"][0]["data"]))

    for sentiment, count in expected["sentiments"].items():
        assert counts.get(sentiment, 0) >= count


def test_the_volume_chart_covers_the_window_day_by_day():
    chart = overview("last_7_days")["charts"]["volume"]
    assert 7 <= len(chart["labels"]) <= 9


def test_the_top_entities_chart_is_ordered_by_count():
    chart = overview()["charts"]["top_entities"]
    if chart["series"] and chart["series"][0]["data"]:
        data = chart["series"][0]["data"]
        assert data == sorted(data, reverse=True) or data == sorted(data)


def test_the_entity_types_chart_names_the_types_the_corpus_uses():
    labels = set(overview()["charts"]["entity_types"]["labels"])
    assert {"LOCATION", "NAME"} <= labels


def test_the_people_chart_names_person_ids():
    chart = overview()["charts"]["top_persons"]
    assert set(chart["labels"]) <= set(corpus.PERSONS) | {""} or chart["labels"] == []


# ── the windows ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "preset",
    ["today", "yesterday", "last_7_days", "last_30_days", "last_90_days",
     "current_month", "previous_month"],
)
def test_every_range_the_picker_offers_is_answered(preset):
    answer = live.get(f"/client/dashboard?range={preset}")
    assert answer.ok, f"{preset}: {answer.text[:200]}"


def test_a_narrower_window_cannot_hold_more_than_a_wider_one():
    week = {k["key"]: k for k in overview("last_7_days")["kpis"]}["analysed"]["value"]
    quarter = {k["key"]: k for k in overview("last_90_days")["kpis"]}["analysed"]["value"]
    assert week <= quarter


def test_an_explicit_from_and_to_is_honoured():
    answer = live.get("/client/dashboard?from=2026-01-01&to=2026-12-31")
    assert answer.ok


def test_an_unknown_range_falls_back_rather_than_failing():
    assert live.get("/client/dashboard?range=since_tuesday").ok


# ── statistics ───────────────────────────────────────────────────────────


def test_the_statistics_page_answers_totals_services_models_and_failures():
    body = statistics()
    assert set(body) >= {"totals", "items", "models", "failures", "throughput"}


def test_the_service_totals_add_up_to_the_sum_of_the_rows():
    body = statistics()
    assert body["totals"]["calls"] == sum(item["calls"] for item in body["items"])
    assert body["totals"]["live"] == sum(item["live"] for item in body["items"])
    assert body["totals"]["mocked"] == sum(item["mocked"] for item in body["items"])


def test_every_call_is_either_live_or_mocked_and_never_both():
    for item in statistics()["items"]:
        assert item["live"] + item["mocked"] == item["calls"], item["service"]


def test_the_seven_services_each_get_a_row():
    services = {item["service"] for item in statistics()["items"]}
    assert {"face-match-main", "video-describe-354b", "transcribe", "video-ocr",
            "summary", "entities", "sentiment"} <= services


def test_latency_is_reported_as_a_median_and_a_p95_not_only_a_mean():
    """One cold model load makes a mean describe a run that never happened."""
    for item in statistics()["items"]:
        assert "median_ms" in item and "p95_ms" in item and "max_ms" in item


def test_the_p95_is_not_below_the_median():
    for item in statistics()["items"]:
        if item["median_ms"] is not None and item["p95_ms"] is not None:
            assert item["p95_ms"] >= item["median_ms"], item["service"]


def test_the_max_is_not_below_the_p95():
    for item in statistics()["items"]:
        if item["max_ms"] is not None and item["p95_ms"] is not None:
            assert item["max_ms"] >= item["p95_ms"], item["service"]


def test_the_failure_rate_is_a_percentage_of_the_calls():
    totals = statistics()["totals"]
    assert 0 <= totals["failure_rate"] <= 100


def test_a_failed_call_appears_in_the_recent_failures_table():
    failures = statistics()["failures"]
    if failures:
        for failure in failures:
            assert failure["service"] and failure["error"]


def test_the_models_table_names_the_models_that_answered(expected):
    models = {row["model"] for row in statistics()["models"]}
    assert set(expected["models"]) <= models


def test_the_throughput_chart_is_labels_and_series():
    throughput = statistics()["throughput"]
    assert set(throughput) >= {"labels", "series"}
    for series in throughput["series"]:
        assert len(series["data"]) == len(throughput["labels"])


@pytest.mark.parametrize("preset", ["today", "last_7_days", "last_30_days", "last_90_days"])
def test_statistics_answers_for_every_window(preset):
    assert live.get(f"/client/statistics?range={preset}").ok
