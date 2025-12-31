# syntax=docker/dockerfile:1

FROM python:3.12-slim AS base

# Prevent Python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Create non-root user
RUN groupadd --gid 1000 axela \
    && useradd --uid 1000 --gid 1000 --shell /bin/bash axela

# ============================================
# Dependencies stage
# ============================================
FROM base AS dependencies

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies (without dev dependencies)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# ============================================
# Production stage
# ============================================
FROM base AS production

# Copy virtual environment from dependencies stage
COPY --from=dependencies /app/.venv /app/.venv

# Create data directory for SQLite and persistent files
RUN mkdir -p /data && chown axela:axela /data
VOLUME /data

# Copy source code
COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini ./
COPY pyproject.toml uv.lock ./

# Install the project itself
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Change ownership
RUN chown -R axela:axela /app

# Switch to non-root user
USER axela

# Add virtual environment to PATH
ENV PATH="/app/.venv/bin:$PATH"

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"

# Default command
CMD ["python", "-m", "axela.main"]
