"""
Backend API testing for Agent Installer - Prep Phase Refactor Fix.

Tests the fix for the Windows install.cmd hang issue where the prep phase
was refactored to eliminate all sources of silent stall by:
  1. Rewriting prep section as 5 linear numbered steps with echo before/after
  2. Removing problematic code: parenthesized cleanup blocks, taskkill on
     PythonService.exe, takeown/icacls/attrib tree walk, 16-second retry loop,
     for %%P taskkill loop, sc query guards
  3. Adding explicit numbered step echoes and "done." markers

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
        print(f"AGENT INSTALLER PREP REFACTOR TESTS - SUMMARY")
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
            
            pairing_code = data.get("pairing_code", "")
            if not re.match(r"^DT-[A-Z0-9]{4}-[A-Z0-9]{4}$", pairing_code):
                results.record_fail(
                    "POST /download-init",
                    f"Invalid pairing_code format: {pairing_code}"
                )
                return None
            
            download_token = data.get("download_token", "")
            if not download_token:
                results.record_fail(
                    "POST /download-init",
                    "Missing download_token"
                )
                return None
            
            results.record_pass(
                "POST /download-init",
                f"pairing_code={pairing_code}, download_token received"
            )
            return data
    
    except Exception as e:
        results.record_fail("POST /download-init", f"Exception: {str(e)}")
        return None


def test_download(download_token: str, pairing_code: str):
    """Test GET /api/agent/installer/download and extract install.cmd."""
    step("Testing GET /api/agent/installer/download")
    
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
            
            content_type = response.headers.get("content-type", "")
            if content_type != "application/zip":
                results.record_fail(
                    "GET /download",
                    f"Content-Type={content_type} (expected 'application/zip')"
                )
                return None
            
            results.record_pass(
                "GET /download",
                f"HTTP 200 application/zip received"
            )
            
            # Save to temp file and extract install.cmd
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.zip', delete=False) as f:
                f.write(response.content)
                temp_path = f.name
            
            try:
                with zipfile.ZipFile(temp_path, 'r') as zf:
                    if "install.cmd" not in zf.namelist():
                        results.record_fail(
                            "ZIP contents",
                            "install.cmd not found in ZIP"
                        )
                        return None
                    
                    install_cmd_content = zf.read("install.cmd").decode("utf-8")
                    results.record_pass(
                        "ZIP contents",
                        f"install.cmd extracted ({len(install_cmd_content)} bytes)"
                    )
                    return install_cmd_content, pairing_code
            finally:
                os.unlink(temp_path)
    
    except Exception as e:
        results.record_fail("GET /download", f"Exception: {str(e)}")
        return None


def filter_rem_lines(content: str) -> str:
    """Filter out REM comment lines from install.cmd.
    
    Returns only LIVE (non-REM) code lines.
    """
    lines = content.split('\n')
    live_lines = []
    
    for line in lines:
        stripped = line.lstrip()
        # Skip empty lines and REM comments
        if not stripped or stripped.upper().startswith('REM '):
            continue
        live_lines.append(line)
    
    return '\n'.join(live_lines)


def test_install_cmd_numbered_steps(install_cmd: str):
    """Test that install.cmd contains all 5 numbered step echoes."""
    step("Testing install.cmd numbered step echoes")
    
    required_echoes = [
        "[1/5] Stopping any existing DigitalTwinAgent Windows service ...",
        "[2/5] Terminating any leftover agent executables ...",
        "[3/5] Cleaning previous install directory (if any) ...",
        "[4/5] Preparing install directory %INSTALL_ROOT% ...",
        "[5/5] Launching installer against %BACKEND_URL% ...",
    ]
    
    for echo_text in required_echoes:
        if echo_text not in install_cmd:
            results.record_fail(
                f"Numbered step echo: {echo_text[:50]}...",
                f"Not found in install.cmd"
            )
        else:
            results.record_pass(
                f"Numbered step echo: {echo_text[:50]}...",
                "Found"
            )


def test_install_cmd_done_markers(install_cmd: str):
    """Test that install.cmd contains at least 4 'done.' markers."""
    step("Testing install.cmd 'done.' markers")
    
    # Count occurrences of "echo       done."
    done_count = install_cmd.count("echo       done.")
    
    if done_count >= 4:
        results.record_pass(
            "Done markers",
            f"Found {done_count} 'echo       done.' markers (expected >=4)"
        )
    else:
        results.record_fail(
            "Done markers",
            f"Found only {done_count} 'echo       done.' markers (expected >=4)"
        )


def test_install_cmd_removed_features(install_cmd: str):
    """Test that removed features are NOT in LIVE code (can be in REM comments)."""
    step("Testing that removed features are NOT in LIVE code")
    
    # Filter out REM lines to get only LIVE code
    live_code = filter_rem_lines(install_cmd)
    
    # List of removed features that should NOT appear in LIVE code
    removed_features = [
        ("taskkill /F /IM PythonService", "taskkill on PythonService.exe"),
        ("takeown ", "takeown command"),
        ("/reset", "icacls /reset"),
        ("attrib -R", "attrib -R command"),
        ("for %%P in", "for %%P in loop"),
        ("for /L %%i in", "for /L retry loop"),
        ("retry %%i/8", "retry loop counter"),
    ]
    
    for feature_str, feature_name in removed_features:
        if feature_str in live_code:
            results.record_fail(
                f"Removed feature: {feature_name}",
                f"Found '{feature_str}' in LIVE code (should only be in REM comments)"
            )
        else:
            results.record_pass(
                f"Removed feature: {feature_name}",
                f"NOT found in LIVE code (correctly removed)"
            )


def test_install_cmd_explicit_taskkill(install_cmd: str):
    """Test that install.cmd contains 3 explicit taskkill lines."""
    step("Testing install.cmd explicit taskkill lines")
    
    live_code = filter_rem_lines(install_cmd)
    
    required_taskkills = [
        "taskkill /F /IM agent.exe",
        "taskkill /F /IM DigitalTwinAgent.exe",
        "taskkill /F /IM uninstaller.exe",
    ]
    
    for taskkill_line in required_taskkills:
        if taskkill_line in live_code:
            results.record_pass(
                f"Explicit taskkill: {taskkill_line}",
                "Found"
            )
        else:
            results.record_fail(
                f"Explicit taskkill: {taskkill_line}",
                "Not found in LIVE code"
            )


def test_install_cmd_regression_checks(install_cmd: str, pairing_code: str):
    """Test regression checks: UAC elevation, DPAPI, fsutil, etc."""
    step("Testing install.cmd regression checks")
    
    # Check 1: PowerShell UAC self-elevation
    if "Start-Process -Verb RunAs" in install_cmd:
        results.record_pass(
            "PowerShell UAC elevation",
            "Found 'Start-Process -Verb RunAs'"
        )
    else:
        results.record_fail(
            "PowerShell UAC elevation",
            "Missing 'Start-Process -Verb RunAs'"
        )
    
    # Check 2: DPAPI CredWriteW P/Invoke
    if "CredWriteW" in install_cmd:
        results.record_pass(
            "DPAPI CredWriteW P/Invoke",
            "Found 'CredWriteW'"
        )
    else:
        results.record_fail(
            "DPAPI CredWriteW P/Invoke",
            "Missing 'CredWriteW'"
        )
    
    # Check 3: fsutil dirty query probe
    if "fsutil dirty query" in install_cmd:
        results.record_pass(
            "fsutil dirty query probe",
            "Found 'fsutil dirty query'"
        )
    else:
        results.record_fail(
            "fsutil dirty query probe",
            "Missing 'fsutil dirty query'"
        )
    
    # Check 4: BACKEND_URL
    if 'set "BACKEND_URL=https://safe-import-pro.preview.emergentagent.com"' in install_cmd:
        results.record_pass(
            "BACKEND_URL",
            "Found correct BACKEND_URL"
        )
    else:
        results.record_fail(
            "BACKEND_URL",
            "Missing or incorrect BACKEND_URL"
        )
    
    # Check 5: Pairing code
    if f'set "__PAIRING_CODE={pairing_code}"' in install_cmd:
        results.record_pass(
            "Pairing code",
            f"Found correct pairing code: {pairing_code}"
        )
    else:
        results.record_fail(
            "Pairing code",
            f"Missing or incorrect pairing code (expected {pairing_code})"
        )
    
    # Check 6: Final installer invocation with --no-pair --silent
    if '--no-pair --silent' in install_cmd:
        results.record_pass(
            "Final installer invocation",
            "Found '--no-pair --silent'"
        )
    else:
        results.record_fail(
            "Final installer invocation",
            "Missing '--no-pair --silent'"
        )


def test_install_cmd_structure(install_cmd: str):
    """Test install.cmd structure: balanced parens/quotes, size."""
    step("Testing install.cmd structure")
    
    # Check 1: Balanced parentheses
    open_parens = install_cmd.count('(')
    close_parens = install_cmd.count(')')
    
    if open_parens == close_parens:
        results.record_pass(
            "Balanced parentheses",
            f"{open_parens} open, {close_parens} close"
        )
    else:
        results.record_fail(
            "Balanced parentheses",
            f"{open_parens} open, {close_parens} close (UNBALANCED)"
        )
    
    # Check 2: Balanced double-quotes (rough check)
    # Count quotes not preceded by backslash
    quote_count = len(re.findall(r'(?<!\\)"', install_cmd))
    
    if quote_count % 2 == 0:
        results.record_pass(
            "Balanced double-quotes",
            f"{quote_count} quotes (even number)"
        )
    else:
        results.record_fail(
            "Balanced double-quotes",
            f"{quote_count} quotes (ODD number - UNBALANCED)"
        )
    
    # Check 3: File size under 20KB
    size_bytes = len(install_cmd.encode('utf-8'))
    size_kb = size_bytes / 1024
    
    if size_kb < 20:
        results.record_pass(
            "File size",
            f"{size_kb:.1f} KB (under 20KB limit)"
        )
    else:
        results.record_fail(
            "File size",
            f"{size_kb:.1f} KB (exceeds 20KB limit)"
        )


def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("AGENT INSTALLER PREP REFACTOR - BACKEND TESTS")
    print("Testing the fix for install.cmd hang issue")
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
    
    # Step 4: Test /download and extract install.cmd
    download_result = test_download(download_token, pairing_code)
    if not download_result:
        print("\n❌ CRITICAL: /download failed. Cannot proceed with install.cmd tests.")
        results.print_summary()
        return 1
    
    install_cmd, pairing_code = download_result
    
    # Step 5: Test install.cmd content
    test_install_cmd_numbered_steps(install_cmd)
    test_install_cmd_done_markers(install_cmd)
    test_install_cmd_removed_features(install_cmd)
    test_install_cmd_explicit_taskkill(install_cmd)
    test_install_cmd_regression_checks(install_cmd, pairing_code)
    test_install_cmd_structure(install_cmd)
    
    # Print summary
    success = results.print_summary()
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
