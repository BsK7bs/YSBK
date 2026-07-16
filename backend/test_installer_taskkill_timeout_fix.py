"""
Backend API testing for Agent Installer - taskkill timeout fix.

Tests the fix for install.cmd hanging indefinitely on 'taskkill /F /IM agent.exe'
when the target process is stuck in STOP_PENDING or deadlock state.

Fix applied:
  - Replaced bare 'taskkill /F /IM ...' commands with backgrounded PowerShell
  - Added 5-second hard timeout via ping sleep
  - Step [2/5] now takes max ~5 seconds even in pathological cases

Test against: https://safe-import-pro.preview.emergentagent.com/api
"""
import json
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path

import httpx

# Public backend endpoint
BASE_URL = "https://safe-import-pro.preview.emergentagent.com/api"

# Test credentials
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
        print(f"INSTALLER TASKKILL TIMEOUT FIX - TEST SUMMARY")
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


def test_installer_info(token: str):
    """Test GET /api/agent/installer/info."""
    step("Testing GET /api/agent/installer/info")
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                f"{BASE_URL}/agent/installer/info",
                headers={"Authorization": f"Bearer {token}"}
            )
            
            if response.status_code != 200:
                results.record_fail(
                    "GET /info",
                    f"Expected 200, got {response.status_code}: {response.text}"
                )
                return False
            
            data = response.json()
            
            # Verify available and bundle
            if not data.get("available"):
                results.record_fail("GET /info", "available=false")
                return False
            
            if not data.get("bundle"):
                results.record_fail("GET /info", "bundle=false (expected true)")
                return False
            
            results.record_pass(
                "GET /info",
                f"available=true, bundle=true"
            )
            return True
    
    except Exception as e:
        results.record_fail("GET /info", f"Exception: {str(e)}")
        return False


def test_download_init(token: str):
    """Test POST /api/agent/installer/download-init."""
    step("Testing POST /api/agent/installer/download-init")
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{BASE_URL}/agent/installer/download-init",
                headers={"Authorization": f"Bearer {token}"}
            )
            
            if response.status_code != 200:
                results.record_fail(
                    "POST /download-init",
                    f"Expected 200, got {response.status_code}: {response.text}"
                )
                return None
            
            data = response.json()
            
            # Verify pairing code format: DT-XXXX-XXXX
            pairing_code = data.get("pairing_code", "")
            if not re.match(r"^DT-[A-Z0-9]{4}-[A-Z0-9]{4}$", pairing_code):
                results.record_fail(
                    "POST /download-init",
                    f"Invalid pairing_code format: {pairing_code}"
                )
                return None
            
            results.record_pass(
                "POST /download-init",
                f"Fresh pairing_code={pairing_code}"
            )
            return data
    
    except Exception as e:
        results.record_fail("POST /download-init", f"Exception: {str(e)}")
        return None


def test_download(download_token: str):
    """Test GET /api/agent/installer/download?token=<jwt>."""
    step("Testing GET /api/agent/installer/download?token=<jwt>")
    
    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.get(
                f"{BASE_URL}/agent/installer/download",
                params={"token": download_token}
            )
            
            if response.status_code != 200:
                results.record_fail(
                    "GET /download",
                    f"Expected 200, got {response.status_code}: {response.text}"
                )
                return None
            
            # Verify content type
            content_type = response.headers.get("content-type", "")
            if content_type != "application/zip":
                results.record_fail(
                    "GET /download",
                    f"Content-Type={content_type} (expected 'application/zip')"
                )
                return None
            
            results.record_pass(
                "GET /download",
                f"HTTP 200 application/zip"
            )
            
            # Save to temp file
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.zip', delete=False) as f:
                f.write(response.content)
                temp_path = f.name
            
            return temp_path
    
    except Exception as e:
        results.record_fail("GET /download", f"Exception: {str(e)}")
        return None


def strip_rem_lines(content: str) -> str:
    """Strip REM comment lines from install.cmd to get LIVE code only.
    
    REM lines are:
      - Lines starting with 'REM ' (case-insensitive)
      - Lines starting with whitespace + 'REM '
    
    We keep all other lines including blank lines.
    """
    lines = content.split('\n')
    live_lines = []
    
    for line in lines:
        stripped = line.lstrip()
        # Check if line starts with REM (case-insensitive)
        if stripped.upper().startswith('REM ') or stripped.upper() == 'REM':
            continue  # Skip REM lines
        live_lines.append(line)
    
    return '\n'.join(live_lines)


def test_install_cmd_content(zip_path: str, pairing_code: str):
    """Test install.cmd content for taskkill timeout fix."""
    step("Testing install.cmd content")
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            # Extract install.cmd
            install_cmd_content = zf.read("install.cmd").decode("utf-8")
            
            # Get LIVE code only (strip REM comments)
            live_code = strip_rem_lines(install_cmd_content)
            
            # TEST 1: LIVE code MUST NOT contain bare taskkill commands
            forbidden_patterns = [
                'taskkill /F /IM agent.exe',
                'taskkill /F /IM DigitalTwinAgent.exe',
                'taskkill /F /IM uninstaller.exe',
            ]
            
            for pattern in forbidden_patterns:
                if pattern in live_code:
                    results.record_fail(
                        "install.cmd LIVE code",
                        f"LIVE code contains forbidden pattern '{pattern}' (should be removed)"
                    )
                    return False
            
            results.record_pass(
                "install.cmd LIVE code - no bare taskkill",
                "LIVE code does NOT contain 'taskkill /F /IM agent.exe', "
                "'taskkill /F /IM DigitalTwinAgent.exe', or 'taskkill /F /IM uninstaller.exe'"
            )
            
            # TEST 2: LIVE code MUST contain the new PowerShell backgrounded process killer
            required_powershell = (
                'start /B /MIN "" powershell -NoProfile -WindowStyle Hidden -Command '
                '"$ErrorActionPreference=\'SilentlyContinue\'; '
                'foreach ($n in @(\'agent\',\'DigitalTwinAgent\',\'uninstaller\')) '
                '{ Get-Process -Name $n | Stop-Process -Force }" >nul 2>&1'
            )
            
            if required_powershell not in live_code:
                results.record_fail(
                    "install.cmd LIVE code - PowerShell process killer",
                    f"LIVE code does NOT contain the required PowerShell one-liner"
                )
                return False
            
            results.record_pass(
                "install.cmd LIVE code - PowerShell process killer",
                "LIVE code contains the exact PowerShell one-liner with start /B /MIN"
            )
            
            # TEST 3: LIVE code MUST contain the ping sleep timebox
            required_ping_sleep = '>nul ping -n 6 127.0.0.1'
            
            if required_ping_sleep not in live_code:
                results.record_fail(
                    "install.cmd LIVE code - ping sleep timebox",
                    f"LIVE code does NOT contain '{required_ping_sleep}'"
                )
                return False
            
            results.record_pass(
                "install.cmd LIVE code - ping sleep timebox",
                "LIVE code contains '>nul ping -n 6 127.0.0.1'"
            )
            
            # TEST 4: LIVE code MUST contain updated [2/5] echo message
            required_echo = 'echo [2/5] Terminating any leftover agent executables (max ~5 seconds) ...'
            
            if required_echo not in install_cmd_content:
                results.record_fail(
                    "install.cmd - [2/5] echo message",
                    f"Does NOT contain updated [2/5] echo message"
                )
                return False
            
            results.record_pass(
                "install.cmd - [2/5] echo message",
                "Contains 'echo [2/5] Terminating any leftover agent executables (max ~5 seconds) ...'"
            )
            
            # TEST 5: Verify all 5 numbered step echoes are present
            required_echoes = [
                '[1/5] Stopping any existing DigitalTwinAgent Windows service',
                '[2/5] Terminating any leftover agent executables (max ~5 seconds)',
                '[3/5] Cleaning previous install directory (if any)',
                '[4/5] Preparing install directory',
                '[5/5] Launching installer against %BACKEND_URL%',
            ]
            
            for echo in required_echoes:
                if echo not in install_cmd_content:
                    results.record_fail(
                        "install.cmd - numbered step echoes",
                        f"Missing echo: '{echo}'"
                    )
                    return False
            
            results.record_pass(
                "install.cmd - numbered step echoes",
                "All 5 numbered step echoes present"
            )
            
            # TEST 6: Verify PowerShell UAC self-elevation (regression)
            if 'Start-Process -Verb RunAs' not in install_cmd_content:
                results.record_fail(
                    "install.cmd - UAC elevation (regression)",
                    "Missing 'Start-Process -Verb RunAs'"
                )
                return False
            
            results.record_pass(
                "install.cmd - UAC elevation (regression)",
                "Contains PowerShell UAC self-elevation"
            )
            
            # TEST 7: Verify DPAPI CredWriteW P/Invoke (regression)
            if 'CredWriteW' not in install_cmd_content:
                results.record_fail(
                    "install.cmd - DPAPI (regression)",
                    "Missing 'CredWriteW' P/Invoke"
                )
                return False
            
            results.record_pass(
                "install.cmd - DPAPI (regression)",
                "Contains DPAPI CredWriteW P/Invoke"
            )
            
            # TEST 8: Verify fsutil dirty query (regression)
            if 'fsutil dirty query %SYSTEMDRIVE%' not in install_cmd_content:
                results.record_fail(
                    "install.cmd - fsutil probe (regression)",
                    "Missing 'fsutil dirty query %SYSTEMDRIVE%'"
                )
                return False
            
            results.record_pass(
                "install.cmd - fsutil probe (regression)",
                "Contains 'fsutil dirty query %SYSTEMDRIVE%'"
            )
            
            # TEST 9: Verify BACKEND_URL (regression)
            expected_backend_url = 'set "BACKEND_URL=https://safe-import-pro.preview.emergentagent.com"'
            if expected_backend_url not in install_cmd_content:
                results.record_fail(
                    "install.cmd - BACKEND_URL (regression)",
                    f"Missing or incorrect BACKEND_URL"
                )
                return False
            
            results.record_pass(
                "install.cmd - BACKEND_URL (regression)",
                "Contains correct BACKEND_URL"
            )
            
            # TEST 10: Verify pairing code (regression)
            expected_pairing = f'set "__PAIRING_CODE={pairing_code}"'
            if expected_pairing not in install_cmd_content:
                results.record_fail(
                    "install.cmd - pairing code (regression)",
                    f"Missing or incorrect pairing code"
                )
                return False
            
            results.record_pass(
                "install.cmd - pairing code (regression)",
                f"Contains correct pairing code {pairing_code}"
            )
            
            # TEST 11: Verify final installer invocation (regression)
            if '--api-url "%BACKEND_URL%" --no-pair --silent' not in install_cmd_content:
                results.record_fail(
                    "install.cmd - installer invocation (regression)",
                    "Missing '--api-url \"%BACKEND_URL%\" --no-pair --silent'"
                )
                return False
            
            results.record_pass(
                "install.cmd - installer invocation (regression)",
                "Contains final installer invocation with --no-pair --silent"
            )
            
            # TEST 12: Verify balanced parentheses (regression)
            open_parens = install_cmd_content.count('(')
            close_parens = install_cmd_content.count(')')
            
            if open_parens != close_parens:
                results.record_fail(
                    "install.cmd - balanced parens (regression)",
                    f"Unbalanced parentheses: {open_parens} open, {close_parens} close"
                )
                return False
            
            results.record_pass(
                "install.cmd - balanced parens (regression)",
                f"Balanced parentheses: {open_parens} open, {close_parens} close"
            )
            
            # TEST 13: Verify balanced double-quotes (regression)
            quote_count = install_cmd_content.count('"')
            
            if quote_count % 2 != 0:
                results.record_fail(
                    "install.cmd - balanced quotes (regression)",
                    f"Unbalanced double-quotes: {quote_count} quotes (odd number)"
                )
                return False
            
            results.record_pass(
                "install.cmd - balanced quotes (regression)",
                f"Balanced double-quotes: {quote_count} quotes (even number)"
            )
            
            # TEST 14: Verify file size < 20 KB (regression)
            install_cmd_size = len(install_cmd_content.encode('utf-8'))
            
            if install_cmd_size >= 20 * 1024:
                results.record_fail(
                    "install.cmd - file size (regression)",
                    f"File size {install_cmd_size/1024:.1f} KB >= 20 KB"
                )
                return False
            
            results.record_pass(
                "install.cmd - file size (regression)",
                f"File size {install_cmd_size/1024:.1f} KB < 20 KB"
            )
            
            return True
    
    except Exception as e:
        results.record_fail("install.cmd content", f"Exception: {str(e)}")
        return False
    finally:
        # Clean up temp file
        try:
            os.unlink(zip_path)
        except Exception:
            pass


def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("INSTALLER TASKKILL TIMEOUT FIX - BACKEND TESTS")
    print("Testing the fix for install.cmd hanging on taskkill")
    print("="*70)
    
    # Step 1: Login
    token = login()
    if not token:
        print("\n❌ CRITICAL: Login failed. Cannot proceed with tests.")
        results.print_summary()
        return 1
    
    # Step 2: Test /info endpoint
    if not test_installer_info(token):
        print("\n❌ CRITICAL: /info endpoint failed. Cannot proceed with tests.")
        results.print_summary()
        return 1
    
    # Step 3: Test /download-init
    init_data = test_download_init(token)
    if not init_data:
        print("\n❌ CRITICAL: /download-init failed. Cannot proceed with tests.")
        results.print_summary()
        return 1
    
    download_token = init_data.get("download_token")
    pairing_code = init_data.get("pairing_code")
    
    # Step 4: Test /download
    zip_path = test_download(download_token)
    if not zip_path:
        print("\n❌ CRITICAL: /download failed. Cannot proceed with tests.")
        results.print_summary()
        return 1
    
    # Step 5: Test install.cmd content
    test_install_cmd_content(zip_path, pairing_code)
    
    # Print summary
    success = results.print_summary()
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
