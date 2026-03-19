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

    if not found_categories:
        return [], "На пути нет объектов, которые нужно избегать."

    prompt = (
        "Ты — ИИ-навигатор.\n"
        f"Пользователь просит: '{user_prompt}'.\n"
        f"На его пути лежат объекты следующих категорий: {found_categories}.\n"
        "Твоя задача: выбрать из ЭТОГО СПИСКА те категории, которые нужно категорически ИЗБЕГАТЬ с учетом запроса пользователя.\n"
        "ОЧЕНЬ ВАЖНО:\n"
        "- поле avoid_categories ДОЛЖНО содержать ТОЛЬКО значения из списка категорий, БЕЗ переименований;\n"
        "- нельзя придумывать новые названия категорий;\n"
        "- строка в avoid_categories должна ПОСИМВОЛЬНО совпадать с исходной категорией.\n"
        "Верни строго JSON:\n"
        '{\n'
        '  "avoid_categories": ["категория_из_списка_1", "категория_из_списка_2"],\n'
        '  "explanation_for_user": "Короткий текст (1-2 предложения), объясняющий твое решение."\n'
        "}\n"
    )

    schema = {
        "name": "avoid_schema",
        "schema": {
            "type": "object",
            "properties": {
                "avoid_categories": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": found_categories,
                    },
                    "description": "Подсписок категорий из выдачи, которые нужно избегать.",
                },
                "explanation_for_user": {
                    "type": "string",
                    "description": "Короткое объяснение для пользователя (1–2 предложения).",
                },
            },
            "required": ["avoid_categories", "explanation_for_user"],
            "additionalProperties": False,
        },
        "strict": True,
    }

    completion = await client.chat.completions.create(
        model=settings.openai_model,
        temperature=0.2,
        response_format={"type": "json_schema", "json_schema": schema},
        messages=[{"role": "user", "content": prompt}],
    )
    raw = completion.choices[0].message.content or "{}"
    parsed = json.loads(raw)
    res = _AvoidResult.model_validate(parsed)

    avoid = [c for c in res.avoid_categories if c in set(found_categories)]
    return avoid, res.explanation_for_user.strip()

