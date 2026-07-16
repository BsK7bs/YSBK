"""End-to-end POC for the Digital Twin Platform core workflow.

Validates the following user stories in one run:
1. As an Owner, I can create an organization and log in to get JWT tokens.
2. As an Admin, I can generate a time-limited enrollment code for a new device.
3. As an Agent, I can enroll with an enrollment code and receive a device API key.
4. As an Agent, I can send heartbeats/telemetry over WebSocket and persist metrics.
5. As an Owner, I cannot see devices from another organization (hard isolation).
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
import websockets

BASE = "http://127.0.0.1:8001/api"
WS_BASE = "ws://127.0.0.1:8001/api/ws"


class TestFailed(Exception):
    pass


def _ok(msg: str) -> None:
    print(f"  \u2713 {msg}")


def _step(msg: str) -> None:
    print(f"\n\u25b6 {msg}")


async def _post(client: httpx.AsyncClient, path: str, json_body: dict | None = None, token: str | None = None) -> httpx.Response:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return await client.post(BASE + path, json=json_body, headers=headers, timeout=15)


async def _get(client: httpx.AsyncClient, path: str, token: str | None = None) -> httpx.Response:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return await client.get(BASE + path, headers=headers, timeout=15)


async def signup_and_login(client: httpx.AsyncClient, org_name: str, email: str, password: str, name: str) -> dict:
    r = await _post(client, "/auth/signup", {
        "email": email,
        "password": password,
        "full_name": name,
        "organization_name": org_name,
    })
    if r.status_code != 200:
        raise TestFailed(f"Signup failed for {email}: {r.status_code} {r.text}")
    data = r.json()
    assert data["user"]["email"] == email.lower()
    assert data["user"]["role"] == "owner"
    _ok(f"Signup + org created for {email} (org={data['organization']['name']})")

    # Login again with same credentials
    r = await _post(client, "/auth/login", {"email": email, "password": password})
    if r.status_code != 200:
        raise TestFailed(f"Login failed: {r.status_code} {r.text}")
    data = r.json()
    _ok(f"Login returns access + refresh tokens for {email}")
    return data


async def test_refresh_token(client: httpx.AsyncClient, refresh_token: str) -> str:
    r = await _post(client, "/auth/refresh", {"refresh_token": refresh_token})
    if r.status_code != 200:
        raise TestFailed(f"Refresh failed: {r.status_code} {r.text}")
    _ok("Refresh token exchanged for new access token")
    return r.json()["access_token"]


async def test_me(client: httpx.AsyncClient, token: str) -> dict:
    r = await _get(client, "/auth/me", token=token)
    if r.status_code != 200:
        raise TestFailed(f"/auth/me failed: {r.status_code} {r.text}")
    _ok("/auth/me returns current user + organization")
    return r.json()


async def create_enrollment_code(client: httpx.AsyncClient, token: str, label: str = "Lab Room 1") -> dict:
    r = await _post(client, "/enrollment/codes", {"label": label}, token=token)
    if r.status_code != 200:
        raise TestFailed(f"Enrollment code create failed: {r.status_code} {r.text}")
    data = r.json()
    assert data.get("code") and "-" in data["code"], f"Bad code format: {data}"
    assert data.get("qr_payload", "").startswith("digitaltwin://enroll")
    _ok(f"Enrollment code generated: {data['code']} (expires_at set, QR payload valid)")
    return data


async def enroll_device_as_agent(client: httpx.AsyncClient, code: str, hostname: str) -> dict:
    r = await _post(client, "/enrollment/enroll", {
        "code": code,
        "hostname": hostname,
        "os_name": "Windows",
        "os_version": "11",
        "agent_version": "0.1.0",
        "hardware_id": uuid.uuid4().hex,
    })
    if r.status_code != 200:
        raise TestFailed(f"Device enroll failed: {r.status_code} {r.text}")
    data = r.json()
    assert data.get("device_id") and data.get("device_api_key", "").startswith("dtk_")
    _ok(f"Agent enrolled -> device_id={data['device_id'][:8]}..., api_key issued")
    return data


async def enroll_should_fail_second_time(client: httpx.AsyncClient, code: str) -> None:
    r = await _post(client, "/enrollment/enroll", {"code": code, "hostname": "attacker"})
    if r.status_code != 409:
        raise TestFailed(f"Reusing enrollment code should return 409, got {r.status_code} {r.text}")
    _ok("Reusing an enrollment code is properly rejected (single-use enforced)")


async def stream_telemetry_via_ws(api_key: str, num_frames: int = 3) -> list[dict]:
    """Connect as agent and send a few telemetry frames."""
    url = f"{WS_BASE}/agent?api_key={api_key}"
    async with websockets.connect(url) as ws:
        hello = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        if hello.get("type") != "hello":
            raise TestFailed(f"Expected hello, got {hello}")
        _ok(f"WebSocket connected; server hello received (device_id={hello['device_id'][:8]}...)")

        # heartbeat
        await ws.send(json.dumps({"type": "heartbeat"}))
        ack = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        if ack.get("type") != "ack":
            raise TestFailed(f"Expected ack for heartbeat, got {ack}")
        _ok("Heartbeat acknowledged")

        # metrics (mix of healthy and stressed to trigger alerts)
        sent_frames = []
        metric_profiles = [
            {"cpu_percent": 32.5, "ram_percent": 55.0, "disk_percent": 42.0, "cpu_temp_c": 55.0, "net_up_kbps": 120, "net_down_kbps": 300},
            {"cpu_percent": 88.0, "ram_percent": 78.0, "disk_percent": 60.0, "cpu_temp_c": 72.0, "net_up_kbps": 90, "net_down_kbps": 210},
            {"cpu_percent": 97.5, "ram_percent": 96.5, "disk_percent": 88.0, "cpu_temp_c": 91.0, "net_up_kbps": 30, "net_down_kbps": 60},
        ][:num_frames]
        for m in metric_profiles:
            frame = {"type": "metrics", "ts": datetime.now(timezone.utc).isoformat(), "metrics": m}
            await ws.send(json.dumps(frame))
            ack = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            if ack.get("type") != "ack":
                raise TestFailed(f"Expected ack for metrics, got {ack}")
            sent_frames.append(frame)
        _ok(f"Sent {len(sent_frames)} telemetry frames and all acknowledged")

        # inventory
        await ws.send(json.dumps({
            "type": "inventory",
            "inventory": {
                "cpu_model": "Intel Core i7-1165G7",
                "cpu_cores": 8,
                "ram_total_gb": 16,
                "disks": [{"name": "C:", "total_gb": 512, "type": "SSD"}],
                "installed_software": [
                    {"name": "Google Chrome", "version": "128.0.6613.85"},
                    {"name": "Notepad++", "version": "8.6.9"},
                ],
                "monitors": [{"model": "Dell U2419H", "resolution": "1920x1080"}],
            },
        }))
        ack = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        if ack.get("type") != "ack":
            raise TestFailed(f"Expected ack for inventory, got {ack}")
        _ok("Inventory frame acknowledged")

        return sent_frames


async def test_devices_visible(client: httpx.AsyncClient, token: str, expected_device_id: str) -> None:
    # Give server a moment to persist final writes
    await asyncio.sleep(0.5)
    r = await _get(client, "/devices", token=token)
    if r.status_code != 200:
        raise TestFailed(f"List devices failed: {r.status_code} {r.text}")
    payload = r.json()
    assert isinstance(payload, dict) and "items" in payload, f"Expected paginated envelope, got {payload}"
    devices = payload["items"]
    ids = [d["id"] for d in devices]
    if expected_device_id not in ids:
        raise TestFailed(f"Expected device {expected_device_id} in list, got {ids}")
    dev = next(d for d in devices if d["id"] == expected_device_id)
    if dev.get("latest_metrics", {}).get("cpu_percent") is None:
        raise TestFailed(f"Device has no latest_metrics: {dev}")
    if dev.get("health_score") is None:
        raise TestFailed("Device has no health_score computed")
    _ok(f"Device visible in owner's list with metrics + health_score={dev['health_score']} risk={dev.get('risk_level')}")

    r = await _get(client, f"/devices/{expected_device_id}", token=token)
    if r.status_code != 200:
        raise TestFailed(f"Get device failed: {r.status_code} {r.text}")
    _ok("Digital twin detail endpoint returns device data")

    r = await _get(client, f"/devices/{expected_device_id}/telemetry?minutes=60&limit=20", token=token)
    if r.status_code != 200:
        raise TestFailed(f"Get telemetry failed: {r.status_code} {r.text}")
    tel = r.json()
    if len(tel) < 3:
        raise TestFailed(f"Expected >= 3 telemetry points, got {len(tel)}")
    _ok(f"Telemetry history endpoint returned {len(tel)} points")


async def test_alerts_created(client: httpx.AsyncClient, token: str, device_id: str) -> None:
    r = await _get(client, f"/alerts?device_id={device_id}", token=token)
    if r.status_code != 200:
        raise TestFailed(f"List alerts failed: {r.status_code} {r.text}")
    alerts = r.json()
    if not alerts:
        raise TestFailed("Expected alerts to be generated from high metrics, got none")
    kinds = {a["kind"] for a in alerts}
    _ok(f"Alerts created from thresholds: {sorted(kinds)}")


async def test_isolation_across_orgs(client: httpx.AsyncClient, other_token: str, foreign_device_id: str) -> None:
    r = await _get(client, "/devices", token=other_token)
    if r.status_code != 200:
        raise TestFailed(f"Other org list failed: {r.status_code} {r.text}")
    payload = r.json()
    devices = payload["items"] if isinstance(payload, dict) else payload
    if any(d["id"] == foreign_device_id for d in devices):
        raise TestFailed("SECURITY: Other org can see foreign device!")
    _ok("Cross-org isolation: other org's device list does NOT contain foreign device")

    r = await _get(client, f"/devices/{foreign_device_id}", token=other_token)
    if r.status_code != 404:
        raise TestFailed(f"Cross-org GET device should be 404, got {r.status_code}")
    _ok("Cross-org GET device returns 404 (hard isolation)")


async def test_rbac_viewer_cannot_create_code(client: httpx.AsyncClient, viewer_token: str) -> None:
    r = await _post(client, "/enrollment/codes", {"label": "hack"}, token=viewer_token)
    if r.status_code != 403:
        raise TestFailed(f"Viewer should NOT be able to create enrollment code, got {r.status_code} {r.text}")
    _ok("RBAC: viewer forbidden from creating enrollment codes")


async def test_invitation_flow(client: httpx.AsyncClient, owner_token: str, owner_org_id: str) -> str:
    invited_email = f"tech_{uuid.uuid4().hex[:6]}@example.com"
    r = await _post(client, "/invitations", {"email": invited_email, "role": "technician"}, token=owner_token)
    if r.status_code != 200:
        raise TestFailed(f"Create invitation failed: {r.status_code} {r.text}")
    inv_token = r.json()["invitation"]["token"]
    _ok(f"Invitation created for {invited_email} as technician")

    r = await _post(client, "/invitations/accept", {
        "token": inv_token,
        "full_name": "Invited Tech",
        "password": "TechPass1234!",
    })
    if r.status_code != 200:
        raise TestFailed(f"Accept invitation failed: {r.status_code} {r.text}")
    accepted = r.json()
    if accepted["user"]["org_id"] != owner_org_id:
        raise TestFailed("Invited user landed in wrong org")
    if accepted["user"]["role"] != "technician":
        raise TestFailed("Invited user has wrong role")
    _ok("Invitation accepted; new user joined the owner's org with technician role")
    return accepted["access_token"]


async def main() -> None:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE}/health", timeout=5)
        if r.status_code != 200:
            raise TestFailed("Backend not healthy")
        _ok("Backend health OK")

        _step("Story 1: Owner signup + login + refresh + me")
        email1 = f"owner1_{uuid.uuid4().hex[:6]}@example.com"
        session1 = await signup_and_login(client, "Acme IT", email1, "OwnerPass123!", "Alice Owner")
        owner_token = session1["access_token"]
        owner_org_id = session1["user"]["org_id"]
        new_access = await test_refresh_token(client, session1["refresh_token"])
        me = await test_me(client, new_access)
        assert me["user"]["org_id"] == owner_org_id

        _step("Story 2: Admin generates enrollment code")
        code_doc = await create_enrollment_code(client, owner_token, label="Room A")

        _step("Story 3: Agent enrolls using the code and gets Device API Key")
        agent_creds = await enroll_device_as_agent(client, code_doc["code"], hostname="LAB-PC-01")
        device_id = agent_creds["device_id"]
        api_key = agent_creds["device_api_key"]
        await enroll_should_fail_second_time(client, code_doc["code"])

        _step("Story 4: Agent streams heartbeat + telemetry + inventory via WebSocket")
        await stream_telemetry_via_ws(api_key, num_frames=3)
        await test_devices_visible(client, owner_token, device_id)
        await test_alerts_created(client, owner_token, device_id)

        _step("Story 5: Cross-org isolation")
        email2 = f"owner2_{uuid.uuid4().hex[:6]}@example.com"
        session2 = await signup_and_login(client, "Beta Corp", email2, "OtherPass123!", "Bob Owner")
        await test_isolation_across_orgs(client, session2["access_token"], device_id)

        _step("Bonus: Invitation flow + RBAC")
        # Create a viewer via invitation
        # First, we need viewer invitation
        invited_email = f"viewer_{uuid.uuid4().hex[:6]}@example.com"
        r = await _post(client, "/invitations", {"email": invited_email, "role": "viewer"}, token=owner_token)
        if r.status_code != 200:
            raise TestFailed(f"Viewer invite failed: {r.text}")
        vtoken = r.json()["invitation"]["token"]
        r = await _post(client, "/invitations/accept", {
            "token": vtoken, "full_name": "Read Only", "password": "ViewerPass123!",
        })
        viewer_token = r.json()["access_token"]
        await test_rbac_viewer_cannot_create_code(client, viewer_token)
        await test_invitation_flow(client, owner_token, owner_org_id)

        _step("Bonus: Remote action queueing")
        # Owner queues restart action for device
        r = await _post(client, f"/actions/devices/{device_id}", {"kind": "refresh_inventory", "params": {}}, token=owner_token)
        if r.status_code != 200:
            raise TestFailed(f"Enqueue action failed: {r.text}")
        action = r.json()
        _ok(f"Remote action enqueued (kind=refresh_inventory, id={action['id'][:8]}...)")
        # Agent fetches pending
        r = await client.get(f"{BASE}/agent/actions/pending", headers={"X-Device-API-Key": api_key}, timeout=10)
        if r.status_code != 200:
            raise TestFailed(f"Agent pending actions failed: {r.text}")
        pending = r.json()
        if not any(a["id"] == action["id"] for a in pending):
            raise TestFailed("Enqueued action not visible to the correct device")
        _ok("Agent (device-auth) can list its pending actions")
        # Agent reports completion
        r = await client.patch(
            f"{BASE}/agent/actions/{action['id']}",
            json={"status": "succeeded", "result": {"ok": True}},
            headers={"X-Device-API-Key": api_key},
            timeout=10,
        )
        if r.status_code != 200:
            raise TestFailed(f"Agent action complete failed: {r.text}")
        _ok("Agent reports action completion successfully")

        print("\n\U0001F389 ALL CORE POC STORIES PASSED\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except TestFailed as e:
        print(f"\n\u274C POC FAILED: {e}")
        sys.exit(1)
    except Exception as e:  # noqa: BLE001
        print(f"\n\u274C POC ERROR: {type(e).__name__}: {e}")
        sys.exit(2)
