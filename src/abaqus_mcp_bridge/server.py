"""MCP stdio server that forwards Python execution requests to Abaqus."""

from __future__ import annotations

import os
from typing import Any

import anyio
from mcp.server.fastmcp import FastMCP

from .client import AbaqusBridgeClient


DEFAULT_HOST = os.environ.get("ABAQUS_MCP_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("ABAQUS_MCP_PORT", "48152"))
DEFAULT_TIMEOUT = float(os.environ.get("ABAQUS_MCP_TIMEOUT", "60"))

mcp = FastMCP("abaqus-mcp-bridge")


def _client(timeout: float | None = None) -> AbaqusBridgeClient:
    return AbaqusBridgeClient(
        host=DEFAULT_HOST,
        port=DEFAULT_PORT,
        timeout=timeout if timeout is not None else DEFAULT_TIMEOUT,
    )


@mcp.tool()
async def abaqus_ping(timeout: float | None = None) -> dict[str, Any]:
    """Check whether the Abaqus-side bridge agent is reachable."""

    return await anyio.to_thread.run_sync(_client(timeout).ping)


@mcp.tool()
async def abaqus_execute_python(code: str, timeout: float | None = None) -> dict[str, Any]:
    """Execute Python code inside the connected Abaqus Python process.

    If code is a single expression, the expression value is returned. Otherwise
    the code is executed and the value of a variable named `result`, if set, is
    returned. Stdout, stderr, and traceback data are included in the response.
    """

    if not code.strip():
        raise ValueError("code must not be empty")
    return await anyio.to_thread.run_sync(_client(timeout).execute, code)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
