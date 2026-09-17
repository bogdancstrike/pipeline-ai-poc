"""
A small load generator: N workers, a fixed duration, one scenario each.

Deliberately not a framework. What these tests need is a number of concurrent
clients, a wall-clock window and an honest histogram — and a dependency that
has to be installed before the suite runs is a suite that stops being run.

Threads rather than asyncio because the thing under test is a *synchronous*
Flask app behind a thread pool: the contention that matters is on its side, and
the client only has to be able to keep the pipe full.
"""

from __future__ import annotations

import statistics
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List


@dataclass
class Result:
    """What one run of one scenario produced."""

    name: str
    concurrency: int
    seconds: float
    latencies_ms: List[float] = field(default_factory=list)
    statuses: Dict[int, int] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    @property
    def requests(self) -> int:
        return len(self.latencies_ms)

    @property
    def throughput(self) -> float:
        return self.requests / self.seconds if self.seconds else 0.0

    @property
    def ok(self) -> int:
        return sum(count for status, count in self.statuses.items() if 200 <= status < 400)

    @property
    def failure_rate(self) -> float:
        total = self.requests + len(self.errors)
        bad = total - self.ok
        return 100.0 * bad / total if total else 0.0

    def percentile(self, fraction: float) -> float:
        if not self.latencies_ms:
            return 0.0
        ordered = sorted(self.latencies_ms)
        index = min(len(ordered) - 1, int(len(ordered) * fraction))
        return ordered[index]

    @property
    def median(self) -> float:
        return statistics.median(self.latencies_ms) if self.latencies_ms else 0.0

    def line(self) -> str:
        return (
            f"[load] {self.name:<28} c={self.concurrency:<3} "
            f"{self.requests:>5} reqs in {self.seconds:>4.1f}s  "
            f"{self.throughput:>6.1f} req/s  "
            f"median={self.median:>6.1f}ms p95={self.percentile(0.95):>7.1f}ms "
            f"p99={self.percentile(0.99):>7.1f}ms max={max(self.latencies_ms or [0]):>7.1f}ms  "
            f"fail={self.failure_rate:.1f}%"
        )


def drive(
    name: str,
    scenario: Callable[[], object],
    *,
    concurrency: int = 8,
    seconds: float = 5.0,
    max_requests: int | None = None,
) -> Result:
    """Run `scenario` from `concurrency` threads for `seconds`, and report.

    `scenario` returns anything with a `.status`; an exception is recorded
    rather than raised, because a load test that stops at the first refusal
    measures nothing about what happens under load.

    `max_requests` stops early. It matters for a scenario with a *cost after the
    response*: submitting a video answers in 9ms and leaves seven workers busy,
    so three seconds of it queues thousands of messages and the next test waits
    behind them. What that scenario is testing is concurrency, not volume.
    """
    result = Result(name=name, concurrency=concurrency, seconds=seconds)
    lock = threading.Lock()
    stop = threading.Event()

    def worker():
        while not stop.is_set():
            if max_requests is not None:
                with lock:
                    if len(result.latencies_ms) >= max_requests:
                        stop.set()
                        return
            started = time.perf_counter()
            try:
                answer = scenario()
            except Exception as exc:  # noqa: BLE001 — recorded, not raised
                with lock:
                    result.errors.append(f"{type(exc).__name__}: {exc}")
                continue
            elapsed = (time.perf_counter() - started) * 1000
            status = int(getattr(answer, "status", 0))
            with lock:
                result.latencies_ms.append(elapsed)
                result.statuses[status] = result.statuses.get(status, 0) + 1

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(concurrency)]
    began = time.perf_counter()
    for thread in threads:
        thread.start()
    time.sleep(seconds)
    stop.set()
    for thread in threads:
        thread.join(timeout=30)
    result.seconds = time.perf_counter() - began

    return result
