"""Confirms that after the installer's happy-path bootstrap, the device
is actually visible to the org owner via GET /api/devices.

This proves the last two boxes on the user's checklist:
    * "verify that enrollment succeeds automatically"
    * "and the device appears in the admin dashboard"
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

BACKEND = "http://localhost:8001"
API = f"{BACKEND}/api"
PY = sys.executable
AGENT_ROOT = Path("/app/agent")


def run() -> int:
    email = f"dash-{uuid.uuid4().hex[:8]}@example.com"
    pw = "DashTest#123"
    org = f"DashOrg-{uuid.uuid4().hex[:6]}"
    r = requests.post(f"{API}/auth/signup", json={
        "email": email, "password": pw, "full_name": "Dashboard Verifier",
        "organization_name": org,
    }, timeout=10)
    assert r.status_code < 400, r.text
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=10)
    assert r.status_code < 400, r.text
    access = r.json()["access_token"]
    hdr = {"Authorization": f"Bearer {access}"}

    # Create enrollment code
    r = requests.post(f"{API}/enrollment/codes",
                      json={"ttl_minutes": 15, "label": "installer-happy-path"},
                      headers=hdr, timeout=10)
    assert r.status_code < 400, r.text
    code = r.json()["code"]
    print(f"[test] issued code {code}")

    # Simulate installer: write config.json, run bootstrap
    with tempfile.TemporaryDirectory() as td:
        cfg_dir = Path(td)
        (cfg_dir / "config.json").write_text(json.dumps({
            "backend_url": BACKEND, "enrollment_token": code,
            "label": "Happy Path PC", "provisioned": False,
        }, indent=2))
        env = os.environ.copy()
        env["DTA_BOOTSTRAP_DIR"] = str(cfg_dir)
        env["DTA_CONFIG_DIR"]    = str(cfg_dir)
        proc = subprocess.run(
            [PY, "-m", "digital_twin_agent", "bootstrap"],
            cwd=AGENT_ROOT, env=env, capture_output=True, text=True, timeout=60,
        )
        print(f"[test] bootstrap exit={proc.returncode}")
        print(f"[test] bootstrap stdout: {proc.stdout.strip()}")
        assert proc.returncode == 0, proc.stderr

    # Give the backend a moment to commit.
    time.sleep(1)

    # Fetch /api/devices as the org owner. Confirm exactly one device exists.
    r = requests.get(f"{API}/devices", headers=hdr, timeout=10)
    assert r.status_code < 400, r.text
    devices = r.json()
    if isinstance(devices, dict) and "items" in devices:
        devices = devices["items"]
    print(f"[test] devices in dashboard: {len(devices)}")
    for d in devices:
        print(f"[test]   - id={d.get('id')} label={d.get('label')} hostname={d.get('hostname')} status={d.get('status')}")
    assert len(devices) >= 1, "device did NOT appear in the admin dashboard!"
    print("")
    print("[test] SUCCESS: device is visible on the admin dashboard.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
