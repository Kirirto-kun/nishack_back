from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_moderator
from app.db.models.enums import IssueStatus
from app.db.models.issue import Issue
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.issue import IssueAdminRead, IssueAdminUpdate

router = APIRouter(prefix="/admin", tags=["admin"])

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
) -> list[Issue]:
    stmt = select(Issue)

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
    return list(result.scalars().all())


@router.patch("/issues/{issue_id}", response_model=IssueAdminRead)
async def update_issue(
    issue_id: int,
    body: IssueAdminUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _moderator: Annotated[User, Depends(get_current_moderator)],
) -> Issue:
    if body.status == IssueStatus.pending_ai or body.status not in _PATCH_ALLOWED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported status transition",
        )

    result = await db.execute(select(Issue).where(Issue.id == issue_id))
    issue = result.scalar_one_or_none()
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")

    issue.status = body.status
    await db.commit()
    await db.refresh(issue)
    return issue

