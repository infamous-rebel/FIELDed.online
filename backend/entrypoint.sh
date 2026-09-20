#!/bin/sh
# FIELDed Cloud Run entrypoint
# Runs Alembic migrations then starts the ASGI server.

set -e

echo "Running Alembic migrations..."
alembic upgrade head

echo "Starting FIELDed API server on port ${PORT:-8000}..."
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers 1 \
    --log-level info
