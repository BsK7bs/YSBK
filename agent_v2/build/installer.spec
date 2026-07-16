# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the installer EXE (produces installer.exe, which
build.ps1 renames to DigitalTwinAgentSetup.exe).

The spec prints every resolved path it uses and asserts the entry script
contains the current fast-path implementation. If PyInstaller ever picks
up a stale or wrong entry script the build FAILS LOUDLY at spec-load time
instead of shipping a broken EXE that hangs the CI.
"""
import hashlib
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------
SPEC_FILE  = Path(SPECPATH).resolve() / "installer.spec"
AGENT_ROOT = Path(SPECPATH).resolve().parents[0]     # <repo>/agent_v2
REPO_ROOT  = Path(SPECPATH).resolve().parents[1]     # <repo>
ENTRY      = AGENT_ROOT / "installer" / "__main__.py"

# Emit resolved paths to stdout so the GitHub Actions log shows exactly
# which files PyInstaller is packaging. This eliminates any "which
# __main__.py did it use?" ambiguity.
print("=" * 72)
print("[installer.spec] RESOLVED PATHS")
print(f"[installer.spec]   SPECPATH   = {SPECPATH}")
print(f"[installer.spec]   REPO_ROOT  = {REPO_ROOT}")
print(f"[installer.spec]   AGENT_ROOT = {AGENT_ROOT}")
print(f"[installer.spec]   ENTRY      = {ENTRY}")
print(f"[installer.spec]   SPEC_FILE  = {SPEC_FILE}")
print(f"[installer.spec]   sys.executable = {sys.executable}")
print("=" * 72)

# ---------------------------------------------------------------------------
# Existence + freshness assertions
# ---------------------------------------------------------------------------
assert ENTRY.is_file(), f"[installer.spec] FATAL: entry not found at {ENTRY}"
assert (REPO_ROOT / "agent_v2" / "__init__.py").is_file(), (
    f"[installer.spec] FATAL: agent_v2 package marker missing at "
    f"{REPO_ROOT / 'agent_v2' / '__init__.py'}"
)

_entry_src = ENTRY.read_text(encoding="utf-8")
_entry_sha = hashlib.sha256(_entry_src.encode("utf-8")).hexdigest()
_entry_size = ENTRY.stat().st_size

print(f"[installer.spec]   ENTRY.size = {_entry_size} bytes")
print(f"[installer.spec]   ENTRY.sha256 = {_entry_sha}")

# ---------------------------------------------------------------------------
# CONTENT ASSERTIONS \u2014 refuse to build if the entry script is missing
# the current fast-path implementation. Each MARKER is a substring that
# MUST be present in the file that will be frozen. If any assertion
# fails the build stops with a clear error pointing at the exact file
# PyInstaller was about to package, so a stale checkout / wrong path /
# case-mismatch on Windows can never silently ship a broken EXE.
# ---------------------------------------------------------------------------
REQUIRED_MARKERS = [
    # Fast-path breadcrumb prefix - must appear in stderr on every launch
    '[installer.boot]',
    # Fast-path guard clause \u2014 must run at module load, not inside run()
    'if "--self-test" in _sys.argv:',
    'if "--version" in _sys.argv:',
    # Emergency-print helper (raw os.write, GUI-subsystem-safe)
    'def _emergency_print(',
    # T0 timer initialisation \u2014 proves breadcrumbs are on
    '_T0 = _time.perf_counter()',
    # No __future__ import at the top (must not appear before fast-path)
    # This is enforced structurally: fast-path is the first thing after
    # imports.
]
_missing = [m for m in REQUIRED_MARKERS if m not in _entry_src]
if _missing:
    print("[installer.spec] FATAL: the entry script does NOT contain the "
          "current fast-path implementation.")
    print(f"[installer.spec]   ENTRY = {ENTRY}")
    print(f"[installer.spec]   Missing markers:")
    for m in _missing:
        print(f"[installer.spec]     - {m!r}")
    print("[installer.spec] This usually means:")
    print("[installer.spec]   * A stale copy of __main__.py is being picked up.")
    print("[installer.spec]   * The workspace checkout is dirty / on the wrong ref.")
    print("[installer.spec]   * PyInstaller cache is stuck on an old version.")
    print("[installer.spec] Refusing to build a broken EXE.")
    raise SystemExit(1)

# Also make sure nothing that would delay the fast-path leaked in above it.
_fastpath_ix = _entry_src.index('if "--self-test" in _sys.argv:')
_prefix = _entry_src[:_fastpath_ix]
FORBIDDEN_ABOVE_FASTPATH = [
    "import tkinter",
    "import httpx",
    "import win32event",
    "import servicemanager",
    "from agent_v2.modules.enrollment",  # imports httpx
    "from agent_v2.modules.service",     # imports pywin32
    "from agent_v2.installer import gui",  # imports tkinter
    "time.sleep(",                       # explicit sleep
    "logging.basicConfig(",              # heavy logging setup
]
_leaked = [t for t in FORBIDDEN_ABOVE_FASTPATH if t in _prefix]
if _leaked:
    print("[installer.spec] FATAL: forbidden imports/calls appear ABOVE "
          "the --self-test fast-path in the entry script.")
    print(f"[installer.spec]   ENTRY = {ENTRY}")
    for t in _leaked:
        print(f"[installer.spec]     - {t!r}")
    print("[installer.spec] Anything above the fast-path can delay or hang "
          "--self-test in a non-interactive session. Refusing to build.")
    raise SystemExit(1)

print(f"[installer.spec] All {len(REQUIRED_MARKERS)} required markers present in ENTRY.")
print(f"[installer.spec] Nothing forbidden appears above the fast-path.")
print("[installer.spec] OK \u2014 proceeding with Analysis / PYZ / EXE build.")
print("=" * 72)

# ---------------------------------------------------------------------------
# Hidden imports
# ---------------------------------------------------------------------------
# Pull in every ``agent_v2.*`` submodule so PyInstaller does not miss anything
# that is imported dynamically at runtime.
hidden = set(collect_submodules("agent_v2"))
hidden.update({
    # pywin32 pieces the service registrar / installer touch
    "win32timezone", "win32serviceutil", "win32service",
    "win32event", "win32cred", "win32api", "win32con",
    "servicemanager", "pywintypes",
    # tkinter GUI wrapper
    "tkinter", "tkinter.ttk", "tkinter.messagebox",
    # Explicit installer surface (belt-and-braces \u2014 collect_submodules already covers)
    "agent_v2",
    "agent_v2.common",
    "agent_v2.common.paths",
    "agent_v2.common.version",
    "agent_v2.common.system_info",
    "agent_v2.installer",
    "agent_v2.installer.file_layout",
    "agent_v2.installer.gui",
    "agent_v2.modules",
    "agent_v2.modules.enrollment",
    "agent_v2.modules.enrollment.pairing",
    "agent_v2.modules.logmod",
    "agent_v2.modules.logmod.setup",
    "agent_v2.modules.service",
    "agent_v2.modules.service.framework",
    "agent_v2.modules.service.registrar",
    "agent_v2.modules.auth",
    "agent_v2.modules.auth.credentials",
})

a = Analysis(
    [str(ENTRY)],
    pathex=[str(REPO_ROOT), str(AGENT_ROOT)],
    binaries=[],
    datas=collect_data_files("agent_v2", include_py_files=False),
    hiddenimports=sorted(hidden),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter.test"],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=None)
exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas,
    name="installer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # console=True is REQUIRED. A Windows GUI-subsystem EXE (console=False)
    # cannot inherit stdin/stdout/stderr pipes from a PowerShell parent that
    # uses ``Start-Process -RedirectStandardOutput``. Under non-interactive
    # automation the process becomes ORPHANED from its output handles and
    # ``WaitForExit`` blocks until the caller's wall-clock timeout kills
    # it \u2014 which is exactly the 30-second CI hang we saw in 2026-07.
    #
    # Making the installer a CONSOLE subsystem app means:
    #   * ``--self-test`` and ``--version`` write cleanly to a redirected
    #     stdout, ``WaitForExit`` returns as soon as the process ends.
    #   * When an end-user double-clicks the EXE, Windows briefly shows a
    #     console window before the tkinter wizard opens \u2014 acceptable
    #     UX; every mainstream Python-based Windows installer works this
    #     way (pyinstaller\'s own bootloader test suite included).
    #   * The runtime UAC elevation path (``_relaunch_elevated`` \u2192
    #     ``ShellExecuteW("runas", ...)``) is unaffected \u2014 that call
    #     produces a UAC dialog independent of console/windowed subsystem.
    console=True,
    disable_windowed_traceback=False,
    icon=None,
    # NOTE: uac_admin=False on purpose. See 2026-07 fix log \u2014 baking
    # requireAdministrator into the manifest triggers a UAC prompt from
    # the OS BEFORE the Python interpreter starts, which hangs any non-
    # interactive session. Runtime elevation is handled by run().
    uac_admin=False,
    manifest=None,
)
