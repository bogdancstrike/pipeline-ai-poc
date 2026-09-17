"""
Shared setup for the live-stack suites.

Every test here needs three things to be true: the stack answers, the database
is up, and the QA corpus is in it. The corpus is seeded once per session and
left behind — it is prefixed, so it is reversible with
`python tests/support/seed.py clear`, and leaving it makes the E2E run that
usually follows immediate.

Seeding is the *only* thing in this directory that touches PostgreSQL from
inside the test process; everything else goes over HTTP. That matters for
isolation: `Config` is a class of module-level values, so the database switch
is flipped for the seed and put back before the first test runs, rather than
left on for whatever else shares the session.
"""

import os
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))

from support import corpus, live  # noqa: E402

pytestmark = pytest.mark.live

#: Big enough for paging, facets and a month of charts; small enough to seed
#: in under a second.
CORPUS_SIZE = int(os.getenv("QA_CORPUS_SIZE", "120"))


@contextmanager
def _database_on():
    """Turn the in-process database on for the length of the block, then off.

    The root conftest turns it off so the unit suite never opens a connection,
    and leaving it on afterwards makes prompt tests read the *stored* wording
    instead of the shipped file — a failure that only appears when both suites
    run in one session, which is the worst kind.
    """
    sys.path.insert(0, str(ROOT / "src"))
    from config import Config

    from client import db, prompt_store

    was_enabled, was_url = Config.DB_ENABLED, Config.DATABASE_URL
    Config.DB_ENABLED = True
    Config.DATABASE_URL = os.getenv(
        "QA_DATABASE_URL", "postgresql+psycopg2://video:video@localhost:5423/video_analysis"
    )
    db._engine = db._maker = None
    db._schema_ready = False
    try:
        yield
    finally:
        Config.DB_ENABLED, Config.DATABASE_URL = was_enabled, was_url
        db._engine = db._maker = None
        db._schema_ready = False
        prompt_store._cache = {}


@pytest.fixture(scope="session", autouse=True)
def stack():
    """Skip the whole suite unless the stack is up, then seed the corpus."""
    if not live.reachable():
        pytest.skip(f"no stack at {live.API_BASE} — docker compose up -d")

    health = live.get("/client/health")
    if health.body.get("status") != "ok":
        pytest.skip(f"the records database is not answering: {health.body}")

    with _database_on():
        from support import seed

        written = seed.seed(CORPUS_SIZE)

    assert written == CORPUS_SIZE, f"seeded {written} of {CORPUS_SIZE}"
    return {"corpus": CORPUS_SIZE}


@pytest.fixture()
def expected():
    """What the seeded corpus adds up to, computed from the generator."""
    return corpus.expected(CORPUS_SIZE)


@pytest.fixture()
def seeded_only():
    """A filter that narrows any search to the seeded records alone.

    The database also holds whatever real runs a developer has made, so a test
    that asserts a total has to say which records it means.
    """
    return {"id__starts": corpus.PREFIX}
