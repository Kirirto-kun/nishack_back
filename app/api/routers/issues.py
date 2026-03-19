from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.models.enums import IssueStatus
from app.db.models.issue import Issue
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.issue import IssueCreate, IssuePublicMapRead, IssueRead
from app.services.ai import enqueue_issue_analysis

router = APIRouter(prefix="/issues", tags=["issues"])

_ALLOWED_IMAGE_TYPES: set[str] = {"image/jpeg", "image/png", "image/webp"}
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MiB


def _safe_filename(name: str) -> str:
    # Strip any path parts and keep a conservative charset
    base = Path(name).name
    cleaned = "".join(ch for ch in base if ch.isalnum() or ch in {".", "-", "_"})
    return cleaned or "upload"


async def _read_limited(upload: UploadFile, max_bytes: int) -> bytes:
    data = await upload.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large (max {max_bytes} bytes)",
        )
    return data


@router.post("/", response_model=IssueRead, status_code=status.HTTP_201_CREATED)
async def create_issue(
    body: IssueCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Issue:
    geom = from_shape(Point(body.longitude, body.latitude), srid=4326)
    issue = Issue(
        user_id=user.id,
        title=body.title,
        description=body.description,
        latitude=body.latitude,
        longitude=body.longitude,
        geom=geom,
        image_url=None,
        status=IssueStatus.pending_ai,
        priority=1,
    )
    db.add(issue)
    await db.commit()
    await db.refresh(issue)
    return issue


_PUBLIC_MAP_STATUSES: tuple[IssueStatus, ...] = (IssueStatus.approved, IssueStatus.in_progress)


@router.get("/public", response_model=list[IssuePublicMapRead])
async def list_public_issues_for_map(
    db: AsyncSession = Depends(get_db),
) -> list[Issue]:
    """Все заявки, видимые горожанам на карте (без авторизации)."""
    stmt = (
        select(Issue)
        .where(Issue.status.in_(_PUBLIC_MAP_STATUSES))
        .where(Issue.latitude.is_not(None))
        .where(Issue.longitude.is_not(None))
        .order_by(desc(Issue.priority), desc(Issue.id))
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/my", response_model=list[IssueRead])
async def my_issues(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Issue]:
    result = await db.execute(
        select(Issue).where(Issue.user_id == user.id).order_by(Issue.id.desc())
    )
    return list(result.scalars().all())


@router.post("/{issue_id}/upload_image", response_model=IssueRead)
async def upload_issue_image(
    issue_id: int,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Issue:
    if file.content_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type",
        )

    result = await db.execute(select(Issue).where(Issue.id == issue_id))
    issue = result.scalar_one_or_none()
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")
    if issue.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    content = await _read_limited(file, _MAX_UPLOAD_BYTES)

    settings = get_settings()
    uploads_root = Path(settings.upload_dir)
    issue_dir = uploads_root / "issues" / str(issue_id)
    issue_dir.mkdir(parents=True, exist_ok=True)

    filename = _safe_filename(file.filename or "upload")
    dest = issue_dir / filename
    dest.write_bytes(content)

    issue.image_url = f"/uploads/issues/{issue_id}/{filename}"
    await db.commit()
    await db.refresh(issue)
    # Fire-and-forget AI analysis on the running event loop.
    enqueue_issue_analysis(issue_id)
    return issue

