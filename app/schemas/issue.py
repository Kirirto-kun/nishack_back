from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.enums import IssueStatus


class IssueCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1, max_length=10_000)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class IssueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    description: str
    latitude: float
    longitude: float
    image_url: str | None
    status: IssueStatus
    priority: int
    category: str | None = None


class IssueAdminRead(IssueRead):
    ai_admin_summary: str | None
    ai_analyzed_at: datetime | None
    ai_error: str | None
    reporter_email: str | None = Field(default=None, description="Email автора заявки (для модерации)")


class IssueAdminUpdate(BaseModel):
    status: IssueStatus


class IssuePublicMapRead(BaseModel):
    """Публичная карточка заявки для городской карты (без user_id и description)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    latitude: float
    longitude: float
    image_url: str | None
    priority: int
    category: str | None = None
    status: IssueStatus


class IssueTrackingEvent(BaseModel):
    from_status: IssueStatus
    to_status: IssueStatus
    changed_at: datetime
    actor_role: str | None = None
    actor_id: int | None = None


class IssueTrackingRead(BaseModel):
    issue_id: int
    current_status: IssueStatus
    title: str
    description: str
    image_url: str | None
    priority: int
    category: str | None = None
    ai_admin_summary: str | None = None
    ai_analyzed_at: datetime | None = None
    ai_error: str | None = None
    events: list[IssueTrackingEvent] = []

