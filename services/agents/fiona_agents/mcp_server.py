"""The MCP server an agent's Claude process talks to: one agent's tools, nothing else.

Claude Code starts it per run (`--mcp-config`) as
    python -m fiona_agents.mcp_server --agent treasurer --tenant ten_karachi_apparel --journal <file>
It speaks MCP over stdio (newline-delimited JSON-RPC 2.0), lists only the tools in that agent's
toolbox, and calls the engine as that agent. Every call and its result summary is appended to
the run journal, which is how the owner sees exactly what an agent looked at and did.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

from fiona_agents.engine import Engine, EngineError
from fiona_agents.toolbox import TOOLBOXES, Tool, ToolError

PROTOCOL_VERSION = "2025-06-18"


def _reply(msg_id: Any, result: Any = None, error: dict[str, Any] | None = None) -> None:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _journal(path: str | None, entry: dict[str, Any]) -> None:
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def _call(tool: Tool, engine: Engine, args: dict[str, Any], journal: str | None) -> dict[str, Any]:
    started = time.monotonic()
    try:
        result = tool.handler(engine, args)
        ok = True
    except (ToolError, EngineError) as exc:
        result = {"error": str(exc)}
        ok = False
    except Exception as exc:  # a tool bug must reach the model as a tool error, not kill the server
        result = {"error": f"internal tool error: {type(exc).__name__}"}
        ok = False
    _journal(
        journal,
        {
            "kind": "tool_call",
            "tool": tool.name,
            "args": args,
            "ok": ok,
            "ms": int((time.monotonic() - started) * 1000),
            "result": result,
        },
    )
    return {
        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, default=str)}],
        "isError": not ok,
    }


def serve(agent: str, toolbox: str, tenant_id: str, journal: str | None) -> None:
    tools = {tool.name: tool for tool in TOOLBOXES[toolbox]}
    engine = Engine(tenant_id, agent)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            _reply(None, error={"code": -32700, "message": "parse error"})
            continue
        method, msg_id = msg.get("method"), msg.get("id")
        if msg_id is None:  # a notification (e.g. notifications/initialized): no reply
            continue
        if method == "initialize":
            _reply(
                msg_id,
                {
                    "protocolVersion": msg.get("params", {}).get(
                        "protocolVersion", PROTOCOL_VERSION
                    ),
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": f"fiona-{agent}", "version": "1.0.0"},
                },
            )
        elif method == "tools/list":
            _reply(
                msg_id,
                {
                    "tools": [
                        {
                            "name": t.name,
                            "description": t.description,
                            "inputSchema": t.input_schema,
                        }
                        for t in tools.values()
                    ]
                },
            )
        elif method == "tools/call":
            params = msg.get("params") or {}
            tool = tools.get(params.get("name"))
            if tool is None:
                _reply(
                    msg_id,
                    error={"code": -32602, "message": f"unknown tool {params.get('name')!r}"},
                )
                continue
            _reply(msg_id, _call(tool, engine, params.get("arguments") or {}, journal))
        elif method == "ping":
            _reply(msg_id, {})
        else:
            _reply(msg_id, error={"code": -32601, "message": f"method not found: {method}"})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", required=True, help="who the engine sees as the caller")
    parser.add_argument("--toolbox", choices=sorted(TOOLBOXES), help="defaults to the agent's own")
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--journal")
    args = parser.parse_args()
    serve(args.agent, args.toolbox or args.agent, args.tenant, args.journal)


if __name__ == "__main__":
    main()
