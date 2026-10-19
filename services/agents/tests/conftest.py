"""Agents tests never reach a real engine for the AI connection: by default every workspace
uses this server's own Claude. Tests about the connection override `credentials.lookup`."""

from __future__ import annotations

import pytest

from fiona_agents import credentials


@pytest.fixture(autouse=True)
def server_claude(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(credentials, "lookup", lambda tenant_id: ("server", None))
