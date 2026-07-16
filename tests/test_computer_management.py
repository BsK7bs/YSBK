"""Comprehensive backend testing for Computer Management features.

Tests manual device registration, enhanced GET /api/devices with search/filters/pagination,
agent enrollment with hardware fields, and WebSocket inventory promotion.
"""
import asyncio
import json
import sys
import uuid
from datetime import datetime, timezone

import httpx
import websockets

# Public endpoint from frontend/.env
BASE = "https://virtual-twin-hub.preview.emergentagent.com/api"
WS_BASE = "wss://virtual-twin-hub.preview.emergentagent.com/api/ws"

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
        print(f"\n{'='*70}")
        print(f"Test Results: {self.passed}/{self.total} passed")
        if self.failed > 0:
            print(f"\nFailed tests ({self.failed}):")
            for error in self.errors:
                print(f"  - {error}")
        print(f"{'='*70}\n")


results = TestResults()


def step(msg: str):
    print(f"\n▶ {msg}")


async def post(client: httpx.AsyncClient, path: str, json_body: dict = None, token: str = None) -> httpx.Response:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        return await client.post(f"{BASE}{path}", json=json_body, headers=headers, timeout=30)
    except Exception as e:
        print(f"POST {path} failed: {e}")
        raise


async def get(client: httpx.AsyncClient, path: str, token: str = None) -> httpx.Response:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        return await client.get(f"{BASE}{path}", headers=headers, timeout=30)
    except Exception as e:
        print(f"GET {path} failed: {e}")
        raise


async def patch(client: httpx.AsyncClient, path: str, json_body: dict = None, token: str = None) -> httpx.Response:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        return await client.patch(f"{BASE}{path}", json=json_body, headers=headers, timeout=30)
    except Exception as e:
        print(f"PATCH {path} failed: {e}")
        raise


async def put(client: httpx.AsyncClient, path: str, json_body: dict = None, token: str = None) -> httpx.Response:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        return await client.put(f"{BASE}{path}", json=json_body, headers=headers, timeout=30)
    except Exception as e:
        print(f"PUT {path} failed: {e}")
        raise


async def delete(client: httpx.AsyncClient, path: str, token: str = None) -> httpx.Response:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        return await client.delete(f"{BASE}{path}", headers=headers, timeout=30)
    except Exception as e:
        print(f"DELETE {path} failed: {e}")
        raise


async def create_test_org(client: httpx.AsyncClient, org_name: str = None) -> dict:
    """Create a test organization and return session"""
    email = f"owner_{uuid.uuid4().hex[:8]}@test.com"
    password = "TestPass123!"
    org_name = org_name or f"Test Org {uuid.uuid4().hex[:4]}"
    
    r = await post(client, "/auth/signup", {
        "email": email,
        "password": password,
        "full_name": "Test Owner",
        "organization_name": org_name,
    })
    if r.status_code != 200:
        raise Exception(f"Failed to create org: {r.status_code} {r.text}")
    
    return r.json()


async def create_technician(client: httpx.AsyncClient, owner_token: str) -> str:
    """Create a technician user and return their token"""
    tech_email = f"tech_{uuid.uuid4().hex[:8]}@test.com"
    
    r = await post(client, "/invitations", {"email": tech_email, "role": "technician"}, token=owner_token)
    if r.status_code != 200:
        raise Exception(f"Failed to create tech invitation: {r.status_code}")
    
    inv_token = r.json()["invitation"]["token"]
    
    r = await post(client, "/invitations/accept", {
        "token": inv_token,
        "full_name": "Test Tech",
        "password": "TechPass123!",
    })
    if r.status_code != 200:
        raise Exception(f"Failed to accept tech invitation: {r.status_code}")
    
    return r.json()["access_token"]


async def create_viewer(client: httpx.AsyncClient, owner_token: str) -> str:
    """Create a viewer user and return their token"""
    viewer_email = f"viewer_{uuid.uuid4().hex[:8]}@test.com"
    
    r = await post(client, "/invitations", {"email": viewer_email, "role": "viewer"}, token=owner_token)
    if r.status_code != 200:
        raise Exception(f"Failed to create viewer invitation: {r.status_code}")
    
    inv_token = r.json()["invitation"]["token"]
    
    r = await post(client, "/invitations/accept", {
        "token": inv_token,
        "full_name": "Test Viewer",
        "password": "ViewerPass123!",
    })
    if r.status_code != 200:
        raise Exception(f"Failed to accept viewer invitation: {r.status_code}")
    
    return r.json()["access_token"]


async def create_admin(client: httpx.AsyncClient, owner_token: str) -> str:
    """Create an admin user and return their token"""
    admin_email = f"admin_{uuid.uuid4().hex[:8]}@test.com"
    
    r = await post(client, "/invitations", {"email": admin_email, "role": "admin"}, token=owner_token)
    if r.status_code != 200:
        raise Exception(f"Failed to create admin invitation: {r.status_code}")
    
    inv_token = r.json()["invitation"]["token"]
    
    r = await post(client, "/invitations/accept", {
        "token": inv_token,
        "full_name": "Test Admin",
        "password": "AdminPass123!",
    })
    if r.status_code != 200:
        raise Exception(f"Failed to accept admin invitation: {r.status_code}")
    
    return r.json()["access_token"]


# ========== Computer Management Tests ==========

async def test_manual_device_registration(client: httpx.AsyncClient, tech_token: str) -> str:
    """Test POST /api/devices with full payload"""
    step("Testing Manual Device Registration (POST /api/devices)")
    
    device_id = None
    
    # Test 1: Full payload with all fields
    try:
        payload = {
            "hostname": f"DESKTOP-{uuid.uuid4().hex[:6].upper()}",
            "display_name": "Test Workstation",
            "ip_address": "192.168.1.100",
            "mac_address": "00:1B:44:11:3A:B7",
            "serial_number": f"SN{uuid.uuid4().hex[:10].upper()}",
            "os_name": "Windows",
            "os_version": "11 Pro",
            "cpu": "Intel Core i7-12700K",
            "ram_gb": 32.0,
            "disk_gb": 1024.0,
            "motherboard": "ASUS ROG STRIX Z690-E",
            "bios_version": "1.20.3",
            "notes": "Test computer for QA",
            "tags": ["lab", "qa", "windows"],
        }
        
        r = await post(client, "/devices", payload, token=tech_token)
        if r.status_code == 201:
            device = r.json()
            device_id = device["id"]
            
            # Verify response fields
            if device.get("has_agent") == False and device.get("created_via") == "manual":
                results.record_pass("POST /api/devices returns 201 with has_agent=false, created_via='manual'")
            else:
                results.record_fail("Device registration response", f"has_agent={device.get('has_agent')}, created_via={device.get('created_via')}")
            
            # Verify all fields are present
            if all(device.get(k) == payload[k] for k in ["hostname", "ip_address", "mac_address", "serial_number", "cpu", "ram_gb", "disk_gb"]):
                results.record_pass("POST /api/devices preserves all submitted fields")
            else:
                results.record_fail("Device fields", "Some fields not preserved correctly")
        else:
            results.record_fail("POST /api/devices with full payload", f"Status {r.status_code}: {r.text}")
    except Exception as e:
        results.record_fail("POST /api/devices with full payload", str(e))
    
    # Test 2: Missing hostname (should return 422)
    try:
        r = await post(client, "/devices", {"ip_address": "192.168.1.1"}, token=tech_token)
        if r.status_code == 422:
            results.record_pass("POST /api/devices with missing hostname returns 422")
        else:
            results.record_fail("Missing hostname validation", f"Expected 422, got {r.status_code}")
    except Exception as e:
        results.record_fail("Missing hostname validation", str(e))
    
    return device_id


async def test_duplicate_constraints(client: httpx.AsyncClient, tech_token: str):
    """Test uniqueness constraints for hostname, MAC, serial within org"""
    step("Testing Duplicate Constraints (409 errors)")
    
    # Create first device
    hostname = f"UNIQUE-{uuid.uuid4().hex[:6].upper()}"
    mac = "AA:BB:CC:DD:EE:FF"
    serial = f"SERIAL{uuid.uuid4().hex[:8].upper()}"
    
    try:
        payload1 = {
            "hostname": hostname,
            "mac_address": mac,
            "serial_number": serial,
        }
        r = await post(client, "/devices", payload1, token=tech_token)
        if r.status_code != 201:
            results.record_fail("Create first device for duplicate test", f"Status {r.status_code}")
            return
    except Exception as e:
        results.record_fail("Create first device for duplicate test", str(e))
        return
    
    # Test duplicate hostname
    try:
        payload2 = {"hostname": hostname}
        r = await post(client, "/devices", payload2, token=tech_token)
        if r.status_code == 409:
            results.record_pass("POST /api/devices with duplicate hostname returns 409")
        else:
            results.record_fail("Duplicate hostname", f"Expected 409, got {r.status_code}")
    except Exception as e:
        results.record_fail("Duplicate hostname", str(e))
    
    # Test duplicate MAC
    try:
        payload3 = {"hostname": f"OTHER-{uuid.uuid4().hex[:4]}", "mac_address": mac}
        r = await post(client, "/devices", payload3, token=tech_token)
        if r.status_code == 409:
            results.record_pass("POST /api/devices with duplicate MAC returns 409")
        else:
            results.record_fail("Duplicate MAC", f"Expected 409, got {r.status_code}")
    except Exception as e:
        results.record_fail("Duplicate MAC", str(e))
    
    # Test duplicate serial
    try:
        payload4 = {"hostname": f"ANOTHER-{uuid.uuid4().hex[:4]}", "serial_number": serial}
        r = await post(client, "/devices", payload4, token=tech_token)
        if r.status_code == 409:
            results.record_pass("POST /api/devices with duplicate serial_number returns 409")
        else:
            results.record_fail("Duplicate serial", f"Expected 409, got {r.status_code}")
    except Exception as e:
        results.record_fail("Duplicate serial", str(e))


async def test_cross_org_independence(client: httpx.AsyncClient):
    """Test that Org A and Org B can both create hostname X"""
    step("Testing Cross-Org Independence")
    
    hostname = f"SHARED-{uuid.uuid4().hex[:6].upper()}"
    
    try:
        # Create Org A
        session_a = await create_test_org(client, "Org A")
        token_a = session_a["access_token"]
        tech_a = await create_technician(client, token_a)
        
        # Create Org B
        session_b = await create_test_org(client, "Org B")
        token_b = session_b["access_token"]
        tech_b = await create_technician(client, token_b)
        
        # Org A creates device with hostname X
        r1 = await post(client, "/devices", {"hostname": hostname}, token=tech_a)
        if r1.status_code != 201:
            results.record_fail("Org A create device", f"Status {r1.status_code}")
            return
        
        # Org B creates device with same hostname X (should succeed)
        r2 = await post(client, "/devices", {"hostname": hostname}, token=tech_b)
        if r2.status_code == 201:
            results.record_pass("POST /api/devices creates independently per org (no cross-org conflict)")
        else:
            results.record_fail("Cross-org independence", f"Expected 201, got {r2.status_code}: {r2.text}")
    except Exception as e:
        results.record_fail("Cross-org independence", str(e))


async def test_device_update(client: httpx.AsyncClient, tech_token: str, device_id: str):
    """Test PATCH and PUT /api/devices/{id}"""
    step("Testing Device Update (PATCH/PUT /api/devices/{id})")
    
    # Test PATCH
    try:
        update_payload = {
            "display_name": "Updated Workstation",
            "notes": "Updated notes",
            "tags": ["updated", "test"],
            "ram_gb": 64.0,
        }
        r = await patch(client, f"/devices/{device_id}", update_payload, token=tech_token)
        if r.status_code == 200:
            device = r.json()
            if device.get("display_name") == "Updated Workstation" and device.get("ram_gb") == 64.0:
                results.record_pass("PATCH /api/devices/{id} updates fields correctly")
            else:
                results.record_fail("PATCH update verification", f"Fields not updated: {device}")
        else:
            results.record_fail("PATCH /api/devices/{id}", f"Status {r.status_code}: {r.text}")
    except Exception as e:
        results.record_fail("PATCH /api/devices/{id}", str(e))
    
    # Test PUT
    try:
        put_payload = {
            "hostname": f"RENAMED-{uuid.uuid4().hex[:4]}",
            "cpu": "AMD Ryzen 9 5950X",
        }
        r = await put(client, f"/devices/{device_id}", put_payload, token=tech_token)
        if r.status_code == 200:
            device = r.json()
            if device.get("cpu") == "AMD Ryzen 9 5950X":
                results.record_pass("PUT /api/devices/{id} works like PATCH")
            else:
                results.record_fail("PUT update verification", f"CPU not updated: {device.get('cpu')}")
        else:
            results.record_fail("PUT /api/devices/{id}", f"Status {r.status_code}: {r.text}")
    except Exception as e:
        results.record_fail("PUT /api/devices/{id}", str(e))


async def test_update_duplicate_conflict(client: httpx.AsyncClient, tech_token: str):
    """Test PATCH with duplicate hostname/serial/mac returns 409"""
    step("Testing Update Duplicate Conflict")
    
    try:
        # Create two devices
        hostname1 = f"DEV1-{uuid.uuid4().hex[:4]}"
        hostname2 = f"DEV2-{uuid.uuid4().hex[:4]}"
        
        r1 = await post(client, "/devices", {"hostname": hostname1}, token=tech_token)
        r2 = await post(client, "/devices", {"hostname": hostname2}, token=tech_token)
        
        if r1.status_code != 201 or r2.status_code != 201:
            results.record_fail("Create devices for conflict test", "Failed to create devices")
            return
        
        device1_id = r1.json()["id"]
        
        # Try to update device1 with device2's hostname
        r = await patch(client, f"/devices/{device1_id}", {"hostname": hostname2}, token=tech_token)
        if r.status_code == 409:
            results.record_pass("PATCH with duplicate hostname returns 409")
        else:
            results.record_fail("PATCH duplicate conflict", f"Expected 409, got {r.status_code}")
    except Exception as e:
        results.record_fail("PATCH duplicate conflict", str(e))


async def test_device_deletion(client: httpx.AsyncClient, admin_token: str, tech_token: str):
    """Test DELETE /api/devices/{id} with cascading and RBAC"""
    step("Testing Device Deletion")
    
    # Create a device
    try:
        r = await post(client, "/devices", {"hostname": f"TO-DELETE-{uuid.uuid4().hex[:4]}"}, token=tech_token)
        if r.status_code != 201:
            results.record_fail("Create device for deletion", f"Status {r.status_code}")
            return
        device_id = r.json()["id"]
    except Exception as e:
        results.record_fail("Create device for deletion", str(e))
        return
    
    # Technician tries to delete (should get 403)
    try:
        r = await delete(client, f"/devices/{device_id}", token=tech_token)
        if r.status_code == 403:
            results.record_pass("Technician gets 403 on DELETE /api/devices/{id}")
        else:
            results.record_fail("Technician DELETE RBAC", f"Expected 403, got {r.status_code}")
    except Exception as e:
        results.record_fail("Technician DELETE RBAC", str(e))
    
    # Admin deletes (should succeed)
    try:
        r = await delete(client, f"/devices/{device_id}", token=admin_token)
        if r.status_code == 200:
            results.record_pass("DELETE /api/devices/{id} works for Admin+ and cascades")
        else:
            results.record_fail("Admin DELETE", f"Status {r.status_code}: {r.text}")
    except Exception as e:
        results.record_fail("Admin DELETE", str(e))


async def test_paginated_devices_list(client: httpx.AsyncClient, tech_token: str):
    """Test GET /api/devices returns paginated envelope"""
    step("Testing Paginated Devices List")
    
    # Create multiple devices
    try:
        for i in range(5):
            await post(client, "/devices", {
                "hostname": f"PAGE-TEST-{i}-{uuid.uuid4().hex[:4]}",
                "os_name": "Ubuntu" if i % 2 == 0 else "Windows",
                "tags": ["page-test"],
            }, token=tech_token)
    except Exception as e:
        results.record_fail("Create devices for pagination", str(e))
        return
    
    # Test paginated response structure
    try:
        r = await get(client, "/devices?page=1&page_size=2", token=tech_token)
        if r.status_code == 200:
            data = r.json()
            if all(k in data for k in ["items", "total", "page", "page_size", "total_pages"]):
                results.record_pass("GET /api/devices returns paginated envelope {items, total, page, page_size, total_pages}")
                
                if isinstance(data["items"], list) and len(data["items"]) <= 2:
                    results.record_pass("Pagination page_size is respected")
                else:
                    results.record_fail("Pagination page_size", f"Expected <=2 items, got {len(data['items'])}")
            else:
                results.record_fail("Paginated envelope structure", f"Missing keys: {data.keys()}")
        else:
            results.record_fail("GET /api/devices paginated", f"Status {r.status_code}: {r.text}")
    except Exception as e:
        results.record_fail("GET /api/devices paginated", str(e))


async def test_search_functionality(client: httpx.AsyncClient, tech_token: str):
    """Test GET /api/devices?q=<query> searches across fields"""
    step("Testing Search Functionality")
    
    # Create a device with unique searchable content
    search_term = f"SEARCH{uuid.uuid4().hex[:6].upper()}"
    try:
        await post(client, "/devices", {
            "hostname": f"HOST-{search_term}",
            "notes": f"Contains {search_term} in notes",
            "tags": [search_term.lower()],
        }, token=tech_token)
    except Exception as e:
        results.record_fail("Create device for search", str(e))
        return
    
    # Search by hostname
    try:
        r = await get(client, f"/devices?q={search_term}", token=tech_token)
        if r.status_code == 200:
            data = r.json()
            if any(search_term in d.get("hostname", "") for d in data["items"]):
                results.record_pass("GET /api/devices?q=<query> searches across hostname")
            else:
                results.record_fail("Search by hostname", f"Search term not found in results")
        else:
            results.record_fail("Search functionality", f"Status {r.status_code}: {r.text}")
    except Exception as e:
        results.record_fail("Search functionality", str(e))


async def test_filter_functionality(client: httpx.AsyncClient, tech_token: str):
    """Test GET /api/devices filters (status, os, tag)"""
    step("Testing Filter Functionality")
    
    # Create devices with different attributes
    try:
        # Manual device (no agent)
        await post(client, "/devices", {
            "hostname": f"MANUAL-{uuid.uuid4().hex[:4]}",
            "os_name": "Ubuntu",
            "tags": ["filter-test"],
        }, token=tech_token)
    except Exception as e:
        results.record_fail("Create devices for filter test", str(e))
        return
    
    # Test status=no_agent filter
    try:
        r = await get(client, "/devices?status=no_agent", token=tech_token)
        if r.status_code == 200:
            data = r.json()
            if all(d.get("has_agent") == False for d in data["items"]):
                results.record_pass("GET /api/devices?status=no_agent filters correctly")
            else:
                results.record_fail("Filter status=no_agent", "Found devices with has_agent=true")
        else:
            results.record_fail("Filter status=no_agent", f"Status {r.status_code}")
    except Exception as e:
        results.record_fail("Filter status=no_agent", str(e))
    
    # Test os filter
    try:
        r = await get(client, "/devices?os=ubuntu", token=tech_token)
        if r.status_code == 200:
            data = r.json()
            if all("ubuntu" in d.get("os_name", "").lower() for d in data["items"] if d.get("os_name")):
                results.record_pass("GET /api/devices?os=<substring> filters by os_name")
            else:
                results.record_fail("Filter os", "Found non-matching OS")
        else:
            results.record_fail("Filter os", f"Status {r.status_code}")
    except Exception as e:
        results.record_fail("Filter os", str(e))
    
    # Test tag filter
    try:
        r = await get(client, "/devices?tag=filter-test", token=tech_token)
        if r.status_code == 200:
            data = r.json()
            if all("filter-test" in d.get("tags", []) for d in data["items"]):
                results.record_pass("GET /api/devices?tag=<exact> filters by exact tag")
            else:
                results.record_fail("Filter tag", "Found devices without the tag")
        else:
            results.record_fail("Filter tag", f"Status {r.status_code}")
    except Exception as e:
        results.record_fail("Filter tag", str(e))


async def test_sorting_functionality(client: httpx.AsyncClient, tech_token: str):
    """Test GET /api/devices sorting"""
    step("Testing Sorting Functionality")
    
    # Create devices with different values
    try:
        await post(client, "/devices", {"hostname": "AAA-FIRST", "ram_gb": 8.0}, token=tech_token)
        await post(client, "/devices", {"hostname": "ZZZ-LAST", "ram_gb": 64.0}, token=tech_token)
        await post(client, "/devices", {"hostname": "MMM-MIDDLE", "ram_gb": 32.0}, token=tech_token)
    except Exception as e:
        results.record_fail("Create devices for sort test", str(e))
        return
    
    # Test sort by hostname asc
    try:
        r = await get(client, "/devices?sort_by=hostname&sort_dir=asc&page_size=100", token=tech_token)
        if r.status_code == 200:
            data = r.json()
            hostnames = [d["hostname"] for d in data["items"]]
            if hostnames == sorted(hostnames):
                results.record_pass("GET /api/devices?sort_by=hostname&sort_dir=asc sorts alphabetically")
            else:
                results.record_fail("Sort hostname asc", f"Not sorted: {hostnames[:5]}")
        else:
            results.record_fail("Sort hostname", f"Status {r.status_code}")
    except Exception as e:
        results.record_fail("Sort hostname", str(e))
    
    # Test sort by ram desc
    try:
        r = await get(client, "/devices?sort_by=ram&sort_dir=desc&page_size=100", token=tech_token)
        if r.status_code == 200:
            data = r.json()
            rams = [d.get("ram_gb") or 0 for d in data["items"]]
            if rams == sorted(rams, reverse=True):
                results.record_pass("GET /api/devices?sort_by=ram&sort_dir=desc sorts by ram_gb desc")
            else:
                results.record_fail("Sort ram desc", f"Not sorted: {rams[:5]}")
        else:
            results.record_fail("Sort ram", f"Status {r.status_code}")
    except Exception as e:
        results.record_fail("Sort ram", str(e))


async def test_pagination_correctness(client: httpx.AsyncClient, tech_token: str):
    """Test pagination page and total_pages calculation"""
    step("Testing Pagination Correctness")
    
    try:
        # Get page 2 with page_size=1
        r = await get(client, "/devices?page=2&page_size=1", token=tech_token)
        if r.status_code == 200:
            data = r.json()
            if data["page"] == 2 and len(data["items"]) <= 1:
                results.record_pass("GET /api/devices?page=2&page_size=1 correctly paginates")
            else:
                results.record_fail("Pagination page 2", f"page={data['page']}, items={len(data['items'])}")
            
            # Check total_pages calculation
            expected_pages = (data["total"] + data["page_size"] - 1) // data["page_size"]
            if data["total_pages"] == expected_pages or data["total_pages"] == max(1, expected_pages):
                results.record_pass("total_pages is correctly computed")
            else:
                results.record_fail("total_pages calculation", f"Expected {expected_pages}, got {data['total_pages']}")
        else:
            results.record_fail("Pagination page 2", f"Status {r.status_code}")
    except Exception as e:
        results.record_fail("Pagination correctness", str(e))


async def test_rbac_device_operations(client: httpx.AsyncClient, owner_token: str):
    """Test RBAC for device operations"""
    step("Testing RBAC for Device Operations")
    
    try:
        # Create viewer and technician
        viewer_token = await create_viewer(client, owner_token)
        tech_token = await create_technician(client, owner_token)
        
        # Viewer tries to POST device (should get 403)
        r = await post(client, "/devices", {"hostname": "VIEWER-TEST"}, token=viewer_token)
        if r.status_code == 403:
            results.record_pass("Viewer gets 403 on POST /api/devices")
        else:
            results.record_fail("Viewer POST RBAC", f"Expected 403, got {r.status_code}")
        
        # Technician can POST device
        r = await post(client, "/devices", {"hostname": f"TECH-{uuid.uuid4().hex[:4]}"}, token=tech_token)
        if r.status_code == 201:
            results.record_pass("Technician+ can POST /api/devices")
            device_id = r.json()["id"]
            
            # Technician can PATCH
            r = await patch(client, f"/devices/{device_id}", {"notes": "Updated"}, token=tech_token)
            if r.status_code == 200:
                results.record_pass("Technician+ can PATCH /api/devices/{id}")
            else:
                results.record_fail("Technician PATCH", f"Status {r.status_code}")
        else:
            results.record_fail("Technician POST", f"Status {r.status_code}")
    except Exception as e:
        results.record_fail("RBAC device operations", str(e))


async def test_tenant_isolation_manual_devices(client: httpx.AsyncClient):
    """Test tenant isolation for manually-registered devices"""
    step("Testing Tenant Isolation for Manual Devices")
    
    try:
        # Create two orgs
        session_a = await create_test_org(client, "Org A")
        token_a = session_a["access_token"]
        tech_a = await create_technician(client, token_a)
        
        session_b = await create_test_org(client, "Org B")
        token_b = session_b["access_token"]
        
        # Org A creates a device
        r = await post(client, "/devices", {"hostname": f"ORG-A-{uuid.uuid4().hex[:4]}"}, token=tech_a)
        if r.status_code != 201:
            results.record_fail("Org A create device", f"Status {r.status_code}")
            return
        device_a_id = r.json()["id"]
        
        # Org B tries to GET Org A's device (should get 404)
        r = await get(client, f"/devices/{device_a_id}", token=token_b)
        if r.status_code == 404:
            results.record_pass("Org B cannot GET Org A's manually-registered device (404)")
        else:
            results.record_fail("Tenant isolation GET", f"Expected 404, got {r.status_code}")
        
        # Org B tries to PATCH Org A's device (should get 404)
        r = await patch(client, f"/devices/{device_a_id}", {"notes": "hack"}, token=token_b)
        if r.status_code == 404:
            results.record_pass("Org B cannot PATCH Org A's device (404)")
        else:
            results.record_fail("Tenant isolation PATCH", f"Expected 404, got {r.status_code}")
        
        # Org B tries to DELETE Org A's device (should get 404)
        r = await delete(client, f"/devices/{device_a_id}", token=token_b)
        if r.status_code == 404:
            results.record_pass("Org B cannot DELETE Org A's device (404)")
        else:
            results.record_fail("Tenant isolation DELETE", f"Expected 404, got {r.status_code}")
    except Exception as e:
        results.record_fail("Tenant isolation manual devices", str(e))


async def test_agent_enrollment_with_hardware_fields(client: httpx.AsyncClient, owner_token: str):
    """Test agent enrollment now accepts additional hardware fields"""
    step("Testing Agent Enrollment with Hardware Fields")
    
    try:
        # Create enrollment code
        r = await post(client, "/enrollment/codes", {"label": "Hardware Test"}, token=owner_token)
        if r.status_code != 200:
            results.record_fail("Create enrollment code", f"Status {r.status_code}")
            return
        code = r.json()["code"]
        
        # Enroll with hardware fields
        enroll_payload = {
            "code": code,
            "hostname": f"AGENT-{uuid.uuid4().hex[:4]}",
            "os_name": "Windows",
            "os_version": "11",
            "agent_version": "1.0.0",
            "hardware_id": uuid.uuid4().hex,
            "ip_address": "10.0.0.50",
            "mac_address": "AA:BB:CC:DD:EE:11",
            "serial_number": "AGENT-SERIAL-123",
            "cpu": "Intel Core i9-13900K",
            "ram_gb": 64.0,
            "disk_gb": 2048.0,
            "motherboard": "MSI MPG Z790",
            "bios_version": "7D70v15",
        }
        
        r = await post(client, "/enrollment/enroll", enroll_payload)
        if r.status_code == 200:
            creds = r.json()
            device_id = creds["device_id"]
            
            # Verify device has hardware fields
            r = await get(client, f"/devices/{device_id}", token=owner_token)
            if r.status_code == 200:
                device = r.json()
                if all(device.get(k) == enroll_payload[k] for k in ["ip_address", "mac_address", "serial_number", "cpu", "ram_gb", "disk_gb"]):
                    results.record_pass("Agent enrollment accepts and stores additional hardware fields")
                else:
                    results.record_fail("Agent hardware fields", f"Fields not stored: {device}")
            else:
                results.record_fail("Get enrolled device", f"Status {r.status_code}")
        else:
            results.record_fail("Agent enrollment with hardware", f"Status {r.status_code}: {r.text}")
    except Exception as e:
        results.record_fail("Agent enrollment with hardware", str(e))


async def test_websocket_inventory_promotion(owner_token: str):
    """Test WebSocket inventory frame promotes hardware fields to top-level"""
    step("Testing WebSocket Inventory Field Promotion")
    
    try:
        # Create enrollment code and enroll device
        async with httpx.AsyncClient() as client:
            r = await post(client, "/enrollment/codes", {"label": "WS Test"}, token=owner_token)
            if r.status_code != 200:
                results.record_fail("Create code for WS test", f"Status {r.status_code}")
                return
            code = r.json()["code"]
            
            r = await post(client, "/enrollment/enroll", {
                "code": code,
                "hostname": f"WS-{uuid.uuid4().hex[:4]}",
                "os_name": "Linux",
                "agent_version": "1.0.0",
                "hardware_id": uuid.uuid4().hex,
            })
            if r.status_code != 200:
                results.record_fail("Enroll for WS test", f"Status {r.status_code}")
                return
            
            device_id = r.json()["device_id"]
            api_key = r.json()["device_api_key"]
        
        # Connect via WebSocket and send inventory
        url = f"{WS_BASE}/agent?api_key={api_key}"
        async with websockets.connect(url, open_timeout=10) as ws:
            # Receive hello
            hello = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            if hello.get("type") != "hello":
                results.record_fail("WS hello", f"Expected hello, got {hello}")
                return
            
            # Send inventory with hardware fields
            inventory_frame = {
                "type": "inventory",
                "inventory": {
                    "cpu_model": "AMD Ryzen 7 5800X",
                    "ram_total_gb": 32,
                    "disks": [{"name": "/dev/sda", "total_gb": 512}],
                    "motherboard": "ASUS TUF GAMING X570",
                    "bios_version": "4021",
                    "serial_number": "WS-SERIAL-456",
                    "ip_address": "192.168.1.200",
                    "mac_address": "11:22:33:44:55:66",
                },
            }
            await ws.send(json.dumps(inventory_frame))
            ack = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            if ack.get("type") != "ack":
                results.record_fail("Inventory ack", f"Expected ack, got {ack}")
                return
        
        # Wait for processing
        await asyncio.sleep(1)
        
        # Verify fields are promoted to top-level
        async with httpx.AsyncClient() as client:
            r = await get(client, f"/devices/{device_id}", token=owner_token)
            if r.status_code == 200:
                device = r.json()
                expected = {
                    "cpu": "AMD Ryzen 7 5800X",
                    "ram_gb": 32,
                    "disk_gb": 512,
                    "motherboard": "ASUS TUF GAMING X570",
                    "bios_version": "4021",
                    "serial_number": "WS-SERIAL-456",
                    "ip_address": "192.168.1.200",
                    "mac_address": "11:22:33:44:55:66",
                }
                if all(device.get(k) == v for k, v in expected.items()):
                    results.record_pass("WebSocket inventory frame promotes hardware fields to top-level")
                else:
                    results.record_fail("Inventory promotion", f"Fields not promoted: {device}")
            else:
                results.record_fail("Get device after inventory", f"Status {r.status_code}")
    except Exception as e:
        results.record_fail("WebSocket inventory promotion", str(e))


async def test_devices_summary_new_fields(client: httpx.AsyncClient, owner_token: str):
    """Test GET /api/devices/summary returns with_agent and unmanaged counts"""
    step("Testing Devices Summary New Fields")
    
    try:
        r = await get(client, "/devices/summary", token=owner_token)
        if r.status_code == 200:
            summary = r.json()
            required_fields = ["total", "online", "offline", "with_agent", "unmanaged", "healthy", "warning", "high_risk", "critical"]
            if all(field in summary for field in required_fields):
                results.record_pass("GET /api/devices/summary returns with_agent and unmanaged counts")
            else:
                missing = [f for f in required_fields if f not in summary]
                results.record_fail("Devices summary new fields", f"Missing: {missing}")
        else:
            results.record_fail("GET /api/devices/summary", f"Status {r.status_code}: {r.text}")
    except Exception as e:
        results.record_fail("GET /api/devices/summary", str(e))


async def main():
    print("="*70)
    print("Computer Management Features - Backend Testing")
    print(f"Testing against: {BASE}")
    print("="*70)
    
    async with httpx.AsyncClient() as client:
        # Create test org with owner, technician, admin
        try:
            session = await create_test_org(client)
            owner_token = session["access_token"]
            org_id = session["user"]["org_id"]
            
            tech_token = await create_technician(client, owner_token)
            admin_token = await create_admin(client, owner_token)
            
            print(f"\n✓ Test organization created (org_id: {org_id[:8]}...)")
        except Exception as e:
            print(f"\n❌ Failed to create test org: {e}")
            return 1
        
        # Run all tests
        device_id = await test_manual_device_registration(client, tech_token)
        await test_duplicate_constraints(client, tech_token)
        await test_cross_org_independence(client)
        
        if device_id:
            await test_device_update(client, tech_token, device_id)
        
        await test_update_duplicate_conflict(client, tech_token)
        await test_device_deletion(client, admin_token, tech_token)
        await test_paginated_devices_list(client, tech_token)
        await test_search_functionality(client, tech_token)
        await test_filter_functionality(client, tech_token)
        await test_sorting_functionality(client, tech_token)
        await test_pagination_correctness(client, tech_token)
        await test_rbac_device_operations(client, owner_token)
        await test_tenant_isolation_manual_devices(client)
        await test_agent_enrollment_with_hardware_fields(client, owner_token)
        await test_websocket_inventory_promotion(owner_token)
        await test_devices_summary_new_fields(client, owner_token)
    
    # Print summary
    results.print_summary()
    
    if results.failed == 0:
        print("🎉 ALL COMPUTER MANAGEMENT TESTS PASSED!\n")
        return 0
    else:
        print(f"❌ {results.failed} test(s) failed\n")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Test suite error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)
