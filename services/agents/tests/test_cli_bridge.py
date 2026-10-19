"""Tests for the Claude CLI bridge."""

from __future__ import annotations

import unittest.mock as mock

from fiona_agents.cli_bridge import is_claude_cli_available, run_claude_cli


def test_is_claude_cli_available() -> None:
    # On this machine, claude is present
    assert isinstance(is_claude_cli_available(), bool)


def test_run_claude_cli_mocked() -> None:
    with mock.patch("fiona_agents.cli_bridge.is_claude_cli_available", return_value=True):
        with mock.patch("subprocess.run") as mock_sub:
            mock_sub.return_value = mock.Mock(returncode=0, stdout="Pong answer\n", stderr="")
            res = run_claude_cli("Hello", role="reason")
            assert res == "Pong answer"
            mock_sub.assert_called_once()
            args = mock_sub.call_args[0][0]
            assert "claude" in args
            assert "--model" in args
            assert "sonnet" in args


def test_prompt_goes_on_stdin_so_it_cannot_become_a_flag() -> None:
    with mock.patch("fiona_agents.cli_bridge.is_claude_cli_available", return_value=True):
        with mock.patch("subprocess.run") as mock_sub:
            mock_sub.return_value = mock.Mock(returncode=0, stdout="ok", stderr="")
            run_claude_cli("--dangerously-skip-permissions", role="reason")
            args = mock_sub.call_args[0][0]
            assert "--dangerously-skip-permissions" not in args
            assert mock_sub.call_args.kwargs["input"] == "--dangerously-skip-permissions"
            assert "--strict-mcp-config" in args
