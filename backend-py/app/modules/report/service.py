"""Analytics report aggregation: pure raw-SQL queries (no ORM query builder)
via SQLAlchemy's `text()`, with in-application bucketing/month-trend loops,
rounding helpers, and a 60s in-memory cache per (period, department).
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.cache import TtlCache

_cache = TtlCache(ttl_seconds=60)

_PERIOD_DAYS = {"7d": 7, "30d": 30, "90d": 90}

_MONTH_ABBREVIATIONS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)


def _period_days(period: str) -> int:
    return _PERIOD_DAYS.get(period, 7)


def _round(value: float, digits: int = 2) -> float:
    """Matches JS `Math.round`, which rounds half-away-from-zero-towards
    +Infinity (`floor(x + 0.5)`) - not Python's banker's-rounding `round()`.
    Returns a plain `int` when the result is whole, mirroring JS's single
    `number` type (no float/int split) so JSON serializes `5`, not `5.0`.
    """
    factor = 10**digits
    result = math.floor(value * factor + 0.5) / factor
    return int(result) if result == int(result) else result


def _safe_pct(current: float, previous: float) -> float:
    if previous <= 0:
        return 100 if current > 0 else 0
    return _round((current - previous) / previous * 100, 1)


def _day_key(value: datetime) -> str:
    return value.date().isoformat()


def _short_date_label(value: datetime) -> str:
    return f"{_MONTH_ABBREVIATIONS[value.month - 1]} {value.day}"


def _month_label(value: datetime) -> str:
    return _MONTH_ABBREVIATIONS[value.month - 1]


def _month_start(base: datetime, offset_months: int) -> datetime:
    """`new Date(base.getFullYear(), base.getMonth() + offsetMonths, 1)` -
    JS auto-rolls negative/overflowing months across year boundaries;
    Python's `datetime` does not, so the rollover is done by hand here.
    """
    total = base.year * 12 + (base.month - 1) + offset_months
    year, month0 = divmod(total, 12)
    return datetime(year, month0 + 1, 1)


def _build_date_buckets(
    start: datetime, end: datetime, bucket_count: int = 6
) -> list[dict[str, Any]]:
    total_ms = int((end - start).total_seconds() * 1000)
    size_ms = max(1, total_ms // bucket_count)
    size = timedelta(milliseconds=size_ms)

    buckets: list[dict[str, Any]] = []
    cursor = start
    for i in range(bucket_count):
        nxt = end if i == bucket_count - 1 else cursor + size
        buckets.append({"start": cursor, "end": nxt, "label": _short_date_label(cursor)})
        cursor = nxt
    return buckets


def _sum_bucket(bucket_start: datetime, bucket_end: datetime, counts: dict[str, int]) -> int:
    total = 0
    d = bucket_start
    while d < bucket_end:
        total += counts.get(_day_key(d), 0)
        d = d + timedelta(days=1)
    return total


def _csv_cell(value: Any) -> str:
    """Mirrors JS `String(cell)`: a whole-number float must render without
    a trailing `.0` (JS has one numeric type, so `5.0 === 5`)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value)


def _build_csv(report: dict[str, Any]) -> str:
    summary = report["summary"]
    rows: list[list[Any]] = [
        ["=== Summary ==="],
        ["Metric", "Value"],
        ["Total Candidates", summary["totalCandidates"]],
        ["Open Positions", summary["openPositions"]],
        ["Avg. Time To Hire (Days)", summary["avgTimeToHireDays"]],
        ["Offer Acceptance Rate (%)", summary["offerAcceptanceRate"]],
        [],
        ["=== Pipeline Report ==="],
        ["Stage", "This Period", "Previous Period"],
        *[[d["stage"], d["current"], d["previous"]] for d in report["pipelineReport"]],
        [],
        ["=== Candidate Volume ==="],
        ["Date", "Applications", "Hires"],
        *[[d["date"], d["applications"], d["hires"]] for d in report["candidateVolume"]],
        [],
        ["=== Source of Candidates ==="],
        ["Source", "Percentage"],
        *[[d["name"], f"{d['value']}%"] for d in report["sourceOfCandidates"]],
        [],
        ["=== Time to Hire by Dept ==="],
        ["Department", "Avg Days"],
        *[[d["dept"], d["days"]] for d in report["timeToHireByDepartment"]],
        [],
        ["=== Offer Trends ==="],
        ["Month", "Sent", "Accepted"],
        *[[d["month"], d["sent"], d["accepted"]] for d in report["offerTrends"]],
    ]

    return "\n".join(
        ",".join(f'"{_csv_cell(cell).replace(chr(34), chr(34) * 2)}"' for cell in row)
        for row in rows
    )


async def get_analytics(db: AsyncSession, *, period: str, department_id: int | None) -> dict[str, Any]:
    cache_key = f"{period}|{department_id if department_id is not None else 'all'}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    days = _period_days(period)
    # Naive but UTC: the `timestamp` (no tz) columns here (applied_at/
    # created_at/moved_at/...) are populated by Postgres's own `now()` under
    # a UTC session timezone, so they hold true-UTC wall-clock values with no
    # offset attached. The query parameter must match that, or every "now"
    # bound into these queries silently drifts behind the row timestamps by
    # the host's local UTC offset (on a UTC-3 host, `datetime.now()` returns
    # a value 3 hours behind these columns, making recently-created rows look
    # like they're "in the future" and dropping them from every window).
    now = datetime.now(UTC).replace(tzinfo=None)
    current_start = now - timedelta(days=days)
    previous_start = current_start - timedelta(days=days)

    dept_filter = "AND j.department_id = :department_id" if department_id is not None else ""
    month_start = _month_start(now, -4)
    params: dict[str, Any] = {
        "current_start": current_start,
        "previous_start": previous_start,
        "now": now,
        "month_start": month_start,
    }
    if department_id is not None:
        params["department_id"] = department_id

    total_candidates = (
        await db.execute(
            text(f"""
                SELECT COUNT(*) AS count
                FROM candidates c
                INNER JOIN jobs j ON j.id = c.job_id
                WHERE 1=1 {dept_filter}
            """),
            params,
        )
    ).scalar_one()

    candidate_period = (
        await db.execute(
            text(f"""
                SELECT
                    SUM(CASE WHEN c.applied_at >= :current_start
                             AND c.applied_at < :now THEN 1 ELSE 0 END) AS current_count,
                    SUM(CASE WHEN c.applied_at >= :previous_start
                             AND c.applied_at < :current_start THEN 1 ELSE 0 END) AS previous_count
                FROM candidates c
                INNER JOIN jobs j ON j.id = c.job_id
                WHERE 1=1 {dept_filter}
            """),
            params,
        )
    ).mappings().one()

    open_position = (
        await db.execute(
            text(f"""
                SELECT
                    SUM(CASE WHEN j.status NOT IN ('closed', 'archived') THEN 1 ELSE 0 END) AS open_count,
                    SUM(CASE WHEN j.created_at >= :current_start
                             AND j.created_at < :now THEN 1 ELSE 0 END) AS current_opened,
                    SUM(CASE WHEN j.created_at >= :previous_start
                             AND j.created_at < :current_start THEN 1 ELSE 0 END) AS previous_opened
                FROM jobs j
                WHERE 1=1 {dept_filter}
            """),
            params,
        )
    ).mappings().one()

    hire_time = (
        await db.execute(
            text(f"""
                SELECT
                    AVG(CASE
                        WHEN o.status = 'accepted' AND o.updated_at >= :current_start AND o.updated_at < :now
                        THEN EXTRACT(EPOCH FROM (o.updated_at - c.applied_at)) / 86400.0
                        ELSE NULL
                    END) AS current_days,
                    AVG(CASE
                        WHEN o.status = 'accepted' AND o.updated_at >= :previous_start AND o.updated_at < :current_start
                        THEN EXTRACT(EPOCH FROM (o.updated_at - c.applied_at)) / 86400.0
                        ELSE NULL
                    END) AS previous_days
                FROM offers o
                INNER JOIN candidates c ON c.id = o.candidate_id
                INNER JOIN jobs j ON j.id = o.job_id
                WHERE 1=1 {dept_filter}
            """),
            params,
        )
    ).mappings().one()

    offer_rate = (
        await db.execute(
            text(f"""
                SELECT
                    SUM(CASE WHEN COALESCE(o.sent_at, o.created_at) >= :current_start
                             AND COALESCE(o.sent_at, o.created_at) < :now
                             THEN 1 ELSE 0 END) AS current_sent,
                    SUM(CASE WHEN COALESCE(o.sent_at, o.created_at) >= :current_start
                             AND COALESCE(o.sent_at, o.created_at) < :now
                             AND o.status = 'accepted' THEN 1 ELSE 0 END) AS current_accepted,
                    SUM(CASE WHEN COALESCE(o.sent_at, o.created_at) >= :previous_start
                             AND COALESCE(o.sent_at, o.created_at) < :current_start
                             THEN 1 ELSE 0 END) AS previous_sent,
                    SUM(CASE WHEN COALESCE(o.sent_at, o.created_at) >= :previous_start
                             AND COALESCE(o.sent_at, o.created_at) < :current_start
                             AND o.status = 'accepted' THEN 1 ELSE 0 END) AS previous_accepted
                FROM offers o
                INNER JOIN jobs j ON j.id = o.job_id
                WHERE 1=1 {dept_filter}
            """),
            params,
        )
    ).mappings().one()

    pipeline_rows = (
        await db.execute(
            text(f"""
                SELECT
                    s.name AS stage,
                    SUM(CASE WHEN h.moved_at >= :current_start
                             AND h.moved_at < :now THEN 1 ELSE 0 END) AS current_count,
                    SUM(CASE WHEN h.moved_at >= :previous_start
                             AND h.moved_at < :current_start THEN 1 ELSE 0 END) AS previous_count,
                    MIN(s.position)::int AS stage_position
                FROM candidate_stage_history h
                INNER JOIN job_pipeline_stages s ON s.id = h.stage_id
                INNER JOIN jobs j ON j.id = s.job_id
                WHERE 1=1 {dept_filter}
                GROUP BY s.name
                ORDER BY stage_position ASC
            """),
            params,
        )
    ).mappings().all()

    app_by_day_rows = (
        await db.execute(
            text(f"""
                SELECT
                    TO_CHAR(c.applied_at::date, 'YYYY-MM-DD') AS day_key,
                    COUNT(*) AS count
                FROM candidates c
                INNER JOIN jobs j ON j.id = c.job_id
                WHERE c.applied_at >= :current_start AND c.applied_at < :now
                {dept_filter}
                GROUP BY c.applied_at::date
                ORDER BY c.applied_at::date ASC
            """),
            params,
        )
    ).mappings().all()

    hire_by_day_rows = (
        await db.execute(
            text(f"""
                SELECT
                    TO_CHAR(o.updated_at::date, 'YYYY-MM-DD') AS day_key,
                    COUNT(*) AS count
                FROM offers o
                INNER JOIN jobs j ON j.id = o.job_id
                WHERE o.status = 'accepted'
                    AND o.updated_at >= :current_start
                    AND o.updated_at < :now
                {dept_filter}
                GROUP BY o.updated_at::date
                ORDER BY o.updated_at::date ASC
            """),
            params,
        )
    ).mappings().all()

    source_rows = (
        await db.execute(
            text(f"""
                SELECT
                    s.name AS source_name,
                    COUNT(*) AS count
                FROM candidates c
                INNER JOIN job_pipeline_stages s ON s.id = c.current_stage_id
                INNER JOIN jobs j ON j.id = c.job_id
                WHERE 1=1
                {dept_filter}
                GROUP BY s.name
                ORDER BY COUNT(*) DESC
            """),
            params,
        )
    ).mappings().all()

    dept_hire_rows = (
        await db.execute(
            text(f"""
                SELECT
                    d.name AS department_name,
                    AVG(EXTRACT(EPOCH FROM (o.updated_at - c.applied_at)) / 86400.0) AS avg_days
                FROM offers o
                INNER JOIN candidates c ON c.id = o.candidate_id
                INNER JOIN jobs j ON j.id = o.job_id
                INNER JOIN departments d ON d.id = j.department_id
                WHERE o.status = 'accepted'
                {dept_filter}
                GROUP BY d.name
                ORDER BY d.name ASC
            """),
            params,
        )
    ).mappings().all()

    offer_trend_rows = (
        await db.execute(
            text(f"""
                SELECT
                    TO_CHAR(DATE_TRUNC('month', COALESCE(o.sent_at, o.created_at)), 'YYYY-MM') AS month_key,
                    COUNT(*) AS sent_count,
                    SUM(CASE WHEN o.status = 'accepted' THEN 1 ELSE 0 END) AS accepted_count
                FROM offers o
                INNER JOIN jobs j ON j.id = o.job_id
                WHERE COALESCE(o.sent_at, o.created_at) >= :month_start
                {dept_filter}
                GROUP BY DATE_TRUNC('month', COALESCE(o.sent_at, o.created_at))
                ORDER BY DATE_TRUNC('month', COALESCE(o.sent_at, o.created_at)) ASC
            """),
            params,
        )
    ).mappings().all()

    total_candidates_n = int(total_candidates or 0)
    current_candidates = int(candidate_period["current_count"] or 0)
    previous_candidates = int(candidate_period["previous_count"] or 0)

    open_positions = int(open_position["open_count"] or 0)
    current_opened = int(open_position["current_opened"] or 0)
    previous_opened = int(open_position["previous_opened"] or 0)

    current_hire_days = float(hire_time["current_days"] or 0)
    previous_hire_days = float(hire_time["previous_days"] or 0)

    current_sent = int(offer_rate["current_sent"] or 0)
    current_accepted = int(offer_rate["current_accepted"] or 0)
    previous_sent = int(offer_rate["previous_sent"] or 0)
    previous_accepted = int(offer_rate["previous_accepted"] or 0)

    current_offer_rate = (current_accepted / current_sent * 100) if current_sent > 0 else 0.0
    previous_offer_rate = (previous_accepted / previous_sent * 100) if previous_sent > 0 else 0.0

    pipeline_report = [
        {
            "stage": row["stage"],
            "current": int(row["current_count"] or 0),
            "previous": int(row["previous_count"] or 0),
        }
        for row in pipeline_rows
    ]

    app_count_by_day = {row["day_key"]: int(row["count"] or 0) for row in app_by_day_rows}
    hire_count_by_day = {row["day_key"]: int(row["count"] or 0) for row in hire_by_day_rows}

    buckets = _build_date_buckets(current_start, now, 6)
    candidate_volume = [
        {
            "date": bucket["label"],
            "applications": _sum_bucket(bucket["start"], bucket["end"], app_count_by_day),
            "hires": _sum_bucket(bucket["start"], bucket["end"], hire_count_by_day),
        }
        for bucket in buckets
    ]

    source_counts = [
        {"name": row["source_name"], "count": int(row["count"] or 0)} for row in source_rows
    ]
    source_total = sum(item["count"] for item in source_counts)
    source_of_candidates = (
        [
            {"name": item["name"], "value": int(_round(item["count"] / source_total * 100, 0))}
            for item in source_counts
        ]
        if source_total > 0
        else [{"name": "Website", "value": 100}]
    )

    time_to_hire_by_department = [
        {"dept": row["department_name"], "days": _round(float(row["avg_days"] or 0), 1)}
        for row in dept_hire_rows
    ]

    trend_map = {
        row["month_key"]: {
            "sent": int(row["sent_count"] or 0),
            "accepted": int(row["accepted_count"] or 0),
        }
        for row in offer_trend_rows
    }

    offer_trends = []
    for i in range(4, -1, -1):
        month_date = _month_start(now, -i)
        month_key = f"{month_date.year}-{month_date.month:02d}"
        data = trend_map.get(month_key, {"sent": 0, "accepted": 0})
        offer_trends.append(
            {"month": _month_label(month_date), "sent": data["sent"], "accepted": data["accepted"]}
        )

    report: dict[str, Any] = {
        "summary": {
            "totalCandidates": total_candidates_n,
            "totalCandidatesDeltaPct": _safe_pct(current_candidates, previous_candidates),
            "openPositions": open_positions,
            "openPositionsDelta": current_opened - previous_opened,
            "avgTimeToHireDays": _round(current_hire_days, 1),
            "avgTimeToHireDeltaDays": _round(previous_hire_days - current_hire_days, 1),
            "offerAcceptanceRate": _round(current_offer_rate, 1),
            "offerAcceptanceRateDeltaPct": _round(current_offer_rate - previous_offer_rate, 1),
        },
        "pipelineReport": pipeline_report,
        "candidateVolume": candidate_volume,
        "sourceOfCandidates": source_of_candidates,
        "timeToHireByDepartment": time_to_hire_by_department,
        "offerTrends": offer_trends,
    }

    _cache.set(cache_key, report)
    return report


async def export_analytics(
    db: AsyncSession, *, period: str, department_id: int | None, format_: str
) -> dict[str, Any]:
    report = await get_analytics(db, period=period, department_id=department_id)

    if format_ == "json":
        import json

        return {
            "format": "json",
            "fileName": f"openats-report-{period}.json",
            "mimeType": "application/json",
            "content": json.dumps(report, indent=2),
        }

    return {
        "format": "csv",
        "fileName": f"openats-report-{period}.csv",
        "mimeType": "text/csv",
        "content": _build_csv(report),
    }
