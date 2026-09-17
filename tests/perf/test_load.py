"""
What the API does when more than one person is using it.

The stack this runs against is a single Flask process serving seven Kafka
workers in the same interpreter, so the interesting questions are not "how many
thousands of requests per second" — they are:

  * does anything *fail* under concurrency, or only slow down?
  * does latency degrade proportionally, or fall off a cliff (a pool exhausted,
    a lock held across a query)?
  * does a slow endpoint block a fast one, which is what a shared connection
    pool of five would look like from the outside?

The thresholds are about shape, not speed. They are written so that a machine
under other load still passes and a *contention* regression still fails.
"""

import pytest

from support import live
from support.loadgen import drive

pytestmark = [pytest.mark.live, pytest.mark.load]

#: Short on purpose: long enough for the numbers to settle, short enough that
#: nobody skips the suite.
SECONDS = float(5)


def search(payload=None):
    body = {"page_size": 25, **(payload or {})}
    return lambda: live.post("/client/records/search", body, timeout=30)


def show(result):
    print("\n" + result.line())
    return result


# ── nothing breaks ───────────────────────────────────────────────────────


def test_sixteen_readers_searching_at_once_all_get_answers(warm, seeded_only):
    result = show(drive("search x16", search({"filters": seeded_only}), concurrency=16, seconds=SECONDS))

    assert result.requests > 0
    assert result.errors == [], result.errors[:3]
    assert result.failure_rate == 0.0, result.statuses
    assert set(result.statuses) == {200}


def test_the_dashboard_survives_being_opened_by_everybody_at_once(warm):
    result = show(drive(
        "dashboard x12",
        lambda: live.get("/client/dashboard?range=last_30_days", timeout=30),
        concurrency=12,
        seconds=SECONDS,
    ))

    assert result.errors == []
    assert result.failure_rate == 0.0, result.statuses


def test_a_mixed_workload_is_all_answered(warm, seeded_only):
    """What a room of people actually does: some searching, some reading."""
    import itertools

    calls = itertools.cycle([
        lambda: live.post("/client/records/search", {"filters": seeded_only, "page_size": 25}, timeout=30),
        lambda: live.get("/client/records/qa-0001", timeout=30),
        lambda: live.get("/client/dashboard?range=last_7_days", timeout=30),
        lambda: live.get("/client/statistics?range=last_7_days", timeout=30),
        lambda: live.get("/client/meta", timeout=30),
    ])
    lock_free = iter(calls)

    result = show(drive("mixed x16", lambda: next(lock_free)(), concurrency=16, seconds=SECONDS))

    assert result.errors == []
    assert result.failure_rate == 0.0, result.statuses


def test_the_database_pool_is_not_exhausted_by_more_clients_than_it_has(warm, seeded_only):
    """DB_POOL_SIZE is 5 with 10 overflow; 24 clients is past both.

    The pool is supposed to make them queue, not fail. A 503 here would be the
    reader seeing "the records database is unavailable" because somebody else
    was searching.
    """
    result = show(drive("search x24", search({"filters": seeded_only}), concurrency=24, seconds=SECONDS))

    assert 503 not in result.statuses, "the pool refused a caller instead of queueing them"
    assert result.failure_rate == 0.0, result.statuses


# ── it degrades, rather than falling over ────────────────────────────────


def test_latency_grows_with_concurrency_rather_than_collapsing(warm, seeded_only):
    one = show(drive("search x1", search({"filters": seeded_only}), concurrency=1, seconds=3))
    many = show(drive("search x16", search({"filters": seeded_only}), concurrency=16, seconds=3))

    assert one.median > 0
    # 16 clients on a handful of workers is allowed to be much slower per
    # request. What it may not be is unbounded — a cliff here is a lock.
    assert many.median < one.median * 60 + 200, (
        f"median went from {one.median:.0f}ms at c=1 to {many.median:.0f}ms at c=16"
    )


def test_throughput_rises_with_concurrency(warm, seeded_only):
    one = show(drive("search x1", search({"filters": seeded_only}), concurrency=1, seconds=3))
    four = show(drive("search x4", search({"filters": seeded_only}), concurrency=4, seconds=3))

    assert four.throughput > one.throughput * 0.9, (
        f"four clients did {four.throughput:.1f} req/s against one client's {one.throughput:.1f}"
    )


def test_the_tail_is_not_an_order_of_magnitude_past_the_median(warm, seeded_only):
    """A p99 far past the median is a queue somewhere, not slow SQL."""
    result = show(drive("search x8", search({"filters": seeded_only}), concurrency=8, seconds=SECONDS))

    assert result.percentile(0.99) < result.median * 30 + 500, (
        f"median={result.median:.0f}ms p99={result.percentile(0.99):.0f}ms"
    )


# ── one slow endpoint does not take the others with it ───────────────────


def test_a_cheap_call_still_answers_while_the_expensive_one_is_hammered(warm, seeded_only):
    """`/client/health` is polled by every open tab; it must stay answerable."""
    import threading

    stop = threading.Event()

    def hammer():
        while not stop.is_set():
            try:
                live.get("/client/statistics?range=last_90_days", timeout=30)
            except Exception:  # noqa: BLE001
                pass

    load = [threading.Thread(target=hammer, daemon=True) for _ in range(8)]
    for thread in load:
        thread.start()
    try:
        result = show(drive(
            "health under load", lambda: live.get("/client/health", timeout=30),
            concurrency=2, seconds=4,
        ))
    finally:
        stop.set()
        for thread in load:
            thread.join(timeout=10)

    assert result.failure_rate == 0.0, result.statuses
    assert result.percentile(0.95) < 5000


# ── the pipeline's own endpoints ─────────────────────────────────────────


def test_submitting_many_videos_at_once_is_accepted(warm, submitted_records):
    """Kafka's producer is shared; a burst of submits must not lose one.

    This one really does run the pipeline: every accepted submission becomes a
    record, which is why the ids are prefixed and the fixture deletes them.
    """
    def submit():
        return live.post(
            "/pipeline/analyze",
            {"path": "/video/migrants.mp4", "id": submitted_records.id()},
            timeout=30,
        )

    # Capped low on purpose. Each accepted submission costs seven workers a
    # unit of work *after* the response, so an unbounded burst queues thousands
    # of messages that the next test waits behind and the cleanup chases for
    # minutes. Fifty concurrent submissions prove what this is about — that a
    # shared producer under contention accepts every one — as well as a
    # thousand would.
    result = show(drive("submit x8", submit, concurrency=8, seconds=3, max_requests=50))

    # Up to one extra per thread: the cap is checked before a request, and the
    # ones already in flight finish.
    assert 50 <= result.requests <= 50 + 8
    assert result.errors == []
    assert set(result.statuses) <= {202}, result.statuses


def test_exports_can_be_asked_for_concurrently(warm, seeded_only):
    """Each one streams from its own session; sharing one would show up here."""
    result = show(drive(
        "export x4",
        lambda: live.post(
            "/client/records/export",
            {"filters": seeded_only, "columns": ["name", "sentiment"]},
            timeout=60,
        ),
        concurrency=4,
        seconds=4,
    ))

    assert result.errors == []
    assert result.failure_rate == 0.0, result.statuses


# ── a corpus ten times the size ──────────────────────────────────────────


def test_the_search_still_answers_over_a_larger_corpus(warm, seeded_only, reseed):
    """Seeded at 120 rows; this says what happens at 1,200.

    Not a scale test — it is a *shape* test. A query that got slower than
    linear between these two is one that stopped using an index.
    """
    small = show(drive("search @120", search({"filters": seeded_only}), concurrency=4, seconds=3))

    assert reseed(1200) == 1200
    large = show(drive("search @1200", search({"filters": seeded_only}), concurrency=4, seconds=3))

    assert large.failure_rate == 0.0
    assert large.median < small.median * 10 + 200, (
        f"120 rows: {small.median:.0f}ms, 1200 rows: {large.median:.0f}ms"
    )


def test_a_page_of_a_larger_corpus_is_still_one_page(warm, seeded_only, reseed):
    """The total grows; the work of answering one page should not."""
    assert reseed(1200) == 1200

    answer = live.post(
        "/client/records/search", {"filters": seeded_only, "page_size": 25, "facets": True}
    )
    assert answer.ok
    assert answer.body["total"] == 1200
    assert len(answer.body["items"]) == 25
    print(f"\n[load] one page of 1,200 answered in {answer.elapsed_ms:.1f}ms")
    assert answer.elapsed_ms < 2000
