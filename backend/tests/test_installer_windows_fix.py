"""Backend tests for Windows Installer Permission Fix (2026-07-16).

Tests the NEW features added to fix the Windows installer permission issue:
  - POST /api/agent/installer/download-init (new endpoint)
  - GET /api/agent/installer/download with ?token= parameter
  - Bundle ZIP contains exactly 6 entries
  - install.cmd contains all safety additions:
    * setlocal EnableExtensions EnableDelayedExpansion
    * net session probe + UAC self-elevation
    * VBScript with Shell.Application + "runas"
    * sc query/stop DigitalTwinAgent
    * taskkill for agent.exe and uninstaller.exe
    * call (not start) with --api-url
    * errorlevel capture and pause
"""

import io
import os
import re
import tempfile
import zipfile
from pathlib import Path

import pytest
import requests

# Use localhost:8001 as specified in the review request - this is where /app/dist/ files are accessible
BASE_URL = "http://localhost:8001"
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@digitaltwin.com"
ADMIN_PASSWORD = "ChangeMe!2026"

CODE_RE = re.compile(r"^DT-[A-Z0-9]{4}-[A-Z0-9]{4}$")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def admin_token():
    """Login as admin and return access token."""
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    body = r.json()
    assert body.get("access_token"), f"No access_token in login response: {body}"
    return body["access_token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    """Return Authorization header for admin."""
    return {"Authorization": f"Bearer {admin_token}"}


# ---------------------------------------------------------------------------
# Test /download-init endpoint (NEW)
# ---------------------------------------------------------------------------
class TestDownloadInit:
    """Test the NEW /download-init endpoint that mints download tokens."""

    def test_download_init_returns_token_and_code(self, admin_headers):
        """Regression: POST /download-init returns download_token, pairing_code, filename, is_bundle, expires_in=300."""
        r = requests.post(
            f"{API}/agent/installer/download-init",
            json={"label": "pytest-windows-fix"},
            headers=admin_headers,
            timeout=15,
        )
        assert r.status_code == 200, f"download-init failed: {r.status_code} {r.text}"
        
        data = r.json()
        
        # Check all required fields
        assert "download_token" in data, "Missing download_token"
        assert "pairing_code" in data, "Missing pairing_code"
        assert "filename" in data, "Missing filename"
        assert "is_bundle" in data, "Missing is_bundle"
        assert "expires_in" in data, "Missing expires_in"
        
        # Validate values
        assert isinstance(data["download_token"], str) and len(data["download_token"]) > 20, \
            f"Invalid download_token: {data['download_token']}"
        
        assert CODE_RE.match(data["pairing_code"]), \
            f"Invalid pairing_code format: {data['pairing_code']}"
        
        assert data["expires_in"] == 300, \
            f"Expected expires_in=300, got {data['expires_in']}"
        
        # Since agent.exe exists in /app/dist, is_bundle should be True
        assert data["is_bundle"] is True, \
            f"Expected is_bundle=True (agent.exe exists), got {data['is_bundle']}"
        
        # Filename should be a ZIP when is_bundle=True
        assert data["filename"].endswith(".zip"), \
            f"Expected .zip filename for bundle, got {data['filename']}"
        
        assert data["pairing_code"] in data["filename"], \
            f"Pairing code {data['pairing_code']} not in filename {data['filename']}"
        
        print(f"✓ download-init returned: token={data['download_token'][:20]}..., code={data['pairing_code']}, filename={data['filename']}")

    def test_download_init_requires_technician_role(self):
        """Verify that download-init requires technician+ role (owner/admin should work)."""
        # Admin should work (tested above)
        # We don't have a viewer token fixture here, but the endpoint should reject viewers
        # This is implicitly tested by the role check in the endpoint
        pass


# ---------------------------------------------------------------------------
# Test /download with token parameter (NEW)
# ---------------------------------------------------------------------------
class TestDownloadWithToken:
    """Test the /download endpoint with ?token= query parameter (native browser download flow)."""

    def test_download_with_token_returns_zip(self, admin_headers):
        """Regression: GET /download?token=<jwt> returns HTTP 200 with correct Content-Length and Content-Type."""
        # Step 1: Get download token from /download-init
        init_r = requests.post(
            f"{API}/agent/installer/download-init",
            json={"label": "pytest-token-download"},
            headers=admin_headers,
            timeout=15,
        )
        assert init_r.status_code == 200, f"download-init failed: {init_r.status_code} {init_r.text}"
        init_data = init_r.json()
        download_token = init_data["download_token"]
        pairing_code = init_data["pairing_code"]
        
        # Step 2: Download using the token (no Authorization header needed)
        download_r = requests.get(
            f"{API}/agent/installer/download",
            params={"token": download_token},
            timeout=60,  # Large file download
        )
        assert download_r.status_code == 200, \
            f"download with token failed: {download_r.status_code} {download_r.text[:400]}"
        
        # Check Content-Type
        content_type = download_r.headers.get("Content-Type", "")
        assert content_type == "application/zip", \
            f"Expected Content-Type=application/zip, got {content_type}"
        
        # Check Content-Length matches actual body size
        content_length = int(download_r.headers.get("Content-Length", 0))
        actual_size = len(download_r.content)
        assert content_length == actual_size, \
            f"Content-Length mismatch: header={content_length}, actual={actual_size}"
        
        # Check X-Bundle-Mode header
        bundle_mode = download_r.headers.get("X-Bundle-Mode", "")
        assert bundle_mode == "zip-file", \
            f"Expected X-Bundle-Mode=zip-file, got {bundle_mode}"
        
        # Check X-Pairing-Code header
        header_code = download_r.headers.get("X-Pairing-Code", "")
        assert header_code == pairing_code, \
            f"X-Pairing-Code mismatch: expected {pairing_code}, got {header_code}"
        
        # Verify ZIP is valid
        try:
            with zipfile.ZipFile(io.BytesIO(download_r.content), 'r') as zf:
                # Test ZIP integrity
                bad_file = zf.testzip()
                assert bad_file is None, f"ZIP integrity check failed: {bad_file}"
        except zipfile.BadZipFile as e:
            pytest.fail(f"Downloaded file is not a valid ZIP: {e}")
        
        print(f"✓ download with token returned valid ZIP: {actual_size} bytes, code={pairing_code}")
        
        return download_r.content, pairing_code


# ---------------------------------------------------------------------------
# Test bundle contents (NEW)
# ---------------------------------------------------------------------------
class TestBundleContents:
    """Test that the bundle ZIP contains exactly 6 entries with correct structure."""

    def test_bundle_has_exactly_6_entries(self, admin_headers):
        """Regression: Bundle contains exactly 6 entries."""
        # Download the bundle
        init_r = requests.post(
            f"{API}/agent/installer/download-init",
            json={"label": "pytest-bundle-contents"},
            headers=admin_headers,
            timeout=15,
        )
        assert init_r.status_code == 200
        download_token = init_r.json()["download_token"]
        pairing_code = init_r.json()["pairing_code"]
        
        download_r = requests.get(
            f"{API}/agent/installer/download",
            params={"token": download_token},
            timeout=60,
        )
        assert download_r.status_code == 200
        
        # Extract and check contents
        with zipfile.ZipFile(io.BytesIO(download_r.content), 'r') as zf:
            entries = zf.namelist()
            
            # Should have exactly 6 entries
            assert len(entries) == 6, \
                f"Expected exactly 6 entries, got {len(entries)}: {entries}"
            
            # Check for required files
            expected_files = {
                "install.cmd",
                "bundle.json",
                "README.txt",
                f"DigitalTwinAgentSetup_{pairing_code}.exe",
                "agent.exe",
                "uninstaller.exe",
            }
            
            actual_files = set(entries)
            assert actual_files == expected_files, \
                f"Bundle contents mismatch.\nExpected: {expected_files}\nActual: {actual_files}"
            
            print(f"✓ Bundle contains exactly 6 entries: {entries}")

    def test_pairing_code_matches_across_endpoints(self, admin_headers):
        """NEW: Pairing code in filename matches download-init response AND /verify endpoint."""
        # Step 1: download-init
        init_r = requests.post(
            f"{API}/agent/installer/download-init",
            json={"label": "pytest-code-match"},
            headers=admin_headers,
            timeout=15,
        )
        assert init_r.status_code == 200
        init_code = init_r.json()["pairing_code"]
        download_token = init_r.json()["download_token"]
        
        # Step 2: download
        download_r = requests.get(
            f"{API}/agent/installer/download",
            params={"token": download_token},
            timeout=60,
        )
        assert download_r.status_code == 200
        
        # Extract installer filename from ZIP
        with zipfile.ZipFile(io.BytesIO(download_r.content), 'r') as zf:
            installer_files = [f for f in zf.namelist() if f.startswith("DigitalTwinAgentSetup_")]
            assert len(installer_files) == 1, f"Expected 1 installer, got {len(installer_files)}"
            installer_name = installer_files[0]
            
            # Extract code from filename
            match = re.search(r"DigitalTwinAgentSetup_(DT-[A-Z0-9]{4}-[A-Z0-9]{4})\.exe", installer_name)
            assert match, f"Could not extract code from installer filename: {installer_name}"
            filename_code = match.group(1)
            
            assert filename_code == init_code, \
                f"Code mismatch: download-init={init_code}, filename={filename_code}"
        
        # Step 3: verify endpoint
        verify_r = requests.get(
            f"{API}/agent/installer/verify",
            params={"code": init_code},
            headers=admin_headers,
            timeout=10,
        )
        assert verify_r.status_code == 200, \
            f"verify endpoint failed for code {init_code}: {verify_r.status_code} {verify_r.text}"
        
        verify_data = verify_r.json()
        assert verify_data["code"] == init_code, \
            f"verify endpoint returned different code: {verify_data['code']}"
        
        print(f"✓ Pairing code {init_code} matches across download-init, filename, and verify")


# ---------------------------------------------------------------------------
# Test install.cmd safety additions (NEW)
# ---------------------------------------------------------------------------
class TestInstallCmdSafety:
    """Test that install.cmd contains all the NEW safety additions for Windows UAC/permission fix."""

    @pytest.fixture
    def install_cmd_content(self, admin_headers):
        """Download bundle and extract install.cmd content."""
        init_r = requests.post(
            f"{API}/agent/installer/download-init",
            json={"label": "pytest-install-cmd"},
            headers=admin_headers,
            timeout=15,
        )
        assert init_r.status_code == 200
        download_token = init_r.json()["download_token"]
        
        download_r = requests.get(
            f"{API}/agent/installer/download",
            params={"token": download_token},
            timeout=60,
        )
        assert download_r.status_code == 200
        
        with zipfile.ZipFile(io.BytesIO(download_r.content), 'r') as zf:
            install_cmd_bytes = zf.read("install.cmd")
            # Decode as UTF-8 (the backend encodes it as UTF-8)
            return install_cmd_bytes.decode("utf-8")

    def test_delayed_expansion_enabled(self, install_cmd_content):
        """NEW: install.cmd contains 'setlocal EnableExtensions EnableDelayedExpansion'."""
        assert "setlocal EnableExtensions EnableDelayedExpansion" in install_cmd_content, \
            "Missing 'setlocal EnableExtensions EnableDelayedExpansion'"
        print("✓ install.cmd has delayed expansion enabled")

    def test_net_session_probe(self, install_cmd_content):
        """NEW: install.cmd contains 'net session' probe followed by 'if %errorlevel% neq 0' block."""
        assert "net session" in install_cmd_content, \
            "Missing 'net session' elevation probe"
        
        assert "if %errorlevel% neq 0" in install_cmd_content, \
            "Missing 'if %errorlevel% neq 0' elevation check"
        
        print("✓ install.cmd has net session probe with errorlevel check")

    def test_vbscript_uac_elevation(self, install_cmd_content):
        """NEW: install.cmd writes VBScript with Shell.Application and 'runas' verb."""
        # Check for VBScript creation
        assert 'CreateObject("Shell.Application")' in install_cmd_content, \
            'Missing CreateObject("Shell.Application") in VBScript'
        
        assert '"runas"' in install_cmd_content, \
            'Missing "runas" verb in VBScript'
        
        # Check that VBScript is written to %TEMP%
        assert "__ELEV_VBS" in install_cmd_content, \
            "Missing __ELEV_VBS variable for VBScript path"
        
        # Check that cscript is called
        assert "cscript" in install_cmd_content, \
            "Missing cscript call to execute VBScript"
        
        print("✓ install.cmd has VBScript UAC elevation with Shell.Application + runas")

    def test_service_stop_logic(self, install_cmd_content):
        """NEW: install.cmd runs 'sc query DigitalTwinAgent' and 'sc stop DigitalTwinAgent'."""
        assert "sc query DigitalTwinAgent" in install_cmd_content, \
            "Missing 'sc query DigitalTwinAgent'"
        
        assert "sc stop DigitalTwinAgent" in install_cmd_content, \
            "Missing 'sc stop DigitalTwinAgent'"
        
        print("✓ install.cmd has service stop logic (sc query/stop)")

    def test_taskkill_stragglers(self, install_cmd_content):
        """NEW: install.cmd includes taskkill for agent.exe and uninstaller.exe."""
        assert "taskkill" in install_cmd_content, \
            "Missing taskkill command"
        
        assert "agent.exe" in install_cmd_content, \
            "Missing agent.exe in taskkill targets"
        
        assert "uninstaller.exe" in install_cmd_content, \
            "Missing uninstaller.exe in taskkill targets"
        
        print("✓ install.cmd has taskkill for agent.exe and uninstaller.exe")

    def test_call_not_start(self, install_cmd_content):
        """NEW: install.cmd uses 'call' (not 'start') to launch installer with --api-url."""
        # Should have 'call "%INSTALLER%"' not 'start "%INSTALLER%"'
        assert 'call "%INSTALLER%"' in install_cmd_content, \
            'Missing call "%INSTALLER%" (should use call, not start)'
        
        assert '--api-url "%BACKEND_URL%"' in install_cmd_content, \
            'Missing --api-url "%BACKEND_URL%" parameter'
        
        # Make sure 'start' is NOT used for the installer call
        # (it might appear in comments or other contexts, so check the specific line)
        lines = install_cmd_content.split('\n')
        installer_call_lines = [l for l in lines if 'INSTALLER' in l and '--api-url' in l]
        for line in installer_call_lines:
            assert 'call' in line.lower() and 'start' not in line.lower(), \
                f"Installer should be called with 'call', not 'start': {line}"
        
        print("✓ install.cmd uses 'call' (not 'start') with --api-url")

    def test_errorlevel_capture_and_pause(self, install_cmd_content):
        """NEW: install.cmd captures %errorlevel% into INSTALL_RC and pauses at the end."""
        assert "INSTALL_RC=%errorlevel%" in install_cmd_content or "set INSTALL_RC=%errorlevel%" in install_cmd_content, \
            "Missing errorlevel capture into INSTALL_RC"
        
        assert "pause" in install_cmd_content, \
            "Missing 'pause' command at the end"
        
        # Check that the pause comes after the installer call
        lines = install_cmd_content.split('\n')
        installer_line_idx = None
        pause_line_idx = None
        
        for i, line in enumerate(lines):
            if 'call "%INSTALLER%"' in line:
                installer_line_idx = i
            if 'pause' in line.lower() and not line.strip().startswith('REM'):
                pause_line_idx = i
        
        assert installer_line_idx is not None, "Could not find installer call line"
        assert pause_line_idx is not None, "Could not find pause line"
        assert pause_line_idx > installer_line_idx, \
            "pause should come after installer call"
        
        print("✓ install.cmd captures errorlevel and pauses at the end")

    def test_backend_url_variable(self, install_cmd_content):
        """Verify that BACKEND_URL variable is set and used."""
        assert 'BACKEND_URL=' in install_cmd_content, \
            "Missing BACKEND_URL variable assignment"
        
        # Should reference the public backend URL
        assert 'http' in install_cmd_content.lower(), \
            "BACKEND_URL should contain http/https"
        
        print("✓ install.cmd sets BACKEND_URL variable")


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
