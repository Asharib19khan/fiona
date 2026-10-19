"""Which Claude account the Guardian uses for a workspace's review.

Same rule as the agents service: the owner's own API key or subscription token if they
connected one, else this server's signed-in Claude. A connection that exists but can't be read
stops the review (it is recorded as a CHECK_ERROR escalation), never a silent fallback.
"""

from __future__ import annotations

import os

from fiona_guardian import engine_client

SECRET_VARS = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")
_VAR_FOR = {"api_key": "ANTHROPIC_API_KEY", "subscription_token": "CLAUDE_CODE_OAUTH_TOKEN"}


class CredentialUnavailable(RuntimeError):
    pass


def lookup(tenant_id: str) -> tuple[str, str | None]:
    try:
        data = engine_client.ai_credential(tenant_id)
    except engine_client.EngineError as exc:
        status = getattr(exc, "status", None)
        if status == 404 and os.environ.get("FIONA_MODE") != "live":
            return "server", None  # an engine without the settings module, in development
        raise CredentialUnavailable(f"the AI connection could not be read ({exc})") from exc
    mode = str(data.get("mode") or "server")
    secret = data.get("secret")
    if mode == "server":
        return "server", None
    if mode not in _VAR_FOR or not isinstance(secret, str):
        raise CredentialUnavailable("the AI connection is incomplete")
    return mode, secret


def claude_env(tenant_id: str) -> dict[str, str] | None:
    """The environment to start Claude with, or None to inherit this process's."""
    mode, secret = lookup(tenant_id)
    if mode == "server" or secret is None:
        return None
    env = {key: value for key, value in os.environ.items() if key not in SECRET_VARS}
    env[_VAR_FOR[mode]] = secret
    return env
