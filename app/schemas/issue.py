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

