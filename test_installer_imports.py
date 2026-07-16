#!/usr/bin/env python3
"""Guardrails for the frozen-EXE import model.

Bug context (2026-07)
---------------------
`DigitalTwinAgentSetup.exe` shipped with a top-level entry point that used
relative imports (``from ..common import paths``).  PyInstaller runs the
entry script as ``__main__`` — with no ``__package__`` — so the very first
import raised:

    ImportError: attempted relative import with no known parent package

The build reported success because PyInstaller only compiles; the crash only
manifested when a customer double-clicked the EXE. This test enforces two
invariants so the class of bug cannot regress:

  A) AST check — every entry-point script (installer, agent, uninstaller)
     uses ONLY absolute ``agent_v2.*`` imports at module scope.
  B) Runtime check — when each entry script is executed as ``__main__``
     (the exact scenario PyInstaller creates), every top-level import
     resolves and ``--self-test`` exits 0 without printing a Python
     traceback.

Modes:
  * ``--imports-only`` runs only (A) — no third-party packages required.
    This is what a bare CI environment (before ``pip install -r
    requirements.txt``) can safely execute.
  * default runs (A) then (B). Requires httpx, websockets, pydantic,
    pywin32 (Windows only), etc. to be importable.

Exit codes:
    0  All checks passed.
    1  A relative-import violation was found, OR a runtime self-test
       failed with a Python traceback / non-zero exit.

Note: In (B) we treat ``ModuleNotFoundError`` for a KNOWN runtime dep
(httpx, pywin32 pieces, wmi, websockets, pydantic, psutil) as an
*environment* problem, not a packaging bug — the script exits with a
distinct diagnostic message so the operator knows to fix the CI, not the
code. Use ``--imports-only`` to bypass this check entirely.
"""
from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
AGENT_ROOT = REPO_ROOT / "agent_v2"
ENTRY_POINTS = [
    AGENT_ROOT / "installer" / "__main__.py",
    AGENT_ROOT / "agent" / "__main__.py",
    AGENT_ROOT / "uninstaller" / "__main__.py",
]

# Third-party / OS-specific modules that MAY be missing from a bare
# environment. Their absence is an environment problem, not a packaging bug.
KNOWN_RUNTIME_DEPS = {
    "httpx", "websockets", "psutil", "pydantic", "wmi",
    "win32event", "win32service", "win32serviceutil", "win32api",
    "win32cred", "win32con", "win32timezone", "servicemanager",
    "pywintypes", "pypiwin32",
}

# Tokens in stdout/stderr that ALWAYS indicate a packaging bug and must
# fail the check regardless of environment state.
PACKAGING_BUG_TOKENS = (
    "ImportError: attempted relative import",
    "ImportError: attempted relative import with no known parent package",
)


# ---------------------------------------------------------------------------
# (A) AST-only check — requires nothing beyond stdlib.
# ---------------------------------------------------------------------------
def check_absolute_imports(path: Path) -> list[str]:
    """Return a list of violation strings; empty when the file is clean."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            # ``level > 0`` == relative import (``from .x`` or ``from ..x``)
            if node.level and node.level > 0:
                dots = "." * node.level
                target = node.module or ""
                violations.append(
                    f"{path.relative_to(REPO_ROOT)}:{node.lineno}: "
                    f"relative import 'from {dots}{target}' \u2014 use "
                    f"'from agent_v2.{target}' instead."
                )
    return violations


# ---------------------------------------------------------------------------
# (B) Runtime self-test — executes each entry as a script, which is the
# exact scenario PyInstaller creates (``__name__ == '__main__'``).
# ---------------------------------------------------------------------------
def run_self_test(entry: Path) -> tuple[int, str, str]:
    """Run the entry as ``__main__ --self-test`` with a hard 10s wall-clock
    timeout. If the child does not return within 10 seconds it is killed
    and reported as a failure \u2014 --self-test is contractually required to
    exit in <5s (no GUI, no service, no network, no admin check, no sleep).
    """
    try:
        proc = subprocess.run(
            [sys.executable, str(entry), "--self-test"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr_prefix = (
            f"[test_installer_imports] TIMEOUT: {entry.name} --self-test did not "
            f"exit within 10s and was killed. --self-test is required to be "
            f"instantaneous \u2014 check for GUI/service/network/sleep in the entry-point.\n"
        )
        stderr = stderr_prefix + (
            (exc.stderr or b"").decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        )
        return 124, stdout, stderr  # 124 == GNU timeout convention


def classify_runtime_failure(stdout: str, stderr: str) -> tuple[str, str | None]:
    """Return (kind, detail).

    kind == 'packaging'  -> hard failure (relative-import regression)
    kind == 'env'        -> soft failure (missing third-party dep)
    kind == 'other'      -> hard failure (unknown traceback)
    """
    combined = f"{stdout}\n{stderr}"
    for tok in PACKAGING_BUG_TOKENS:
        if tok in combined:
            return "packaging", tok
    # Look for ModuleNotFoundError: No module named 'X'
    for line in combined.splitlines():
        line = line.strip()
        if line.startswith("ModuleNotFoundError: No module named"):
            # Extract the module name between the quotes.
            module = line.split("'")[1] if "'" in line else ""
            top_level = module.split(".")[0]
            if top_level in KNOWN_RUNTIME_DEPS:
                return "env", module
    if "Traceback (most recent call last)" in combined:
        return "other", None
    return "other", None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--imports-only",
        action="store_true",
        help="Only run the AST relative-import check. Skips the runtime self-test.",
    )
    args = parser.parse_args()

    # ----- (A) AST relative-import check --------------------------------
    print("== check_absolute_imports (AST) ==")
    all_violations: list[str] = []
    for entry in ENTRY_POINTS:
        if not entry.is_file():
            print(f"  MISSING: {entry}")
            all_violations.append(f"missing entry: {entry}")
            continue
        vs = check_absolute_imports(entry)
        if vs:
            for v in vs:
                print(f"  FAIL {v}")
            all_violations.extend(vs)
        else:
            print(f"  OK   {entry.relative_to(REPO_ROOT)}")

    if args.imports_only:
        print()
        if all_violations:
            print("STATIC ANALYSIS FAILED (relative-import regressions).")
            return 1
        print("STATIC ANALYSIS PASSED (AST only \u2014 runtime self-test skipped).")
        return 0

    # ----- (B) Runtime self-test ---------------------------------------
    print()
    print("== run --self-test on every entry (simulates frozen __main__) ==")
    packaging_failures: list[str] = []
    other_failures: list[str] = []
    env_gaps: list[tuple[str, str]] = []

    for entry in ENTRY_POINTS:
        if not entry.is_file():
            continue
        rc, stdout, stderr = run_self_test(entry)
        label = str(entry.relative_to(REPO_ROOT))
        combined = f"{stdout}\n{stderr}"

        if rc == 0 and "Traceback" not in combined:
            print(f"  OK   {label} (rc=0, no traceback)")
            continue

        kind, detail = classify_runtime_failure(stdout, stderr)
        if kind == "packaging":
            print(f"  FAIL {label} rc={rc}  [PACKAGING BUG: {detail}]")
            packaging_failures.append(label)
        elif kind == "env":
            print(f"  SKIP {label} rc={rc}  [ENV: missing third-party dep '{detail}']")
            env_gaps.append((label, detail or "?"))
        else:
            print(f"  FAIL {label} rc={rc}  [UNKNOWN traceback]")
            other_failures.append(label)

        if stderr.strip():
            print("       --- stderr (first 20 lines) ---")
            for line in stderr.strip().splitlines()[:20]:
                print(f"       {line}")

    # ----- Verdict -----------------------------------------------------
    print()
    if all_violations:
        print(f"AST check found {len(all_violations)} relative-import violation(s).")
    if packaging_failures:
        print(f"Runtime check found {len(packaging_failures)} packaging failure(s).")
    if other_failures:
        print(f"Runtime check found {len(other_failures)} unclassified traceback(s).")
    if env_gaps:
        print("Runtime self-test could not fully run due to missing third-party "
              "dependencies. This is NOT a packaging bug \u2014 install the deps and "
              "re-run without --imports-only:")
        for label, module in env_gaps:
            print(f"    * {label}  missing: {module}")
        print("    Hint: `python -m pip install -r agent_v2/requirements.txt`")

    hard_fail = bool(all_violations or packaging_failures or other_failures)
    if hard_fail:
        print("STATIC ANALYSIS FAILED")
        return 1
    if env_gaps:
        print("STATIC ANALYSIS PASSED (AST clean; runtime self-test degraded by "
              "missing runtime deps \u2014 see hint above).")
        # Non-zero to make CI notice, but a distinct exit code (2) so the
        # operator knows to fix the environment, not the code.
        return 2
    print("STATIC ANALYSIS PASSED \u2014 every entry-point boots cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
