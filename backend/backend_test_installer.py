"""
Backend API testing for Agent Installer Download Flow.

Tests the fix for the "downloading half" bug where large ZIP bundles were
truncating during download. The fix materializes ZIPs to disk and serves
them via FileResponse with accurate Content-Length + HTTP Range support.

Test against: http://localhost:8001 (internal backend)
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path

import httpx
import jwt as pyjwt

# Internal backend endpoint
BASE_URL = "http://localhost:8001/api"

# Test credentials (seeded owner account)
ADMIN_EMAIL = "admin@digitaltwin.com"
ADMIN_PASSWORD = "ChangeMe!2026"

# Expected dist files
DIST_DIR = Path("/app/dist")
INSTALLER_EXE = DIST_DIR / "DigitalTwinAgentSetup.exe"
AGENT_EXE = DIST_DIR / "agent.exe"
UNINSTALLER_EXE = DIST_DIR / "uninstaller.exe"


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
        print(f"AGENT INSTALLER DOWNLOAD TESTS - SUMMARY")
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


def verify_dist_files():
    """Verify that all required dist files exist."""
    step("Verifying dist files exist")
    
    if not INSTALLER_EXE.exists():
        results.record_fail("Dist files check", f"Missing {INSTALLER_EXE}")
        return False
    
    if not AGENT_EXE.exists():
        results.record_fail("Dist files check", f"Missing {AGENT_EXE}")
        return False
    
    if not UNINSTALLER_EXE.exists():
        results.record_fail("Dist files check", f"Missing {UNINSTALLER_EXE}")
        return False
    
    installer_size = INSTALLER_EXE.stat().st_size
    agent_size = AGENT_EXE.stat().st_size
    uninstaller_size = UNINSTALLER_EXE.stat().st_size
    total_size = installer_size + agent_size + uninstaller_size
    
    results.record_pass(
        "Dist files check",
        f"All files present: installer={installer_size/1024/1024:.1f}MB, "
        f"agent={agent_size/1024/1024:.1f}MB, "
        f"uninstaller={uninstaller_size/1024/1024:.1f}MB, "
        f"total={total_size/1024/1024:.1f}MB"
    )
    return True


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
                return None
            
            data = response.json()
            
            # Verify required fields
            required_fields = [
                "available", "bundle", "filename", "bundle_contents",
                "download_extension", "bundle_size"
            ]
            
            missing = [f for f in required_fields if f not in data]
            if missing:
                results.record_fail("GET /info", f"Missing fields: {missing}")
                return None
            
            # Verify values
            if not data.get("available"):
                results.record_fail("GET /info", "available=false")
                return None
            
            if not data.get("bundle"):
                results.record_fail("GET /info", "bundle=false (expected true)")
                return None
            
            if data.get("filename") != "DigitalTwinAgentSetup.exe":
                results.record_fail(
                    "GET /info",
                    f"filename={data.get('filename')} (expected DigitalTwinAgentSetup.exe)"
                )
                return None
            
            expected_contents = ["DigitalTwinAgentSetup.exe", "agent.exe", "uninstaller.exe"]
            actual_contents = data.get("bundle_contents", [])
            if set(actual_contents) != set(expected_contents):
                results.record_fail(
                    "GET /info",
                    f"bundle_contents={actual_contents} (expected {expected_contents})"
                )
                return None
            
            if data.get("download_extension") != "zip":
                results.record_fail(
                    "GET /info",
                    f"download_extension={data.get('download_extension')} (expected 'zip')"
                )
                return None
            
            bundle_size = data.get("bundle_size", 0)
            if bundle_size < 200 * 1024 * 1024:  # 200 MB
                results.record_fail(
                    "GET /info",
                    f"bundle_size={bundle_size/1024/1024:.1f}MB (expected >200MB)"
                )
                return None
            
            results.record_pass(
                "GET /info",
                f"All checks passed: bundle_size={bundle_size/1024/1024:.1f}MB, "
                f"contents={len(actual_contents)} files"
            )
            return data
    
    except Exception as e:
        results.record_fail("GET /info", f"Exception: {str(e)}")
        return None


def test_download_init_with_auth(token: str):
    """Test POST /api/agent/installer/download-init with Bearer token."""
    step("Testing POST /api/agent/installer/download-init (with auth)")
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{BASE_URL}/agent/installer/download-init",
                headers={"Authorization": f"Bearer {token}"}
            )
            
            if response.status_code != 200:
                results.record_fail(
                    "POST /download-init (with auth)",
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
                    "POST /download-init (with auth)",
                    f"Missing fields: {missing}"
                )
                return None
            
            # Verify pairing code format: DT-XXXX-XXXX
            pairing_code = data.get("pairing_code", "")
            import re
            if not re.match(r"^DT-[A-Z0-9]{4}-[A-Z0-9]{4}$", pairing_code):
                results.record_fail(
                    "POST /download-init (with auth)",
                    f"Invalid pairing_code format: {pairing_code}"
                )
                return None
            
            # Verify filename ends with .zip
            filename = data.get("filename", "")
            if not filename.endswith(".zip"):
                results.record_fail(
                    "POST /download-init (with auth)",
                    f"filename doesn't end with .zip: {filename}"
                )
                return None
            
            # Verify is_bundle is true
            if not data.get("is_bundle"):
                results.record_fail(
                    "POST /download-init (with auth)",
                    "is_bundle=false (expected true)"
                )
                return None
            
            # Verify expires_in is 300 seconds
            if data.get("expires_in") != 300:
                results.record_fail(
                    "POST /download-init (with auth)",
                    f"expires_in={data.get('expires_in')} (expected 300)"
                )
                return None
            
            # Verify download_token is a valid JWT
            download_token = data.get("download_token", "")
            try:
                # Decode without verification to check structure
                decoded = pyjwt.decode(download_token, options={"verify_signature": False})
                if decoded.get("type") != "installer_download":
                    results.record_fail(
                        "POST /download-init (with auth)",
                        f"JWT type={decoded.get('type')} (expected 'installer_download')"
                    )
                    return None
            except Exception as e:
                results.record_fail(
                    "POST /download-init (with auth)",
                    f"Invalid JWT: {str(e)}"
                )
                return None
            
            results.record_pass(
                "POST /download-init (with auth)",
                f"pairing_code={pairing_code}, filename={filename}, expires_in=300s"
            )
            return data
    
    except Exception as e:
        results.record_fail(
            "POST /download-init (with auth)",
            f"Exception: {str(e)}"
        )
        return None


def test_download_init_without_auth():
    """Test POST /api/agent/installer/download-init without auth (should fail)."""
    step("Testing POST /api/agent/installer/download-init (without auth)")
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(f"{BASE_URL}/agent/installer/download-init")
            
            if response.status_code == 401:
                results.record_pass(
                    "POST /download-init (no auth)",
                    "Correctly returned 401 Unauthorized"
                )
                return True
            else:
                results.record_fail(
                    "POST /download-init (no auth)",
                    f"Expected 401, got {response.status_code}"
                )
                return False
    
    except Exception as e:
        results.record_fail(
            "POST /download-init (no auth)",
            f"Exception: {str(e)}"
        )
        return False


def test_download_with_token(download_token: str, pairing_code: str):
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
                    "GET /download?token=<jwt>",
                    f"Expected 200, got {response.status_code}: {response.text}"
                )
                return None
            
            # Verify headers
            content_type = response.headers.get("content-type", "")
            if content_type != "application/zip":
                results.record_fail(
                    "GET /download?token=<jwt>",
                    f"Content-Type={content_type} (expected 'application/zip')"
                )
                return None
            
            content_length = response.headers.get("content-length")
            if not content_length:
                results.record_fail(
                    "GET /download?token=<jwt>",
                    "Missing Content-Length header"
                )
                return None
            
            content_length = int(content_length)
            
            content_disposition = response.headers.get("content-disposition", "")
            expected_filename = f"DigitalTwinAgentSetup_{pairing_code}.zip"
            if expected_filename not in content_disposition:
                results.record_fail(
                    "GET /download?token=<jwt>",
                    f"Content-Disposition doesn't contain {expected_filename}: {content_disposition}"
                )
                return None
            
            x_pairing_code = response.headers.get("x-pairing-code", "")
            if x_pairing_code != pairing_code:
                results.record_fail(
                    "GET /download?token=<jwt>",
                    f"X-Pairing-Code={x_pairing_code} (expected {pairing_code})"
                )
                return None
            
            x_bundle_mode = response.headers.get("x-bundle-mode", "")
            if x_bundle_mode != "zip-file":
                results.record_fail(
                    "GET /download?token=<jwt>",
                    f"X-Bundle-Mode={x_bundle_mode} (expected 'zip-file')"
                )
                return None
            
            # Download the file
            actual_bytes = len(response.content)
            
            # CRITICAL: Content-Length must match actual bytes received
            if content_length != actual_bytes:
                results.record_fail(
                    "GET /download?token=<jwt>",
                    f"Content-Length={content_length} but received {actual_bytes} bytes "
                    f"(THIS WAS THE ROOT CAUSE OF THE 'HALF DOWNLOAD' BUG)"
                )
                return None
            
            results.record_pass(
                "GET /download?token=<jwt>",
                f"All headers correct, Content-Length={content_length} matches actual bytes"
            )
            
            # Save to temp file for ZIP integrity test
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.zip', delete=False) as f:
                f.write(response.content)
                temp_path = f.name
            
            return temp_path
    
    except Exception as e:
        results.record_fail(
            "GET /download?token=<jwt>",
            f"Exception: {str(e)}"
        )
        return None


def test_zip_integrity(zip_path: str, pairing_code: str):
    """Test ZIP integrity with unzip -t and verify contents."""
    step("Testing ZIP integrity")
    
    try:
        # Test 1: unzip -t (test integrity)
        result = subprocess.run(
            ["unzip", "-t", zip_path],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            results.record_fail(
                "ZIP integrity (unzip -t)",
                f"unzip -t failed with code {result.returncode}: {result.stderr}"
            )
            return False
        
        if "No errors detected" not in result.stdout:
            results.record_fail(
                "ZIP integrity (unzip -t)",
                f"unzip -t didn't report 'No errors detected': {result.stdout}"
            )
            return False
        
        results.record_pass(
            "ZIP integrity (unzip -t)",
            "No errors detected"
        )
        
        # Test 2: Verify ZIP contains exactly 6 entries
        with zipfile.ZipFile(zip_path, 'r') as zf:
            entries = zf.namelist()
            
            expected_entries = [
                "install.cmd",
                "bundle.json",
                "README.txt",
                f"DigitalTwinAgentSetup_{pairing_code}.exe",
                "agent.exe",
                "uninstaller.exe"
            ]
            
            if len(entries) != 6:
                results.record_fail(
                    "ZIP contents count",
                    f"Expected 6 entries, found {len(entries)}: {entries}"
                )
                return False
            
            missing = [e for e in expected_entries if e not in entries]
            if missing:
                results.record_fail(
                    "ZIP contents",
                    f"Missing entries: {missing}"
                )
                return False
            
            # Verify file sizes are reasonable
            installer_info = zf.getinfo(f"DigitalTwinAgentSetup_{pairing_code}.exe")
            agent_info = zf.getinfo("agent.exe")
            uninstaller_info = zf.getinfo("uninstaller.exe")
            
            # Check approximate sizes (allowing for compression)
            if installer_info.file_size < 40 * 1024 * 1024:  # ~45 MB
                results.record_fail(
                    "ZIP contents",
                    f"Installer too small: {installer_info.file_size/1024/1024:.1f}MB"
                )
                return False
            
            if agent_info.file_size < 140 * 1024 * 1024:  # ~150 MB
                results.record_fail(
                    "ZIP contents",
                    f"agent.exe too small: {agent_info.file_size/1024/1024:.1f}MB"
                )
                return False
            
            if uninstaller_info.file_size < 10 * 1024 * 1024:  # ~15 MB
                results.record_fail(
                    "ZIP contents",
                    f"uninstaller.exe too small: {uninstaller_info.file_size/1024/1024:.1f}MB"
                )
                return False
            
            results.record_pass(
                "ZIP contents",
                f"All 6 entries present with correct sizes: "
                f"installer={installer_info.file_size/1024/1024:.1f}MB, "
                f"agent={agent_info.file_size/1024/1024:.1f}MB, "
                f"uninstaller={uninstaller_info.file_size/1024/1024:.1f}MB"
            )
            
            # Verify file size on disk matches Content-Length
            zip_size = Path(zip_path).stat().st_size
            results.record_pass(
                "ZIP file size",
                f"File on disk: {zip_size/1024/1024:.1f}MB"
            )
            
            return True
    
    except Exception as e:
        results.record_fail(
            "ZIP integrity",
            f"Exception: {str(e)}"
        )
        return False
    finally:
        # Clean up temp file
        try:
            os.unlink(zip_path)
        except Exception:
            pass


def test_download_without_auth():
    """Test GET /api/agent/installer/download without auth (should fail)."""
    step("Testing GET /api/agent/installer/download (no auth, no token)")
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(f"{BASE_URL}/agent/installer/download")
            
            if response.status_code == 401:
                results.record_pass(
                    "GET /download (no auth)",
                    "Correctly returned 401 Unauthorized"
                )
                return True
            else:
                results.record_fail(
                    "GET /download (no auth)",
                    f"Expected 401, got {response.status_code}"
                )
                return False
    
    except Exception as e:
        results.record_fail(
            "GET /download (no auth)",
            f"Exception: {str(e)}"
        )
        return False


def test_download_with_stale_token():
    """Test GET /api/agent/installer/download with tampered token (should fail)."""
    step("Testing GET /api/agent/installer/download (stale/tampered token)")
    
    try:
        # Create a fake/tampered token
        fake_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                f"{BASE_URL}/agent/installer/download",
                params={"token": fake_token}
            )
            
            if response.status_code == 401:
                results.record_pass(
                    "GET /download (stale token)",
                    "Correctly returned 401 Unauthorized"
                )
                return True
            else:
                results.record_fail(
                    "GET /download (stale token)",
                    f"Expected 401, got {response.status_code}"
                )
                return False
    
    except Exception as e:
        results.record_fail(
            "GET /download (stale token)",
            f"Exception: {str(e)}"
        )
        return False


def test_download_with_bearer_token(token: str):
    """Test GET /api/agent/installer/download with Bearer token (backwards compat)."""
    step("Testing GET /api/agent/installer/download (Bearer token, no ?token=)")
    
    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.get(
                f"{BASE_URL}/agent/installer/download",
                headers={"Authorization": f"Bearer {token}"}
            )
            
            if response.status_code != 200:
                results.record_fail(
                    "GET /download (Bearer token)",
                    f"Expected 200, got {response.status_code}: {response.text}"
                )
                return None
            
            # Verify it's a valid ZIP
            content_type = response.headers.get("content-type", "")
            if content_type != "application/zip":
                results.record_fail(
                    "GET /download (Bearer token)",
                    f"Content-Type={content_type} (expected 'application/zip')"
                )
                return None
            
            content_length = response.headers.get("content-length")
            if not content_length:
                results.record_fail(
                    "GET /download (Bearer token)",
                    "Missing Content-Length header"
                )
                return None
            
            content_length = int(content_length)
            actual_bytes = len(response.content)
            
            if content_length != actual_bytes:
                results.record_fail(
                    "GET /download (Bearer token)",
                    f"Content-Length={content_length} but received {actual_bytes} bytes"
                )
                return None
            
            results.record_pass(
                "GET /download (Bearer token)",
                f"Backwards compatibility works: Content-Length={content_length} matches actual bytes"
            )
            
            # Extract pairing code from response header
            pairing_code = response.headers.get("x-pairing-code", "")
            return pairing_code
    
    except Exception as e:
        results.record_fail(
            "GET /download (Bearer token)",
            f"Exception: {str(e)}"
        )
        return None


def test_verify_endpoint(token: str, pairing_code: str):
    """Test GET /api/agent/installer/verify?code=<pairing_code>."""
    step(f"Testing GET /api/agent/installer/verify?code={pairing_code}")
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                f"{BASE_URL}/agent/installer/verify",
                params={"code": pairing_code},
                headers={"Authorization": f"Bearer {token}"}
            )
            
            if response.status_code != 200:
                results.record_fail(
                    "GET /verify",
                    f"Expected 200, got {response.status_code}: {response.text}"
                )
                return None
            
            data = response.json()
            
            # Verify required fields
            required_fields = ["code", "paired", "device", "expires_at"]
            missing = [f for f in required_fields if f not in data]
            if missing:
                results.record_fail(
                    "GET /verify",
                    f"Missing fields: {missing}"
                )
                return None
            
            # Verify code matches
            if data.get("code") != pairing_code:
                results.record_fail(
                    "GET /verify",
                    f"code={data.get('code')} (expected {pairing_code})"
                )
                return None
            
            # Verify paired is false (device hasn't paired yet)
            if data.get("paired") != False:
                results.record_fail(
                    "GET /verify",
                    f"paired={data.get('paired')} (expected false)"
                )
                return None
            
            # Verify device is null
            if data.get("device") is not None:
                results.record_fail(
                    "GET /verify",
                    f"device={data.get('device')} (expected null)"
                )
                return None
            
            # Verify expires_at is in the future (~10 minutes)
            expires_at = data.get("expires_at")
            if not expires_at:
                results.record_fail(
                    "GET /verify",
                    "expires_at is missing or null"
                )
                return None
            
            results.record_pass(
                "GET /verify",
                f"code={pairing_code}, paired=false, device=null, expires_at={expires_at}"
            )
            return data
    
    except Exception as e:
        results.record_fail(
            "GET /verify",
            f"Exception: {str(e)}"
        )
        return None


def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("AGENT INSTALLER DOWNLOAD FLOW - BACKEND TESTS")
    print("Testing the fix for 'downloading half' bug")
    print("="*70)
    
    # Step 1: Verify dist files
    if not verify_dist_files():
        print("\n❌ CRITICAL: Dist files missing. Cannot proceed with tests.")
        results.print_summary()
        return 1
    
    # Step 2: Login
    token = login()
    if not token:
        print("\n❌ CRITICAL: Login failed. Cannot proceed with tests.")
        results.print_summary()
        return 1
    
    # Step 3: Test /info endpoint
    info = test_installer_info(token)
    if not info:
        print("\n❌ CRITICAL: /info endpoint failed. Cannot proceed with tests.")
        results.print_summary()
        return 1
    
    # Step 4: Test /download-init without auth (should fail)
    test_download_init_without_auth()
    
    # Step 5: Test /download-init with auth
    init_data = test_download_init_with_auth(token)
    if not init_data:
        print("\n❌ CRITICAL: /download-init failed. Cannot proceed with download tests.")
        results.print_summary()
        return 1
    
    download_token = init_data.get("download_token")
    pairing_code = init_data.get("pairing_code")
    
    # Step 6: Test /download without auth (should fail)
    test_download_without_auth()
    
    # Step 7: Test /download with stale token (should fail)
    test_download_with_stale_token()
    
    # Step 8: Test /download with token (main test)
    zip_path = test_download_with_token(download_token, pairing_code)
    if zip_path:
        # Step 9: Test ZIP integrity
        test_zip_integrity(zip_path, pairing_code)
    
    # Step 10: Test /download with Bearer token (backwards compat)
    bearer_pairing_code = test_download_with_bearer_token(token)
    
    # Step 11: Test /verify endpoint
    if pairing_code:
        test_verify_endpoint(token, pairing_code)
    
    # Print summary
    success = results.print_summary()
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
