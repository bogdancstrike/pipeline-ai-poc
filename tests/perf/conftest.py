"""
Setup shared by the performance and load suites.

Both need the stack up and the corpus seeded — the same session fixture the
integration suite uses, imported rather than copied so the two can never
disagree about how much data is in front of them.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))

# The integration package owns the seeding; reusing its fixtures keeps one
# definition of "the corpus".
from integration.conftest import (  # noqa: E402,F401
    CORPUS_SIZE,
    _database_on,
    expected,
    seeded_only,
    stack,
    sweep,
)

from support import live  # noqa: E402


@pytest.fixture(scope="session")
def warm():
    """One call per endpoint before anything is timed.

    The first request to a Flask process pays for imports, the first query
    against a cold connection pool pays for the handshake, and the first
    statement of a shape pays for the plan. None of those are what a reader
    experiences on the tenth search, and a benchmark that includes them
    measures the boot.
    """
    for _ in range(3):
        live.post("/client/records/search", {"page_size": 25, "facets": True})
        live.get("/client/dashboard?range=last_30_days")
        live.get("/client/statistics?range=last_30_days")
        live.get("/client/meta")
    return True


@pytest.fixture()
def reseed():
    """Re-seed the corpus at a given size, and put it back at 120 afterwards.

    The database switch is off for the rest of the session on purpose (see
    `integration/conftest.py`), so a test that needs to write has to say so.
    """
    from support import seed

    def _seed(count: int) -> int:
        with _database_on():
            return seed.seed(count)

    yield _seed

    with _database_on():
        seed.seed(CORPUS_SIZE)


class Submissions:
    """The id prefix a test submits under, and how many it submitted.

    The count is what lets the sweep know when it is finished: the pipeline is
    asynchronous, and "no new records for a few seconds" means nothing when the
    workers are a minute behind.

    The prefix carries a token unique to this run, because the ids must be too.
    Reusing `load-1` between runs let a sweep count rows the *previous* run had
    left, decide it was done, and leave this run's behind — which is how 207 of
    207 were removed and 207 were still there afterwards.
    """

    def __init__(self):
        import uuid

        self.prefix = f"load-{uuid.uuid4().hex[:8]}-"
        self.count = 0

    def id(self) -> str:
        self.count += 1
        return f"{self.prefix}{self.count}"


@pytest.fixture()
def submitted_records():
    """Hand out ids, then delete every record they became.

    Submitting to `/pipeline/analyze` puts a message on `video.in`, and with
    every service mocked the seven workers turn it into a real row. They are
    not the corpus and must not be left in it.
    """
    submissions = Submissions()
    yield submissions

    removed = sweep(submissions.prefix, expect=submissions.count, timeout=180)
    print(f"\n[load] removed {removed} of {submissions.count} records submitted by this test")
