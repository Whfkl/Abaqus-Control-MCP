"""CLI entry points for diagnostics, connectivity check, and plugin setup."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
from importlib import metadata, resources
from pathlib import Path
from typing import Any

from .client import AbaqusBridgeClient


def _print_json(label: str, payload: dict[str, Any]) -> None:
    print(f"{label}:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _entrypoint_path(command: str) -> str | None:
    return shutil.which(command)


def _static_diagnostics() -> dict[str, Any]:
    try:
        version = metadata.version("abaqus-control-mcp")
    except metadata.PackageNotFoundError:
        version = "unknown"

    return {
        "package": {
            "name": "abaqus-control-mcp",
            "version": version,
        },
        "runtime": {
            "python": sys.version,
            "executable": sys.executable,
            "platform": platform.platform(),
        },
        "entrypoints": {
            "abaqus-control-mcp-server": _entrypoint_path("abaqus-control-mcp-server"),
            "abaqus-control-check": _entrypoint_path("abaqus-control-check"),
            "abaqus-control-doctor": _entrypoint_path("abaqus-control-doctor"),
            "abaqus-control-setup": _entrypoint_path("abaqus-control-setup"),
        },
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="abaqus-control-mcp")
    subparsers = parser.add_subparsers(dest="command")

    check_parser = subparsers.add_parser(
        "check",
        help="Check connectivity to the running Abaqus GUI plugin.",
    )
    check_parser.add_argument("--host", default=os.environ.get("ABAQUS_MCP_HOST", "127.0.0.1"))
    check_parser.add_argument("--port", type=int, default=int(os.environ.get("ABAQUS_MCP_PORT", "48152")))
    check_parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("ABAQUS_MCP_TIMEOUT", "10")),
    )
    check_parser.add_argument(
        "--code",
        default="import sys\nresult = {'python': sys.version.split()[0], 'ok': True}",
        help="Python code to execute in the Abaqus-side agent.",
    )

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Print installation and runtime diagnostics.",
    )
    doctor_parser.add_argument(
        "--verify-connection",
        action="store_true",
        help="Also ping the running Abaqus GUI plugin after printing static diagnostics.",
    )
    doctor_parser.add_argument("--host", default=os.environ.get("ABAQUS_MCP_HOST", "127.0.0.1"))
    doctor_parser.add_argument("--port", type=int, default=int(os.environ.get("ABAQUS_MCP_PORT", "48152")))
    doctor_parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("ABAQUS_MCP_TIMEOUT", "10")),
    )

    return parser


def _check_main(args: argparse.Namespace) -> None:
    client = AbaqusBridgeClient(host=args.host, port=args.port, timeout=args.timeout)
    try:
        ping = client.ping()
        execution = client.execute(args.code)
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print("Abaqus MCP agent is reachable.")
    _print_json("Ping", ping)
    _print_json("Execution", execution)


def _doctor_main(args: argparse.Namespace) -> None:
    diagnostics = _static_diagnostics()
    _print_json("Diagnostics", diagnostics)
    if not args.verify_connection:
        return

    client = AbaqusBridgeClient(host=args.host, port=args.port, timeout=args.timeout)
    try:
        ping = client.ping()
    except Exception as exc:
        print(f"Connection check failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    _print_json("Connection", ping)


def setup_main() -> None:
    """Copy the Abaqus GUI plugin into the local Abaqus plugin directory."""
    target_dir = Path(os.environ.get("ABAQUS_MCP_PLUGIN_DIR", Path.home() / "abaqus_plugins"))
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "abaqus_mcp_gui_plugin.py"

    package_files = resources.files("abaqus_mcp_bridge")
    source = package_files.joinpath("gui_plugin.py")
    with resources.as_file(source) as src:
        # If target exists and is identical, skip
        if target.exists() and target.read_bytes() == Path(src).read_bytes():
            print(f"Plugin already up to date: {target}")
            return
        shutil.copy2(src, target)

    print(f"Installed GUI plugin to: {target}")
    print()
    print("Restart Abaqus/CAE, then activate:")
    print("Plug-ins -> Abaqus-Control-MCP -> Start MCP Bridge")


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    command = args.command or "check"

    if command == "check":
        _check_main(args)
    elif command == "doctor":
        _doctor_main(args)
    else:
        parser.error(f"unknown command: {command}")


def check_main() -> None:
    parser = _build_parser()
    args = parser.parse_args(["check", *sys.argv[1:]])
    _check_main(args)


def doctor_main() -> None:
    parser = _build_parser()
    args = parser.parse_args(["doctor", *sys.argv[1:]])
    _doctor_main(args)


if __name__ == "__main__":
    main()
