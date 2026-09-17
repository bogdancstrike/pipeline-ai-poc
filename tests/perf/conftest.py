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


@pytest.fixture()
def submitted_records():
    """The id prefix for records a test creates by submitting videos.

    Returns the prefix and deletes everything under it afterwards. Submitting
    to `/pipeline/analyze` puts a message on `video.in`, and with every service
    mocked the seven workers turn it into a real row in seconds — thousands of
    them, if the test is a burst. They are not the corpus and must not be left
    in it.
    """
    prefix = "load-"
    yield prefix

    print(f"\n[load] removed {sweep(prefix)} records submitted by this test")
