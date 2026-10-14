# Multi-stage Dockerfile optimized for uv, speed, security, and minimal layer size
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

# Enable bytecode compilation and fast copy linking
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Install dependencies in a separate layer for optimal caching
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# Copy the rest of the application code
COPY . /app

# Install the application itself
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Final production runtime image
FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

# Set runtime environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    STC_ENVIRONMENT="production"

# Create a secure non-root user and group
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/bash -m appuser && \
    mkdir -p /app/artifacts/receipts && \
    chown -R appuser:appgroup /app

# Copy virtualenv and application artifacts from builder
COPY --from=builder --chown=appuser:appgroup /app /app

# Switch to non-root user
USER appuser

# Container healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD ["stc", "health"]

# Entrypoint to the CLI
ENTRYPOINT ["stc"]
CMD ["--help"]
