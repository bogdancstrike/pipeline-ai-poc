"""
How long the API takes, with a budget it is allowed to fail.

The budgets are deliberately loose — this runs on a laptop beside Docker, and
a test that fails when somebody else starts a build is a test people delete.
What they catch is the *class* of regression that matters here: a query that
stopped using an index, a facet computed per row, an N+1 that turns a page of
25 into 25 round trips. Those cost an order of magnitude, not 20%.

Every measurement is a median of several runs, because one scheduling hiccup
is not a performance regression.
"""

import statistics
import time
from typing import Callable, List

import pytest

from support import live

pytestmark = [pytest.mark.live, pytest.mark.perf]

#: Milliseconds. A page of records is the thing a reader waits for most often.
BUDGET_SEARCH_MS = 400
BUDGET_SEARCH_WITH_FACETS_MS = 700
BUDGET_DETAIL_MS = 300
BUDGET_DASHBOARD_MS = 1200
BUDGET_STATISTICS_MS = 1200
BUDGET_META_MS = 200
BUDGET_EXPORT_MS = 2500

RUNS = 7


def timed(call: Callable[[], object], runs: int = RUNS) -> dict:
    """Run `call` and report the median, the p95 and the worst of it."""
    samples: List[float] = []
    for _ in range(runs):
        started = time.perf_counter()
        answer = call()
        samples.append((time.perf_counter() - started) * 1000)
        ok = getattr(answer, "ok", True)
        assert ok, f"the call failed while being timed: {answer}"
    samples.sort()
    return {
        "median": statistics.median(samples),
        "p95": samples[min(len(samples) - 1, int(len(samples) * 0.95))],
        "max": samples[-1],
        "samples": samples,
    }


def report(name: str, measured: dict, budget: float):
    """Print the numbers, then hold them to the budget."""
    print(
        f"\n[perf] {name:<34} median={measured['median']:7.1f}ms "
        f"p95={measured['p95']:7.1f}ms max={measured['max']:7.1f}ms budget={budget}ms"
    )
    assert measured["median"] < budget, (
        f"{name}: median {measured['median']:.0f}ms is over the {budget}ms budget "
        f"(samples: {[round(s) for s in measured['samples']]})"
    )


# ── the page a reader waits for ──────────────────────────────────────────


def test_a_page_of_records_is_quick(warm, seeded_only):
    measured = timed(lambda: live.post(
        "/client/records/search", {"filters": seeded_only, "page_size": 25}
    ))
    report("search, 25 rows", measured, BUDGET_SEARCH_MS)


def test_facets_cost_something_but_not_everything(warm, seeded_only):
    """One GROUP BY per faceted column, each with its own filter lifted."""
    measured = timed(lambda: live.post(
        "/client/records/search", {"filters": seeded_only, "page_size": 25, "facets": True}
    ))
    report("search + facets", measured, BUDGET_SEARCH_WITH_FACETS_MS)


def test_a_free_text_sweep_is_quick(warm, seeded_only):
    measured = timed(lambda: live.post(
        "/client/records/search",
        {"filters": seeded_only, "query_text": "breakwater", "page_size": 25},
    ))
    report("search, free text", measured, BUDGET_SEARCH_MS)


def test_the_largest_page_is_still_quick(warm, seeded_only):
    measured = timed(lambda: live.post(
        "/client/records/search", {"filters": seeded_only, "page_size": 200}
    ))
    report("search, 200 rows", measured, BUDGET_SEARCH_MS * 2)


def test_a_deep_page_costs_what_a_shallow_one_does(warm, seeded_only):
    """OFFSET over a small corpus should not degrade; a table scan would."""
    first = timed(lambda: live.post(
        "/client/records/search", {"filters": seeded_only, "page": 1, "page_size": 10}
    ))
    last = timed(lambda: live.post(
        "/client/records/search", {"filters": seeded_only, "page": 12, "page_size": 10}
    ))

    print(f"\n[perf] page 1 median={first['median']:.1f}ms  page 12 median={last['median']:.1f}ms")
    assert last["median"] < first["median"] * 3 + 100


def test_a_condition_tree_does_not_change_the_order_of_magnitude(warm, seeded_only):
    plain = timed(lambda: live.post(
        "/client/records/search", {"filters": seeded_only, "page_size": 25}
    ))
    with_tree = timed(lambda: live.post(
        "/client/records/search",
        {
            "filters": seeded_only,
            "page_size": 25,
            "condition_tree": {
                "type": "group",
                "properties": {"conjunction": "AND"},
                "children1": {
                    "a": {"type": "rule", "properties": {
                        "field": "sentiment", "operator": "select_equals", "value": ["NEGATIVE"]}},
                    "b": {"type": "rule", "properties": {
                        "field": "person_count", "operator": "greater", "value": 0}},
                },
            },
        },
    ))

    print(
        f"\n[perf] plain median={plain['median']:.1f}ms  "
        f"with a 2-rule tree median={with_tree['median']:.1f}ms"
    )
    assert with_tree["median"] < plain["median"] * 4 + 200


# ── one record ───────────────────────────────────────────────────────────


def test_a_record_detail_is_quick(warm):
    from support import corpus

    record_id = corpus.ids(1)[0]
    measured = timed(lambda: live.get(f"/client/records/{record_id}"))
    report("record detail", measured, BUDGET_DETAIL_MS)


def test_reading_ten_records_is_ten_times_one_not_a_hundred(warm):
    """The children are eager-loaded (`lazy='selectin'`); an N+1 would show here."""
    from support import corpus

    one = timed(lambda: live.get(f"/client/records/{corpus.ids(1)[0]}"))

    started = time.perf_counter()
    for record_id in corpus.ids(10):
        assert live.get(f"/client/records/{record_id}").ok
    ten = (time.perf_counter() - started) * 1000

    print(f"\n[perf] one detail={one['median']:.1f}ms  ten in sequence={ten:.1f}ms")
    assert ten < one["median"] * 25 + 500


def test_related_records_are_quick(warm):
    from support import corpus

    measured = timed(lambda: live.get(f"/client/records/{corpus.ids(1)[0]}/related"))
    report("related records", measured, BUDGET_DETAIL_MS * 2)


# ── the pages of numbers ─────────────────────────────────────────────────


def test_the_dashboard_is_built_in_one_pass(warm):
    measured = timed(lambda: live.get("/client/dashboard?range=last_30_days"))
    report("dashboard, 30 days", measured, BUDGET_DASHBOARD_MS)


def test_a_wider_window_does_not_cost_an_order_of_magnitude(warm):
    narrow = timed(lambda: live.get("/client/dashboard?range=last_7_days"), runs=5)
    wide = timed(lambda: live.get("/client/dashboard?range=last_90_days"), runs=5)

    print(f"\n[perf] 7 days={narrow['median']:.1f}ms  90 days={wide['median']:.1f}ms")
    assert wide["median"] < narrow["median"] * 4 + 300


def test_the_statistics_page_is_quick(warm):
    measured = timed(lambda: live.get("/client/statistics?range=last_30_days"))
    report("statistics, 30 days", measured, BUDGET_STATISTICS_MS)


# ── the small calls every page makes ─────────────────────────────────────


def test_the_field_catalogue_is_effectively_free(warm):
    measured = timed(lambda: live.get("/client/meta"))
    report("meta", measured, BUDGET_META_MS)


def test_health_is_effectively_free(warm):
    """The shell polls it; anything slow here is felt on every page."""
    measured = timed(lambda: live.get("/client/health"))
    report("health", measured, BUDGET_META_MS)


def test_the_pipeline_configuration_is_effectively_free(warm):
    measured = timed(lambda: live.get("/pipeline/config"))
    report("pipeline config", measured, BUDGET_META_MS)


# ── the download ─────────────────────────────────────────────────────────


def test_exporting_the_whole_corpus_is_quick(warm, seeded_only):
    def export():
        status, blob, _ = live.raw("/client/records?page_size=1")  # keep-alive warm
        return live.post(
            "/client/records/export", {"filters": seeded_only, "columns": ["name", "sentiment"]}
        )

    measured = timed(export, runs=3)
    report("export csv, whole corpus", measured, BUDGET_EXPORT_MS)


def test_the_first_byte_of_an_export_does_not_wait_for_the_last_row(warm, seeded_only):
    """It is streamed from a generator that owns its own session."""
    import json
    import urllib.request

    body = json.dumps({"filters": seeded_only, "columns": ["name"]}).encode("utf-8")
    request = urllib.request.Request(
        f"{live.API_BASE}/client/records/export",
        data=body,
        headers={"content-type": "application/json"},
        method="POST",
    )

    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=60) as response:
        response.read(1)
        first_byte = (time.perf_counter() - started) * 1000
        response.read()
        complete = (time.perf_counter() - started) * 1000

    print(f"\n[perf] export first byte={first_byte:.1f}ms  complete={complete:.1f}ms")
    assert first_byte <= complete


# ── the mocked pipeline itself ───────────────────────────────────────────


def test_a_mocked_worker_answers_immediately(warm):
    """With MOCK_LATENCY_MS at its default, a mocked branch is bookkeeping."""
    measured = timed(
        lambda: live.post("/workers/face-match-main/run", {"path": "/video/migrants.mp4"}),
        runs=5,
    )
    report("one mocked worker", measured, 1500)


def test_the_whole_mocked_pipeline_runs_inside_one_request(warm):
    measured = timed(
        lambda: live.post(
            "/workers/aggregator/run",
            {"path": "/video/migrants.mp4", "chain": True, "persist": False},
            timeout=120,
        ),
        runs=3,
    )
    report("whole pipeline, mocked", measured, 5000)
