"""
`client.clock` — one definition of "now" and of the windows the UI offers.

Every range preset is resolved server-side so that the KPI header and the chart
underneath it cannot disagree about what "this month" means. These tests pin
the boundaries, because an off-by-one day in a window is invisible until
somebody reconciles two numbers.
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from client import clock


# ── writing a moment down ────────────────────────────────────────────────


def test_iso_renders_utc_with_a_z_suffix():
    moment = datetime(2026, 5, 18, 9, 30, tzinfo=UTC)
    assert clock.iso(moment) == "2026-05-18T09:30:00Z"


def test_a_naive_datetime_is_read_as_utc():
    assert clock.iso(datetime(2026, 5, 18, 9, 30)) == "2026-05-18T09:30:00Z"


def test_an_offset_datetime_is_converted_not_relabelled():
    from datetime import timezone

    madrid = timezone(timedelta(hours=2))
    assert clock.iso(datetime(2026, 5, 18, 11, 30, tzinfo=madrid)) == "2026-05-18T09:30:00Z"


def test_a_date_keeps_its_own_rendering():
    assert clock.iso(date(2026, 5, 18)) == "2026-05-18"


def test_nothing_renders_as_nothing():
    assert clock.iso(None) is None


# ── reading one back ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text",
    ["2026-05-18T09:30:00Z", "2026-05-18T09:30:00+00:00", "2026-05-18T09:30:00"],
)
def test_parse_accepts_every_spelling_the_api_emits(text):
    parsed = clock.parse(text)
    assert parsed == datetime(2026, 5, 18, 9, 30, tzinfo=UTC)
    assert parsed.tzinfo is not None


@pytest.mark.parametrize("junk", ["", None, "not a date", "2026-13-45"])
def test_parse_answers_none_rather_than_raising(junk):
    """A bad `?from=` is a filter that did not apply, not a 500."""
    assert clock.parse(junk) is None


def test_a_round_trip_through_iso_and_parse_is_lossless():
    moment = datetime(2026, 5, 18, 9, 30, 15, tzinfo=UTC)
    assert clock.parse(clock.iso(moment)) == moment


# ── the windows the dashboard offers ─────────────────────────────────────


def test_the_default_window_is_thirty_days():
    start, end = clock.resolve_range(None)
    assert 29 <= (end - start).days <= 30


@pytest.mark.parametrize(
    ("preset", "days"),
    [("last_7_days", 7), ("last_30_days", 30), ("last_90_days", 90)],
)
def test_the_rolling_windows_are_the_length_they_are_named(preset, days):
    start, end = clock.resolve_range(preset)
    assert (end - start).days == days


def test_today_starts_at_midnight():
    start, end = clock.resolve_range("today")
    assert (start.hour, start.minute, start.second, start.microsecond) == (0, 0, 0, 0)
    assert start <= end


def test_yesterday_is_a_closed_day_ending_at_todays_midnight():
    start, end = clock.resolve_range("yesterday")
    assert (end - start).days == 1
    assert end.hour == 0 and end.minute == 0


def test_the_current_month_starts_on_the_first():
    start, _ = clock.resolve_range("current_month")
    assert start.day == 1


def test_the_previous_month_is_closed_at_this_months_first():
    start, end = clock.resolve_range("previous_month")
    assert start.day == 1
    assert end.day == 1
    assert start < end


def test_an_unknown_preset_falls_back_rather_than_failing():
    start, end = clock.resolve_range("last_fortnight_ish")
    assert start < end


def test_the_preset_is_case_insensitive():
    assert clock.resolve_range("LAST_7_DAYS")[0] == pytest.approx(
        clock.resolve_range("last_7_days")[0], abs=timedelta(seconds=2)
    )


# ── the window before this one, for the KPI deltas ───────────────────────


def test_the_previous_period_is_the_same_length_immediately_before():
    start = datetime(2026, 5, 11, tzinfo=UTC)
    end = datetime(2026, 5, 18, tzinfo=UTC)

    previous_start, previous_end = clock.previous_period(start, end)

    assert previous_end == start
    assert (previous_end - previous_start) == (end - start)


def test_ago_counts_back_from_now():
    assert clock.now() - clock.ago(days=2) >= timedelta(days=2) - timedelta(seconds=2)
