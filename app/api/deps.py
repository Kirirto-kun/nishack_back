from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.models.enums import UserRole
from app.db.models.user import User
from app.db.session import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        sub = decode_access_token(token)
        user_id = int(sub)
    except (JWTError, ValueError):
        raise credentials_exception from None

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user


async def get_current_moderator(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if user.role != UserRole.moderator:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Moderator role required",
        )
    return user


async def get_optional_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User | None:
    """Optional bearer auth for endpoints that support public access.

    Returns None if auth is missing/invalid.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return None

    token = auth_header.split(" ", 1)[1].strip()
    try:
        sub = decode_access_token(token)
        user_id = int(sub)
    except (JWTError, ValueError):
        return None

    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
