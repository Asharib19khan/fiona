# syntax=docker/dockerfile:1.7
# Fiona agents. Build context is the repository root:
#   docker build -f services/agents/Dockerfile .
FROM ghcr.io/astral-sh/uv:0.11.12 AS uv

FROM python:3.12-slim AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /srv/services/agents
COPY services/agents/pyproject.toml services/agents/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY services/agents/ ./
RUN uv sync --locked --no-dev --no-editable

FROM python:3.12-slim AS runtime
RUN useradd --create-home --uid 10001 fiona
WORKDIR /srv/services/agents
COPY --from=build --chown=fiona:fiona /srv/services/agents/.venv /srv/services/agents/.venv
ENV PATH="/srv/services/agents/.venv/bin:${PATH}" PYTHONUNBUFFERED=1
USER fiona
EXPOSE 8100
CMD ["uvicorn", "fiona_agents.main:app", "--host", "0.0.0.0", "--port", "8100"]
