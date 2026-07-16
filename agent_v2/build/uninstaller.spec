# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for uninstaller.exe.

Entry point:  agent_v2/uninstaller/__main__.py  (absolute imports only).
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

AGENT_ROOT = Path(SPECPATH).resolve().parents[0]   # <repo>/agent_v2
REPO_ROOT  = Path(SPECPATH).resolve().parents[1]   # <repo>

ENTRY = AGENT_ROOT / "uninstaller" / "__main__.py"
assert ENTRY.is_file(), f"uninstaller entry not found at {ENTRY}"
assert (REPO_ROOT / "agent_v2" / "__init__.py").is_file(), (
    f"agent_v2 package marker missing at {REPO_ROOT / 'agent_v2' / '__init__.py'}"
)

hidden = set(collect_submodules("agent_v2"))
hidden.update({
    "win32cred", "win32serviceutil", "win32service", "win32api", "win32con",
    "servicemanager", "pywintypes",
})

a = Analysis(
    [str(ENTRY)],
    pathex=[str(REPO_ROOT), str(AGENT_ROOT)],
    binaries=[],
    datas=collect_data_files("agent_v2", include_py_files=False),
    hiddenimports=sorted(hidden),
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter.test"],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=None)
exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas,
    name="uninstaller",
    debug=False, strip=False, upx=False, console=True,
    # See installer.spec for the rationale. Runtime elevation is handled
    # in the entry-point code, not by a mandatory manifest bit \u2014 so
    # --version / --self-test can complete without the OS blocking on UAC.
    uac_admin=False,
)
