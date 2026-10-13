# syntax=docker/dockerfile:1.7
# Fiona engine. Build context is the repository root:
#   docker build -f services/engine/Dockerfile .
FROM ghcr.io/astral-sh/uv:0.11.12 AS uv

FROM python:3.12-slim AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /srv/services/engine
COPY services/engine/pyproject.toml services/engine/uv.lock ./
RUN uv sync --locked --no-dev
COPY services/engine/ ./

FROM python:3.12-slim AS runtime
RUN useradd --create-home --uid 10001 fiona
WORKDIR /srv/services/engine
COPY --from=build --chown=fiona:fiona /srv/services/engine /srv/services/engine
ENV PATH="/srv/services/engine/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    FIONA_MODE=mock
USER fiona
EXPOSE 8000
CMD ["uvicorn", "engine.app.main:app", "--app-dir", "/srv/services", "--host", "0.0.0.0", "--port", "8000"]
