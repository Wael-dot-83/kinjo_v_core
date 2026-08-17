# syntax=docker/dockerfile:1
# =============================================================================
# KinJo application image (multi-stage).
#
# Build wheels in a stage that has a compiler, then copy them into a runtime
# stage that does not. build-essential is ~250MB of C toolchain that was
# previously shipped to production inside the running image, where it is both
# dead weight and a ready-made toolkit for anyone who gets code execution.
# =============================================================================

FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt


FROM python:3.12-slim AS runtime

# libpq5 is the runtime half of libpq-dev; curl is used by the compose
# healthcheck and by deploy_locked.sh's in-container probe.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

# Non-root. A container that runs as root shares the host's uid 0, so any
# container escape or writable bind mount starts with full privileges. Created
# before COPY so the application files land with the right owner.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin kinjo

COPY --chown=kinjo:kinjo . .

# Writable at runtime: supervisor logs here, and data/ is a bind mount whose
# in-image mountpoint must already belong to the app user.
RUN mkdir -p /app/logs /app/data && chown -R kinjo:kinjo /app/logs /app/data

USER kinjo

# Unbuffered so container logs appear in real time rather than on flush, and no
# .pyc writes into a filesystem the app should not be dirtying.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

EXPOSE 8000

# Compose declares its own healthcheck for `web`; this one covers `docker run`
# and any orchestrator that reads image metadata instead.
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
