"""Install-time helpers for the Abaqus GUI plugin."""

from __future__ import annotations

import filecmp
import os
import shutil
from importlib import resources
from pathlib import Path
from typing import Any


PLUGIN_FILENAME = "abaqus_mcp_gui_plugin.py"
PLUGIN_RESOURCE = "gui_plugin.py"
DEFAULT_PLUGIN_DIR = Path.home() / "abaqus_plugins"
PLUGIN_DIR_ENV = "ABAQUS_MCP_PLUGIN_DIR"


def default_plugin_dir() -> Path:
    """Return the preferred Abaqus plugin directory."""
    configured = os.environ.get(PLUGIN_DIR_ENV)
    if configured:
        return Path(configured).expanduser()
    return DEFAULT_PLUGIN_DIR


def plugin_resource_name() -> str:
    """Return the resource name for the packaged GUI plugin template."""
    return PLUGIN_RESOURCE


def _copy_source_to_target(source: Path, target: Path, overwrite: bool) -> dict[str, Any]:
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists():
        same_file = filecmp.cmp(source, target, shallow=False)
        if same_file:
            return {"installed": False, "updated": False, "already_current": True}
        if not overwrite:
            return {
                "installed": False,
                "updated": False,
                "already_current": False,
                "skipped": True,
            }

    shutil.copyfile(source, target)
    return {"installed": True, "updated": True, "already_current": False}


def install_gui_plugin(target_dir: str | os.PathLike[str] | None = None, overwrite: bool = True) -> dict[str, Any]:
    """Install the packaged GUI plugin into an Abaqus plugin directory."""
    destination_dir = Path(target_dir).expanduser() if target_dir is not None else default_plugin_dir()
    package_files = resources.files("abaqus_mcp_bridge")
    resource = package_files.joinpath(PLUGIN_RESOURCE)

    with resources.as_file(resource) as source_path:
        target = destination_dir / PLUGIN_FILENAME
        copy_result = _copy_source_to_target(Path(source_path), target, overwrite=overwrite)

    return {
        "ok": True,
        "source": str(resource),
        "target_dir": str(destination_dir),
        "target": str(target),
        "plugin_filename": PLUGIN_FILENAME,
        "overwrite": overwrite,
        **copy_result,
    }
