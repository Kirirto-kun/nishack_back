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

3. Проверка:

   ```bash
   curl http://localhost:8000/health
   ```

   Ожидается ответ: `{"status":"ok"}`.

Остановка: `docker compose down` (данные БД сохраняются в volume `postgres_data`).

## Локальная разработка без Docker

Установите зависимости: `pip install -r requirements.txt`. В `.env` укажите `POSTGRES_HOST=localhost` и запустите PostgreSQL локально. Запуск API:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
