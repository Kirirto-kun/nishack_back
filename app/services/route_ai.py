from __future__ import annotations

import json

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app.core.config import get_settings


class _AvoidResult(BaseModel):
    avoid_categories: list[str] = Field(default_factory=list)
    explanation_for_user: str = Field(min_length=1, max_length=500)


async def select_avoid_categories(user_prompt: str, found_categories: list[str]) -> tuple[list[str], str]:
    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    prompt = (
        "Ты — ИИ-навигатор.\n"
        f"Пользователь просит: '{user_prompt}'.\n"
        f"На его пути лежат объекты следующих категорий: {found_categories}.\n"
        "Твоя задача: выбрать из этого списка те категории, которые нужно категорически ИЗБЕГАТЬ с учетом запроса пользователя.\n"
        "Верни строго JSON:\n"
        '{\n'
        '  "avoid_categories": ["категория1", "категория2"],\n'
        '  "explanation_for_user": "Короткий текст (1-2 предложения), объясняющий твое решение."\n'
        "}\n"
    )

    completion = await client.chat.completions.create(
        model=settings.openai_model,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )
    raw = completion.choices[0].message.content or "{}"
    parsed = json.loads(raw)
    res = _AvoidResult.model_validate(parsed)

    avoid = [c for c in res.avoid_categories if c in set(found_categories)]
    return avoid, res.explanation_for_user.strip()

