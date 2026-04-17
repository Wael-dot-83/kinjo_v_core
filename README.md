# KInJo Platform

KInJo is a FastAPI-based kindergarten management platform with:
- Backend APIs and WebSocket endpoints
- Server-rendered frontend templates (Jinja2)
- PostgreSQL/SQLite support through SQLAlchemy
- Alembic database migrations

## Tech Stack

- Python 3.11+
- FastAPI + Uvicorn
- SQLAlchemy + Alembic
- Jinja2
- Redis/Celery (optional but recommended for production)

## Project Layout

- `main.py`: app entrypoint and router composition
- `frontend.py`: server-rendered frontend routes
- `models.py`: ORM schema
- `alembic/`: migration history
- `templates/`, `static/`: frontend assets
- `tests/`: automated test suite

## Local Setup

```bash
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
```

Create `.env` from `.env.example`, then set at minimum:

- `SECRET_KEY`
- `DATABASE_URL`
- `ENVIRONMENT` (`development` or `production`)
- `CORS_ALLOWED_ORIGINS`
- `TRUSTED_HOSTS`

## Run Migrations

```bash
alembic upgrade head
```

## Run Application

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## Tests

```bash
pytest -m "p0" -q
pytest tests/ -q
```

## Docker

Build and run with Compose:

```bash
docker compose up --build
```

Services:
- App: `http://localhost:8001`
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`

## Production Notes

- Run `alembic upgrade head` during deploy.
- `database.init_db()` intentionally skips `create_all()` in production.
- Ensure persistent volumes for DB/uploads/backups.
- Set secure values for `SECRET_KEY`, DB credentials, and Redis URLs.
- API docs are disabled automatically in production.
- The default `docker-compose.yml` is now safe-by-default for local use; override `KINJO_WEB_COMMAND` if you explicitly want `--reload`.
