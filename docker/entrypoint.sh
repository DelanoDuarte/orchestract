#!/usr/bin/env bash
# Container entrypoint: apply database migrations, then hand off to the CMD
# (the uvicorn server). Set RUN_MIGRATIONS=0 to skip migrations for a given
# container — e.g. when running multiple web replicas and migrating separately.
set -euo pipefail

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  echo "[entrypoint] Applying database migrations (alembic upgrade head)..."
  # Retry briefly so a web container that races ahead of a just-started
  # database still comes up cleanly.
  attempts=0
  until alembic upgrade head; do
    attempts=$((attempts + 1))
    if [ "$attempts" -ge 10 ]; then
      echo "[entrypoint] Migrations failed after $attempts attempts; giving up." >&2
      exit 1
    fi
    echo "[entrypoint] Migration attempt $attempts failed; retrying in 3s..." >&2
    sleep 3
  done
  echo "[entrypoint] Migrations applied."
fi

echo "[entrypoint] Starting: $*"
exec "$@"
