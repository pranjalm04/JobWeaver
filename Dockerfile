# Playwright base ships with Chromium and matching system deps required by crawl4ai.
FROM mcr.microsoft.com/playwright/python:v1.50.0-jammy

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VERSION=1.8.5 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

WORKDIR /app

RUN pip install "poetry==${POETRY_VERSION}"

COPY pyproject.toml poetry.lock ./

RUN poetry install --no-root --only main

COPY src ./src
COPY README.md ./README.md

RUN poetry install --only-root

RUN useradd --create-home --uid 1001 jobweaver \
    && mkdir -p /app/outputs /app/listing_cache \
    && chown -R jobweaver:jobweaver /app

USER jobweaver

CMD ["celery", "-A", "jobweaver.worker.celery_app", "worker", "--loglevel=info"]
