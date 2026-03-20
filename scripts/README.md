# Скрипты

## Тестовый админ (модератор)

Роль в БД: `moderator` (доступ к `/admin` во фронте).

### Через Docker (рекомендуется)

Из каталога `nishack_back`, пока подняты `db` и приложение:

```bash
docker compose build web
docker compose run --rm web python scripts/create_moderator.py \
  --email admin@nishack.test \
  --password AdminTest123
```

Переменные `POSTGRES_*` подставятся из `docker compose` (хост БД — `db`).

### С хоста (Python + локальный порт 5432)

Если Postgres слушает `localhost:5432` с теми же учётными данными, что в `.env`:

```bash
cd nishack_back
python scripts/create_moderator.py \
  --email admin@nishack.test \
  --password AdminTest123 \
  --postgres-host localhost
```

### Учётная запись по умолчанию (пример)

| Поле     | Значение           |
|----------|--------------------|
| Email    | `admin@nishack.test` |
| Пароль   | `AdminTest123`     |
| Роль     | модератор (акимат) |

Смените пароль в проде; не коммитьте реальные секреты.
