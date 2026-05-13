"""CLI entry points for diagnostics, connectivity check, and plugin setup."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from importlib import metadata, resources
from pathlib import Path
from typing import Any

from .client import AbaqusBridgeClient


def _ensure_utf8_stdout() -> None:
    """Reconfigure stdout/stderr to UTF-8 on Windows to avoid GBK encoding errors."""
    if sys.platform == "win32":
        for stream_name in ("stdout", "stderr"):
            stream = getattr(sys, stream_name, None)
            if stream is not None:
                try:
                    stream.reconfigure(encoding="utf-8", errors="replace")
                except (AttributeError, OSError):
                    pass


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
        "mcp_clients": _mcp_status(),
    }


def _register_mcp_claude(scope: str = "user") -> dict[str, Any]:
    """Register the MCP server with Claude Code via ``claude mcp add``."""
    claude = shutil.which("claude")
    if not claude:
        return {"status": "skipped", "reason": "claude CLI not found on PATH"}

    server_exe = shutil.which("abaqus-control-mcp-server")
    if not server_exe:
        return {"status": "skipped", "reason": "abaqus-control-mcp-server not found on PATH"}

    cmd = [
        claude, "mcp", "add",
        "-s", scope,
        "-e", "ABAQUS_MCP_HOST=127.0.0.1",
        "-e", "ABAQUS_MCP_PORT=48152",
        "-e", "ABAQUS_MCP_TIMEOUT=120",
        "abaqus",
        server_exe,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
        )
        if result.returncode == 0:
            return {"status": "registered", "scope": scope, "output": result.stdout.strip()}
        return {"status": "failed", "returncode": result.returncode, "stderr": result.stderr.strip()}
    except FileNotFoundError:
        return {"status": "skipped", "reason": "claude CLI not found"}
    except subprocess.TimeoutExpired:
        return {"status": "failed", "reason": "claude mcp add timed out"}


def _mcp_status() -> dict[str, Any]:
    """Check MCP registration status for known clients."""
    status: dict[str, Any] = {}

    claude = shutil.which("claude")
    status["claude_cli"] = claude is not None
    if claude:
        try:
            result = subprocess.run(
                [claude, "mcp", "list"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
            )
            status["claude_mcp_registered"] = "abaqus" in result.stdout.lower()
            status["claude_mcp_output"] = result.stdout.strip()
        except Exception:
            status["claude_mcp_registered"] = None

    return status


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

    setup_parser = subparsers.add_parser(
        "setup",
        help="Install GUI plugin and register MCP server.",
    )
    setup_parser.add_argument(
        "--scope",
        choices=["user", "project", "skip"],
        default="user",
        help="MCP registration scope: 'user' (global), 'project' (current dir), or 'skip' (no registration). Default: user.",
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


def _setup_main(args: argparse.Namespace) -> None:
    """Copy the Abaqus GUI plugin and optionally register MCP server."""
    # Step 1: Install GUI plugin
    target_dir = Path(os.environ.get("ABAQUS_MCP_PLUGIN_DIR", Path.home() / "abaqus_plugins"))
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "abaqus_mcp_gui_plugin.py"

    package_files = resources.files("abaqus_mcp_bridge")
    source = package_files.joinpath("gui_plugin.py")
    with resources.as_file(source) as src:
        if target.exists() and target.read_bytes() == Path(src).read_bytes():
            print(f"Plugin already up to date: {target}")
        else:
            shutil.copy2(src, target)
            print(f"Installed GUI plugin to: {target}")

    # Step 2: Register MCP server
    scope = getattr(args, "scope", "user")
    if scope != "skip":
        print()
        print(f"Registering MCP server with Claude Code (scope={scope})...")
        result = _register_mcp_claude(scope)
        if result["status"] == "registered":
            print(f"MCP server registered: {result.get('output', '')}")
        elif result["status"] == "skipped":
            print(f"MCP registration skipped: {result['reason']}")
            _print_manual_mcp_instructions()
        else:
            print(f"MCP registration failed: {result.get('stderr', result.get('reason', ''))}")
            _print_manual_mcp_instructions()

    print()
    print("Restart Abaqus/CAE, then activate:")
    print("Plug-ins -> Abaqus-Control-MCP -> Start MCP Bridge")


def _print_manual_mcp_instructions() -> None:
    """Print fallback manual MCP registration instructions."""
    print()
    print("To register manually, run:")
    print("  claude mcp add -s user -e ABAQUS_MCP_HOST=127.0.0.1 \\")
    print("    -e ABAQUS_MCP_PORT=48152 -e ABAQUS_MCP_TIMEOUT=120 \\")
    print("    abaqus /absolute/path/to/abaqus-control-mcp-server")
    print()
    print("Find the path with: where abaqus-control-mcp-server (Windows)")
    print("                    which abaqus-control-mcp-server (Linux/macOS)")


def main() -> None:
    _ensure_utf8_stdout()
    parser = _build_parser()
    args = parser.parse_args()
    command = args.command or "check"

    if command == "check":
        _check_main(args)
    elif command == "doctor":
        _doctor_main(args)
    elif command == "setup":
        _setup_main(args)
    else:
        parser.error(f"unknown command: {command}")


def check_main() -> None:
    _ensure_utf8_stdout()
    parser = _build_parser()
    args = parser.parse_args(["check", *sys.argv[1:]])
    _check_main(args)


def doctor_main() -> None:
    _ensure_utf8_stdout()
    parser = _build_parser()
    args = parser.parse_args(["doctor", *sys.argv[1:]])
    _doctor_main(args)


def setup_main() -> None:
    _ensure_utf8_stdout()
    parser = _build_parser()
    args = parser.parse_args(["setup", *sys.argv[1:]])
    _setup_main(args)


if __name__ == "__main__":
    main()
