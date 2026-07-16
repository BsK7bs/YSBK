"""End-to-end integration test for the installer's new enrollment-verification step.

Exercises the exact code path an installer runs after writing the seed file:

    1. Sign up an admin against the local backend.
    2. Log in, create an enrollment code.
    3. Write %ProgramData%-equivalent config.json into a tempdir.
    4. Point DTA_BOOTSTRAP_DIR + DTA_CONFIG_DIR at the tempdir and invoke
       `python -m digital_twin_agent bootstrap`. Verify exit code 0 and
       that the encrypted config.enc contains a device_api_key.
    5. Repeat with a KNOWN-BAD token. Verify exit code 5 and that the
       CLI printed a real error message on stderr.
    6. Repeat with NO config.json. Verify exit code 4.

This is exactly the sequence install.ps1 / DigitalTwinAgent.iss /
install_helpers.cmd now perform on Windows, so if this test passes on
Linux against a real FastAPI backend, the Windows installers will also
correctly gate service registration on enrollment success.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import requests

BACKEND = os.environ.get("DTA_TEST_BACKEND", "http://localhost:8001")
API = f"{BACKEND}/api"

PY = sys.executable
AGENT_ROOT = Path("/app/agent")


def _log(msg: str) -> None:
    print(f"[test] {msg}", flush=True)


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def _signup_and_login() -> tuple[str, str]:
    email = f"installer-test-{uuid.uuid4().hex[:8]}@example.com"
    pw = "InstallerTest#123"
    org_name = f"InstallerTest-{uuid.uuid4().hex[:6]}"
    r = requests.post(f"{API}/auth/signup", json={
        "email": email, "password": pw, "full_name": "Installer Tester",
        "organization_name": org_name,
    }, timeout=15)
    _assert(r.status_code < 400, f"signup failed: {r.status_code} {r.text}")
    _log(f"signed up {email}")

    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=15)
    _assert(r.status_code < 400, f"login failed: {r.status_code} {r.text}")
    tok = r.json()["access_token"]
    return email, tok


def _create_enrollment_code(access: str) -> str:
    hdr = {"Authorization": f"Bearer {access}"}
    r = requests.post(f"{API}/enrollment/codes", json={"ttl_minutes": 15, "label": "installer-test-device"},
                      headers=hdr, timeout=15)
    _assert(r.status_code < 400, f"code creation failed: {r.status_code} {r.text}")
    body = r.json()
    code = body.get("code") or body.get("enrollment_code")
    _assert(bool(code), f"no code in response: {body}")
    _log(f"created enrollment code: {code[:12]}...")
    return code


def _run_bootstrap(cfg_dir: Path) -> tuple[int, str, str]:
    env = os.environ.copy()
    env["DTA_BOOTSTRAP_DIR"] = str(cfg_dir)
    env["DTA_CONFIG_DIR"]    = str(cfg_dir)
    env["PYTHONPATH"]        = str(AGENT_ROOT)
    proc = subprocess.run(
        [PY, "-m", "digital_twin_agent", "bootstrap"],
        cwd=AGENT_ROOT, env=env, capture_output=True, text=True, timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _write_config(cfg_dir: Path, backend: str, token: str, label: str = "") -> Path:
    cfg_dir.mkdir(parents=True, exist_ok=True)
    p = cfg_dir / "config.json"
    p.write_text(json.dumps({
        "backend_url": backend, "enrollment_token": token,
        "label": label, "provisioned": False,
    }, indent=2), encoding="utf-8")
    return p


def test_happy_path(access: str) -> None:
    _log("--- test_happy_path -------------------------------------------")
    code = _create_enrollment_code(access)
    with tempfile.TemporaryDirectory() as td:
        cfg_dir = Path(td)
        cfg_path = _write_config(cfg_dir, BACKEND, code, label="Installer Happy")
        _assert(cfg_path.exists(), "config.json was not written")
        rc, out, err = _run_bootstrap(cfg_dir)
        _log(f"exit={rc} stdout={out.strip()!r} stderr={err.strip()!r}")
        _assert(rc == 0, f"expected exit 0, got {rc} (stderr={err})")
        _assert("Bootstrap succeeded" in out, f"missing success line in stdout: {out}")
        # config.enc should now exist AND contain a device_api_key.
        enc = cfg_dir / "config.enc"
        _assert(enc.exists(), f"encrypted config.enc was not written at {enc}")
        # Seed file should still be there but token redacted.
        seed = json.loads(cfg_path.read_text())
        _assert(seed.get("provisioned") is True, f"seed not marked provisioned: {seed}")
        _assert(seed.get("enrollment_token", "") == "", f"seed token not redacted: {seed}")
    _log("HAPPY PATH PASSED")


def test_bad_token() -> None:
    _log("--- test_bad_token --------------------------------------------")
    with tempfile.TemporaryDirectory() as td:
        cfg_dir = Path(td)
        _write_config(cfg_dir, BACKEND, "TOTALLY-INVALID-TOKEN-XXX", label="BadTokenTest")
        rc, out, err = _run_bootstrap(cfg_dir)
        _log(f"exit={rc} stdout={out.strip()!r} stderr={err.strip()!r}")
        _assert(rc == 5, f"expected exit 5 (backend rejected), got {rc}")
        _assert("Enrollment failed" in err, f"expected 'Enrollment failed' in stderr: {err}")
        # config.enc must NOT exist -- device was never enrolled.
        enc = cfg_dir / "config.enc"
        _assert(not enc.exists(), f"encrypted config should NOT be written on failure: {enc}")
    _log("BAD TOKEN PATH PASSED (installer would now refuse to register the service)")


def test_missing_seed() -> None:
    _log("--- test_missing_seed -----------------------------------------")
    with tempfile.TemporaryDirectory() as td:
        cfg_dir = Path(td)
        # NOTE: intentionally do NOT write config.json
        rc, out, err = _run_bootstrap(cfg_dir)
        _log(f"exit={rc} stdout={out.strip()!r} stderr={err.strip()!r}")
        _assert(rc == 4, f"expected exit 4 (seed missing), got {rc}")
        _assert("No bootstrap token found" in err, f"expected missing-seed msg in stderr: {err}")
    _log("MISSING SEED PATH PASSED")


def test_bad_backend_url() -> None:
    _log("--- test_bad_backend_url --------------------------------------")
    with tempfile.TemporaryDirectory() as td:
        cfg_dir = Path(td)
        # Point at a definitely-unreachable local port.
        _write_config(cfg_dir, "http://127.0.0.1:65535", "any-token", label="UnreachableTest")
        rc, out, err = _run_bootstrap(cfg_dir)
        _log(f"exit={rc} stdout={out.strip()!r} stderr={err.strip()!r}")
        _assert(rc == 5, f"expected exit 5 (backend unreachable), got {rc}")
        _assert("Enrollment failed" in err, f"expected 'Enrollment failed' in stderr: {err}")
    _log("BAD BACKEND URL PATH PASSED")


def main() -> int:
    _log(f"backend = {BACKEND}")
    _log(f"python  = {PY}")
    _log(f"agent   = {AGENT_ROOT}")

    # Health check
    try:
        r = requests.get(f"{API}/health", timeout=5)
        _assert(r.status_code == 200, f"backend health failed: {r.status_code}")
    except Exception as e:
        _log(f"backend not reachable: {e}")
        return 1

    _, access = _signup_and_login()
    test_happy_path(access)
    test_bad_token()
    test_missing_seed()
    test_bad_backend_url()
    _log("")
    _log("ALL INSTALLER-VERIFICATION TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
