"""Which Claude account a workspace's runs use.

The owner picks it on the AI connection page: this server's own signed-in Claude, their
Anthropic API key, or their Claude subscription token (from `claude setup-token`). The engine
keeps the secret sealed and hands it only to Fiona's services. Each Claude process is started
with exactly that one credential; the other is stripped from its environment.

Fail closed: if a workspace has its own connection but it can't be read, the run stops rather
than spending the server owner's account. Only local development (not FIONA_MODE=live) with no
engine running falls back to this machine's Claude.
"""

from __future__ import annotations

import os

from fiona_agents.engine import Engine, EngineError

SECRET_VARS = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")
_VAR_FOR = {"api_key": "ANTHROPIC_API_KEY", "subscription_token": "CLAUDE_CODE_OAUTH_TOKEN"}


class CredentialUnavailable(RuntimeError):
    pass


def lookup(tenant_id: str) -> tuple[str, str | None]:
    """(mode, secret) for the workspace; mode "server" means this server's own Claude."""
    try:
        data = Engine(tenant_id, "runtime").get("/v1/settings/ai/credential")
    except EngineError as exc:
        unreachable = exc.code in ("engine_unreachable", "not_found")
        if unreachable and os.environ.get("FIONA_MODE") != "live":
            return "server", None
        raise CredentialUnavailable(
            f"This workspace's AI connection could not be read ({exc.code})."
        ) from exc
    mode = str(data.get("mode") or "server")
    secret = data.get("secret")
    if mode not in ("server", *_VAR_FOR):
        raise CredentialUnavailable(f"Unknown AI connection mode {mode!r}.")
    if mode != "server" and not isinstance(secret, str):
        raise CredentialUnavailable("The AI connection has no secret.")
    return mode, secret if mode != "server" else None


def claude_env(tenant_id: str | None) -> dict[str, str] | None:
    """The environment to start Claude with, or None to inherit this process's (server mode)."""
    if tenant_id is None:
        return None
    mode, secret = lookup(tenant_id)
    if mode == "server" or secret is None:
        return None
    env = {key: value for key, value in os.environ.items() if key not in SECRET_VARS}
    env[_VAR_FOR[mode]] = secret
    return env
