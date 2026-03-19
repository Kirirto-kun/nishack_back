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
        f"На маршруте встречаются объекты следующих категорий: {found_categories}.\n"
        "\n"
        "Типы категорий:\n"
        "- Зарегистрированные проблемы (заявки города): infrastructure, danger, trash, other.\n"
        "- POI из OpenStreetMap и базы: bar (бары, пабы, клубы), alcohol_shop (алкогольные магазины), "
        "gambling (азартные заведения), tobacco_shop (табачные и вейпы), hookah (кальянные), "
        "liquor_store (устаревшая метка для алкоголя — трактуй как алкогольную зону), "
        "school, kindergarten (образование), park, garden, playground, convenience — обычно безопасные зелёные зоны.\n"
        "\n"
        "Правила:\n"
        "- Если пользователь упоминает ребёнка, семью, трезвость, безопасность — избегай bar, alcohol_shop, "
        "gambling, tobacco_shop, hookah, liquor_store, nightclub-логику; danger и trash — по смыслу.\n"
        "- Школы, детсады, парки сами по себе не «опасность» для ребёнка — не добавляй school/park в avoid, "
        "если только пользователь явно не просит их обойти.\n"
        "\n"
        "Твоя задача: выбрать из ЭТОГО СПИСКА те категории, которые нужно категорически ИЗБЕГАТЬ с учётом запроса.\n"
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

