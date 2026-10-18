# syntax=docker/dockerfile:1.7
# Fiona Guardian. Build context is the repository root:
#   docker build -f services/guardian/Dockerfile .
FROM ghcr.io/astral-sh/uv:0.11.12 AS uv

FROM node:22-bookworm-slim AS claude
# The CLI ships a native Linux binary; only that file goes into the runtime image.
RUN npm install -g @anthropic-ai/claude-code@2.1.296 \
 && cp "$(readlink -f "$(npm root -g)/@anthropic-ai/claude-code/bin/claude.exe")" /claude \
 && /claude --version

FROM python:3.12-slim AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /srv/services/guardian
COPY packages/contracts/python /srv/packages/contracts/python
COPY services/guardian/pyproject.toml services/guardian/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --no-editable
COPY services/guardian/ ./
RUN uv sync --locked --no-dev --no-editable

FROM python:3.12-slim AS runtime
RUN useradd --create-home --uid 10001 fiona
WORKDIR /srv/services/guardian
COPY --from=build --chown=fiona:fiona /srv/services/guardian/.venv /srv/services/guardian/.venv
# Each agent is a `claude -p` process; it authenticates with the ANTHROPIC_API_KEY secret.
COPY --from=claude /claude /usr/local/bin/claude
COPY --chown=fiona:fiona rulebook /srv/rulebook
ENV PATH="/srv/services/guardian/.venv/bin:${PATH}" PYTHONUNBUFFERED=1
USER fiona
EXPOSE 8200
CMD ["uvicorn", "fiona_guardian.main:app", "--host", "0.0.0.0", "--port", "8200"]
