# Nishack Backend

FastAPI + PostgreSQL, развёртывание через Docker Compose.

## Быстрый старт

1. Скопируйте файл окружения:

   ```bash
   cp .env.example .env
   ```

   При необходимости измените логин, пароль и имя БД в `.env`.

2. Запустите сервисы:

   ```bash
   docker compose up -d --build
   ```

3. Примените миграции БД (таблицы `users` и `issues`):

   ```bash
   docker compose run --rm web alembic upgrade head
   ```

   После изменения моделей: пересоберите образ (`docker compose build web`), затем снова `alembic upgrade head`. Чтобы сгенерировать новую ревизию из моделей, удобно смонтировать проект в контейнер (из корня `nishack_back`):

   ```bash
   docker compose run --rm -v "${PWD}:/app" web alembic revision --autogenerate -m "описание"
   ```

4. Проверка:

   ```bash
   curl http://localhost:8000/health
   ```

   Ожидается ответ: `{"status":"ok"}`.

Остановка: `docker compose down` (данные БД сохраняются в volume `postgres_data`).

## Подключение к PostgreSQL (DBeaver и др.)

Сервис `db` проброшен на хост: **localhost:5432** (логин/пароль/имя БД — из `.env`, по умолчанию как в `.env.example`). Для локального `alembic` без Docker задайте в `.env` значение `POSTGRES_HOST=localhost` и убедитесь, что пароль совпадает с контейнером.

## Локальная разработка без Docker

Установите зависимости: `pip install -r requirements.txt`. В `.env` укажите `POSTGRES_HOST=localhost` и запустите PostgreSQL локально (или поднимите только `db` через Compose). Миграции: `alembic upgrade head`. Запуск API:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
