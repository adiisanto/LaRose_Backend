# ============================================================================
# STAGE 1: Builder
# ============================================================================
FROM python:3.12-slim AS builder

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv for ultra-fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:0.4.24 /uv /bin/uv

# Copy project specification files
COPY pyproject.toml uv.lock README.md ./

# Install dependencies into virtual environment
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
RUN uv sync --frozen --no-dev --no-install-project

# ============================================================================
# STAGE 2: Runner
# ============================================================================
FROM python:3.12-slim AS runner

WORKDIR /app

# Security: create non-root user
RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -s /bin/bash -m appuser

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy source code and config
COPY --chown=appuser:appgroup src/ /app/src/
COPY --chown=appuser:appgroup alembic.ini* /app/
COPY --chown=appuser:appgroup migrations/ /app/migrations/

# Switch to non-root user
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/healthz || exit 1

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
