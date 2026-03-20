from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from openai import AsyncOpenAI, BadRequestError
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models.enums import IssueStatus
from app.db.models.issue import Issue
from app.db.models.issue_status_events import IssueStatusEvent
from app.db.session import AsyncSessionLocal


class _AIResult(BaseModel):
    priority: int = Field(ge=1, le=5)
    is_false_call: bool
    admin_summary: str = Field(min_length=1, max_length=4000)
    category: str = Field(
        description="Issue category: infrastructure|danger|trash|other",
        pattern=r"^(infrastructure|danger|trash|other)$",
    )


@dataclass(frozen=True)
class _ImageInput:
    media_type: str
    b64: str


def _guess_media_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if ext == ".png":
        return "image/png"
    if ext == ".webp":
        return "image/webp"
    return "application/octet-stream"


def _image_from_disk(path: Path) -> _ImageInput:
    data = path.read_bytes()
    return _ImageInput(media_type=_guess_media_type(path), b64=base64.b64encode(data).decode("ascii"))


def _issue_image_fs_path(image_url: str) -> Path:
    # image_url is stored as: /uploads/issues/{issue_id}/{filename}
    # uploads are served from settings.upload_dir mounted at /uploads
    settings = get_settings()
    prefix = "/uploads/"
    rel = image_url[len(prefix) :] if image_url.startswith(prefix) else image_url.lstrip("/")
    return Path(settings.upload_dir) / rel


async def analyze_issue_with_ai(issue_id: int) -> None:
    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Issue).where(Issue.id == issue_id))
        issue = result.scalar_one_or_none()
        if issue is None:
            return

        prev_status = issue.status

        if not issue.image_url:
            issue.ai_error = "No image_url set; upload an image first."
            issue.ai_analyzed_at = datetime.now(tz=timezone.utc)
            db.add(
                IssueStatusEvent(
                    issue_id=issue.id,
                    from_status=prev_status,
                    to_status=issue.status,
                    actor_role="system",
                    actor_id=None,
                )
            )
            await db.commit()
            return

        try:
            img_path = _issue_image_fs_path(issue.image_url)
            if not img_path.exists():
                raise FileNotFoundError(str(img_path))

            img = _image_from_disk(img_path)
            prompt = (
                "Ты помощник для городского сервиса. Проанализируй заявку гражданина.\n"
                "Верни ТОЛЬКО JSON (без markdown), строго в формате:\n"
                "{\n"
                '  "priority": 1-5,\n'
                '  "is_false_call": true|false,\n'
                '  "admin_summary": "короткое, практичное резюме для акимата: что случилось, риск, что делать",\n'
                '  "category": "infrastructure|danger|trash|other"\n'
                "}\n\n"
                f"Заголовок: {issue.title}\n"
                f"Описание: {issue.description}\n"
                f"Координаты: {issue.latitude}, {issue.longitude}\n"
            )

            async def _call(with_image: bool) -> str:
                content: list[dict[str, object]] = [{"type": "text", "text": prompt}]
                if with_image:
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{img.media_type};base64,{img.b64}"},
                        }
                    )
                completion = await client.chat.completions.create(
                    model=settings.openai_model,
                    temperature=0.2,
                    response_format={"type": "json_object"},
                    messages=[{"role": "user", "content": content}],
                )
                return completion.choices[0].message.content or ""

            try:
                raw = await _call(with_image=True)
            except BadRequestError as e:
                # Some tiny/edge-case images may fail parsing; fall back to text-only.
                raw = await _call(with_image=False)

            parsed = json.loads(raw)
            ai = _AIResult.model_validate(parsed)

            issue.priority = int(ai.priority)
            issue.ai_admin_summary = ai.admin_summary.strip()
            issue.ai_analyzed_at = datetime.now(tz=timezone.utc)
            issue.ai_error = None
            issue.category = ai.category
            issue.status = IssueStatus.rejected if ai.is_false_call else IssueStatus.approved
            db.add(
                IssueStatusEvent(
                    issue_id=issue.id,
                    from_status=prev_status,
                    to_status=issue.status,
                    actor_role="system",
                    actor_id=None,
                )
            )
            await db.commit()
        except (OSError, json.JSONDecodeError, ValidationError) as e:
            issue.ai_error = f"{type(e).__name__}: {e}"
            issue.ai_analyzed_at = datetime.now(tz=timezone.utc)
            db.add(
                IssueStatusEvent(
                    issue_id=issue.id,
                    from_status=prev_status,
                    to_status=issue.status,
                    actor_role="system",
                    actor_id=None,
                )
            )
            await db.commit()
        except Exception as e:  # noqa: BLE001
            issue.ai_error = f"UnexpectedError: {type(e).__name__}: {e}"
            issue.ai_analyzed_at = datetime.now(tz=timezone.utc)
            db.add(
                IssueStatusEvent(
                    issue_id=issue.id,
                    from_status=prev_status,
                    to_status=issue.status,
                    actor_role="system",
                    actor_id=None,
                )
            )
            await db.commit()


def enqueue_issue_analysis(issue_id: int) -> None:
    # For FastAPI BackgroundTasks: schedule coroutine on the running event loop.
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(analyze_issue_with_ai(issue_id))
    except RuntimeError:
        # No running loop (e.g., executed in a different context) — run synchronously.
        asyncio.run(analyze_issue_with_ai(issue_id))

