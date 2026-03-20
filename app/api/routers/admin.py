from __future__ import annotations

from typing import Annotated
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_moderator
from app.db.models.enums import IssueStatus
from app.db.models.issue import Issue
from app.db.models.issue_status_events import IssueStatusEvent
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.issue import IssueAdminRead, IssueAdminUpdate

router = APIRouter(prefix="/admin", tags=["admin"])


def _issue_to_admin_read(issue: Issue) -> IssueAdminRead:
    reporter_email = issue.user.email if issue.user is not None else None
    return IssueAdminRead(
        id=issue.id,
        user_id=issue.user_id,
        title=issue.title,
        description=issue.description,
        latitude=issue.latitude,
        longitude=issue.longitude,
        image_url=issue.image_url,
        status=issue.status,
        priority=issue.priority,
        category=issue.category,
        ai_admin_summary=issue.ai_admin_summary,
        ai_analyzed_at=issue.ai_analyzed_at,
        ai_error=issue.ai_error,
        reporter_email=reporter_email,
    )

_PATCH_ALLOWED: set[IssueStatus] = {
    IssueStatus.approved,
    IssueStatus.rejected,
    IssueStatus.in_progress,
    IssueStatus.resolved,
}


@router.get("/issues", response_model=list[IssueAdminRead])
async def list_issues(
    db: Annotated[AsyncSession, Depends(get_db)],
    _moderator: Annotated[User, Depends(get_current_moderator)],
    status_filter: Annotated[list[IssueStatus] | None, Query(alias="status")] = None,
    hide_rejected: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[IssueAdminRead]:
    stmt = select(Issue).options(selectinload(Issue.user))

    if status_filter:
        stmt = stmt.where(Issue.status.in_(status_filter))
    if hide_rejected:
        stmt = stmt.where(Issue.status != IssueStatus.rejected)

    stmt = (
        stmt.order_by(desc(Issue.priority), desc(Issue.id))
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(stmt)
    issues = list(result.scalars().unique().all())
    return [_issue_to_admin_read(i) for i in issues]


@router.patch("/issues/{issue_id}", response_model=IssueAdminRead)
async def update_issue(
    issue_id: int,
    body: IssueAdminUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _moderator: Annotated[User, Depends(get_current_moderator)],
) -> IssueAdminRead:
    if body.status == IssueStatus.pending_ai or body.status not in _PATCH_ALLOWED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported status transition",
        )

    result = await db.execute(
        select(Issue).where(Issue.id == issue_id).options(selectinload(Issue.user))
    )
    issue = result.scalar_one_or_none()
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")

    prev_status = issue.status
    issue.status = body.status

    if prev_status != body.status:
        db.add(
            IssueStatusEvent(
                issue_id=issue.id,
                from_status=prev_status,
                to_status=body.status,
                changed_at=datetime.now(tz=timezone.utc),
                actor_role="moderator",
                actor_id=_moderator.id,
            )
        )
    await db.commit()
    result_reload = await db.execute(
        select(Issue).where(Issue.id == issue_id).options(selectinload(Issue.user))
    )
    issue_reloaded = result_reload.scalar_one()
    return _issue_to_admin_read(issue_reloaded)

