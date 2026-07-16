#!/usr/bin/env python3
"""
Digital Twin Platform - Agent Pairing & Telemetry Flow Test
Tests the complete agent lifecycle: signup -> login -> create pairing code -> pair device -> status check -> WebSocket telemetry
"""
import asyncio
import json
import sys
import time
import uuid
from datetime import datetime

import requests
import websockets

# Configuration - use the CURRENT deployment
BASE_URL = "https://safe-import-pro.preview.emergentagent.com/api"
WS_BASE = "wss://safe-import-pro.preview.emergentagent.com/api"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'

class AgentPairingTest:
    def __init__(self):
        self.base_url = BASE_URL
        self.ws_base = WS_BASE
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        
        # Test data
        self.test_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
        self.test_password = "TestPass123!"
        self.test_org_name = f"Test Org {uuid.uuid4().hex[:6]}"
        
        # Auth tokens
        self.access_token = None
        self.org_id = None
        self.user_id = None
        
        # Pairing data
        self.pairing_code = None
        self.device_id = None
        self.device_access_token = None
        self.device_refresh_token = None
        self.ws_url = None
        self.api_url = None

    def log(self, message, level="INFO"):
        colors = {"INFO": Colors.BLUE, "PASS": Colors.GREEN, "FAIL": Colors.RED, "WARN": Colors.YELLOW}
        color = colors.get(level, Colors.RESET)
        print(f"{color}[{level}]{Colors.RESET} {message}")

    def test_signup(self):
        """Test POST /api/auth/signup"""
        self.tests_run += 1
        self.log(f"Test {self.tests_run}: POST /api/auth/signup creates org and user", "INFO")
        
        try:
            response = requests.post(
                f"{self.base_url}/auth/signup",
                json={
                    "email": self.test_email,
                    "password": self.test_password,
                    "full_name": "Test User",
                    "organization_name": self.test_org_name
                },
                timeout=10
            )
            
            if response.status_code != 200:
                self.tests_failed += 1
                self.log(f"✗ Signup failed: {response.status_code} - {response.text}", "FAIL")
                return False
            
            data = response.json()
            
            # Verify response structure
            required_fields = ["access_token", "refresh_token", "user", "organization"]
            missing = [f for f in required_fields if f not in data]
            if missing:
                self.tests_failed += 1
                self.log(f"✗ Missing fields: {missing}", "FAIL")
                return False
            
            self.access_token = data["access_token"]
            self.org_id = data["organization"]["id"]
            self.user_id = data["user"]["id"]
            
            self.tests_passed += 1
            self.log(f"✓ Signup successful (org: {self.org_id})", "PASS")
            return True
            
        except Exception as e:
            self.tests_failed += 1
            self.log(f"✗ Signup exception: {e}", "FAIL")
            return False

    def test_login(self):
        """Test POST /api/auth/login"""
        self.tests_run += 1
        self.log(f"Test {self.tests_run}: POST /api/auth/login returns tokens", "INFO")
        
        try:
            response = requests.post(
                f"{self.base_url}/auth/login",
                json={
                    "email": self.test_email,
                    "password": self.test_password,
                    "remember_me": False
                },
                timeout=10
            )
            
            if response.status_code != 200:
                self.tests_failed += 1
                self.log(f"✗ Login failed: {response.status_code} - {response.text}", "FAIL")
                return False
            
            data = response.json()
            
            if "access_token" not in data:
                self.tests_failed += 1
                self.log(f"✗ No access_token in response", "FAIL")
                return False
            
            self.tests_passed += 1
            self.log(f"✓ Login successful", "PASS")
            return True
            
        except Exception as e:
            self.tests_failed += 1
            self.log(f"✗ Login exception: {e}", "FAIL")
            return False

    def test_create_pairing_code(self):
        """Test POST /api/enrollment/codes"""
        self.tests_run += 1
        self.log(f"Test {self.tests_run}: POST /api/enrollment/codes creates pairing code", "INFO")
        
        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = requests.post(
                f"{self.base_url}/enrollment/codes",
                headers=headers,
                json={"label": "test-device"},
                timeout=10
            )
            
            if response.status_code != 200:
                self.tests_failed += 1
                self.log(f"✗ Create pairing code failed: {response.status_code} - {response.text}", "FAIL")
                return False
            
            data = response.json()
            
            if "code" not in data:
                self.tests_failed += 1
                self.log(f"✗ No code in response", "FAIL")
                return False
            
            self.pairing_code = data["code"]
            
            # Verify code format (DT-XXXX-XXXX)
            import re
            if not re.match(r"^DT-[A-Z0-9]{4}-[A-Z0-9]{4}$", self.pairing_code):
                self.tests_failed += 1
                self.log(f"✗ Invalid code format: {self.pairing_code}", "FAIL")
                return False
            
            self.tests_passed += 1
            self.log(f"✓ Pairing code created: {self.pairing_code}", "PASS")
            return True
            
        except Exception as e:
            self.tests_failed += 1
            self.log(f"✗ Create pairing code exception: {e}", "FAIL")
            return False

    def test_agent_pair(self):
        """Test POST /api/agent/pair"""
        self.tests_run += 1
        self.log(f"Test {self.tests_run}: POST /api/agent/pair exchanges code for device credentials", "INFO")
        
        try:
            response = requests.post(
                f"{self.base_url}/agent/pair",
                json={
                    "pairing_code": self.pairing_code,
                    "hostname": "test-device-001",
                    "machine_guid": str(uuid.uuid4()),
                    "os_name": "Windows 11 Pro",
                    "os_version": "10.0.22631",
                    "agent_version": "1.0.0-test",
                    "device_name": "Test Device",
                    "hardware_fingerprint": f"test-fp-{uuid.uuid4().hex[:16]}",
                    "ip_address": "192.168.1.100",
                    "mac_address": "00:11:22:33:44:55",
                    "serial_number": "TEST-SN-12345",
                    "cpu": "Intel Core i7-13700K",
                    "ram_gb": 32.0,
                    "disk_gb": 1024.0
                },
                timeout=10
            )
            
            if response.status_code != 200:
                self.tests_failed += 1
                self.log(f"✗ Agent pair failed: {response.status_code} - {response.text}", "FAIL")
                return False
            
            data = response.json()
            
            # Verify all required fields
            required_fields = [
                "device_id", "access_token", "refresh_token", "org_id",
                "ws_url", "api_url", "heartbeat_interval_sec", "telemetry_interval_sec",
                "policy", "issued_at", "access_token_expires_at"
            ]
            missing = [f for f in required_fields if f not in data]
            if missing:
                self.tests_failed += 1
                self.log(f"✗ Missing fields: {missing}", "FAIL")
                return False
            
            self.device_id = data["device_id"]
            self.device_access_token = data["access_token"]
            self.device_refresh_token = data["refresh_token"]
            self.ws_url = data["ws_url"]
            self.api_url = data["api_url"]
            
            # Verify policy config
            policy = data["policy"]
            if not isinstance(policy, dict):
                self.tests_failed += 1
                self.log(f"✗ Policy is not a dict", "FAIL")
                return False
            
            self.tests_passed += 1
            self.log(f"✓ Device paired successfully (device_id: {self.device_id})", "PASS")
            return True
            
        except Exception as e:
            self.tests_failed += 1
            self.log(f"✗ Agent pair exception: {e}", "FAIL")
            return False

    def test_device_status_200(self):
        """Test GET /api/agent/device/{device_id}/status returns 200 for paired device"""
        self.tests_run += 1
        self.log(f"Test {self.tests_run}: GET /api/agent/device/{{device_id}}/status returns 200", "INFO")
        
        try:
            response = requests.get(
                f"{self.base_url}/agent/device/{self.device_id}/status",
                timeout=10
            )
            
            if response.status_code != 200:
                self.tests_failed += 1
                self.log(f"✗ Status check failed: {response.status_code} - {response.text}", "FAIL")
                return False
            
            data = response.json()
            
            # Verify response fields
            required_fields = ["id", "hostname", "online", "status"]
            missing = [f for f in required_fields if f not in data]
            if missing:
                self.tests_failed += 1
                self.log(f"✗ Missing fields: {missing}", "FAIL")
                return False
            
            if data["id"] != self.device_id:
                self.tests_failed += 1
                self.log(f"✗ Device ID mismatch: {data['id']} != {self.device_id}", "FAIL")
                return False
            
            self.tests_passed += 1
            self.log(f"✓ Status endpoint returns 200 with correct data", "PASS")
            return True
            
        except Exception as e:
            self.tests_failed += 1
            self.log(f"✗ Status check exception: {e}", "FAIL")
            return False

    def test_device_status_404(self):
        """Test GET /api/agent/device/{unknown_id}/status returns 404"""
        self.tests_run += 1
        self.log(f"Test {self.tests_run}: GET /api/agent/device/{{unknown_id}}/status returns 404", "INFO")
        
        try:
            unknown_id = uuid.uuid4().hex
            response = requests.get(
                f"{self.base_url}/agent/device/{unknown_id}/status",
                timeout=10
            )
            
            if response.status_code != 404:
                self.tests_failed += 1
                self.log(f"✗ Expected 404, got {response.status_code}", "FAIL")
                return False
            
            data = response.json()
            if "detail" not in data:
                self.tests_failed += 1
                self.log(f"✗ No detail in 404 response", "FAIL")
                return False
            
            self.tests_passed += 1
            self.log(f"✓ Status endpoint returns 404 for unknown device", "PASS")
            return True
            
        except Exception as e:
            self.tests_failed += 1
            self.log(f"✗ Status 404 check exception: {e}", "FAIL")
            return False

    async def test_websocket_auth(self):
        """Test WebSocket /api/ws/agent authentication"""
        self.tests_run += 1
        self.log(f"Test {self.tests_run}: WebSocket /api/ws/agent authenticates device", "INFO")
        
        try:
            ws_url = f"{self.ws_base}/ws/agent?token={self.device_access_token}"
            
            async with websockets.connect(ws_url, ping_interval=None) as websocket:
                # Wait for hello message
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    data = json.loads(message)
                    
                    if data.get("type") != "hello":
                        self.tests_failed += 1
                        self.log(f"✗ Expected hello, got {data.get('type')}", "FAIL")
                        return False
                    
                    if data.get("device_id") != self.device_id:
                        self.tests_failed += 1
                        self.log(f"✗ Device ID mismatch in hello", "FAIL")
                        return False
                    
                    self.tests_passed += 1
                    self.log(f"✓ WebSocket authenticated, received hello", "PASS")
                    return True
                    
                except asyncio.TimeoutError:
                    self.tests_failed += 1
                    self.log(f"✗ Timeout waiting for hello message", "FAIL")
                    return False
                    
        except Exception as e:
            self.tests_failed += 1
            self.log(f"✗ WebSocket auth exception: {e}", "FAIL")
            return False

    async def test_websocket_metrics(self):
        """Test WebSocket metrics frame ingestion"""
        self.tests_run += 1
        self.log(f"Test {self.tests_run}: WebSocket metrics frame persists telemetry", "INFO")
        
        try:
            ws_url = f"{self.ws_base}/ws/agent?token={self.device_access_token}"
            
            async with websockets.connect(ws_url, ping_interval=None) as websocket:
                # Wait for hello
                await asyncio.wait_for(websocket.recv(), timeout=5.0)
                
                # Send metrics frame
                metrics_frame = {
                    "type": "metrics",
                    "ts": datetime.utcnow().isoformat() + "Z",
                    "metrics": {
                        "cpu_percent": 45.2,
                        "ram_percent": 62.8,
                        "disk_percent": 55.0,
                        "cpu_temp": 58.5,
                        "network_rx_kbps": 1024.5,
                        "network_tx_kbps": 512.3
                    }
                }
                
                await websocket.send(json.dumps(metrics_frame))
                
                # Wait for ack
                try:
                    ack_msg = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    ack_data = json.loads(ack_msg)
                    
                    if ack_data.get("type") != "ack":
                        self.tests_failed += 1
                        self.log(f"✗ Expected ack, got {ack_data.get('type')}", "FAIL")
                        return False
                    
                    # Give backend time to process
                    await asyncio.sleep(1)
                    
                    self.tests_passed += 1
                    self.log(f"✓ Metrics frame sent and acknowledged", "PASS")
                    return True
                    
                except asyncio.TimeoutError:
                    self.tests_failed += 1
                    self.log(f"✗ Timeout waiting for ack", "FAIL")
                    return False
                    
        except Exception as e:
            self.tests_failed += 1
            self.log(f"✗ WebSocket metrics exception: {e}", "FAIL")
            return False

    async def test_websocket_inventory(self):
        """Test WebSocket inventory frame ingestion"""
        self.tests_run += 1
        self.log(f"Test {self.tests_run}: WebSocket inventory frame promotes device fields", "INFO")
        
        try:
            ws_url = f"{self.ws_base}/ws/agent?token={self.device_access_token}"
            
            async with websockets.connect(ws_url, ping_interval=None) as websocket:
                # Wait for hello
                await asyncio.wait_for(websocket.recv(), timeout=5.0)
                
                # Send inventory frame
                inventory_frame = {
                    "type": "inventory",
                    "ts": datetime.utcnow().isoformat() + "Z",
                    "inventory": {
                        "cpu_model": "Intel Core i7-13700K",
                        "cpu_cores_physical": 16,
                        "cpu_cores_logical": 24,
                        "motherboard": "ASUS ROG STRIX Z790-E",
                        "bios_version": "1.23.4",
                        "ram_total_gb": 32.0,
                        "disk_total_gb": 1024.0,
                        "os_name": "Windows 11 Pro",
                        "os_version": "10.0.22631",
                        "os_build": "22631.3085"
                    }
                }
                
                await websocket.send(json.dumps(inventory_frame))
                
                # Wait for ack
                try:
                    ack_msg = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    ack_data = json.loads(ack_msg)
                    
                    if ack_data.get("type") != "ack":
                        self.tests_failed += 1
                        self.log(f"✗ Expected ack, got {ack_data.get('type')}", "FAIL")
                        return False
                    
                    # Give backend time to process
                    await asyncio.sleep(1)
                    
                    self.tests_passed += 1
                    self.log(f"✓ Inventory frame sent and acknowledged", "PASS")
                    return True
                    
                except asyncio.TimeoutError:
                    self.tests_failed += 1
                    self.log(f"✗ Timeout waiting for ack", "FAIL")
                    return False
                    
        except Exception as e:
            self.tests_failed += 1
            self.log(f"✗ WebSocket inventory exception: {e}", "FAIL")
            return False

    def test_device_details_after_telemetry(self):
        """Test GET /api/devices/{device_id} returns updated metrics"""
        self.tests_run += 1
        self.log(f"Test {self.tests_run}: GET /api/devices/{{device_id}} shows updated metrics", "INFO")
        
        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = requests.get(
                f"{self.base_url}/devices/{self.device_id}",
                headers=headers,
                timeout=10
            )
            
            if response.status_code != 200:
                self.tests_failed += 1
                self.log(f"✗ Get device failed: {response.status_code} - {response.text}", "FAIL")
                return False
            
            data = response.json()
            
            # Check that latest_metrics is populated
            if "latest_metrics" not in data:
                self.tests_failed += 1
                self.log(f"✗ No latest_metrics in response", "FAIL")
                return False
            
            metrics = data["latest_metrics"]
            if not metrics or "cpu_percent" not in metrics:
                self.tests_failed += 1
                self.log(f"✗ latest_metrics is empty or missing cpu_percent", "FAIL")
                return False
            
            # Check that inventory fields are promoted
            if "cpu" not in data or "motherboard" not in data or "bios_version" not in data:
                self.tests_failed += 1
                self.log(f"✗ Inventory fields not promoted to device", "FAIL")
                return False
            
            # Check health score is computed
            if "health_score" not in data or data["health_score"] is None:
                self.tests_failed += 1
                self.log(f"✗ health_score not computed", "FAIL")
                return False
            
            self.tests_passed += 1
            self.log(f"✓ Device shows updated metrics and inventory (health: {data['health_score']})", "PASS")
            return True
            
        except Exception as e:
            self.tests_failed += 1
            self.log(f"✗ Device details exception: {e}", "FAIL")
            return False

    def test_devices_list(self):
        """Test GET /api/devices returns the paired device"""
        self.tests_run += 1
        self.log(f"Test {self.tests_run}: GET /api/devices returns paired device", "INFO")
        
        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = requests.get(
                f"{self.base_url}/devices",
                headers=headers,
                timeout=10
            )
            
            if response.status_code != 200:
                self.tests_failed += 1
                self.log(f"✗ List devices failed: {response.status_code} - {response.text}", "FAIL")
                return False
            
            data = response.json()
            
            if "items" not in data:
                self.tests_failed += 1
                self.log(f"✗ No items in response", "FAIL")
                return False
            
            # Find our device
            device_found = any(d["id"] == self.device_id for d in data["items"])
            if not device_found:
                self.tests_failed += 1
                self.log(f"✗ Paired device not in list", "FAIL")
                return False
            
            self.tests_passed += 1
            self.log(f"✓ Devices list includes paired device", "PASS")
            return True
            
        except Exception as e:
            self.tests_failed += 1
            self.log(f"✗ Devices list exception: {e}", "FAIL")
            return False

    def test_devices_summary(self):
        """Test GET /api/devices/summary"""
        self.tests_run += 1
        self.log(f"Test {self.tests_run}: GET /api/devices/summary returns stats", "INFO")
        
        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = requests.get(
                f"{self.base_url}/devices/summary",
                headers=headers,
                timeout=10
            )
            
            if response.status_code != 200:
                self.tests_failed += 1
                self.log(f"✗ Devices summary failed: {response.status_code} - {response.text}", "FAIL")
                return False
            
            data = response.json()
            
            required_fields = ["total", "online", "offline", "with_agent"]
            missing = [f for f in required_fields if f not in data]
            if missing:
                self.tests_failed += 1
                self.log(f"✗ Missing fields: {missing}", "FAIL")
                return False
            
            if data["total"] < 1:
                self.tests_failed += 1
                self.log(f"✗ Total devices is 0", "FAIL")
                return False
            
            self.tests_passed += 1
            self.log(f"✓ Devices summary correct (total: {data['total']})", "PASS")
            return True
            
        except Exception as e:
            self.tests_failed += 1
            self.log(f"✗ Devices summary exception: {e}", "FAIL")
            return False

    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*70)
        print(f"{Colors.BLUE}TEST SUMMARY{Colors.RESET}")
        print("="*70)
        print(f"Total tests run:    {self.tests_run}")
        print(f"{Colors.GREEN}Tests passed:       {self.tests_passed}{Colors.RESET}")
        print(f"{Colors.RED}Tests failed:       {self.tests_failed}{Colors.RESET}")
        
        if self.tests_failed == 0:
            print(f"\n{Colors.GREEN}✓ ALL TESTS PASSED{Colors.RESET}")
            return 0
        else:
            print(f"\n{Colors.RED}✗ SOME TESTS FAILED{Colors.RESET}")
            return 1

    async def run_all_tests_async(self):
        """Run all tests in sequence"""
        print(f"\n{Colors.BLUE}{'='*70}{Colors.RESET}")
        print(f"{Colors.BLUE}Digital Twin Platform - Agent Pairing & Telemetry Tests{Colors.RESET}")
        print(f"{Colors.BLUE}Backend: {self.base_url}{Colors.RESET}")
        print(f"{Colors.BLUE}{'='*70}{Colors.RESET}\n")
        
        # Auth flow
        if not self.test_signup():
            self.log("Signup failed, cannot proceed", "FAIL")
            return self.print_summary()
        
        if not self.test_login():
            self.log("Login failed, cannot proceed", "FAIL")
            return self.print_summary()
        
        # Enrollment
        if not self.test_create_pairing_code():
            self.log("Create pairing code failed, cannot proceed", "FAIL")
            return self.print_summary()
        
        # Agent pairing
        if not self.test_agent_pair():
            self.log("Agent pair failed, cannot proceed", "FAIL")
            return self.print_summary()
        
        # Status endpoint (the critical one that was 404)
        self.test_device_status_200()
        self.test_device_status_404()
        
        # WebSocket tests
        await self.test_websocket_auth()
        await self.test_websocket_metrics()
        await self.test_websocket_inventory()
        
        # Dashboard endpoints
        self.test_device_details_after_telemetry()
        self.test_devices_list()
        self.test_devices_summary()
        
        return self.print_summary()

    def run_all_tests(self):
        """Synchronous wrapper for async tests"""
        return asyncio.run(self.run_all_tests_async())


def main():
    tester = AgentPairingTest()
    exit_code = tester.run_all_tests()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
