from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import UserRole

if TYPE_CHECKING:
    from app.db.models.issue import Issue


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="userrole", native_enum=True),
        nullable=False,
    )

    issues: Mapped[list[Issue]] = relationship(
        "Issue",
        back_populates="user",
        cascade="all, delete-orphan",
    )
