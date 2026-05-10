"""Small human-facing CLI helpers for bridge diagnostics."""

from __future__ import annotations

import argparse
import json
import os
import sys

from .client import AbaqusBridgeClient


def check_main() -> None:
    parser = argparse.ArgumentParser(
        description="Check the Abaqus MCP socket agent without starting an MCP stdio session."
    )
    parser.add_argument("--host", default=os.environ.get("ABAQUS_MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("ABAQUS_MCP_PORT", "48152")))
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("ABAQUS_MCP_TIMEOUT", "10")),
    )
    parser.add_argument(
        "--code",
        default="import sys\nresult = {'python': sys.version.split()[0], 'ok': True}",
        help="Python code to execute in the Abaqus-side agent.",
    )
    args = parser.parse_args()

    client = AbaqusBridgeClient(host=args.host, port=args.port, timeout=args.timeout)
    try:
        ping = client.ping()
        execution = client.execute(args.code)
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print("Abaqus MCP agent is reachable.")
    print("Ping:")
    print(json.dumps(ping, ensure_ascii=False, indent=2))
    print("Execution:")
    print(json.dumps(execution, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    check_main()
