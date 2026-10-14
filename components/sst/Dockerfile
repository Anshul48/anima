# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git curl && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.12.9 /uv /bin/uv

COPY pyproject.toml ./
RUN uv sync --no-dev --no-install-project

COPY src/ src/
RUN uv sync --no-dev

FROM python:3.12-slim AS runner
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY docs/ docs/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

EXPOSE 8501
ENTRYPOINT ["sst"]
CMD ["--help"]
