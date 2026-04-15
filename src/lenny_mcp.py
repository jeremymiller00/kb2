"""Minimal HTTP JSON-RPC client for the Lenny's Podcast MCP server.

The server speaks MCP's Streamable HTTP transport: JSON-RPC over POST, with
responses returned as Server-Sent Events. A session is established via
`initialize`, identified by an `mcp-session-id` response header, and reused
for subsequent requests.
"""
import json
import logging

import httpx

logger = logging.getLogger(__name__)

MCP_URL = "https://lenny-mcp.onrender.com/mcp"
TIMEOUT = httpx.Timeout(60.0, connect=10.0)


def _parse_sse(text: str) -> dict:
    for line in text.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    raise ValueError(f"No data event in SSE response: {text[:200]}")


class LennyMCPClient:
    def __init__(self) -> None:
        self._client = httpx.Client(timeout=TIMEOUT)
        self._session_id: str | None = None
        self._next_id = 0

    def __enter__(self) -> "LennyMCPClient":
        self._initialize()
        return self

    def __exit__(self, *exc) -> None:
        self._client.close()

    def _rpc(self, method: str, params: dict | None = None, notification: bool = False) -> dict:
        payload: dict = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        if not notification:
            self._next_id += 1
            payload["id"] = self._next_id

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            headers["mcp-session-id"] = self._session_id

        response = self._client.post(MCP_URL, json=payload, headers=headers)
        response.raise_for_status()

        if self._session_id is None:
            sid = response.headers.get("mcp-session-id")
            if sid:
                self._session_id = sid

        if notification:
            return {}

        parsed = _parse_sse(response.text)
        if "error" in parsed:
            raise RuntimeError(f"MCP error from {method}: {parsed['error']}")
        return parsed.get("result", {})

    def _initialize(self) -> None:
        self._rpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "kb", "version": "1.0"},
        })
        self._rpc("notifications/initialized", notification=True)

    def list_tools(self) -> list[dict]:
        return self._rpc("tools/list").get("tools", [])

    def call_tool(self, name: str, arguments: dict) -> str:
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        chunks = [c.get("text", "") for c in result.get("content", []) if c.get("type") == "text"]
        return "\n".join(chunks)
