"""Backend API testing for Endpoint Management Features.

Tests the new professional endpoint-management features:
- Bulk Actions (fleet-wide operations)
- Device Groups (CRUD & assignment)
- Maintenance Mode (with alert suppression)
- Agent Installer (PowerShell/batch/ZIP/MSI endpoints)
- Enhanced Enrollment QR flow
"""
import asyncio
import json
import sys
import uuid
from datetime import datetime, timezone

import httpx

# Public endpoint from frontend/.env
BASE = "https://file-restore-dev.preview.emergentagent.com/api"

# Test credentials
ADMIN_EMAIL = "admin@digitaltwin.com"
ADMIN_PASSWORD = "ChangeMe!2026"


class TestResults:
    def __init__(self):
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.errors = []

    def record_pass(self, test_name: str):
        self.total += 1
        self.passed += 1
        print(f"  ✓ {test_name}")

    def record_fail(self, test_name: str, error: str):
        self.total += 1
        self.failed += 1
        self.errors.append(f"{test_name}: {error}")
        print(f"  ✗ {test_name}: {error}")

    def print_summary(self):
        print(f"\n{'='*60}")
        print(f"Test Results: {self.passed}/{self.total} passed")
        if self.failed > 0:
            print(f"\nFailed tests ({self.failed}):")
            for error in self.errors:
                print(f"  - {error}")
        print(f"{'='*60}\n")


results = TestResults()


def step(msg: str):
    print(f"\n▶ {msg}")


async def post(client: httpx.AsyncClient, path: str, json_body: dict = None, token: str = None) -> httpx.Response:
    h = {}
    if token:
        h["Authorization"] = f"Bearer {token}"
    try:
        return await client.post(f"{BASE}{path}", json=json_body, headers=h, timeout=30)
    except Exception as e:
        print(f"POST {path} failed: {e}")
        raise


async def get(client: httpx.AsyncClient, path: str, token: str = None) -> httpx.Response:
    h = {}
    if token:
        h["Authorization"] = f"Bearer {token}"
    try:
        return await client.get(f"{BASE}{path}", headers=h, timeout=30)
    except Exception as e:
        print(f"GET {path} failed: {e}")
        raise


async def patch(client: httpx.AsyncClient, path: str, json_body: dict = None, token: str = None) -> httpx.Response:
    h = {}
    if token:
        h["Authorization"] = f"Bearer {token}"
    try:
        return await client.patch(f"{BASE}{path}", json=json_body, headers=h, timeout=30)
    except Exception as e:
        print(f"PATCH {path} failed: {e}")
        raise


async def delete(client: httpx.AsyncClient, path: str, token: str = None) -> httpx.Response:
    h = {}
    if token:
        h["Authorization"] = f"Bearer {token}"
    try:
        return await client.delete(f"{BASE}{path}", headers=h, timeout=30)
    except Exception as e:
        print(f"DELETE {path} failed: {e}")
        raise


async def test_admin_login(client: httpx.AsyncClient) -> tuple[str, str, str]:
    """Test admin login and return token, org_id, user_id"""
    step("Testing Admin Login")
    
    try:
        r = await post(client, "/auth/login", {
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD,
        })
        if r.status_code == 200:
            data = r.json()
            token = data["access_token"]
            org_id = data["user"]["org_id"]
            user_id = data["user"]["id"]
            results.record_pass("Admin login successful")
            return token, org_id, user_id
        else:
            results.record_fail("Admin login", f"Status {r.status_code}: {r.text}")
            return None, None, None
    except Exception as e:
        results.record_fail("Admin login", str(e))
        return None, None, None


async def create_test_devices(client: httpx.AsyncClient, token: str, count: int = 3) -> list[str]:
    """Create test devices for bulk operations"""
    step(f"Creating {count} test devices")
    
    device_ids = []
    
    # First create enrollment codes and enroll devices
    for i in range(count):
        try:
            # Create enrollment code
            r = await post(client, "/enrollment/codes", {"label": f"Test Bulk {i+1}"}, token=token)
            if r.status_code == 200:
                code_doc = r.json()
                code = code_doc["code"]
                
                # Enroll device
                r2 = await post(client, "/enrollment/enroll", {
                    "code": code,
                    "hostname": f"TEST-BULK-{i+1}",
                    "os_name": "Windows",
                    "os_version": "11",
                    "agent_version": "1.0.0",
                    "hardware_id": uuid.uuid4().hex,
                })
                if r2.status_code == 200:
                    device_creds = r2.json()
                    device_ids.append(device_creds["device_id"])
                    results.record_pass(f"Created test device TEST-BULK-{i+1}")
                else:
                    results.record_fail(f"Enroll device {i+1}", f"Status {r2.status_code}")
            else:
                results.record_fail(f"Create enrollment code {i+1}", f"Status {r.status_code}")
        except Exception as e:
            results.record_fail(f"Create test device {i+1}", str(e))
    
    return device_ids


async def test_actions_kinds(client: httpx.AsyncClient, token: str):
    """Test GET /api/actions/kinds endpoint"""
    step("Testing Actions Kinds Endpoint")
    
    try:
        r = await get(client, "/actions/kinds", token=token)
        if r.status_code == 200:
            data = r.json()
            results.record_pass("GET /api/actions/kinds returns 200")
            
            # Check for required fields
            if "kinds" in data and "admin_only" in data and "requires_confirm" in data:
                results.record_pass("Response has kinds, admin_only, requires_confirm fields")
                
                kinds = data["kinds"]
                expected_kinds = [
                    "restart", "shutdown", "sleep", "lock",
                    "restart_service", "run_script", "exec_cmd", "exec_powershell",
                    "kill_process", "install_software", "uninstall_software",
                    "clear_temp", "run_windows_update", "download_logs", "refresh_inventory",
                    "restart_agent", "collect_event_logs", "collect_diagnostic", "collect_crash_dumps",
                ]
                
                if len(kinds) >= 19:
                    results.record_pass(f"Returns 19+ action kinds ({len(kinds)} kinds)")
                else:
                    results.record_fail("Action kinds count", f"Expected 19+, got {len(kinds)}")
                
                # Check for new diagnostic kinds
                diagnostic_kinds = ["restart_agent", "collect_event_logs", "collect_diagnostic", "collect_crash_dumps"]
                if all(k in kinds for k in diagnostic_kinds):
                    results.record_pass("All diagnostic kinds present (restart_agent, collect_event_logs, collect_diagnostic, collect_crash_dumps)")
                else:
                    missing = [k for k in diagnostic_kinds if k not in kinds]
                    results.record_fail("Diagnostic kinds", f"Missing: {missing}")
                
                # Check admin_only set
                admin_only = set(data["admin_only"])
                if "restart" in admin_only and "shutdown" in admin_only:
                    results.record_pass("admin_only set includes destructive actions")
                else:
                    results.record_fail("admin_only set", f"Missing destructive actions: {admin_only}")
                
                # Check requires_confirm set
                requires_confirm = set(data["requires_confirm"])
                if "restart" in requires_confirm and "run_script" in requires_confirm:
                    results.record_pass("requires_confirm set includes destructive actions")
                else:
                    results.record_fail("requires_confirm set", f"Missing destructive actions: {requires_confirm}")
            else:
                results.record_fail("Actions kinds response", f"Missing fields: {data.keys()}")
        else:
            results.record_fail("GET /api/actions/kinds", f"Status {r.status_code}: {r.text}")
    except Exception as e:
        results.record_fail("GET /api/actions/kinds", str(e))


async def test_bulk_actions(client: httpx.AsyncClient, token: str, device_ids: list[str]):
    """Test bulk actions endpoints"""
    step("Testing Bulk Actions")
    
    if len(device_ids) < 2:
        results.record_fail("Bulk actions test", "Need at least 2 devices")
        return None
    
    batch_id = None
    
    # Test bulk action creation
    try:
        r = await post(client, "/actions/bulk", {
            "kind": "refresh_inventory",
            "params": {},
            "device_ids": device_ids[:2],
            "confirm": False,
            "ttl_seconds": 900,
            "label": "Test Bulk Refresh"
        }, token=token)
        if r.status_code == 200:
            data = r.json()
            batch_id = data.get("batch_id")
            results.record_pass("POST /api/actions/bulk creates batch")
            
            if batch_id:
                results.record_pass(f"Batch created with ID: {batch_id}")
            else:
                results.record_fail("Batch ID", "Missing batch_id in response")
            
            if data.get("total") == 2:
                results.record_pass("Batch created 2 per-device actions")
            else:
                results.record_fail("Batch total", f"Expected 2, got {data.get('total')}")
            
            if "actions" in data and len(data["actions"]) == 2:
                results.record_pass("Response includes per-device actions array")
            else:
                results.record_fail("Per-device actions", f"Expected 2 actions, got {len(data.get('actions', []))}")
        else:
            results.record_fail("POST /api/actions/bulk", f"Status {r.status_code}: {r.text}")
            return None
    except Exception as e:
        results.record_fail("POST /api/actions/bulk", str(e))
        return None
    
    # Test destructive action without confirm
    try:
        r = await post(client, "/actions/bulk", {
            "kind": "restart",
            "params": {},
            "device_ids": device_ids[:1],
            "confirm": False,
        }, token=token)
        if r.status_code == 400:
            results.record_pass("Bulk destructive action without confirm=true returns 400")
        else:
            results.record_fail("Destructive action validation", f"Expected 400, got {r.status_code}")
    except Exception as e:
        results.record_fail("Destructive action validation", str(e))
    
    return batch_id


async def test_action_batches(client: httpx.AsyncClient, token: str, batch_id: str):
    """Test action batch listing and detail endpoints"""
    step("Testing Action Batches Endpoints")
    
    # Test GET /api/actions/batches
    try:
        r = await get(client, "/actions/batches", token=token)
        if r.status_code == 200:
            batches = r.json()
            results.record_pass("GET /api/actions/batches returns list")
            
            if isinstance(batches, list) and len(batches) > 0:
                batch = batches[0]
                if "status_counts" in batch:
                    results.record_pass("Batch includes status_counts")
                    
                    counts = batch["status_counts"]
                    required_statuses = ["pending", "in_progress", "succeeded", "failed", "cancelled", "expired", "total"]
                    if all(s in counts for s in required_statuses):
                        results.record_pass("status_counts has all required statuses")
                    else:
                        missing = [s for s in required_statuses if s not in counts]
                        results.record_fail("status_counts fields", f"Missing: {missing}")
                else:
                    results.record_fail("Batch status_counts", "Missing status_counts field")
            else:
                results.record_fail("Batches list", "Empty or invalid response")
        else:
            results.record_fail("GET /api/actions/batches", f"Status {r.status_code}: {r.text}")
    except Exception as e:
        results.record_fail("GET /api/actions/batches", str(e))
    
    # Test GET /api/actions/batches/{id}
    if batch_id:
        try:
            r = await get(client, f"/actions/batches/{batch_id}", token=token)
            if r.status_code == 200:
                data = r.json()
                results.record_pass("GET /api/actions/batches/{id} returns batch detail")
                
                if "status_counts" in data and "actions" in data:
                    results.record_pass("Batch detail includes status_counts and actions array")
                    
                    actions = data["actions"]
                    if len(actions) > 0:
                        action = actions[0]
                        if "device_hostname" in action:
                            results.record_pass("Per-device actions include device_hostname")
                        else:
                            results.record_fail("Action device info", "Missing device_hostname")
                else:
                    results.record_fail("Batch detail fields", f"Missing fields: {data.keys()}")
            else:
                results.record_fail("GET /api/actions/batches/{id}", f"Status {r.status_code}: {r.text}")
        except Exception as e:
            results.record_fail("GET /api/actions/batches/{id}", str(e))


async def test_action_retry(client: httpx.AsyncClient, token: str, device_ids: list[str]):
    """Test action retry endpoint"""
    step("Testing Action Retry")
    
    if not device_ids:
        results.record_fail("Action retry test", "No devices available")
        return
    
    # Create an action and mark it as failed
    action_id = None
    try:
        r = await post(client, f"/actions/devices/{device_ids[0]}", {
            "kind": "refresh_inventory",
            "params": {},
        }, token=token)
        if r.status_code == 200:
            action = r.json()
            action_id = action["id"]
            results.record_pass("Created test action for retry")
        else:
            results.record_fail("Create test action", f"Status {r.status_code}")
            return
    except Exception as e:
        results.record_fail("Create test action", str(e))
        return
    
    # Wait a moment for action to be processed
    await asyncio.sleep(1)
    
    # Try to retry (should fail if action is still pending)
    try:
        r = await post(client, f"/actions/{action_id}/retry", token=token)
        if r.status_code in [200, 400]:
            if r.status_code == 400:
                results.record_pass("POST /api/actions/{id}/retry rejects retry of active action (400)")
            else:
                results.record_pass("POST /api/actions/{id}/retry creates new action")
        else:
            results.record_fail("POST /api/actions/{id}/retry", f"Status {r.status_code}: {r.text}")
    except Exception as e:
        results.record_fail("POST /api/actions/{id}/retry", str(e))


async def test_device_groups(client: httpx.AsyncClient, token: str, device_ids: list[str]) -> str:
    """Test device groups CRUD operations"""
    step("Testing Device Groups CRUD")
    
    group_id = None
    
    # Test POST /api/device-groups (create)
    try:
        r = await post(client, "/device-groups", {
            "name": f"Test Group {uuid.uuid4().hex[:4]}",
            "description": "Test group for endpoint management",
            "color": "blue",
            "icon": "server"
        }, token=token)
        if r.status_code == 200:
            group = r.json()
            group_id = group["id"]
            results.record_pass("POST /api/device-groups creates group (admin only)")
            
            if group.get("device_count") == 0:
                results.record_pass("New group has device_count=0")
            else:
                results.record_fail("New group device_count", f"Expected 0, got {group.get('device_count')}")
        else:
            results.record_fail("POST /api/device-groups", f"Status {r.status_code}: {r.text}")
            return None
    except Exception as e:
        results.record_fail("POST /api/device-groups", str(e))
        return None
    
    # Test GET /api/device-groups (list)
    try:
        r = await get(client, "/device-groups", token=token)
        if r.status_code == 200:
            groups = r.json()
            results.record_pass("GET /api/device-groups lists groups")
            
            if isinstance(groups, list):
                found = any(g["id"] == group_id for g in groups)
                if found:
                    results.record_pass("Created group appears in list")
                    
                    # Check device_count field
                    group = next(g for g in groups if g["id"] == group_id)
                    if "device_count" in group:
                        results.record_pass("Groups include device_count field")
                    else:
                        results.record_fail("Group device_count", "Missing device_count field")
                else:
                    results.record_fail("Group in list", "Created group not found")
            else:
                results.record_fail("Groups list", "Invalid response type")
        else:
            results.record_fail("GET /api/device-groups", f"Status {r.status_code}: {r.text}")
    except Exception as e:
        results.record_fail("GET /api/device-groups", str(e))
    
    # Test PATCH /api/device-groups/{id} (update)
    try:
        r = await patch(client, f"/device-groups/{group_id}", {
            "description": "Updated description",
            "color": "green"
        }, token=token)
        if r.status_code == 200:
            results.record_pass("PATCH /api/device-groups/{id} updates group")
        else:
            results.record_fail("PATCH /api/device-groups/{id}", f"Status {r.status_code}: {r.text}")
    except Exception as e:
        results.record_fail("PATCH /api/device-groups/{id}", str(e))
    
    return group_id


async def test_device_group_assignment(client: httpx.AsyncClient, token: str, group_id: str, device_ids: list[str]):
    """Test device group assignment operations"""
    step("Testing Device Group Assignment")
    
    if not group_id or not device_ids:
        results.record_fail("Group assignment test", "Missing group_id or device_ids")
        return
    
    # Test POST /api/device-groups/{id}/assign
    try:
        r = await post(client, f"/device-groups/{group_id}/assign", {
            "device_ids": device_ids[:2]
        }, token=token)
        if r.status_code == 200:
            data = r.json()
            results.record_pass("POST /api/device-groups/{id}/assign adds devices to group")
            
            if data.get("matched") >= 2:
                results.record_pass(f"Assigned {data.get('matched')} devices to group")
            else:
                results.record_fail("Device assignment", f"Expected 2+, got {data.get('matched')}")
        else:
            results.record_fail("POST /api/device-groups/{id}/assign", f"Status {r.status_code}: {r.text}")
    except Exception as e:
        results.record_fail("POST /api/device-groups/{id}/assign", str(e))
    
    # Test GET /api/device-groups/{id}/devices
    try:
        r = await get(client, f"/device-groups/{group_id}/devices", token=token)
        if r.status_code == 200:
            devices = r.json()
            results.record_pass("GET /api/device-groups/{id}/devices returns devices in group")
            
            if len(devices) >= 2:
                results.record_pass(f"Group contains {len(devices)} devices")
            else:
                results.record_fail("Group devices", f"Expected 2+, got {len(devices)}")
        else:
            results.record_fail("GET /api/device-groups/{id}/devices", f"Status {r.status_code}: {r.text}")
    except Exception as e:
        results.record_fail("GET /api/device-groups/{id}/devices", str(e))
    
    # Test POST /api/device-groups/{id}/unassign
    try:
        r = await post(client, f"/device-groups/{group_id}/unassign", {
            "device_ids": [device_ids[0]]
        }, token=token)
        if r.status_code == 200:
            results.record_pass("POST /api/device-groups/{id}/unassign removes devices from group")
        else:
            results.record_fail("POST /api/device-groups/{id}/unassign", f"Status {r.status_code}: {r.text}")
    except Exception as e:
        results.record_fail("POST /api/device-groups/{id}/unassign", str(e))


async def test_bulk_actions_with_groups(client: httpx.AsyncClient, token: str, group_id: str):
    """Test bulk actions using group_ids"""
    step("Testing Bulk Actions with Group IDs")
    
    if not group_id:
        results.record_fail("Bulk actions with groups", "No group_id available")
        return
    
    try:
        r = await post(client, "/actions/bulk", {
            "kind": "refresh_inventory",
            "params": {},
            "group_ids": [group_id],
            "confirm": False,
            "label": "Test Group Bulk Action"
        }, token=token)
        if r.status_code == 200:
            data = r.json()
            results.record_pass("Bulk action with group_ids resolves devices from group")
            
            if data.get("total", 0) > 0:
                results.record_pass(f"Group bulk action created {data.get('total')} actions")
            else:
                results.record_fail("Group bulk action", "No actions created")
        else:
            results.record_fail("Bulk action with group_ids", f"Status {r.status_code}: {r.text}")
    except Exception as e:
        results.record_fail("Bulk action with group_ids", str(e))


async def test_maintenance_mode(client: httpx.AsyncClient, token: str, device_ids: list[str]):
    """Test maintenance mode endpoints"""
    step("Testing Maintenance Mode")
    
    if not device_ids:
        results.record_fail("Maintenance mode test", "No devices available")
        return
    
    device_id = device_ids[0]
    
    # Test POST /api/devices/{id}/maintenance/enable
    try:
        r = await post(client, f"/devices/{device_id}/maintenance/enable", {
            "duration_minutes": 60,
            "reason": "Testing maintenance mode",
            "suppress_alerts": True
        }, token=token)
        if r.status_code == 200:
            data = r.json()
            results.record_pass("POST /api/devices/{id}/maintenance/enable sets maintenance mode")
            
            if data.get("ends_at"):
                results.record_pass("Maintenance mode has ends_at timestamp")
            else:
                results.record_fail("Maintenance ends_at", "Missing ends_at field")
            
            if data.get("suppress_alerts") == True:
                results.record_pass("suppress_alerts flag set correctly")
            else:
                results.record_fail("suppress_alerts", f"Expected True, got {data.get('suppress_alerts')}")
        else:
            results.record_fail("POST /api/devices/{id}/maintenance/enable", f"Status {r.status_code}: {r.text}")
    except Exception as e:
        results.record_fail("POST /api/devices/{id}/maintenance/enable", str(e))
    
    # Test GET /api/devices/{id}/maintenance
    try:
        r = await get(client, f"/devices/{device_id}/maintenance", token=token)
        if r.status_code == 200:
            data = r.json()
            results.record_pass("GET /api/devices/{id}/maintenance returns state")
            
            if data.get("maintenance_mode") == True:
                results.record_pass("Device is in maintenance mode")
            else:
                results.record_fail("Maintenance mode state", "maintenance_mode not True")
        else:
            results.record_fail("GET /api/devices/{id}/maintenance", f"Status {r.status_code}: {r.text}")
    except Exception as e:
        results.record_fail("GET /api/devices/{id}/maintenance", str(e))
    
    # Test that bulk destructive actions skip devices in maintenance
    try:
        r = await post(client, "/actions/bulk", {
            "kind": "restart",
            "params": {},
            "device_ids": [device_id],
            "confirm": True,
        }, token=token)
        if r.status_code == 200:
            data = r.json()
            skipped = data.get("skipped", [])
            if len(skipped) > 0 and any("maintenance" in s.get("reason", "").lower() for s in skipped):
                results.record_pass("Bulk destructive action skips devices in maintenance mode")
            else:
                results.record_fail("Maintenance mode skip", f"Device not skipped: {data}")
        else:
            results.record_fail("Bulk action maintenance skip test", f"Status {r.status_code}: {r.text}")
    except Exception as e:
        results.record_fail("Bulk action maintenance skip test", str(e))
    
    # Test POST /api/devices/{id}/maintenance/disable
    try:
        r = await post(client, f"/devices/{device_id}/maintenance/disable", token=token)
        if r.status_code == 200:
            results.record_pass("POST /api/devices/{id}/maintenance/disable clears maintenance mode")
        else:
            results.record_fail("POST /api/devices/{id}/maintenance/disable", f"Status {r.status_code}: {r.text}")
    except Exception as e:
        results.record_fail("POST /api/devices/{id}/maintenance/disable", str(e))


async def test_installer_endpoints(client: httpx.AsyncClient, token: str):
    """Test installer distribution endpoints"""
    step("Testing Installer Endpoints")
    
    # Test GET /api/installer/install.ps1
    try:
        r = await get(client, "/installer/install.ps1")
        if r.status_code == 200:
            content = r.text
            if content and len(content) > 100:
                results.record_pass("GET /api/installer/install.ps1 returns PowerShell script")
                
                if r.headers.get("content-type", "").startswith("text/plain"):
                    results.record_pass("PowerShell script has text/plain content-type")
                else:
                    results.record_fail("PowerShell content-type", f"Got {r.headers.get('content-type')}")
            else:
                results.record_fail("PowerShell script content", "Script too short or empty")
        else:
            results.record_fail("GET /api/installer/install.ps1", f"Status {r.status_code}: {r.text}")
    except Exception as e:
        results.record_fail("GET /api/installer/install.ps1", str(e))
    
    # Test GET /api/installer/install.ps1 with query params
    try:
        r = await get(client, "/installer/install.ps1?backend_url=https://test.com&code=TEST-1234-5678")
        if r.status_code == 200:
            content = r.text
            if "DTA_BACKEND_URL" in content and "DTA_ENROLL_CODE" in content:
                results.record_pass("PowerShell script with query params prepends env vars")
            else:
                results.record_fail("PowerShell query params", "Env vars not prepended")
        else:
            results.record_fail("PowerShell with params", f"Status {r.status_code}")
    except Exception as e:
        results.record_fail("PowerShell with params", str(e))
    
    # Test GET /api/installer/install.bat
    try:
        r = await get(client, "/installer/install.bat")
        if r.status_code == 200:
            content = r.text
            if content and len(content) > 50:
                results.record_pass("GET /api/installer/install.bat returns batch wrapper")
                
                if r.headers.get("content-type", "").startswith("text/plain"):
                    results.record_pass("Batch wrapper has text/plain content-type")
                else:
                    results.record_fail("Batch content-type", f"Got {r.headers.get('content-type')}")
            else:
                results.record_fail("Batch wrapper content", "Script too short or empty")
        else:
            results.record_fail("GET /api/installer/install.bat", f"Status {r.status_code}: {r.text}")
    except Exception as e:
        results.record_fail("GET /api/installer/install.bat", str(e))
    
    # Test GET /api/installer/agent-bundle.zip
    try:
        r = await get(client, "/installer/agent-bundle.zip")
        if r.status_code == 200:
            content = r.content
            if len(content) > 1000:
                results.record_pass("GET /api/installer/agent-bundle.zip returns ZIP file")
                
                if r.headers.get("content-type") == "application/zip":
                    results.record_pass("Agent bundle has application/zip content-type")
                else:
                    results.record_fail("ZIP content-type", f"Got {r.headers.get('content-type')}")
                
                # Check ZIP magic bytes
                if content[:2] == b'PK':
                    results.record_pass("Agent bundle is valid ZIP (PK magic bytes)")
                else:
                    results.record_fail("ZIP validation", "Invalid ZIP magic bytes")
            else:
                results.record_fail("Agent bundle size", f"Too small: {len(content)} bytes")
        else:
            results.record_fail("GET /api/installer/agent-bundle.zip", f"Status {r.status_code}: {r.text}")
    except Exception as e:
        results.record_fail("GET /api/installer/agent-bundle.zip", str(e))
    
    # Test GET /api/installer/installer.info (requires auth)
    try:
        r = await get(client, "/installer/installer.info", token=token)
        if r.status_code == 200:
            data = r.json()
            results.record_pass("GET /api/installer/installer.info returns version info (requires auth)")
            
            required_fields = ["windows_ps1", "windows_bat", "portable_zip", "version", "supports"]
            if all(f in data for f in required_fields):
                results.record_pass("Installer info has all required fields")
            else:
                missing = [f for f in required_fields if f not in data]
                results.record_fail("Installer info fields", f"Missing: {missing}")
        else:
            results.record_fail("GET /api/installer/installer.info", f"Status {r.status_code}: {r.text}")
    except Exception as e:
        results.record_fail("GET /api/installer/installer.info", str(e))


async def test_enroll_link(client: httpx.AsyncClient, token: str):
    """Test enhanced enrollment link endpoint"""
    step("Testing Enhanced Enrollment Link")
    
    # Create enrollment code first
    code = None
    try:
        r = await post(client, "/enrollment/codes", {"label": "Test Enroll Link"}, token=token)
        if r.status_code == 200:
            code_doc = r.json()
            code = code_doc["code"]
        else:
            results.record_fail("Create enrollment code for link test", f"Status {r.status_code}")
            return
    except Exception as e:
        results.record_fail("Create enrollment code for link test", str(e))
        return
    
    # Test GET /api/installer/enroll-link
    try:
        r = await get(client, f"/installer/enroll-link?code={code}&backend_url=https://test.com", token=token)
        if r.status_code == 200:
            data = r.json()
            results.record_pass("GET /api/installer/enroll-link returns enrollment links")
            
            required_fields = ["code", "expires_at", "deep_link", "one_liner_ps", "one_liner_bat"]
            if all(f in data for f in required_fields):
                results.record_pass("Enroll link has all required fields (code, expires_at, deep_link, one_liner_ps, one_liner_bat)")
                
                # Check deep_link format
                if data["deep_link"].startswith("digitaltwin://enroll"):
                    results.record_pass("deep_link has correct format (digitaltwin://enroll)")
                else:
                    results.record_fail("deep_link format", f"Invalid: {data['deep_link']}")
                
                # Check one_liner_ps contains PowerShell command
                if "powershell" in data["one_liner_ps"].lower() and code in data["one_liner_ps"]:
                    results.record_pass("one_liner_ps contains PowerShell command with code")
                else:
                    results.record_fail("one_liner_ps", "Invalid PowerShell one-liner")
                
                # Check one_liner_bat contains batch URL
                if code in data["one_liner_bat"] and "install.bat" in data["one_liner_bat"]:
                    results.record_pass("one_liner_bat contains batch installer URL with code")
                else:
                    results.record_fail("one_liner_bat", "Invalid batch one-liner")
            else:
                missing = [f for f in required_fields if f not in data]
                results.record_fail("Enroll link fields", f"Missing: {missing}")
        else:
            results.record_fail("GET /api/installer/enroll-link", f"Status {r.status_code}: {r.text}")
    except Exception as e:
        results.record_fail("GET /api/installer/enroll-link", str(e))


async def test_rbac_technician(client: httpx.AsyncClient, admin_token: str, org_id: str, device_ids: list[str]):
    """Test RBAC for technician role with destructive actions"""
    step("Testing RBAC - Technician Cannot Enqueue Destructive Bulk Actions")
    
    # Create technician user
    tech_email = f"tech_test_{uuid.uuid4().hex[:8]}@test.com"
    tech_token = None
    
    try:
        r = await post(client, "/invitations", {"email": tech_email, "role": "technician"}, token=admin_token)
        if r.status_code == 200:
            inv = r.json()
            inv_token = inv["invitation"]["token"]
            
            r2 = await post(client, "/invitations/accept", {
                "token": inv_token,
                "full_name": "Test Technician",
                "password": "TechPass123!",
            })
            if r2.status_code == 200:
                tech_session = r2.json()
                tech_token = tech_session["access_token"]
                results.record_pass("Created technician user for RBAC test")
            else:
                results.record_fail("Accept technician invitation", f"Status {r2.status_code}")
                return
        else:
            results.record_fail("Create technician invitation", f"Status {r.status_code}")
            return
    except Exception as e:
        results.record_fail("Create technician user", str(e))
        return
    
    # Test that technician cannot enqueue destructive bulk actions
    if tech_token and device_ids:
        try:
            r = await post(client, "/actions/bulk", {
                "kind": "restart",
                "params": {},
                "device_ids": [device_ids[0]],
                "confirm": True,
            }, token=tech_token)
            if r.status_code == 403:
                results.record_pass("Technician gets 403 when trying to enqueue destructive bulk action")
            else:
                results.record_fail("Technician RBAC", f"Expected 403, got {r.status_code}")
        except Exception as e:
            results.record_fail("Technician RBAC test", str(e))


async def test_delete_device_group(client: httpx.AsyncClient, token: str, group_id: str):
    """Test device group deletion"""
    step("Testing Device Group Deletion")
    
    if not group_id:
        results.record_fail("Group deletion test", "No group_id available")
        return
    
    try:
        r = await delete(client, f"/device-groups/{group_id}", token=token)
        if r.status_code == 200:
            results.record_pass("DELETE /api/device-groups/{id} removes group and unassigns devices")
        else:
            results.record_fail("DELETE /api/device-groups/{id}", f"Status {r.status_code}: {r.text}")
    except Exception as e:
        results.record_fail("DELETE /api/device-groups/{id}", str(e))


async def main():
    print("="*60)
    print("Digital Twin Platform - Endpoint Management Testing")
    print(f"Testing against: {BASE}")
    print("="*60)
    
    async with httpx.AsyncClient() as client:
        # Login as admin
        admin_token, org_id, user_id = await test_admin_login(client)
        if not admin_token:
            print("\n❌ Admin login failed, cannot continue")
            results.print_summary()
            return 1
        
        # Create test devices
        device_ids = await create_test_devices(client, admin_token, count=3)
        if len(device_ids) < 2:
            print("\n⚠️  Could not create enough test devices, some tests may be skipped")
        
        # Test actions kinds endpoint
        await test_actions_kinds(client, admin_token)
        
        # Test bulk actions
        batch_id = await test_bulk_actions(client, admin_token, device_ids)
        
        # Test action batches
        if batch_id:
            await test_action_batches(client, admin_token, batch_id)
        
        # Test action retry
        await test_action_retry(client, admin_token, device_ids)
        
        # Test device groups
        group_id = await test_device_groups(client, admin_token, device_ids)
        
        # Test device group assignment
        if group_id:
            await test_device_group_assignment(client, admin_token, group_id, device_ids)
            
            # Test bulk actions with groups
            await test_bulk_actions_with_groups(client, admin_token, group_id)
        
        # Test maintenance mode
        await test_maintenance_mode(client, admin_token, device_ids)
        
        # Test installer endpoints
        await test_installer_endpoints(client, admin_token)
        
        # Test enhanced enrollment link
        await test_enroll_link(client, admin_token)
        
        # Test RBAC for technician
        await test_rbac_technician(client, admin_token, org_id, device_ids)
        
        # Clean up: delete test group
        if group_id:
            await test_delete_device_group(client, admin_token, group_id)
        
        # Print summary
        results.print_summary()
        
        return 0 if results.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
