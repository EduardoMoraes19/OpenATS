"""Bootstraps the first super_admin user directly in the database, bypassing
the API - there is no other way to create the very first user, since
POST /api/users (app/modules/user/router.py) itself requires an
authenticated super_admin to call it. Equivalent in spirit to
backend/src/db/seed.ts's "required on first setup" script, but this one is
for users/auth (see app/shared/auth/jwt_auth.py, app/modules/auth/) rather
than pipeline stages (see app/db/seed.py for that).

Run from backend-py/:
    python -m app.db.create_admin --email admin@example.com \\
        --password 'SomeStrongPass1!' --first-name Admin --last-name User
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select

from app.db.base import session_scope
from app.db.models.enums import AppRole
from app.db.models.users import User
from app.logging import get_logger
from app.modules.auth.schemas import validate_password_strength
from app.shared.auth.jwt_auth import hash_password

logger = get_logger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create the first super_admin user.")
    parser.add_argument("--email", required=True, help="Login email for the new super_admin")
    parser.add_argument("--password", required=True, help="Must meet the standard complexity rule")
    parser.add_argument("--first-name", required=True)
    parser.add_argument("--last-name", required=True)
    return parser.parse_args()


async def create_admin(*, email: str, password: str, first_name: str, last_name: str) -> User:
    try:
        validate_password_strength(password)
    except ValueError as exc:
        print(f"Invalid password: {exc}", file=sys.stderr)
        sys.exit(1)

    async with session_scope() as session:
        result = await session.execute(select(User).where(User.email == email))
        existing = result.scalar_one_or_none()
        if existing is not None:
            print(
                f"A user with email {email!r} already exists (id={existing.id}). Aborting.",
                file=sys.stderr,
            )
            sys.exit(1)

        user = User(
            email=email,
            password_hash=hash_password(password),
            role=AppRole.super_admin,
            token_version=0,
            first_name=first_name,
            last_name=last_name,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def _main() -> None:
    args = _parse_args()
    user = await create_admin(
        email=args.email,
        password=args.password,
        first_name=args.first_name,
        last_name=args.last_name,
    )
    logger.info("Created super_admin user id=%s email=%s", user.id, user.email)
    print(f"Created super_admin user: id={user.id} email={user.email}")


if __name__ == "__main__":
    asyncio.run(_main())
