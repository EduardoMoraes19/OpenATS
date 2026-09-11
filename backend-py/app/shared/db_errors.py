"""Postgres error-code helpers, equivalent to backend/src/utils/error.utils.ts.

asyncpg surfaces the 5-char SQLSTATE code as `.sqlstate` on the original
asyncpg exception, which SQLAlchemy wraps in `IntegrityError.orig`.
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError

UNIQUE_VIOLATION = "23505"
FOREIGN_KEY_VIOLATION = "23503"


def pg_error_code(exc: IntegrityError) -> str | None:
    return getattr(exc.orig, "sqlstate", None)


def is_unique_violation(exc: IntegrityError) -> bool:
    return pg_error_code(exc) == UNIQUE_VIOLATION


def is_foreign_key_violation(exc: IntegrityError) -> bool:
    return pg_error_code(exc) == FOREIGN_KEY_VIOLATION
