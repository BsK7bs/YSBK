"""Thin shim — the actual agent lives in ``modules.core``.

Kept as its own top-level so PyInstaller can produce ``agent.exe`` with a
stable entry point.

IMPORT MODEL
------------
Absolute imports only + lazy loading of heavy deps. See the docstring in
``agent_v2/installer/__main__.py`` for the full rationale.

The ``--self-test`` / ``--version`` fast-path runs at MODULE LOAD TIME so
it cannot be blocked by anything in ``_entry()``. Every step emits a
timestamped breadcrumb via ``os.write(2, ...)`` so any regression that
reintroduces a hang shows up in the CI log with millisecond resolution.
"""
import os as _os
import sys as _sys
import time as _time

_T0 = _time.perf_counter()


def _breadcrumb(label: str) -> None:
    try:
        ms = (_time.perf_counter() - _T0) * 1000.0
        line = f"[agent.boot] {ms:8.2f} ms  {label}\n".encode("utf-8", "replace")
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
# FAST-PATH: --self-test / --version. See installer/__main__.py for the
# full rationale + invariants that must never be broken.
# ---------------------------------------------------------------------------
if "--self-test" in _sys.argv:
    _breadcrumb("--self-test detected")
    _fastpath_syspath_bootstrap()
    _breadcrumb("sys.path bootstrapped")

    from agent_v2.common.version import AGENT_VERSION as _AGENT_VERSION
    import importlib.util as _iutil
    import json as _json

    _banner = {
        "check": "agent.self_test",
        "result": "ok",
        "agent_version": _AGENT_VERSION,
        "frozen": getattr(_sys, "frozen", False),
        "meipass": getattr(_sys, "_MEIPASS", None),
        "executable": _sys.executable,
        "argv": _sys.argv,
        "package_tree": {},
        "boot_timeline_ms": {},
    }
    _breadcrumb("banner initialised")

    _safe_packages = ("agent_v2", "agent_v2.common", "agent_v2.modules", "agent_v2.agent")
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
    from agent_v2.common.version import AGENT_VERSION as _AGENT_VERSION
    _emergency_print(_AGENT_VERSION)
    _sys.exit(0)


# ---------------------------------------------------------------------------
# Real service path. Lazy imports below.
# ---------------------------------------------------------------------------
_breadcrumb("fast-path not taken; loading orchestrator")

from pathlib import Path


def _bootstrap_syspath() -> None:
    _fastpath_syspath_bootstrap()  # already idempotent


_bootstrap_syspath()

from agent_v2.common.version import AGENT_VERSION  # noqa: E402

sys = _sys  # convenience alias for the rest of the file


def _entry() -> int:
    # --self-test / --version handled above at module load time.
    from agent_v2.modules.core import main  # lazy — needs httpx/pywin32/websockets
    return int(main() or 0)


if __name__ == "__main__":
    raise SystemExit(_entry())
