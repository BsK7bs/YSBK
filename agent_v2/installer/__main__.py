"""Digital Twin Agent installer — the ONE and ONLY install path.

Customer flow (no PowerShell, no Python prompts, no external prerequisites):

    Dashboard  →  Download Agent  →  DigitalTwinAgentSetup_DT-XXXX-YYYY.exe
                                           |
                                           v  double-click (UAC prompt)
                                     1. Elevate
                                     2. Create ProgramData\\DigitalTwin
                                     3. Copy binaries into Program Files
                                     4. Register + start Windows Service
                                     5. Pair with backend (POST /api/agent/pair)
                                     6. Verify enrollment (device is online)
                                     7. Success screen

If any step fails, the installer shows a clear error dialog with the failing
step + underlying reason. It never silently continues.

The pairing code is encoded into the installer's own filename by the backend
download endpoint (see ``backend/app/routers/agent_installer.py``), so no
external sidecar files or interactive prompts are required.

IMPORT MODEL (two invariants)
-----------------------------
1. **Entry-point scripts use absolute imports only.**
   PyInstaller runs the frozen EXE with ``__name__ == '__main__'`` and
   ``__package__ == ''``, so ``from ..common import paths`` raises
   ``ImportError: attempted relative import with no known parent package``.
   Every import at module scope below is absolute (``from agent_v2.<x>...``).

2. **Module scope stays lightweight.**
   Only ``agent_v2.common.paths`` and ``agent_v2.common.version`` are
   imported eagerly — they are pure-Python, stdlib-only, and are needed by
   the argparse defaults + ``--self-test`` output. Everything else
   (networking via ``httpx``, Windows service registration via ``pywin32``,
   pairing, tkinter GUI, etc.) is imported LAZILY inside the function that
   uses it. This has two big wins:
     * ``DigitalTwinAgentSetup.exe --version`` and ``--self-test`` boot in
       milliseconds with zero third-party dependencies, so CI smoke tests
       cannot be blocked by a missing ``httpx`` or ``pywin32`` wheel.
     * The frozen EXE can still tell the operator "I started successfully"
       even in extreme environments (offline, no pywin32, wrong Windows SKU).

Both invariants are enforced by ``test_installer_imports.py`` in CI.
"""
# ===========================================================================
# STARTUP FAST-PATH  \u2014  read carefully before editing.
# ===========================================================================
# The block below runs BEFORE every other line of user code in this module.
# It exists because CI (and any non-interactive automation) needs
# ``DigitalTwinAgentSetup.exe --self-test`` and ``--version`` to return in
# a few hundred milliseconds with:
#
#   * no imports beyond stdlib
#   * no logging init
#   * no sys.path shuffling
#   * no admin check / UAC re-launch
#   * no service registration
#   * no backend contact
#   * no GUI (tkinter / ttk / messagebox)
#   * no sleeps, no locks, no background threads
#
# The only characters that run before the fast-path check are the module
# docstring above (a string literal, not code) and the ``import sys, os,
# time`` triple. Every other import happens AFTER we have decided we are
# NOT on the fast-path.
#
# We also emit timestamped breadcrumbs to stderr via ``os.write(2, ...)``
# so any future regression that reintroduces a hang shows up in the CI
# log with a millisecond-resolution timeline pointing at the exact line
# that blocked.
# ===========================================================================
import os as _os  # noqa: E402
import sys as _sys  # noqa: E402
import time as _time  # noqa: E402

_T0 = _time.perf_counter()


def _breadcrumb(label: str) -> None:
    """Emit a timestamped breadcrumb to fd 2 (stderr) via a raw OS write.

    Uses ``os.write`` (not ``print``) because on Windows GUI-subsystem EXEs
    the higher-level ``sys.stderr`` may be a NullWriter, a closed handle,
    or a buffered stream that blocks on flush. A raw fd write is the most
    likely thing to make it into a CI redirect file.
    """
    try:
        ms = (_time.perf_counter() - _T0) * 1000.0
        line = f"[installer.boot] {ms:8.2f} ms  {label}\n".encode("utf-8", "replace")
        try:
            _os.write(2, line)
        except (OSError, ValueError):
            # fd 2 may be closed under Windows subsystem apps; try fd 1 next.
            try:
                _os.write(1, line)
            except (OSError, ValueError):
                pass
    except Exception:
        # Never let logging break the installer.
        pass


_breadcrumb("process started; interpreter is up")


def _emergency_print(text: str) -> None:
    """Best-effort write to stdout that survives GUI-subsystem stripping."""
    payload = (text if text.endswith("\n") else text + "\n").encode("utf-8", "replace")
    for fd in (1, 2):
        try:
            _os.write(fd, payload)
            return
        except (OSError, ValueError):
            continue


def _fastpath_syspath_bootstrap() -> None:
    """Minimal sys.path prep for the fast-path only.

    Adds the repo root (or PyInstaller _MEIPASS) to sys.path so the two
    stdlib-only imports below can resolve. This is a strict subset of the
    full ``_bootstrap_syspath()`` further down; kept separate + inlined so
    the fast-path never depends on any code below the ``exit()`` line.
    """
    if getattr(_sys, "frozen", False):
        meipass = getattr(_sys, "_MEIPASS", "")
        for candidate in (meipass, _os.path.join(meipass, "agent_v2"),
                          _os.path.dirname(_sys.executable)):
            if candidate and candidate not in _sys.path:
                _sys.path.insert(0, candidate)
    else:
        # ``__file__`` == <repo>/agent_v2/installer/__main__.py
        # so <repo> is two directories up.
        repo_root = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
        if repo_root not in _sys.path:
            _sys.path.insert(0, repo_root)


# ---------------------------------------------------------------------------
# THE FAST-PATH. Nothing above this line is allowed to (a) import a third-
# party package, (b) call into the OS, or (c) block. Nothing between here
# and the ``return`` below is allowed to do any of those things either.
# ---------------------------------------------------------------------------
if "--self-test" in _sys.argv:
    _breadcrumb("--self-test detected; entering _self_test()")
    _fastpath_syspath_bootstrap()
    _breadcrumb("sys.path bootstrapped")
    # Import the two stdlib-only helpers used inside _self_test lazily so
    # even the version import cannot delay the fast-path. Both modules are
    # verified to have NO third-party imports in test_installer_imports.py.
    from agent_v2.common.version import (
        AGENT_VERSION as _AGENT_VERSION,
        DEFAULT_BACKEND_URL as _DEFAULT_BACKEND_URL,
        INSTALLER_VERSION as _INSTALLER_VERSION,
    )
    from agent_v2.common import paths as _paths_ft

    import importlib.util as _iutil
    import json as _json

    _banner = {
        "check": "installer.self_test",
        "result": "ok",
        "installer_version": _INSTALLER_VERSION,
        "agent_version": _AGENT_VERSION,
        "default_backend_url": _DEFAULT_BACKEND_URL,
        "frozen": getattr(_sys, "frozen", False),
        "meipass": getattr(_sys, "_MEIPASS", None),
        "executable": _sys.executable,
        "argv": _sys.argv,
        "sys_path_head": _sys.path[:5],
        "package_tree": {},
        "boot_timeline_ms": {},
    }
    _breadcrumb("fast-path banner initialised")

    _safe_packages = ("agent_v2", "agent_v2.common", "agent_v2.installer", "agent_v2.modules")
    _missing = []
    for _p in _safe_packages:
        _t = _time.perf_counter()
        _spec = _iutil.find_spec(_p)
        _banner["boot_timeline_ms"][f"find_spec({_p})"] = round((_time.perf_counter() - _t) * 1000, 3)
        if _spec is None:
            _missing.append(_p)
            _banner["package_tree"][_p] = None
        else:
            _banner["package_tree"][_p] = _spec.origin or "namespace-package"

    _banner["boot_timeline_ms"]["total"] = round((_time.perf_counter() - _T0) * 1000, 3)
    if _missing:
        _banner["result"] = "fail"
        _banner["missing_packages"] = _missing

    _emergency_print(_json.dumps(_banner, indent=2, default=str))
    _breadcrumb(f"--self-test complete; exit={0 if not _missing else 1}")
    _sys.exit(0 if not _missing else 1)

if "--version" in _sys.argv:
    _breadcrumb("--version detected; printing and exiting")
    _fastpath_syspath_bootstrap()
    from agent_v2.common.version import INSTALLER_VERSION as _INSTALLER_VERSION
    _emergency_print(_INSTALLER_VERSION)
    _sys.exit(0)


# ===========================================================================
# END FAST-PATH. From here on we are on the "real install" path and may
# freely import heavy modules (tkinter, pywin32, httpx, etc.).
# ===========================================================================
_breadcrumb("fast-path not taken; loading full install pipeline")

import argparse
import logging
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# sys.path bootstrap \u2014 must run BEFORE the first ``import agent_v2.*`` below.
# ---------------------------------------------------------------------------
def _bootstrap_syspath() -> None:
    if getattr(_sys, "frozen", False):
        meipass = Path(getattr(_sys, "_MEIPASS", ""))
        for candidate in (meipass, meipass / "agent_v2", Path(_sys.executable).parent):
            if candidate and str(candidate) not in _sys.path:
                _sys.path.insert(0, str(candidate))
    else:
        # Dev mode: ensure the repo root (grandparent of this file) is on sys.path.
        repo_root = Path(__file__).resolve().parents[2]
        if str(repo_root) not in _sys.path:
            _sys.path.insert(0, str(repo_root))


_bootstrap_syspath()

# ---------------------------------------------------------------------------
# The ONLY absolute imports allowed at module scope: stdlib-only, no third-
# party dependencies. Anything that pulls in httpx / pywin32 / tkinter /
# websockets etc. MUST be imported lazily inside the function that uses it.
# ---------------------------------------------------------------------------
from agent_v2.common import paths as _paths  # noqa: E402  (stdlib-only)
from agent_v2.common.version import (  # noqa: E402  (constants module, stdlib-only)
    AGENT_VERSION,
    DEFAULT_BACKEND_URL,
    INSTALLER_VERSION,
)

# Rebind stdlib module aliases used elsewhere in the file (the fast-path
# used ``_sys`` / ``_os`` / ``_time`` \u2014 the rest of the file still uses
# the conventional short names).
sys = _sys
os = _os

log = logging.getLogger("dta.installer")

# DT-XXXX-YYYY   e.g. DT-9K3P-42AB
CODE_RE = re.compile(r"DT-[A-Z0-9]{4}-[A-Z0-9]{4}")


class InstallStepError(RuntimeError):
    """Raised when a specific install step fails; the message becomes the
    error dialog text so it MUST be end-user-friendly."""


# ---------------------------------------------------------------------------
# Admin elevation
# ---------------------------------------------------------------------------
def _is_admin() -> bool:
    if sys.platform != "win32":
        return os.geteuid() == 0 if hasattr(os, "geteuid") else True
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001
        return False


def _relaunch_elevated() -> int:
    if sys.platform != "win32":
        return 0
    try:
        import ctypes
        params = " ".join(f'"{a}"' for a in sys.argv[1:])
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
        return 0 if rc > 32 else 1
    except Exception as exc:  # noqa: BLE001
        log.error("UAC elevation failed: %s", exc)
        return 1


# ---------------------------------------------------------------------------
# Pairing-code extraction (from filename or --code arg)
# ---------------------------------------------------------------------------
def _extract_pairing_code(cli_code: str | None) -> str | None:
    if cli_code:
        cli_code = cli_code.strip().upper()
        if CODE_RE.fullmatch(cli_code):
            return cli_code
        raise InstallStepError(
            f"--code '{cli_code}' is not a valid pairing code (expected DT-XXXX-YYYY)."
        )
    candidates: list[str] = []
    if _paths.running_frozen():
        candidates.append(Path(sys.executable).name)
    if sys.argv:
        candidates.append(Path(sys.argv[0]).name)
        candidates.append(Path(sys.argv[0]).parent.name)
    for name in candidates:
        m = CODE_RE.search(name.upper())
        if m:
            return m.group(0)
    return None


# ---------------------------------------------------------------------------
# Individual install steps — each imports its heavy dependencies LAZILY so
# --self-test / --version never trigger httpx or pywin32.
# ---------------------------------------------------------------------------
def _step_prepare(cb):
    cb("Preparing ProgramData…")
    try:
        _paths.ensure_data_dirs()
    except OSError as exc:
        raise InstallStepError(
            f"Could not create {_paths.program_data_dir()} — check disk space + permissions ({exc})."
        ) from exc


def _step_copy(cb, install_dir: Path) -> Path:
    cb("Copying agent files to Program Files…")
    from agent_v2.installer import file_layout  # lazy — pure-Python, but keep style consistent
    try:
        return file_layout.copy_agent_files(install_dir)
    except Exception as exc:  # noqa: BLE001
        raise InstallStepError(
            f"Could not copy agent binaries into {install_dir}. Detail: {exc}"
        ) from exc


def _step_register_service(cb, agent_exe: Path):
    cb("Registering Windows Service (DigitalTwinAgent)…")
    from agent_v2.modules.service import registrar as service_registrar  # lazy — needs pywin32
    try:
        service_registrar.install(agent_exe, start_type="auto")
    except service_registrar.ServiceError as exc:
        raise InstallStepError(f"Windows Service registration failed: {exc}") from exc


def _step_start_service(cb):
    cb("Starting Windows Service…")
    from agent_v2.modules.service import registrar as service_registrar  # lazy — needs pywin32
    try:
        service_registrar.start()
    except service_registrar.ServiceError as exc:
        raise InstallStepError(f"Windows Service failed to start: {exc}") from exc
    if not service_registrar.wait_until_running(timeout=30.0):
        raise InstallStepError(
            "Windows Service did not reach the RUNNING state within 30 seconds. "
            "Check the Event Viewer under 'Digital Twin Agent' for details."
        )


def _step_pair(cb, backend_url: str, code: str) -> dict:
    cb("Pairing with backend…")
    from agent_v2.modules.enrollment.pairing import PairError, pair  # lazy — needs httpx
    try:
        creds = pair(backend_url, code)
    except PairError as exc:
        raise InstallStepError(f"Pairing failed: {exc}") from exc
    try:
        creds.save(_paths.program_data_dir())
    except Exception as exc:  # noqa: BLE001
        raise InstallStepError(
            f"Pairing succeeded but the credentials could not be persisted: {exc}"
        ) from exc
    return {"device_id": creds.device_id, "org_id": creds.org_id, "hostname": creds.hostname}


def _step_verify_online(cb, backend_url: str, device_id: str, access_token: str, timeout: float = 90.0):
    cb("Verifying device appears online in the dashboard…")
    import time  # stdlib
    from agent_v2.modules.enrollment.pairing import verify_online  # lazy — needs httpx
    deadline = time.monotonic() + timeout
    last_err: str | None = None
    while time.monotonic() < deadline:
        try:
            snapshot = verify_online(backend_url, device_id, access_token)
            if snapshot.get("online") or snapshot.get("last_seen"):
                return snapshot
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
        time.sleep(3.0)
    raise InstallStepError(
        f"The device paired successfully but never reported telemetry within {int(timeout)}s. "
        f"Last error: {last_err or 'no heartbeat received'}."
    )


# ---------------------------------------------------------------------------
# Main install pipeline
# ---------------------------------------------------------------------------
def _run_pipeline(cb, *, backend_url: str, code: str, install_dir: Path, skip_pair: bool) -> dict:
    _step_prepare(cb)
    agent_exe = _step_copy(cb, install_dir)
    _step_register_service(cb, agent_exe)
    _step_start_service(cb)
    if skip_pair:
        cb("Skipping pair (--no-pair supplied).")
        return {"paired": False}
    pair_result = _step_pair(cb, backend_url, code)
    snapshot = _step_verify_online(
        cb, backend_url, pair_result["device_id"], pair_result.get("access_token", ""),
    )
    cb("Success — the device is online and streaming telemetry.")
    return {"paired": True, **pair_result, "snapshot": snapshot}


# ---------------------------------------------------------------------------
# --self-test  — lightweight startup + packaging verification. NO third-party
# imports (no httpx, no pywin32, no tkinter, no websockets). Anyone running
# this on any OS must see a clean JSON banner + exit 0, provided the EXE
# itself was frozen correctly.
# ---------------------------------------------------------------------------
def _self_test() -> int:
    """Prove the frozen EXE (or the ``python -m`` invocation) can:
      * be launched by the OS,
      * bootstrap sys.path,
      * import the ``agent_v2`` package tree at every intermediate level
        (all of which have deliberately-empty ``__init__.py`` files, so
        this triggers NO third-party imports),
      * resolve the two stdlib-only modules the installer entry point
        needs at module scope (``common.paths`` + ``common.version``).

    IMPORTANT: this check does NOT import leaf modules like
    ``enrollment.pairing`` or ``service.registrar`` \u2014 those pull in
    httpx / pywin32 respectively. All we need to prove is that the
    frozen bundle is structurally intact; a broken package tree would
    already have crashed the ``from agent_v2.common import paths`` line
    at module scope before we ever reached ``_self_test``.

    Return code 0 == packaging is sound. Anything else is a real bug.
    """
    import importlib.util
    import json

    banner: dict = {
        "check": "installer.self_test",
        "result": "ok",
        "installer_version": INSTALLER_VERSION,
        "agent_version": AGENT_VERSION,
        "default_backend_url": DEFAULT_BACKEND_URL,
        "frozen": _paths.running_frozen(),
        "meipass": getattr(sys, "_MEIPASS", None),
        "executable": sys.executable,
        "sys_path_head": sys.path[:5],
        "eagerly_loaded": {
            "agent_v2.common.paths": _paths.__file__,
            "agent_v2.common.version": "constant module",
        },
        "package_tree": {},
    }

    # These packages have EMPTY __init__.py files (verified by
    # test_installer_imports.py in CI), so ``find_spec`` on them never
    # executes user code that could import httpx / pywin32 / tkinter.
    safe_packages = [
        "agent_v2",
        "agent_v2.common",
        "agent_v2.installer",
        "agent_v2.modules",
    ]
    missing: list[str] = []
    for pkg in safe_packages:
        spec = importlib.util.find_spec(pkg)
        if spec is None:
            missing.append(pkg)
            banner["package_tree"][pkg] = None
        else:
            banner["package_tree"][pkg] = spec.origin or "namespace-package"

    if missing:
        banner["result"] = "fail"
        banner["missing_packages"] = missing
        sys.stdout.write(json.dumps(banner, indent=2, default=str) + "\n")
        sys.stdout.flush()
        return 1

    sys.stdout.write(json.dumps(banner, indent=2, default=str) + "\n")
    sys.stdout.flush()
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def run() -> int:
    # NOTE: ``--self-test`` and ``--version`` are handled at module load
    # time (see the FAST-PATH block near the top of this file) so they
    # cannot be delayed by anything in this function. Any argv that
    # reaches here is a real-install invocation.
    parser = argparse.ArgumentParser(prog="DigitalTwinAgentSetup")
    parser.add_argument("--install-dir", metavar="DIR", default=str(_paths.program_files_dir()),
                        help="Where the agent binaries are copied (default: Program Files\\DigitalTwin)")
    parser.add_argument("--api-url", metavar="URL", default=DEFAULT_BACKEND_URL,
                        help="Backend URL — usually pre-baked at build time.")
    parser.add_argument("--code", metavar="DT-XXXX-YYYY", default=None,
                        help="Pairing code (auto-detected from EXE filename when omitted).")
    parser.add_argument("--silent", action="store_true",
                        help="No GUI. Progress is printed to stderr / installer.log.")
    parser.add_argument("--no-pair", action="store_true",
                        help="Register the service but do not pair. For MSI/GPO mass deploys.")
    parser.add_argument("--self-test", action="store_true",
                        help="Lightweight packaging check. Handled before this parser to "
                             "guarantee it returns in <5s with no GUI, no service, no network.")
    parser.add_argument("--version", action="version", version=INSTALLER_VERSION)
    args = parser.parse_args()

    # From here on we are on the "real install" path — lazy imports OK.
    from agent_v2.modules.logmod import configure_installer_logging  # lazy
    from agent_v2.installer import gui  # lazy — imports tkinter

    log_file = configure_installer_logging()
    log.info(
        "installer %s starting (agent=%s, backend=%s, argv=%s)",
        INSTALLER_VERSION, AGENT_VERSION, args.api_url, sys.argv[1:],
    )

    if not _is_admin():
        log.info("not elevated — relaunching under UAC")
        return _relaunch_elevated()

    install_dir = Path(args.install_dir)
    try:
        code = _extract_pairing_code(args.code) if not args.no_pair else None
    except InstallStepError as exc:
        return gui.show_error(str(exc), log_file, silent=args.silent)

    if not args.no_pair and not code:
        return gui.show_error(
            "This installer was launched without a pairing code. Download a fresh copy "
            "from your Digital Twin dashboard (\"Download Agent\") — the code is embedded "
            "in the filename automatically.",
            log_file, silent=args.silent,
        )

    def _execute(cb):
        return _run_pipeline(
            cb,
            backend_url=args.api_url,
            code=code or "",
            install_dir=install_dir,
            skip_pair=args.no_pair,
        )

    if args.silent:
        try:
            _execute(lambda m: log.info(m))
            return 0
        except InstallStepError as exc:
            log.error("install failed (silent): %s", exc)
            sys.stderr.write(f"[installer] FAILED: {exc}\n[installer] Log: {log_file}\n")
            return 1
        except Exception as exc:  # noqa: BLE001
            log.exception("unexpected failure in silent install")
            sys.stderr.write(f"[installer] FAILED (unexpected): {exc}\n")
            return 2
    return gui.run_wizard(_execute, log_file=log_file)


if __name__ == "__main__":
    sys.exit(run())
