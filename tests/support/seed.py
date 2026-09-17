"""
Put the QA corpus into PostgreSQL, and take it out again.

    python tests/support/seed.py seed --count 120
    python tests/support/seed.py clear
    python tests/support/seed.py count

Seeding is **idempotent and additive**: it deletes only the rows whose id
starts with `corpus.PREFIX` and writes them again. Records produced by real
runs are never touched, which is what makes it safe to point this at a
developer's own stack — the one it is meant for.

Records go in through `client.store.save_record`, the same writer W7 uses, so
the flattened columns, the entity split, the person rows and the call rows are
all produced by the code under test rather than by this file.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

# The seeder writes to a real database by definition; the unit-test default of
# DB_ENABLED=false would make every save a silent no-op.
os.environ.setdefault("DB_ENABLED", "true")
os.environ.setdefault("LOGGING_LEVEL", "WARNING")

from support import corpus  # noqa: E402

DEFAULT_COUNT = 120


def _db():
    from client import db

    return db


def clear(prefix: str = corpus.PREFIX) -> int:
    """Delete every row whose id starts with `prefix`. Children cascade.

    The default is the QA corpus. The other caller is the load suite, which
    submits real videos to Kafka and therefore leaves real records behind —
    they are prefixed for the same reason these are.
    """
    from sqlalchemy import delete

    from client.models import VideoRecord

    db = _db()
    db.create_schema()
    with db.session_scope() as session:
        result = session.execute(delete(VideoRecord).where(VideoRecord.id.like(f"{prefix}%")))
        return int(result.rowcount or 0)


def seed(count: int = DEFAULT_COUNT) -> int:
    """Replace the seeded corpus with `count` fresh records. Returns how many."""
    from client import store

    clear()
    written = 0
    for index in range(count):
        if store.save_record(corpus.record(index), corpus.calls(index)):
            written += 1
    return written


def count() -> dict:
    from sqlalchemy import func, select

    from client.models import VideoRecord

    db = _db()
    db.create_schema()
    with db.session_scope() as session:
        seeded = session.scalar(
            select(func.count())
            .select_from(VideoRecord)
            .where(VideoRecord.id.like(f"{corpus.PREFIX}%"))
        )
        everything = session.scalar(select(func.count()).select_from(VideoRecord))
    return {"seeded": int(seeded or 0), "total": int(everything or 0)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seed", "clear", "count"))
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT)
    parser.add_argument(
        "--prefix",
        default=corpus.PREFIX,
        help="which ids to clear (default: the QA corpus). Try `load-` or `probe-`.",
    )
    args = parser.parse_args(argv)

    started = time.monotonic()
    if args.action == "seed":
        written = seed(args.count)
        elapsed = time.monotonic() - started
        print(f"seeded {written} records in {elapsed:.2f}s ({written / max(elapsed, 1e-9):.0f}/s)")
        return 0 if written == args.count else 1
    if args.action == "clear":
        print(f"deleted {clear(args.prefix)} records with ids starting {args.prefix!r}")
        return 0
    print(count())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
