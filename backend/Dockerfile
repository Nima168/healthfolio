# The API and the extraction worker in one container (run on AWS Lightsail).
FROM public.ecr.aws/docker/library/python:3.12-slim

# Tesseract reads scanned copies (app/ai/reading.py).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.11.25 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY alembic.ini start.sh ./
COPY alembic ./alembic
COPY app ./app

RUN useradd --create-home appuser && mkdir -p /app/storage && chown -R appuser /app/storage
USER appuser
CMD ["sh", "start.sh"]
