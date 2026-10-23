# Modern WeasyPrint deps for Debian Trixie (python:3.13-slim)
FROM python:3.13-slim AS base

# System libraries required by WeasyPrint at runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz-subset0 \
    shared-mime-info \
    fonts-liberation \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

# Install uv (pinned) for fast, reproducible installs from the lockfile
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /usr/local/bin/uv

# Dependency layer (best cache hit)
COPY pyproject.toml ./
COPY uv.lock* ./

RUN uv sync --frozen --no-dev || uv sync --no-dev

# Application code
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
COPY scripts ./scripts

ENV PATH="/srv/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
