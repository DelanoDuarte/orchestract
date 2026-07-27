# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------------------
# Orchestract production image.
#
# Multi-stage build with uv. Both stages share the same python:3.13-slim base
# so the virtualenv built in the first stage (which references the image's
# /usr/local/bin/python) is portable to the runtime stage. UV_PYTHON_DOWNLOADS=0
# forces uv to use that system Python instead of downloading a standalone one.
# ---------------------------------------------------------------------------

FROM python:3.13-slim-bookworm AS builder

# uv is pinned to the version that produced uv.lock so installs stay frozen.
COPY --from=ghcr.io/astral-sh/uv:0.7.1 /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Install only third-party dependencies first for a well-cached layer. The
# project itself is a non-packaged app (no build-system), so --no-install-project
# just resolves + installs the locked dependencies into /app/.venv.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project


FROM python:3.13-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# Run as an unprivileged user.
RUN groupadd --system app && useradd --system --gid app --create-home --home-dir /app app

WORKDIR /app

# Resolved virtualenv from the builder stage.
COPY --from=builder --chown=app:app /app/.venv /app/.venv

# Application source (see .dockerignore for what's excluded).
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app app ./app
COPY --chown=app:app main.py ./
COPY --chown=app:app docker/entrypoint.sh /usr/local/bin/entrypoint.sh

# Local-disk storage fallback lives here; mount a volume over it in compose.
RUN chmod +x /usr/local/bin/entrypoint.sh \
    && mkdir -p /app/storage \
    && chown app:app /app/storage

USER app

EXPOSE 8000

# Liveness against the app's own /healthz (no external tools needed).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status==200 else 1)"

# entrypoint.sh runs DB migrations (unless RUN_MIGRATIONS=0) then execs the CMD.
ENTRYPOINT ["entrypoint.sh"]
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips '*' --workers ${WEB_CONCURRENCY:-2}"]
