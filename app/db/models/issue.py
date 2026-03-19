from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, Float, ForeignKey, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import IssueStatus

if TYPE_CHECKING:
    from app.db.models.user import User


class Issue(Base):
    __tablename__ = "issues"
    __table_args__ = (
        CheckConstraint("priority >= 1 AND priority <= 5", name="ck_issues_priority_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    status: Mapped[IssueStatus] = mapped_column(
        Enum(IssueStatus, name="issuestatus", native_enum=True),
        nullable=False,
    )
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    user: Mapped[User] = relationship("User", back_populates="issues")
