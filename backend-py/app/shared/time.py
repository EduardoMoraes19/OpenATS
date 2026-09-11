"""Datetime helpers for the naive-timestamp columns this schema uses
throughout (every `timestamp` column in the source Drizzle schema is
WITHOUT TIME ZONE - see app/db/models/mixins.py). asyncpg refuses to write a
timezone-aware datetime.datetime into one of those columns, so any datetime
that arrives from a request body (which Pydantic parses as tz-aware when the
client sends an offset, e.g. "...+00:00" or "...Z") must be normalized
before it reaches the DB.
"""

from __future__ import annotations

from datetime import UTC, datetime


def to_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)
