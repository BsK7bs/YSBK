"""Copy installer + agent + uninstaller EXEs into Program Files.

Runs in two modes:
  * ``running_frozen()`` → the caller is ``installer.exe``. We expect
    ``agent.exe`` (and optionally ``uninstaller.exe``) to sit next to it, and
    we copy them into ``C:\\Program Files\\DigitalTwin``.
  * Dev mode → we copy the whole ``agent_v2`` source tree so ``python -m
    agent_v2.agent`` still works after install.

Returns the path to the executable that Windows Service Control Manager
should launch.

Imports use the absolute ``agent_v2.*`` path so this file is safe whether
it is imported through the frozen entry-point or via ``python -m``.
"""
from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path

from agent_v2.common import paths

log = logging.getLogger("dta.installer.layout")


def copy_agent_files(destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    if paths.running_frozen():
        src = Path(sys.executable).parent
        agent_exe = src / "agent.exe"
        if not agent_exe.exists():
            raise RuntimeError(
                f"agent.exe missing next to installer.exe (looked in {src}). Re-download the installer bundle."
            )
        shutil.copy2(agent_exe, destination / "agent.exe")
        for extra in ("uninstaller.exe", "README.txt", "LICENSE.txt"):
            p = src / extra
            if p.exists():
                shutil.copy2(p, destination / extra)
        log.info("copied binaries → %s", destination)
        return destination / "agent.exe"
    # Dev mode
    src_root = Path(__file__).resolve().parents[1]  # /app/agent_v2
    src_dst = destination / "src"
    if src_dst.exists():
        shutil.rmtree(src_dst)
    shutil.copytree(
        src_root, src_dst,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "build", "dist", "node_modules"),
    )
    shim = destination / "agent.cmd"
    shim.write_text(
        f'@echo off\r\n"{sys.executable}" -m agent_v2.agent %*\r\n', encoding="utf-8",
    )
    log.info("dev-mode source tree copied → %s", src_dst)
    return shim
