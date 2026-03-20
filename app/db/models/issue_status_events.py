from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import IssueStatus


class IssueStatusEvent(Base):
    __tablename__ = "issue_status_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), nullable=False, index=True)

    # Store as plain strings to avoid enum-type duplication during migrations.
    # Pydantic will coerce these back to `IssueStatus` when building response schemas.
    from_status: Mapped[str] = mapped_column(String(50), nullable=False)
    to_status: Mapped[str] = mapped_column(String(50), nullable=False)

    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(tz=timezone.utc),
    )

    actor_role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    issue: Mapped["Issue"] = relationship("Issue", back_populates="status_events")

