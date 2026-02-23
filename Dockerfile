FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1

# System deps for trafilatura, playwright, pymupdf
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Playwright browsers (for Phase 5 js_renderer)
RUN playwright install --with-deps chromium || true

COPY . .
