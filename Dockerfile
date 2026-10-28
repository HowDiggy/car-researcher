# -------------------------------------------------------------
# Stage 1: Build virtual environment with Poetry
# -------------------------------------------------------------
FROM python:3.14-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=2.5.1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install pinned Poetry version
RUN pip install "poetry==${POETRY_VERSION}"

# Copy dependency specifications first to leverage Docker layer caching
COPY pyproject.toml poetry.lock ./

# Install main production dependencies (skipping project root)
RUN poetry install --only main --no-root

# Copy source code and install project
COPY src ./src
COPY README.md ./
RUN poetry install --only main

# -------------------------------------------------------------
# Stage 2: Hardened, non-root runtime image
# -------------------------------------------------------------
FROM python:3.14-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# Install runtime dependencies (libpq5 for asyncpg/psycopg, ca-certificates, curl)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy pre-built virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Install Playwright Chromium and its native OS dependencies
RUN playwright install --with-deps chromium \
    && chmod -R 755 /ms-playwright \
    && rm -rf /var/lib/apt/lists/*

# Create dedicated non-root application user
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/sh -d /home/appuser -m appuser

# Copy application source code with proper ownership
COPY --chown=appuser:appgroup src ./src
COPY --chown=appuser:appgroup README.md pyproject.toml ./

USER 10001:10001

EXPOSE 8000

CMD ["python", "src/runner.py", "--start-worker"]
