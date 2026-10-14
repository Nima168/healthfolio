#!/bin/sh
# Container start: bring the database schema up to date, start the extraction worker, then serve the API.
set -e
alembic upgrade head
python -m app.worker &
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips="*"
