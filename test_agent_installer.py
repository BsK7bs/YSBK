"""Test agent installer endpoints and install.cmd generation.

This test verifies the fix for the install.cmd freeze issue:
- Progress echo markers are present
- taskkill /T flag is removed
- icacls split into recursive/non-recursive branches
- No VBS-related code (regression check)
"""
import io
import json
import re
import sys
import zipfile
from typing import Dict, List, Tuple

import httpx

# Public endpoint from frontend/.env
BASE_URL = "https://safe-import-pro.preview.emergentagent.com"
API_BASE = f"{BASE_URL}/api"

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
        self.errors.append({"test": test_name, "error": error})
        print(f"  ✗ {test_name}")
        print(f"    Error: {error}")

    def print_summary(self):
        print(f"\n{'='*70}")
        print(f"Test Results: {self.passed}/{self.total} passed, {self.failed} failed")
        if self.failed > 0:
            print(f"\nFailed tests:")
            for err in self.errors:
                print(f"  - {err['test']}")
                print(f"    {err['error']}")
        print(f"{'='*70}\n")
        return self.failed == 0


results = TestResults()


def test_auth() -> str:
    """Test authentication and return access token."""
    print("\n▶ Testing authentication...")
    
    with httpx.Client(timeout=30) as client:
        try:
            resp = client.post(
                f"{API_BASE}/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
            )
            
            if resp.status_code != 200:
                results.record_fail(
                    "Auth login",
                    f"Expected 200, got {resp.status_code}: {resp.text}"
                )
                return None
            
            data = resp.json()
            if "access_token" not in data:
                results.record_fail("Auth login", "No access_token in response")
                return None
            
            results.record_pass("Auth login")
            return data["access_token"]
            
        except Exception as e:
            results.record_fail("Auth login", str(e))
            return None


def test_installer_info(token: str) -> bool:
    """Test GET /api/agent/installer/info."""
    print("\n▶ Testing GET /api/agent/installer/info...")
    
    with httpx.Client(timeout=30) as client:
        try:
            resp = client.get(
                f"{API_BASE}/agent/installer/info",
                headers={"Authorization": f"Bearer {token}"}
            )
            
            if resp.status_code != 200:
                results.record_fail(
                    "GET /api/agent/installer/info",
                    f"Expected 200, got {resp.status_code}: {resp.text}"
                )
                return False
            
            data = resp.json()
            
            # Check required fields
            if not data.get("available"):
                results.record_fail(
                    "installer/info available field",
                    f"available should be true, got {data.get('available')}"
                )
                return False
            
            if not data.get("bundle"):
                results.record_fail(
                    "installer/info bundle field",
                    f"bundle should be true, got {data.get('bundle')}"
                )
                return False
            
            # Check bundle_contents
            bundle_contents = data.get("bundle_contents", [])
            required_files = [
                "DigitalTwinAgentSetup.exe",
                "agent.exe",
                "uninstaller.exe"
            ]
            
            for required_file in required_files:
                if required_file not in bundle_contents:
                    results.record_fail(
                        f"installer/info bundle_contents",
                        f"Missing {required_file} in bundle_contents: {bundle_contents}"
                    )
                    return False
            
            results.record_pass("GET /api/agent/installer/info")
            results.record_pass("installer/info available=true")
            results.record_pass("installer/info bundle=true")
            results.record_pass("installer/info bundle_contents complete")
            return True
            
        except Exception as e:
            results.record_fail("GET /api/agent/installer/info", str(e))
            return False


def test_download_init(token: str) -> Tuple[str, str]:
    """Test POST /api/agent/installer/download-init.
    
    Returns: (pairing_code, download_token)
    """
    print("\n▶ Testing POST /api/agent/installer/download-init...")
    
    with httpx.Client(timeout=30) as client:
        try:
            resp = client.post(
                f"{API_BASE}/agent/installer/download-init",
                headers={"Authorization": f"Bearer {token}"}
            )
            
            if resp.status_code != 200:
                results.record_fail(
                    "POST /api/agent/installer/download-init",
                    f"Expected 200, got {resp.status_code}: {resp.text}"
                )
                return None, None
            
            data = resp.json()
            
            # Check pairing_code format (DT-XXXX-XXXX)
            pairing_code = data.get("pairing_code")
            if not pairing_code or not re.match(r"^DT-[A-Z0-9]{4}-[A-Z0-9]{4}$", pairing_code):
                results.record_fail(
                    "download-init pairing_code format",
                    f"Invalid pairing_code format: {pairing_code}"
                )
                return None, None
            
            # Check download_token
            download_token = data.get("download_token")
            if not download_token:
                results.record_fail(
                    "download-init download_token",
                    "Missing download_token in response"
                )
                return None, None
            
            # Check is_bundle
            if not data.get("is_bundle"):
                results.record_fail(
                    "download-init is_bundle",
                    f"is_bundle should be true, got {data.get('is_bundle')}"
                )
                return None, None
            
            results.record_pass("POST /api/agent/installer/download-init")
            results.record_pass("download-init pairing_code format")
            results.record_pass("download-init download_token present")
            results.record_pass("download-init is_bundle=true")
            
            return pairing_code, download_token
            
        except Exception as e:
            results.record_fail("POST /api/agent/installer/download-init", str(e))
            return None, None


def test_download_and_extract(token: str, download_token: str) -> bytes:
    """Test GET /api/agent/installer/download and return install.cmd content."""
    print("\n▶ Testing GET /api/agent/installer/download...")
    
    with httpx.Client(timeout=60) as client:
        try:
            resp = client.get(
                f"{API_BASE}/agent/installer/download",
                params={"token": download_token},
                headers={"Authorization": f"Bearer {token}"}
            )
            
            if resp.status_code != 200:
                results.record_fail(
                    "GET /api/agent/installer/download",
                    f"Expected 200, got {resp.status_code}"
                )
                return None
            
            # Check content type
            content_type = resp.headers.get("content-type", "")
            if "application/zip" not in content_type:
                results.record_fail(
                    "download content-type",
                    f"Expected application/zip, got {content_type}"
                )
                return None
            
            results.record_pass("GET /api/agent/installer/download")
            results.record_pass("download content-type=application/zip")
            
            # Extract install.cmd from ZIP
            try:
                zip_data = io.BytesIO(resp.content)
                with zipfile.ZipFile(zip_data, 'r') as zf:
                    # List files in ZIP
                    file_list = zf.namelist()
                    print(f"    ZIP contains {len(file_list)} files")
                    
                    # Find install.cmd
                    install_cmd_path = None
                    for name in file_list:
                        if name.endswith("install.cmd"):
                            install_cmd_path = name
                            break
                    
                    if not install_cmd_path:
                        results.record_fail(
                            "ZIP contains install.cmd",
                            f"install.cmd not found in ZIP. Files: {file_list}"
                        )
                        return None
                    
                    results.record_pass("ZIP contains install.cmd")
                    
                    # Extract install.cmd
                    install_cmd_bytes = zf.read(install_cmd_path)
                    print(f"    install.cmd size: {len(install_cmd_bytes)} bytes")
                    
                    return install_cmd_bytes
                    
            except zipfile.BadZipFile as e:
                results.record_fail("ZIP extraction", f"Invalid ZIP file: {e}")
                return None
            except Exception as e:
                results.record_fail("ZIP extraction", str(e))
                return None
            
        except Exception as e:
            results.record_fail("GET /api/agent/installer/download", str(e))
            return None


def verify_install_cmd(install_cmd_bytes: bytes, pairing_code: str):
    """Verify all required changes in install.cmd."""
    print("\n▶ Verifying install.cmd content...")
    
    try:
        # Decode as UTF-8
        install_cmd = install_cmd_bytes.decode("utf-8")
    except UnicodeDecodeError:
        results.record_fail("install.cmd encoding", "Failed to decode as UTF-8")
        return
    
    # 1. Check for NEW progress echoes
    required_echoes = [
        "[.] Stopping and unregistering existing DigitalTwinAgent service ...",
        "[.] Terminating any lingering agent processes ...",
        "[.] Ensuring install directory has write access ...",
        "[.] Existing install directory found - resetting permissions ...",
        "(this can take 10-30 seconds if the folder is large; please wait)"
    ]
    
    for echo_text in required_echoes:
        if echo_text in install_cmd:
            results.record_pass(f"Progress echo present: '{echo_text[:50]}...'")
        else:
            results.record_fail(
                f"Progress echo missing",
                f"Required echo not found: '{echo_text}'"
            )
    
    # 2. Check that taskkill does NOT contain /T flag
    # Look for taskkill lines
    taskkill_pattern = r'taskkill\s+/F\s+/IM\s+%%P\s+/T'
    if re.search(taskkill_pattern, install_cmd):
        results.record_fail(
            "taskkill /T flag removed",
            "Found 'taskkill /F /IM %%P /T' - the /T flag should be removed"
        )
    else:
        results.record_pass("taskkill /T flag removed")
    
    # 3. Check that taskkill still terminates all 4 process names
    required_processes = ["agent.exe", "uninstaller.exe", "DigitalTwinAgent.exe", "PythonService.exe"]
    taskkill_line_pattern = r'for\s+%%P\s+in\s+\(([^)]+)\)\s+do\s+.*taskkill'
    match = re.search(taskkill_line_pattern, install_cmd)
    
    if match:
        processes_in_cmd = match.group(1)
        all_present = all(proc in processes_in_cmd for proc in required_processes)
        if all_present:
            results.record_pass("taskkill terminates all 4 process names")
        else:
            results.record_fail(
                "taskkill process names",
                f"Not all required processes found. Expected: {required_processes}, Found: {processes_in_cmd}"
            )
    else:
        results.record_fail(
            "taskkill process names",
            "Could not find taskkill for loop pattern"
        )
    
    # 4. Check NO VBS-related strings (regression check)
    vbs_strings = ["CreateObject", "cscript", "ELEV_VBS", "WScript.Arguments", "dt-elevate"]
    found_vbs = []
    for vbs_str in vbs_strings:
        if vbs_str in install_cmd:
            found_vbs.append(vbs_str)
    
    if found_vbs:
        results.record_fail(
            "No VBS code (regression)",
            f"Found VBS-related strings: {found_vbs}"
        )
    else:
        results.record_pass("No VBS code (regression check)")
    
    # 5. Check PowerShell UAC self-elevation is present
    if "Start-Process -FilePath 'cmd.exe'" in install_cmd and "-Verb RunAs" in install_cmd:
        results.record_pass("PowerShell UAC self-elevation present")
    else:
        results.record_fail(
            "PowerShell UAC self-elevation",
            "PowerShell Start-Process -Verb RunAs not found"
        )
    
    # 6. Check split icacls block
    # Look for: if exist %INSTALL_ROOT%\agent.exe ( ... icacls ... /T ... ) else ( ... icacls ... no /T ... )
    icacls_if_pattern = r'if\s+exist\s+"%INSTALL_ROOT%\\agent\.exe".*?icacls.*?/T.*?/C.*?/Q'
    icacls_else_pattern = r'else\s+\(.*?icacls.*?/C.*?/Q.*?\)'
    
    has_recursive_icacls = bool(re.search(icacls_if_pattern, install_cmd, re.DOTALL))
    has_nonrecursive_icacls = bool(re.search(icacls_else_pattern, install_cmd, re.DOTALL))
    
    if has_recursive_icacls and has_nonrecursive_icacls:
        results.record_pass("Split icacls block (recursive vs non-recursive)")
    else:
        results.record_fail(
            "Split icacls block",
            f"Recursive: {has_recursive_icacls}, Non-recursive: {has_nonrecursive_icacls}"
        )
    
    # 7. Check required elements still present
    # Check fsutil
    if "fsutil dirty query" in install_cmd:
        results.record_pass("Required element present: 'fsutil dirty query'")
    else:
        results.record_fail("Required element missing", "fsutil dirty query not found")
    
    # Check BACKEND_URL (may have quotes)
    if f'BACKEND_URL={BASE_URL}' in install_cmd or f'BACKEND_URL="{BASE_URL}"' in install_cmd:
        results.record_pass(f"Required element present: 'BACKEND_URL={BASE_URL}'")
    else:
        results.record_fail("Required element missing", f"BACKEND_URL={BASE_URL} not found")
    
    # Check __PAIRING_CODE (may have quotes)
    if f'__PAIRING_CODE={pairing_code}' in install_cmd or f'__PAIRING_CODE="{pairing_code}"' in install_cmd:
        results.record_pass(f"Required element present: '__PAIRING_CODE={pairing_code}'")
    else:
        results.record_fail("Required element missing", f"__PAIRING_CODE={pairing_code} not found")
    
    # Check CredWriteW
    if "CredWriteW" in install_cmd:
        results.record_pass("Required element present: 'CredWriteW'")
    else:
        results.record_fail("Required element missing", "CredWriteW not found")
    
    # Check --no-pair --silent
    if "--no-pair --silent" in install_cmd:
        results.record_pass("Required element present: '--no-pair --silent'")
    else:
        results.record_fail("Required element missing", "--no-pair --silent not found")
    
    # 8. Check balanced parens and quotes (basic sanity)
    open_parens = install_cmd.count("(")
    close_parens = install_cmd.count(")")
    
    if open_parens == close_parens:
        results.record_pass("Balanced parentheses")
    else:
        results.record_fail(
            "Balanced parentheses",
            f"Open: {open_parens}, Close: {close_parens}"
        )
    
    # Count quotes (should be even)
    quote_count = install_cmd.count('"')
    if quote_count % 2 == 0:
        results.record_pass("Balanced double-quotes")
    else:
        results.record_fail(
            "Balanced double-quotes",
            f"Found {quote_count} double-quotes (should be even)"
        )


def main():
    print("="*70)
    print("Digital Twin Agent Installer Test Suite")
    print("Testing install.cmd freeze fix")
    print("="*70)
    
    # 1. Test auth
    token = test_auth()
    if not token:
        print("\n❌ Authentication failed. Cannot proceed with tests.")
        results.print_summary()
        return 1
    
    # 2. Test installer info
    if not test_installer_info(token):
        print("\n❌ Installer info endpoint failed. Cannot proceed.")
        results.print_summary()
        return 1
    
    # 3. Test download-init
    pairing_code, download_token = test_download_init(token)
    if not pairing_code or not download_token:
        print("\n❌ Download-init failed. Cannot proceed.")
        results.print_summary()
        return 1
    
    print(f"\n    Pairing code: {pairing_code}")
    print(f"    Download token: {download_token[:20]}...")
    
    # 4. Test download and extract
    install_cmd_bytes = test_download_and_extract(token, download_token)
    if not install_cmd_bytes:
        print("\n❌ Download/extraction failed. Cannot proceed.")
        results.print_summary()
        return 1
    
    # 5. Verify install.cmd content
    verify_install_cmd(install_cmd_bytes, pairing_code)
    
    # Print summary
    success = results.print_summary()
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
