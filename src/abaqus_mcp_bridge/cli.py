"""Small human-facing CLI helpers for bridge diagnostics and setup."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
from importlib import metadata
from typing import Any

from .client import AbaqusBridgeClient
from .installer import default_plugin_dir, install_gui_plugin, plugin_resource_name


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
            "abaqus-control-install-plugin": _entrypoint_path("abaqus-control-install-plugin"),
            "abaqus-control-doctor": _entrypoint_path("abaqus-control-doctor"),
        },
        "plugin": {
            "resource": plugin_resource_name(),
            "default_target_dir": str(default_plugin_dir()),
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

    install_parser = subparsers.add_parser(
        "install-plugin",
        help="Install the Abaqus/CAE GUI plugin into the local plugin directory.",
    )
    install_parser.add_argument(
        "--target-dir",
        default=None,
        help="Target plugin directory. Defaults to ABAQUS_MCP_PLUGIN_DIR or ~/abaqus_plugins.",
    )
    install_parser.add_argument(
        "--no-overwrite",
        action="store_true",
        help="Do not overwrite an existing plugin file if it differs.",
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


def _install_plugin_main(args: argparse.Namespace) -> None:
    result = install_gui_plugin(target_dir=args.target_dir, overwrite=not args.no_overwrite)
    if result.get("skipped"):
        print("Plugin already exists and overwrite was disabled.")
    elif result.get("already_current"):
        print("Plugin is already up to date.")
    else:
        print("Installed Abaqus GUI plugin.")
    _print_json("Result", result)
    print("Restart Abaqus/CAE, then activate:")
    print("Plug-ins -> Abaqus-Control-MCP -> Start MCP GUI Agent")


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


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    command = args.command or "check"

    if command == "check":
        _check_main(args)
    elif command == "install-plugin":
        _install_plugin_main(args)
    elif command == "doctor":
        _doctor_main(args)
    else:
        parser.error(f"unknown command: {command}")


def check_main() -> None:
    parser = _build_parser()
    args = parser.parse_args(["check", *sys.argv[1:]])
    _check_main(args)


def install_plugin_main() -> None:
    parser = _build_parser()
    args = parser.parse_args(["install-plugin", *sys.argv[1:]])
    _install_plugin_main(args)


def doctor_main() -> None:
    parser = _build_parser()
    args = parser.parse_args(["doctor", *sys.argv[1:]])
    _doctor_main(args)


if __name__ == "__main__":
    main()
