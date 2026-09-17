"""
The statistics page: how the seven AI calls are actually behaving.

The dashboard answers "what is in the corpus"; this answers "what did it cost
to get it". Both read the same `record_calls` rows W7 stored, which carry the
provenance the record itself leaves out — mocked or live, which URL, how long,
and the error when a service would not answer.

Latency is reported as a median and a p95 rather than only a mean, because one
cold model load is enough to make a mean describe a run that never happened.
Mocked calls are counted and reported *separately*: folding a canned answer
into a latency average is how a pipeline gets reported as instantaneous.
"""

from typing import Any, Dict, List, Optional

from sqlalchemy import Float, case, cast, func, select

from client.clock import iso, resolve_range
from client.models import RecordCall, VideoRecord


def services(session, *, preset: Optional[str] = None, frm: Optional[str] = None,
             to: Optional[str] = None) -> Dict[str, Any]:
    start, end = resolve_range(preset, frm, to)
    window = RecordCall.analysed_at.between(start, end)

    live_ms = case((RecordCall.mocked.is_(False), cast(RecordCall.duration_ms, Float)))

    rows = session.execute(
        select(
            RecordCall.service,
            func.count(RecordCall.id),
            func.sum(case((RecordCall.mocked.is_(True), 1), else_=0)),
            func.sum(case((RecordCall.ok.is_(False), 1), else_=0)),
            func.avg(live_ms),
            func.percentile_cont(0.5).within_group(live_ms),
            func.percentile_cont(0.95).within_group(live_ms),
            func.max(live_ms),
            func.sum(func.coalesce(RecordCall.input_tokens, 0)),
            func.sum(func.coalesce(RecordCall.output_tokens, 0)),
        )
        .where(window)
        .group_by(RecordCall.service)
        .order_by(RecordCall.service)
    ).all()

    items: List[Dict[str, Any]] = []
    for (service, calls, mocked, failed, avg_ms, median_ms, p95_ms, max_ms,
         input_tokens, output_tokens) in rows:
        calls = int(calls or 0)
        failed = int(failed or 0)
        items.append(
            {
                "service": service,
                "calls": calls,
                "mocked": int(mocked or 0),
                "live": calls - int(mocked or 0),
                "failed": failed,
                "failure_rate": round(100.0 * failed / calls, 1) if calls else 0.0,
                "avg_ms": _ms(avg_ms),
                "median_ms": _ms(median_ms),
                "p95_ms": _ms(p95_ms),
                "max_ms": _ms(max_ms),
                "input_tokens": int(input_tokens or 0),
                "output_tokens": int(output_tokens or 0),
            }
        )

    return {
        "range": {"preset": (preset or "last_30_days"), "from": iso(start), "to": iso(end)},
        "items": items,
        "totals": _totals(items),
        "models": _models(session, start, end),
        "failures": _failures(session, start, end),
        "throughput": _throughput(session, start, end),
    }


def _ms(value: Any) -> Optional[float]:
    return round(float(value), 1) if value is not None else None


def _totals(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    calls = sum(item["calls"] for item in items)
    failed = sum(item["failed"] for item in items)
    return {
        "calls": calls,
        "live": sum(item["live"] for item in items),
        "mocked": sum(item["mocked"] for item in items),
        "failed": failed,
        "failure_rate": round(100.0 * failed / calls, 1) if calls else 0.0,
        "input_tokens": sum(item["input_tokens"] for item in items),
        "output_tokens": sum(item["output_tokens"] for item in items),
    }


def _models(session, start, end) -> List[Dict[str, Any]]:
    """Which model answered how many calls, and how fast — the summary service
    is the one that can change model underneath a corpus."""
    rows = session.execute(
        select(
            RecordCall.model,
            RecordCall.provider,
            func.count(RecordCall.id),
            func.avg(cast(RecordCall.duration_ms, Float)),
            func.sum(func.coalesce(RecordCall.output_tokens, 0)),
        )
        .where(RecordCall.analysed_at.between(start, end), RecordCall.model != "")
        .group_by(RecordCall.model, RecordCall.provider)
        .order_by(func.count(RecordCall.id).desc())
    ).all()
    return [
        {
            "model": model,
            "provider": provider,
            "calls": int(calls or 0),
            "avg_ms": _ms(avg_ms),
            "output_tokens": int(tokens or 0),
        }
        for model, provider, calls, avg_ms, tokens in rows
    ]


def _failures(session, start, end) -> List[Dict[str, Any]]:
    """The most recent refusals, with the message the service gave.

    A count of failures tells you something is wrong; the message tells you
    what, and it is the one thing a log search would otherwise be needed for.
    """
    rows = session.execute(
        select(RecordCall.record_id, RecordCall.service, RecordCall.error,
               RecordCall.analysed_at, VideoRecord.name)
        .join(VideoRecord, VideoRecord.id == RecordCall.record_id)
        .where(RecordCall.analysed_at.between(start, end), RecordCall.ok.is_(False))
        .order_by(RecordCall.analysed_at.desc())
        .limit(25)
    ).all()
    return [
        {
            "record_id": record_id,
            "name": name,
            "service": service,
            "error": error,
            "analysed_at": iso(moment),
        }
        for record_id, service, error, moment, name in rows
    ]


def _throughput(session, start, end) -> Dict[str, Any]:
    """Calls and average latency per day — the shape of a bad afternoon."""
    day = func.date_trunc("day", RecordCall.analysed_at)
    rows = session.execute(
        select(
            day,
            func.count(RecordCall.id),
            func.avg(case((RecordCall.mocked.is_(False), cast(RecordCall.duration_ms, Float)))),
            func.sum(case((RecordCall.ok.is_(False), 1), else_=0)),
        )
        .where(RecordCall.analysed_at.between(start, end))
        .group_by(day)
        .order_by(day)
    ).all()
    return {
        "labels": [iso(moment) for moment, _, _, _ in rows],
        "series": [
            {"name": "Calls", "data": [int(calls or 0) for _, calls, _, _ in rows]},
            {"name": "Avg ms", "data": [_ms(avg) or 0 for _, _, avg, _ in rows]},
            {"name": "Failed", "data": [int(failed or 0) for _, _, _, failed in rows]},
        ],
    }
