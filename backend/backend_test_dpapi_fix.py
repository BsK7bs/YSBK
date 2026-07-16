"""
Backend API testing for DPAPI Credential Bootstrap Fix.

Tests the fix for the "device paired but offline forever" bug where the
frozen installer wrote device.json but the frozen agent read from DPAPI
Credential Manager (which was never populated).

Fix: 
1. AgentPairResponse now includes device_api_key field
2. New GET /api/agent/device/{device_id}/status endpoint (public, no auth)
3. install.cmd does the pair call itself via PowerShell and writes DPAPI

Test against: https://bulk-file-loader.preview.emergentagent.com/api
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import httpx

# Public backend endpoint
BASE_URL = "https://bulk-file-loader.preview.emergentagent.com/api"

# Test credentials (seeded owner account)
ADMIN_EMAIL = "admin@digitaltwin.com"
ADMIN_PASSWORD = "ChangeMe!2026"


class TestResults:
    def __init__(self):
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.errors = []
        self.test_details = []

    def record_pass(self, test_name: str, details: str = ""):
        self.total += 1
        self.passed += 1
        print(f"  ✅ PASS: {test_name}")
        if details:
            print(f"     {details}")
        self.test_details.append({
            "test": test_name,
            "status": "PASS",
            "details": details
        })

    def record_fail(self, test_name: str, error: str):
        self.total += 1
        self.failed += 1
        self.errors.append(f"{test_name}: {error}")
        print(f"  ❌ FAIL: {test_name}")
        print(f"     Error: {error}")
        self.test_details.append({
            "test": test_name,
            "status": "FAIL",
            "error": error
        })

    def print_summary(self):
        print(f"\n{'='*70}")
        print(f"DPAPI CREDENTIAL BOOTSTRAP FIX - SUMMARY")
        print(f"{'='*70}")
        print(f"Total Tests: {self.total}")
        print(f"Passed: {self.passed} ✅")
        print(f"Failed: {self.failed} ❌")
        print(f"Success Rate: {(self.passed/self.total*100) if self.total > 0 else 0:.1f}%")
        
        if self.failed > 0:
            print(f"\n{'='*70}")
            print(f"FAILED TESTS:")
            print(f"{'='*70}")
            for error in self.errors:
                print(f"  ❌ {error}")
        
        print(f"{'='*70}\n")
        return self.failed == 0


results = TestResults()


def step(msg: str):
    """Print a test step header."""
    print(f"\n{'▶'*3} {msg}")


def login() -> str:
    """Login and return access token."""
    step("Logging in as admin")
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{BASE_URL}/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
            )
            
            if response.status_code != 200:
                results.record_fail(
                    "Login",
                    f"Expected 200, got {response.status_code}: {response.text}"
                )
                return None
            
            data = response.json()
            token = data.get("access_token")
            
            if not token:
                results.record_fail("Login", "No access_token in response")
                return None
            
            results.record_pass("Login", f"Successfully logged in as {ADMIN_EMAIL}")
            return token
    
    except Exception as e:
        results.record_fail("Login", f"Exception: {str(e)}")
        return None


def test_regression_download_init(token: str):
    """REGRESSION: POST /api/agent/installer/download-init returns expected fields."""
    step("REGRESSION: Testing POST /api/agent/installer/download-init")
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{BASE_URL}/agent/installer/download-init",
                headers={"Authorization": f"Bearer {token}"}
            )
            
            if response.status_code != 200:
                results.record_fail(
                    "REGRESSION: POST /download-init",
                    f"Expected 200, got {response.status_code}: {response.text}"
                )
                return None
            
            data = response.json()
            
            # Verify required fields
            required_fields = [
                "download_token", "pairing_code", "filename",
                "is_bundle", "expires_in"
            ]
            
            missing = [f for f in required_fields if f not in data]
            if missing:
                results.record_fail(
                    "REGRESSION: POST /download-init",
                    f"Missing fields: {missing}"
                )
                return None
            
            # Verify pairing code format: DT-XXXX-XXXX
            pairing_code = data.get("pairing_code", "")
            if not re.match(r"^DT-[A-Z0-9]{4}-[A-Z0-9]{4}$", pairing_code):
                results.record_fail(
                    "REGRESSION: POST /download-init",
                    f"Invalid pairing_code format: {pairing_code}"
                )
                return None
            
            # Verify is_bundle is true
            if not data.get("is_bundle"):
                results.record_fail(
                    "REGRESSION: POST /download-init",
                    "is_bundle=false (expected true)"
                )
                return None
            
            # Verify expires_in is 300 seconds
            if data.get("expires_in") != 300:
                results.record_fail(
                    "REGRESSION: POST /download-init",
                    f"expires_in={data.get('expires_in')} (expected 300)"
                )
                return None
            
            results.record_pass(
                "REGRESSION: POST /download-init",
                f"pairing_code={pairing_code}, is_bundle=true, expires_in=300"
            )
            return data
    
    except Exception as e:
        results.record_fail(
            "REGRESSION: POST /download-init",
            f"Exception: {str(e)}"
        )
        return None


def test_regression_download(download_token: str, pairing_code: str):
    """REGRESSION: GET /api/agent/installer/download returns valid ZIP."""
    step("REGRESSION: Testing GET /api/agent/installer/download")
    
    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.get(
                f"{BASE_URL}/agent/installer/download",
                params={"token": download_token}
            )
            
            if response.status_code != 200:
                results.record_fail(
                    "REGRESSION: GET /download",
                    f"Expected 200, got {response.status_code}: {response.text}"
                )
                return None
            
            # Verify Content-Type
            content_type = response.headers.get("content-type", "")
            if content_type != "application/zip":
                results.record_fail(
                    "REGRESSION: GET /download",
                    f"Content-Type={content_type} (expected 'application/zip')"
                )
                return None
            
            # Verify Content-Length exists and matches actual bytes
            content_length = response.headers.get("content-length")
            if not content_length:
                results.record_fail(
                    "REGRESSION: GET /download",
                    "Missing Content-Length header"
                )
                return None
            
            content_length = int(content_length)
            actual_bytes = len(response.content)
            
            if content_length != actual_bytes:
                results.record_fail(
                    "REGRESSION: GET /download",
                    f"Content-Length={content_length} but received {actual_bytes} bytes"
                )
                return None
            
            results.record_pass(
                "REGRESSION: GET /download",
                f"HTTP 200, Content-Type=application/zip, Content-Length={content_length} matches actual bytes"
            )
            
            # Save to temp file for further tests
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.zip', delete=False) as f:
                f.write(response.content)
                temp_path = f.name
            
            return temp_path
    
    except Exception as e:
        results.record_fail(
            "REGRESSION: GET /download",
            f"Exception: {str(e)}"
        )
        return None


def test_regression_zip_integrity(zip_path: str, pairing_code: str):
    """REGRESSION: ZIP integrity and payload/ layout."""
    step("REGRESSION: Testing ZIP integrity and layout")
    
    try:
        # Test ZIP integrity with unzip -t
        result = subprocess.run(
            ["unzip", "-t", zip_path],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            results.record_fail(
                "REGRESSION: ZIP integrity",
                f"unzip -t failed with code {result.returncode}: {result.stderr}"
            )
            return None
        
        if "No errors detected" not in result.stdout:
            results.record_fail(
                "REGRESSION: ZIP integrity",
                f"unzip -t didn't report 'No errors detected'"
            )
            return None
        
        results.record_pass(
            "REGRESSION: ZIP integrity",
            "ZIP is clean (unzip -t passed)"
        )
        
        # Verify ZIP layout: install.cmd + README.txt + bundle.json at root, 3 EXEs under payload/
        with zipfile.ZipFile(zip_path, 'r') as zf:
            entries = zf.namelist()
            
            # Check root files
            root_files = ["install.cmd", "README.txt", "bundle.json"]
            for f in root_files:
                if f not in entries:
                    results.record_fail(
                        "REGRESSION: ZIP layout",
                        f"Missing root file: {f}"
                    )
                    return None
            
            # Check payload/ files
            payload_files = [
                f"payload/DigitalTwinAgentSetup_{pairing_code}.exe",
                "payload/agent.exe",
                "payload/uninstaller.exe"
            ]
            for f in payload_files:
                if f not in entries:
                    results.record_fail(
                        "REGRESSION: ZIP layout",
                        f"Missing payload file: {f}"
                    )
                    return None
            
            results.record_pass(
                "REGRESSION: ZIP layout",
                "install.cmd + README.txt + bundle.json at root, 3 EXEs under payload/"
            )
            
            # Extract install.cmd for further tests
            install_cmd_content = zf.read("install.cmd").decode("utf-8")
            
            return install_cmd_content
    
    except Exception as e:
        results.record_fail(
            "REGRESSION: ZIP integrity",
            f"Exception: {str(e)}"
        )
        return None
    finally:
        # Clean up temp file
        try:
            os.unlink(zip_path)
        except Exception:
            pass


def test_new_pair_response_includes_device_api_key(pairing_code: str):
    """NEW: POST /api/agent/pair response includes device_api_key field."""
    step("NEW: Testing POST /api/agent/pair includes device_api_key")
    
    try:
        with httpx.Client(timeout=30.0) as client:
            # Prepare payload
            payload = {
                "pairing_code": pairing_code,
                "hostname": "TEST-MACHINE",
                "machine_guid": "test-guid-12345",
                "os_name": "Windows 11 Pro",
                "os_version": "10.0.22631",
                "agent_version": "2.1.0",
                "installer_version": "2.1.0",
                "ip_address": "192.168.1.100",
                "mac_address": "00:11:22:33:44:55",
                "hardware_fingerprint": "test-guid-12345"
            }
            
            response = client.post(
                f"{BASE_URL}/agent/pair",
                json=payload
            )
            
            if response.status_code != 200:
                results.record_fail(
                    "NEW: POST /agent/pair",
                    f"Expected 200, got {response.status_code}: {response.text}"
                )
                return None
            
            data = response.json()
            
            # Verify device_api_key field exists
            if "device_api_key" not in data:
                results.record_fail(
                    "NEW: POST /agent/pair",
                    "Missing device_api_key field in response"
                )
                return None
            
            device_api_key = data.get("device_api_key", "")
            
            # Verify device_api_key is non-empty and starts with 'dtk_'
            if not device_api_key:
                results.record_fail(
                    "NEW: POST /agent/pair",
                    "device_api_key is empty"
                )
                return None
            
            if not device_api_key.startswith("dtk_"):
                results.record_fail(
                    "NEW: POST /agent/pair",
                    f"device_api_key doesn't start with 'dtk_': {device_api_key[:20]}..."
                )
                return None
            
            # Verify all previously-returned fields are still present
            required_fields = [
                "device_id", "access_token", "refresh_token", "org_id",
                "ws_url", "api_url", "heartbeat_interval_sec",
                "telemetry_interval_sec", "policy"
            ]
            
            missing = [f for f in required_fields if f not in data]
            if missing:
                results.record_fail(
                    "NEW: POST /agent/pair",
                    f"Missing previously-returned fields: {missing}"
                )
                return None
            
            results.record_pass(
                "NEW: POST /agent/pair",
                f"device_api_key present (starts with 'dtk_'), all previous fields intact"
            )
            
            return data
    
    except Exception as e:
        results.record_fail(
            "NEW: POST /agent/pair",
            f"Exception: {str(e)}"
        )
        return None


def test_new_device_status_endpoint(device_id: str):
    """NEW: GET /api/agent/device/{device_id}/status (public, no auth)."""
    step(f"NEW: Testing GET /api/agent/device/{device_id}/status")
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                f"{BASE_URL}/agent/device/{device_id}/status"
            )
            
            if response.status_code != 200:
                results.record_fail(
                    "NEW: GET /device/{id}/status",
                    f"Expected 200, got {response.status_code}: {response.text}"
                )
                return None
            
            data = response.json()
            
            # Verify required fields
            required_fields = [
                "id", "hostname", "display_name", "online",
                "last_seen", "agent_version", "enrolled_at", "status"
            ]
            
            missing = [f for f in required_fields if f not in data]
            if missing:
                results.record_fail(
                    "NEW: GET /device/{id}/status",
                    f"Missing fields: {missing}"
                )
                return None
            
            # Verify online is false (immediately after pairing, before telemetry)
            if data.get("online") != False:
                results.record_fail(
                    "NEW: GET /device/{id}/status",
                    f"online={data.get('online')} (expected false immediately after pairing)"
                )
                return None
            
            # Verify status is 'offline'
            if data.get("status") != "offline":
                results.record_fail(
                    "NEW: GET /device/{id}/status",
                    f"status={data.get('status')} (expected 'offline')"
                )
                return None
            
            results.record_pass(
                "NEW: GET /device/{id}/status",
                f"HTTP 200 (public, no auth), online=false, status='offline'"
            )
            
            return data
    
    except Exception as e:
        results.record_fail(
            "NEW: GET /device/{id}/status",
            f"Exception: {str(e)}"
        )
        return None


def test_new_device_status_unknown_id():
    """NEW: GET /api/agent/device/UNKNOWN_ID/status returns 404."""
    step("NEW: Testing GET /api/agent/device/UNKNOWN_ID/status")
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                f"{BASE_URL}/agent/device/UNKNOWN_ID_12345/status"
            )
            
            if response.status_code != 404:
                results.record_fail(
                    "NEW: GET /device/UNKNOWN_ID/status",
                    f"Expected 404, got {response.status_code}"
                )
                return False
            
            data = response.json()
            detail = data.get("detail", "")
            
            if "Device not paired yet" not in detail:
                results.record_fail(
                    "NEW: GET /device/UNKNOWN_ID/status",
                    f"Expected detail='Device not paired yet', got '{detail}'"
                )
                return False
            
            results.record_pass(
                "NEW: GET /device/UNKNOWN_ID/status",
                "HTTP 404 with detail='Device not paired yet'"
            )
            
            return True
    
    except Exception as e:
        results.record_fail(
            "NEW: GET /device/UNKNOWN_ID/status",
            f"Exception: {str(e)}"
        )
        return False


def test_install_cmd_dpapi_section(install_cmd_content: str):
    """NEW: install.cmd contains DPAPI CREDENTIAL BOOTSTRAP section."""
    step("NEW: Testing install.cmd DPAPI CREDENTIAL BOOTSTRAP section")
    
    try:
        # Check for section header
        if "DPAPI CREDENTIAL BOOTSTRAP" not in install_cmd_content:
            results.record_fail(
                "NEW: install.cmd DPAPI section",
                "Missing 'DPAPI CREDENTIAL BOOTSTRAP' section header"
            )
            return False
        
        results.record_pass(
            "NEW: install.cmd DPAPI section",
            "Contains 'DPAPI CREDENTIAL BOOTSTRAP' section header"
        )
        
        return True
    
    except Exception as e:
        results.record_fail(
            "NEW: install.cmd DPAPI section",
            f"Exception: {str(e)}"
        )
        return False


def test_install_cmd_powershell_bridge(install_cmd_content: str):
    """NEW: install.cmd writes PowerShell script to %TEMP%."""
    step("NEW: Testing install.cmd PowerShell bridge")
    
    try:
        # Check for __PS_BRIDGE variable
        if "__PS_BRIDGE" not in install_cmd_content:
            results.record_fail(
                "NEW: install.cmd PS bridge",
                "Missing __PS_BRIDGE variable"
            )
            return False
        
        # Check for echo statements building .ps1 file
        if "echo" not in install_cmd_content or ".ps1" not in install_cmd_content:
            results.record_fail(
                "NEW: install.cmd PS bridge",
                "Missing echo statements or .ps1 file reference"
            )
            return False
        
        # Check for DT_BACKEND_URL and DT_PAIR_CODE environment variables
        if "DT_BACKEND_URL" not in install_cmd_content:
            results.record_fail(
                "NEW: install.cmd PS bridge",
                "Missing DT_BACKEND_URL environment variable"
            )
            return False
        
        if "DT_PAIR_CODE" not in install_cmd_content:
            results.record_fail(
                "NEW: install.cmd PS bridge",
                "Missing DT_PAIR_CODE environment variable"
            )
            return False
        
        results.record_pass(
            "NEW: install.cmd PS bridge",
            "Writes PowerShell script to %TEMP% with DT_BACKEND_URL and DT_PAIR_CODE"
        )
        
        return True
    
    except Exception as e:
        results.record_fail(
            "NEW: install.cmd PS bridge",
            f"Exception: {str(e)}"
        )
        return False


def test_install_cmd_pair_endpoint(install_cmd_content: str):
    """NEW: PowerShell bridge POSTs to /api/agent/pair."""
    step("NEW: Testing PowerShell bridge POSTs to /api/agent/pair")
    
    try:
        # Check for /api/agent/pair substring
        if "/api/agent/pair" not in install_cmd_content:
            results.record_fail(
                "NEW: install.cmd pair endpoint",
                "Missing '/api/agent/pair' substring"
            )
            return False
        
        # Check for device_api_key read from response
        if "device_api_key" not in install_cmd_content:
            results.record_fail(
                "NEW: install.cmd pair endpoint",
                "Missing 'device_api_key' read from response"
            )
            return False
        
        results.record_pass(
            "NEW: install.cmd pair endpoint",
            "PowerShell bridge POSTs to /api/agent/pair and reads device_api_key"
        )
        
        return True
    
    except Exception as e:
        results.record_fail(
            "NEW: install.cmd pair endpoint",
            f"Exception: {str(e)}"
        )
        return False


def test_install_cmd_credwrite(install_cmd_content: str):
    """NEW: PowerShell bridge has Add-Type with CredWriteW DllImport."""
    step("NEW: Testing PowerShell bridge CredWriteW DllImport")
    
    try:
        # Check for CredWriteW
        if "CredWriteW" not in install_cmd_content:
            results.record_fail(
                "NEW: install.cmd CredWriteW",
                "Missing 'CredWriteW' DllImport"
            )
            return False
        
        # Check for advapi32.dll
        if "advapi32.dll" not in install_cmd_content:
            results.record_fail(
                "NEW: install.cmd CredWriteW",
                "Missing 'advapi32.dll' reference"
            )
            return False
        
        # Check for Add-Type
        if "Add-Type" not in install_cmd_content:
            results.record_fail(
                "NEW: install.cmd CredWriteW",
                "Missing 'Add-Type' declaration"
            )
            return False
        
        results.record_pass(
            "NEW: install.cmd CredWriteW",
            "Add-Type block with CredWriteW DllImport in advapi32.dll"
        )
        
        return True
    
    except Exception as e:
        results.record_fail(
            "NEW: install.cmd CredWriteW",
            f"Exception: {str(e)}"
        )
        return False


def test_install_cmd_target_name(install_cmd_content: str):
    """NEW: PowerShell bridge target name is 'DigitalTwin/AgentCredentials'."""
    step("NEW: Testing PowerShell bridge target name")
    
    try:
        # Check for target name
        if "DigitalTwin/AgentCredentials" not in install_cmd_content:
            results.record_fail(
                "NEW: install.cmd target name",
                "Missing 'DigitalTwin/AgentCredentials' target name"
            )
            return False
        
        # Check for UserName
        if "digitaltwin-agent" not in install_cmd_content:
            results.record_fail(
                "NEW: install.cmd target name",
                "Missing 'digitaltwin-agent' UserName"
            )
            return False
        
        # Check for Persist=2 (LocalMachine)
        if "Persist = 2" not in install_cmd_content and "$c.Persist = 2" not in install_cmd_content:
            results.record_fail(
                "NEW: install.cmd target name",
                "Missing 'Persist = 2' (LocalMachine)"
            )
            return False
        
        results.record_pass(
            "NEW: install.cmd target name",
            "target='DigitalTwin/AgentCredentials', UserName='digitaltwin-agent', Persist=2"
        )
        
        return True
    
    except Exception as e:
        results.record_fail(
            "NEW: install.cmd target name",
            f"Exception: {str(e)}"
        )
        return False


def test_install_cmd_no_pair_flag(install_cmd_content: str):
    """NEW: install.cmd invokes installer with --no-pair and --silent."""
    step("NEW: Testing install.cmd --no-pair and --silent flags")
    
    try:
        # Check for --no-pair flag
        if "--no-pair" not in install_cmd_content:
            results.record_fail(
                "NEW: install.cmd flags",
                "Missing '--no-pair' flag"
            )
            return False
        
        # Check for --silent flag
        if "--silent" not in install_cmd_content:
            results.record_fail(
                "NEW: install.cmd flags",
                "Missing '--silent' flag"
            )
            return False
        
        # Verify both flags appear in the same call line
        lines = install_cmd_content.split("\n")
        found_both = False
        for line in lines:
            if "--no-pair" in line and "--silent" in line:
                found_both = True
                break
        
        if not found_both:
            results.record_fail(
                "NEW: install.cmd flags",
                "--no-pair and --silent not in the same call line"
            )
            return False
        
        results.record_pass(
            "NEW: install.cmd flags",
            "Invokes installer with --no-pair and --silent in the same call"
        )
        
        return True
    
    except Exception as e:
        results.record_fail(
            "NEW: install.cmd flags",
            f"Exception: {str(e)}"
        )
        return False


def test_install_cmd_fallback_branch(install_cmd_content: str):
    """NEW: install.cmd has fallback branch if PS bridge fails."""
    step("NEW: Testing install.cmd fallback branch")
    
    try:
        # Check for BRIDGE_RC check
        if "BRIDGE_RC" not in install_cmd_content:
            results.record_fail(
                "NEW: install.cmd fallback",
                "Missing 'BRIDGE_RC' variable"
            )
            return False
        
        # Check for "if BRIDGE_RC equ 0" or "if BRIDGE_RC neq 0" pattern
        has_bridge_check = (
            "if %BRIDGE_RC% equ 0" in install_cmd_content or
            "if %BRIDGE_RC% neq 0" in install_cmd_content
        )
        
        if not has_bridge_check:
            results.record_fail(
                "NEW: install.cmd fallback",
                "Missing 'if BRIDGE_RC' conditional check"
            )
            return False
        
        # Verify fallback runs installer WITHOUT --no-pair
        # The pattern is: if BRIDGE_RC equ 0 (success path with --no-pair) else (fallback without --no-pair)
        lines = install_cmd_content.split("\n")
        found_success_with_no_pair = False
        found_fallback_without_no_pair = False
        
        for i, line in enumerate(lines):
            # Look for the success branch (with --no-pair)
            if "if %BRIDGE_RC% equ 0" in line:
                # Check next few lines for call with --no-pair
                for j in range(i+1, min(i+5, len(lines))):
                    if "call" in lines[j] and ".exe" in lines[j] and "--no-pair" in lines[j]:
                        found_success_with_no_pair = True
                        break
            
            # Look for the else branch (fallback without --no-pair)
            if ") else (" in line:
                # Check next few lines for call WITHOUT --no-pair
                for j in range(i+1, min(i+5, len(lines))):
                    if "call" in lines[j] and ".exe" in lines[j]:
                        if "--no-pair" not in lines[j]:
                            found_fallback_without_no_pair = True
                        break
        
        if not found_success_with_no_pair:
            results.record_fail(
                "NEW: install.cmd fallback",
                "Success branch doesn't have call with --no-pair"
            )
            return False
        
        if not found_fallback_without_no_pair:
            results.record_fail(
                "NEW: install.cmd fallback",
                "Fallback branch doesn't run installer without --no-pair"
            )
            return False
        
        results.record_pass(
            "NEW: install.cmd fallback",
            "Has fallback branch that runs installer without --no-pair if PS bridge fails"
        )
        
        return True
    
    except Exception as e:
        results.record_fail(
            "NEW: install.cmd fallback",
            f"Exception: {str(e)}"
        )
        return False


def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("DPAPI CREDENTIAL BOOTSTRAP FIX - BACKEND TESTS")
    print("Testing device_api_key in pair response + device status endpoint")
    print("="*70)
    
    # Step 1: Login
    token = login()
    if not token:
        print("\n❌ CRITICAL: Login failed. Cannot proceed with tests.")
        results.print_summary()
        return 1
    
    # Step 2: REGRESSION - Test /download-init
    init_data = test_regression_download_init(token)
    if not init_data:
        print("\n❌ CRITICAL: /download-init failed. Cannot proceed.")
        results.print_summary()
        return 1
    
    download_token = init_data.get("download_token")
    pairing_code = init_data.get("pairing_code")
    
    # Step 3: REGRESSION - Test /download
    zip_path = test_regression_download(download_token, pairing_code)
    if not zip_path:
        print("\n❌ CRITICAL: /download failed. Cannot proceed.")
        results.print_summary()
        return 1
    
    # Step 4: REGRESSION - Test ZIP integrity and extract install.cmd
    install_cmd_content = test_regression_zip_integrity(zip_path, pairing_code)
    if not install_cmd_content:
        print("\n❌ CRITICAL: ZIP integrity check failed. Cannot proceed.")
        results.print_summary()
        return 1
    
    # Step 5: NEW - Test POST /api/agent/pair includes device_api_key
    pair_data = test_new_pair_response_includes_device_api_key(pairing_code)
    if not pair_data:
        print("\n❌ CRITICAL: /agent/pair failed. Cannot proceed.")
        results.print_summary()
        return 1
    
    device_id = pair_data.get("device_id")
    
    # Step 6: NEW - Test GET /api/agent/device/{device_id}/status
    test_new_device_status_endpoint(device_id)
    
    # Step 7: NEW - Test GET /api/agent/device/UNKNOWN_ID/status returns 404
    test_new_device_status_unknown_id()
    
    # Step 8-14: NEW - Test install.cmd content
    test_install_cmd_dpapi_section(install_cmd_content)
    test_install_cmd_powershell_bridge(install_cmd_content)
    test_install_cmd_pair_endpoint(install_cmd_content)
    test_install_cmd_credwrite(install_cmd_content)
    test_install_cmd_target_name(install_cmd_content)
    test_install_cmd_no_pair_flag(install_cmd_content)
    test_install_cmd_fallback_branch(install_cmd_content)
    
    # Print summary
    success = results.print_summary()
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
