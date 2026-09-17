"""Time helpers. One definition of "now" and one of "how it is written down"."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta


def now() -> datetime:
    return datetime.now(UTC)


def iso(value: datetime | date | None) -> str | None:
    """ISO-8601 with a `Z` suffix, which is what the browser parses cleanly."""
    if value is None:
        return None
    if isinstance(value, datetime):
        aware = value if value.tzinfo else value.replace(tzinfo=UTC)
        return aware.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return value.isoformat()


def parse(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def ago(**kwargs) -> datetime:
    return now() - timedelta(**kwargs)


#: Named ranges the dashboard offers (§2). Resolved server-side so "this month"
#: means the same thing to the KPI header and to the chart underneath it.
def resolve_range(preset: str | None, frm: str | None = None, to: str | None = None):
    end = now()
    start = end - timedelta(days=30)
    key = (preset or "last_30_days").lower()
    today = end.replace(hour=0, minute=0, second=0, microsecond=0)

    if key == "today":
        start, end = today, end
    elif key == "yesterday":
        start, end = today - timedelta(days=1), today
    elif key == "last_7_days":
        start = end - timedelta(days=7)
    elif key == "last_30_days":
        start = end - timedelta(days=30)
    elif key == "last_90_days":
        start = end - timedelta(days=90)
    elif key == "current_month":
        start = today.replace(day=1)
    elif key == "previous_month":
        first = today.replace(day=1)
        end = first
        start = (first - timedelta(days=1)).replace(day=1)
    elif key == "current_year":
        start = today.replace(month=1, day=1)
    elif key == "previous_year":
        first = today.replace(month=1, day=1)
        end = first
        start = first.replace(year=first.year - 1)
    elif key == "custom":
        start = parse(frm) or start
        end = parse(to) or end
    return start, end


def previous_period(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    """The equally long window immediately before `start` — what "vs previous
    period" on every KPI compares against."""
    span = end - start
    return start - span, start
