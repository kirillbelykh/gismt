#!/usr/bin/env bash

set -e

echo "▶ Activating virtual environment"
source venv/bin/activate

echo "▶ Starting Redis"
brew services start redis

echo "▶ Starting PostgreSQL 14"
brew services start postgresql@14

echo "▶ Starting Uvicorn"
uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload &

UVICORN_PID=$!

echo "▶ Starting Celery worker"
celery -A app.workers.celery_app worker \
  --loglevel=info \
  --concurrency=3 &

CELERY_PID=$!

echo "▶ All services started"
echo "▶ Uvicorn PID: $UVICORN_PID"
echo "▶ Celery PID:  $CELERY_PID"

trap "echo '⏹ Stopping services'; kill $UVICORN_PID $CELERY_PID" SIGINT SIGTERM

wait
