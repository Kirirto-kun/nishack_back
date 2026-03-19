import argparse
import asyncio
import os
import sys
from pathlib import Path

# Allow running as `python scripts/create_moderator.py` from repo root
sys.path.append(str(Path(__file__).resolve().parents[1]))


async def _run(email: str, password: str) -> None:
    from sqlalchemy import select

    from app.core.security import hash_password
    from app.db.models.enums import UserRole
    from app.db.models.user import User
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none() is not None:
            raise SystemExit(f"User already exists: {email}")

        user = User(
            email=email,
            hashed_password=hash_password(password),
            role=UserRole.moderator,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        print(f"Created moderator: id={user.id} email={user.email}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a moderator user (for local testing).")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument(
        "--postgres-host",
        default=None,
        help="Override POSTGRES_HOST for local runs (e.g. localhost).",
    )
    parser.add_argument("--postgres-user", default=None, help="Override POSTGRES_USER.")
    parser.add_argument("--postgres-password", default=None, help="Override POSTGRES_PASSWORD.")
    parser.add_argument("--postgres-db", default=None, help="Override POSTGRES_DB.")
    parser.add_argument("--postgres-port", default=None, help="Override POSTGRES_PORT.")
    args = parser.parse_args()
    if args.postgres_host:
        os.environ["POSTGRES_HOST"] = args.postgres_host
    if args.postgres_user:
        os.environ["POSTGRES_USER"] = args.postgres_user
    if args.postgres_password:
        os.environ["POSTGRES_PASSWORD"] = args.postgres_password
    if args.postgres_db:
        os.environ["POSTGRES_DB"] = args.postgres_db
    if args.postgres_port:
        os.environ["POSTGRES_PORT"] = str(args.postgres_port)
    asyncio.run(_run(email=args.email, password=args.password))


if __name__ == "__main__":
    main()

