# Python 3.11+ is required (pyproject.toml: requires-python = ">=3.11").
# Pin to 3.13-slim to match the production target; override with --build-arg if needed.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ENVIRONMENT=production

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

RUN addgroup --system kinjo && adduser --system --ingroup kinjo kinjo && \
    mkdir -p /app/data /app/backups /app/upload /app/logs && \
    chown -R kinjo:kinjo /app

USER kinjo

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["supervisord", "-c", "/app/supervisor.conf"]
