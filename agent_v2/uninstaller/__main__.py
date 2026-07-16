"""Uninstaller — removes the service, credentials, and installed files.

All steps idempotent; any single failure keeps going but exits non-zero.

IMPORT MODEL
------------
Frozen PyInstaller entry-point. Same rule as the installer:
  * Absolute imports only at module scope.
  * ``--self-test`` / ``--version`` fast-path runs at MODULE LOAD TIME so
    they cannot be blocked by anything in ``run()``.
  * Every step emits a timestamped breadcrumb to fd 2 so any regression
    that reintroduces a hang shows up in the CI log with ms resolution.
"""
import os as _os
import sys as _sys
import time as _time

_T0 = _time.perf_counter()


def _breadcrumb(label: str) -> None:
    try:
        ms = (_time.perf_counter() - _T0) * 1000.0
        line = f"[uninstaller.boot] {ms:8.2f} ms  {label}\n".encode("utf-8", "replace")
        try:
            _os.write(2, line)
        except (OSError, ValueError):
            try:
                _os.write(1, line)
            except (OSError, ValueError):
                pass
    except Exception:
        pass


_breadcrumb("process started; interpreter is up")


def _emergency_print(text: str) -> None:
    payload = (text if text.endswith("\n") else text + "\n").encode("utf-8", "replace")
    for fd in (1, 2):
        try:
            _os.write(fd, payload)
            return
        except (OSError, ValueError):
            continue


def _fastpath_syspath_bootstrap() -> None:
    if getattr(_sys, "frozen", False):
        meipass = getattr(_sys, "_MEIPASS", "")
        for candidate in (meipass, _os.path.join(meipass, "agent_v2"),
                          _os.path.dirname(_sys.executable)):
            if candidate and candidate not in _sys.path:
                _sys.path.insert(0, candidate)
    else:
        repo_root = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
        if repo_root not in _sys.path:
            _sys.path.insert(0, repo_root)


# ---------------------------------------------------------------------------
# FAST-PATH
# ---------------------------------------------------------------------------
if "--self-test" in _sys.argv:
    _breadcrumb("--self-test detected")
    _fastpath_syspath_bootstrap()
    _breadcrumb("sys.path bootstrapped")

    from agent_v2.common.version import INSTALLER_VERSION as _INSTALLER_VERSION
    from agent_v2.common import paths as _paths_ft
    import importlib.util as _iutil
    import json as _json

    _banner = {
        "check": "uninstaller.self_test",
        "result": "ok",
        "uninstaller_version": _INSTALLER_VERSION,
        "frozen": getattr(_sys, "frozen", False),
        "meipass": getattr(_sys, "_MEIPASS", None),
        "executable": _sys.executable,
        "argv": _sys.argv,
        "eagerly_loaded": {
            "agent_v2.common.paths": _paths_ft.__file__,
        },
        "package_tree": {},
        "boot_timeline_ms": {},
    }
    _breadcrumb("banner initialised")

    _safe_packages = ("agent_v2", "agent_v2.common", "agent_v2.modules", "agent_v2.uninstaller")
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
    _breadcrumb("--version detected")
    _fastpath_syspath_bootstrap()
    from agent_v2.common.version import INSTALLER_VERSION as _INSTALLER_VERSION
    _emergency_print(_INSTALLER_VERSION)
    _sys.exit(0)


# ---------------------------------------------------------------------------
# Real uninstall path.
# ---------------------------------------------------------------------------
_breadcrumb("fast-path not taken; loading uninstall pipeline")

import logging
from pathlib import Path

_fastpath_syspath_bootstrap()

from agent_v2.common import paths as _paths  # noqa: E402
from agent_v2.common.version import INSTALLER_VERSION  # noqa: E402

sys = _sys  # convenience alias

log = logging.getLogger("dta.uninstaller")


def run() -> int:
    # --self-test / --version handled above at module load time.
    import shutil
    from agent_v2.common.paths import program_data_dir, program_files_dir
    from agent_v2.modules.auth import delete as delete_credentials
    from agent_v2.modules.logmod import configure_installer_logging
    from agent_v2.modules.service import registrar as service_registrar

    log_file = configure_installer_logging()
    log.info("uninstaller starting")

    ok = True
    for step, action in (
        ("stop+remove service", lambda: service_registrar.remove(force=True)),
        ("delete DPAPI credentials", delete_credentials),
        ("remove ProgramData", lambda: shutil.rmtree(program_data_dir(), ignore_errors=True)),
        ("remove Program Files", lambda: shutil.rmtree(program_files_dir(), ignore_errors=True)),
    ):
        try:
            log.info("step: %s", step)
            action()
        except Exception as exc:  # noqa: BLE001
            log.exception("step failed: %s", step)
            ok = False
    log.info("uninstaller finished %s (log=%s)", "OK" if ok else "WITH ERRORS", log_file)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run())
