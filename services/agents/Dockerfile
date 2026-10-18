# syntax=docker/dockerfile:1.7
# Fiona agents. Build context is the repository root:
#   docker build -f services/agents/Dockerfile .
FROM ghcr.io/astral-sh/uv:0.11.12 AS uv

FROM node:22-bookworm-slim AS claude
# The CLI ships a native Linux binary; only that file goes into the runtime image.
RUN npm install -g @anthropic-ai/claude-code@2.1.296 \
 && cp "$(readlink -f "$(npm root -g)/@anthropic-ai/claude-code/bin/claude.exe")" /claude \
 && /claude --version

FROM python:3.12-slim AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /srv/services/agents
COPY packages/contracts/python /srv/packages/contracts/python
COPY services/agents/pyproject.toml services/agents/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --no-editable
COPY services/agents/ ./
RUN uv sync --locked --no-dev --no-editable

FROM python:3.12-slim AS runtime
RUN useradd --create-home --uid 10001 fiona
WORKDIR /srv/services/agents
COPY --from=build --chown=fiona:fiona /srv/services/agents/.venv /srv/services/agents/.venv
# Each agent is a `claude -p` process; it authenticates with the ANTHROPIC_API_KEY secret.
COPY --from=claude /claude /usr/local/bin/claude
COPY --chown=fiona:fiona packages/contracts/examples /srv/packages/contracts/examples
ENV PATH="/srv/services/agents/.venv/bin:${PATH}" PYTHONUNBUFFERED=1
USER fiona
EXPOSE 8100
CMD ["uvicorn", "fiona_agents.main:app", "--host", "0.0.0.0", "--port", "8100"]
