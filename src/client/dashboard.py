"""
The dashboard: the KPI tiles and the charts under them.

Every number is computed in PostgreSQL over the *whole* corpus (narrowed by the
date range the header carries), never over the page the explorer happens to be
showing. A tile that averages 25 rows and labels itself "average processing
time" is a lie that looks like a metric.

Each KPI carries its own previous-period value, so "vs previous period" is a
comparison the server made rather than a subtraction the browser guessed at:
the two windows are the same length, ending where the current one begins.

    GET /client/dashboard?range=last_30_days
      { range, kpis: [...], charts: {...} }
"""

from typing import Any, Dict, List, Optional

from sqlalchemy import Float, case, cast, func, select

from client.clock import iso, previous_period, resolve_range
from client.models import RecordCall, RecordEntity, RecordPerson, VideoRecord

#: How many slices a "top N" chart shows before the tail stops being readable.
TOP_N = 10


def overview(session, *, preset: Optional[str] = None, frm: Optional[str] = None,
             to: Optional[str] = None) -> Dict[str, Any]:
    start, end = resolve_range(preset, frm, to)
    previous_start, previous_end = previous_period(start, end)

    current = _window(session, start, end)
    previous = _window(session, previous_start, previous_end)

    return {
        "range": {
            "preset": (preset or "last_30_days"),
            "from": iso(start),
            "to": iso(end),
            "previous_from": iso(previous_start),
            "previous_to": iso(previous_end),
        },
        "kpis": _kpis(current, previous),
        "charts": {
            "volume": _volume(session, start, end),
            "sentiment": _sentiment(session, start, end),
            "entity_types": _entity_types(session, start, end),
            "top_entities": _top_entities(session, start, end),
            "top_persons": _top_persons(session, start, end),
            "service_latency": _service_latency(session, start, end),
        },
    }


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------

def _window(session, start, end) -> Dict[str, Any]:
    """The five aggregate numbers one time window produces, in one query."""
    row = session.execute(
        select(
            func.count(VideoRecord.id),
            func.coalesce(func.avg(VideoRecord.processing_seconds), 0.0),
            func.coalesce(func.sum(VideoRecord.entity_count), 0),
            func.coalesce(func.sum(VideoRecord.person_count), 0),
            func.coalesce(
                func.sum(case((VideoRecord.status == "partial", 1), else_=0)), 0
            ),
        ).where(_between(start, end))
    ).one()

    analysed, avg_seconds, entities, persons, partial = row
    return {
        "analysed": int(analysed or 0),
        "avg_seconds": round(float(avg_seconds or 0.0), 2),
        "entities": int(entities or 0),
        "persons": int(persons or 0),
        "partial": int(partial or 0),
        "failure_rate": round(100.0 * (partial or 0) / analysed, 1) if analysed else 0.0,
    }


def _kpis(current: Dict[str, Any], previous: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One tile per metric, each carrying what it was in the window before.

    `better` says which direction is good, because the tile cannot know: more
    videos analysed is good, more failures is not, and colouring both green
    for "up" is how a dashboard teaches people to ignore it.
    """
    return [
        _kpi("analysed", "Videos analysed", current, previous, unit="", better="up"),
        _kpi("avg_seconds", "Avg processing time", current, previous, unit="s", better="down"),
        _kpi("entities", "Entities extracted", current, previous, unit="", better="up"),
        _kpi("persons", "Person matches", current, previous, unit="", better="up"),
        _kpi("failure_rate", "Partial records", current, previous, unit="%", better="down"),
    ]


def _kpi(key: str, label: str, current: Dict[str, Any], previous: Dict[str, Any],
         *, unit: str, better: str) -> Dict[str, Any]:
    now_value = current[key]
    was = previous[key]
    delta = round(now_value - was, 2)
    return {
        "key": key,
        "label": label,
        "value": now_value,
        "unit": unit,
        "previous": was,
        "delta": delta,
        # None rather than 0 when there is nothing to compare to: "+100%"
        # against an empty previous window is arithmetic, not information.
        "delta_pct": round(100.0 * delta / was, 1) if was else None,
        "better": better,
    }


# ---------------------------------------------------------------------------
# Charts — each returns {labels, series} the frontend maps straight to ECharts
# ---------------------------------------------------------------------------

def _between(start, end):
    return VideoRecord.analysed_at.between(start, end)


def _volume(session, start, end) -> Dict[str, Any]:
    """Videos analysed per day, split by how they ended."""
    day = func.date_trunc("day", VideoRecord.analysed_at)
    rows = session.execute(
        select(
            day,
            func.count(VideoRecord.id),
            func.sum(case((VideoRecord.status == "partial", 1), else_=0)),
        )
        .where(_between(start, end))
        .group_by(day)
        .order_by(day)
    ).all()

    return {
        "labels": [iso(moment) for moment, _, _ in rows],
        "series": [
            {"name": "Analysed", "data": [int(total or 0) for _, total, _ in rows]},
            {"name": "Partial", "data": [int(partial or 0) for _, _, partial in rows]},
        ],
    }


def _sentiment(session, start, end) -> Dict[str, Any]:
    rows = session.execute(
        select(VideoRecord.sentiment, func.count(VideoRecord.id))
        .where(_between(start, end))
        .group_by(VideoRecord.sentiment)
        .order_by(func.count(VideoRecord.id).desc())
    ).all()
    return {
        "labels": [(value or "UNKNOWN") for value, _ in rows],
        "series": [{"name": "Videos", "data": [int(count) for _, count in rows]}],
    }


def _entity_types(session, start, end) -> Dict[str, Any]:
    rows = session.execute(
        select(RecordEntity.type, func.count(RecordEntity.id))
        .join(VideoRecord, VideoRecord.id == RecordEntity.record_id)
        .where(_between(start, end))
        .group_by(RecordEntity.type)
        .order_by(func.count(RecordEntity.id).desc())
        .limit(TOP_N)
    ).all()
    return {
        "labels": [kind for kind, _ in rows],
        "series": [{"name": "Entities", "data": [int(count) for _, count in rows]}],
    }


def _top_entities(session, start, end) -> Dict[str, Any]:
    """The most-mentioned entities, counted once per video.

    `count(distinct record_id)` rather than `count(*)`: an entity a single
    talkative video repeats forty times is not the corpus's top entity.
    """
    rows = session.execute(
        select(
            func.min(RecordEntity.value),
            RecordEntity.value_key,
            func.count(func.distinct(RecordEntity.record_id)),
        )
        .join(VideoRecord, VideoRecord.id == RecordEntity.record_id)
        .where(_between(start, end), RecordEntity.value_key != "")
        .group_by(RecordEntity.value_key)
        .order_by(func.count(func.distinct(RecordEntity.record_id)).desc())
        .limit(TOP_N)
    ).all()
    return {
        "labels": [value for value, _, _ in rows],
        "series": [{"name": "Videos", "data": [int(count) for _, _, count in rows]}],
    }


def _top_persons(session, start, end) -> Dict[str, Any]:
    rows = session.execute(
        select(RecordPerson.person, func.count(func.distinct(RecordPerson.record_id)))
        .join(VideoRecord, VideoRecord.id == RecordPerson.record_id)
        .where(_between(start, end), RecordPerson.person != "")
        .group_by(RecordPerson.person)
        .order_by(func.count(func.distinct(RecordPerson.record_id)).desc())
        .limit(TOP_N)
    ).all()
    return {
        "labels": [person for person, _ in rows],
        "series": [{"name": "Videos", "data": [int(count) for _, count in rows]}],
    }


def _service_latency(session, start, end) -> Dict[str, Any]:
    """Average call time per AI service, with the call count behind it.

    Mocked calls are excluded: they answer in microseconds and would report the
    pipeline as a hundred times faster than it is.
    """
    rows = session.execute(
        select(
            RecordCall.service,
            func.coalesce(func.avg(cast(RecordCall.duration_ms, Float)), 0.0),
            func.count(RecordCall.id),
        )
        .where(RecordCall.analysed_at.between(start, end), RecordCall.mocked.is_(False))
        .group_by(RecordCall.service)
        .order_by(func.avg(cast(RecordCall.duration_ms, Float)).desc())
    ).all()
    return {
        "labels": [service for service, _, _ in rows],
        "series": [
            {
                "name": "Avg ms",
                "data": [round(float(avg or 0.0), 1) for _, avg, _ in rows],
            },
            {"name": "Calls", "data": [int(count) for _, _, count in rows]},
        ],
    }
