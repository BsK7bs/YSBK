"""Backend tests for Windows Installer fsutil + retry-loop + write-test fixes (2026-07-16 iteration 2).

This iteration adds MORE defensive measures on top of the payload/ subfolder structure:
  - CHANGED: Elevation probe from `net session` to `fsutil dirty query %SYSTEMDRIVE%`
  - NEW: `sc delete DigitalTwinAgent` after `sc stop` to prevent SCM auto-restart
  - NEW: PythonService.exe added to taskkill list
  - NEW: Retry loop `for /L %%i in (1,1,8)` to delete agent.exe with 2s delays
  - NEW: Final guard `if exist %INSTALL_ROOT%\agent.exe` with reboot message and exit code 32
  - NEW: WRITE-TEST section before `pushd payload` with sentinel file and exit code 5
"""

import io
import os
import re
import zipfile

import pytest
import requests

# Use public backend URL for testing
PUBLIC_BACKEND_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://bulk-file-loader.preview.emergentagent.com")
API = f"{PUBLIC_BACKEND_URL}/api"

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


@pytest.fixture(scope="session")
def install_cmd_content(admin_headers):
    """Download bundle and extract install.cmd content (shared across all tests)."""
    init_r = requests.post(
        f"{API}/agent/installer/download-init",
        json={"label": "pytest-fsutil-fix"},
        headers=admin_headers,
        timeout=15,
    )
    assert init_r.status_code == 200, f"download-init failed: {init_r.status_code} {init_r.text}"
    download_token = init_r.json()["download_token"]
    pairing_code = init_r.json()["pairing_code"]
    
    download_r = requests.get(
        f"{API}/agent/installer/download",
        params={"token": download_token},
        timeout=60,
    )
    assert download_r.status_code == 200, f"download failed: {download_r.status_code}"
    
    with zipfile.ZipFile(io.BytesIO(download_r.content), 'r') as zf:
        install_cmd_bytes = zf.read("install.cmd")
        content = install_cmd_bytes.decode("utf-8")
        print(f"\n✓ Downloaded bundle with pairing code {pairing_code}, install.cmd size: {len(content)} bytes")
        return content


# ---------------------------------------------------------------------------
# Regression tests (ensure previous features still work)
# ---------------------------------------------------------------------------
class TestRegression:
    """Verify that previous features still work after this iteration's changes."""

    def test_download_init_returns_correct_response(self, admin_headers):
        """Regression: POST /download-init returns download_token, pairing_code, filename, is_bundle=true, expires_in=300."""
        r = requests.post(
            f"{API}/agent/installer/download-init",
            json={"label": "pytest-regression"},
            headers=admin_headers,
            timeout=15,
        )
        assert r.status_code == 200, f"download-init failed: {r.status_code} {r.text}"
        
        data = r.json()
        assert "download_token" in data, "Missing download_token"
        assert "pairing_code" in data, "Missing pairing_code"
        assert "filename" in data, "Missing filename"
        assert "is_bundle" in data, "Missing is_bundle"
        assert "expires_in" in data, "Missing expires_in"
        
        assert CODE_RE.match(data["pairing_code"]), f"Invalid pairing_code: {data['pairing_code']}"
        assert data["expires_in"] == 300, f"Expected expires_in=300, got {data['expires_in']}"
        assert data["is_bundle"] is True, f"Expected is_bundle=True, got {data['is_bundle']}"
        assert data["filename"].endswith(".zip"), f"Expected .zip filename, got {data['filename']}"
        
        print(f"✓ Regression: download-init returns correct response (code={data['pairing_code']})")

    def test_download_returns_valid_zip(self, admin_headers):
        """Regression: GET /download returns HTTP 200 with Content-Type application/zip and valid ZIP."""
        init_r = requests.post(
            f"{API}/agent/installer/download-init",
            json={"label": "pytest-zip-regression"},
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
        assert download_r.status_code == 200, f"download failed: {download_r.status_code}"
        
        content_type = download_r.headers.get("Content-Type", "")
        assert content_type == "application/zip", f"Expected application/zip, got {content_type}"
        
        content_length = int(download_r.headers.get("Content-Length", 0))
        actual_size = len(download_r.content)
        assert content_length == actual_size, f"Content-Length mismatch: {content_length} vs {actual_size}"
        
        # Verify ZIP integrity
        with zipfile.ZipFile(io.BytesIO(download_r.content), 'r') as zf:
            bad_file = zf.testzip()
            assert bad_file is None, f"ZIP integrity check failed: {bad_file}"
        
        print(f"✓ Regression: download returns valid ZIP ({actual_size} bytes)")

    def test_zip_layout_payload_subfolder(self, admin_headers):
        """Regression: ZIP has install.cmd/README.txt/bundle.json at root, EXEs under payload/."""
        init_r = requests.post(
            f"{API}/agent/installer/download-init",
            json={"label": "pytest-layout-regression"},
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
        
        with zipfile.ZipFile(io.BytesIO(download_r.content), 'r') as zf:
            entries = zf.namelist()
            
            # Root files (no .exe at root)
            root_files = [e for e in entries if '/' not in e]
            assert set(root_files) == {"install.cmd", "README.txt", "bundle.json"}, \
                f"Root files mismatch: {root_files}"
            
            # Payload files
            payload_files = [e for e in entries if e.startswith("payload/")]
            expected_payload = {
                f"payload/DigitalTwinAgentSetup_{pairing_code}.exe",
                "payload/agent.exe",
                "payload/uninstaller.exe",
            }
            assert set(payload_files) == expected_payload, \
                f"Payload files mismatch: {payload_files}"
            
            print(f"✓ Regression: ZIP layout correct (3 root + 3 payload)")

    def test_pairing_code_matches_verify_endpoint(self, admin_headers):
        """Regression: Pairing code in filename is recognized by /verify endpoint."""
        init_r = requests.post(
            f"{API}/agent/installer/download-init",
            json={"label": "pytest-verify-regression"},
            headers=admin_headers,
            timeout=15,
        )
        assert init_r.status_code == 200
        pairing_code = init_r.json()["pairing_code"]
        
        verify_r = requests.get(
            f"{API}/agent/installer/verify",
            params={"code": pairing_code},
            headers=admin_headers,
            timeout=10,
        )
        assert verify_r.status_code == 200, f"verify failed: {verify_r.status_code} {verify_r.text}"
        
        verify_data = verify_r.json()
        assert verify_data["code"] == pairing_code, \
            f"verify returned different code: {verify_data['code']}"
        
        print(f"✓ Regression: Pairing code {pairing_code} recognized by /verify")


# ---------------------------------------------------------------------------
# NEW feature tests (this iteration's changes)
# ---------------------------------------------------------------------------
class TestFsutilElevationProbe:
    """NEW: Elevation probe changed from `net session` to `fsutil dirty query`."""

    def test_fsutil_probe_present(self, install_cmd_content):
        """NEW: install.cmd uses `fsutil dirty query %SYSTEMDRIVE%` as elevation probe."""
        assert "fsutil dirty query %SYSTEMDRIVE%" in install_cmd_content, \
            "Missing 'fsutil dirty query %SYSTEMDRIVE%' elevation probe"
        
        print("✓ NEW: install.cmd uses fsutil dirty query for elevation probe")

    def test_net_session_removed(self, install_cmd_content):
        """NEW: install.cmd does NOT use `net session` anymore (replaced by fsutil)."""
        # net session should NOT appear (except maybe in comments)
        lines = [l for l in install_cmd_content.split('\n') if not l.strip().startswith('REM')]
        non_comment_content = '\n'.join(lines)
        
        assert "net session" not in non_comment_content, \
            "Found 'net session' in install.cmd - it should be replaced by fsutil"
        
        print("✓ NEW: install.cmd does NOT use net session (replaced by fsutil)")


class TestServiceDeleteCommand:
    """NEW: `sc delete DigitalTwinAgent` added after `sc stop`."""

    def test_sc_delete_present(self, install_cmd_content):
        """NEW: install.cmd runs `sc delete DigitalTwinAgent`."""
        assert "sc delete DigitalTwinAgent" in install_cmd_content, \
            "Missing 'sc delete DigitalTwinAgent' command"
        
        print("✓ NEW: install.cmd has 'sc delete DigitalTwinAgent'")

    def test_sc_delete_after_sc_stop(self, install_cmd_content):
        """NEW: `sc delete` comes AFTER `sc stop` in the service cleanup block."""
        lines = install_cmd_content.split('\n')
        
        sc_stop_idx = None
        sc_delete_idx = None
        
        for i, line in enumerate(lines):
            if 'sc stop DigitalTwinAgent' in line and not line.strip().startswith('REM'):
                sc_stop_idx = i
            if 'sc delete DigitalTwinAgent' in line and not line.strip().startswith('REM'):
                sc_delete_idx = i
        
        assert sc_stop_idx is not None, "Could not find 'sc stop DigitalTwinAgent'"
        assert sc_delete_idx is not None, "Could not find 'sc delete DigitalTwinAgent'"
        assert sc_delete_idx > sc_stop_idx, \
            f"'sc delete' (line {sc_delete_idx}) should come AFTER 'sc stop' (line {sc_stop_idx})"
        
        print(f"✓ NEW: 'sc delete' (line {sc_delete_idx}) comes after 'sc stop' (line {sc_stop_idx})")

    def test_sc_delete_inside_errorlevel_block(self, install_cmd_content):
        """NEW: `sc delete` is inside the `if %errorlevel% equ 0` block after sc query."""
        # Find the sc query block
        lines = install_cmd_content.split('\n')
        
        sc_query_idx = None
        errorlevel_block_start = None
        sc_delete_idx = None
        
        for i, line in enumerate(lines):
            if 'sc query DigitalTwinAgent' in line and not line.strip().startswith('REM'):
                sc_query_idx = i
            if 'if %errorlevel% equ 0' in line and sc_query_idx is not None and errorlevel_block_start is None:
                errorlevel_block_start = i
            if 'sc delete DigitalTwinAgent' in line and not line.strip().startswith('REM'):
                sc_delete_idx = i
        
        assert sc_query_idx is not None, "Could not find 'sc query DigitalTwinAgent'"
        assert errorlevel_block_start is not None, "Could not find 'if %errorlevel% equ 0' after sc query"
        assert sc_delete_idx is not None, "Could not find 'sc delete DigitalTwinAgent'"
        assert sc_delete_idx > errorlevel_block_start, \
            f"'sc delete' should be inside the 'if %errorlevel% equ 0' block"
        
        print(f"✓ NEW: 'sc delete' is inside the service-cleanup block")


class TestPythonServiceTaskkill:
    """NEW: PythonService.exe added to taskkill list."""

    def test_pythonservice_in_taskkill(self, install_cmd_content):
        """NEW: install.cmd includes PythonService.exe in taskkill targets."""
        assert "PythonService.exe" in install_cmd_content, \
            "Missing 'PythonService.exe' in taskkill targets"
        
        # Verify it's in the same taskkill line/block as agent.exe
        lines = install_cmd_content.split('\n')
        taskkill_lines = [l for l in lines if 'taskkill' in l.lower() and not l.strip().startswith('REM')]
        
        found_pythonservice = False
        for line in taskkill_lines:
            if 'PythonService.exe' in line:
                found_pythonservice = True
                # Should also mention agent.exe or uninstaller.exe in the same context
                assert 'agent.exe' in line or 'uninstaller.exe' in line or 'for %%P in' in line, \
                    f"PythonService.exe should be in the same taskkill block as other EXEs: {line}"
        
        assert found_pythonservice, "PythonService.exe not found in any taskkill line"
        
        print("✓ NEW: PythonService.exe included in taskkill list")


class TestRetryLoop:
    """NEW: Retry loop to delete agent.exe with 8 attempts and 2s delays."""

    def test_retry_loop_present(self, install_cmd_content):
        """NEW: install.cmd has `for /L %%i in (1,1,8)` retry loop."""
        assert "for /L %%i in (1,1,8)" in install_cmd_content, \
            "Missing 'for /L %%i in (1,1,8)' retry loop"
        
        print("✓ NEW: install.cmd has retry loop 'for /L %%i in (1,1,8)'")

    def test_retry_loop_deletes_agent_exe(self, install_cmd_content):
        """NEW: Retry loop attempts `del /F /Q %INSTALL_ROOT%\agent.exe`."""
        assert "del /F /Q" in install_cmd_content, \
            "Missing 'del /F /Q' command in retry loop"
        
        # Check that it targets agent.exe specifically
        lines = install_cmd_content.split('\n')
        retry_block = []
        in_retry_loop = False
        
        for line in lines:
            if 'for /L %%i in (1,1,8)' in line:
                in_retry_loop = True
            if in_retry_loop:
                retry_block.append(line)
                # Loop ends at the closing parenthesis (simplified check)
                if line.strip() == ')' and len(retry_block) > 5:
                    break
        
        retry_content = '\n'.join(retry_block)
        assert 'agent.exe' in retry_content, \
            "Retry loop should target agent.exe"
        assert 'del /F /Q' in retry_content, \
            "Retry loop should use 'del /F /Q'"
        
        print("✓ NEW: Retry loop deletes agent.exe with 'del /F /Q'")

    def test_retry_loop_has_timeout(self, install_cmd_content):
        """NEW: Retry loop includes `timeout /t 2 /nobreak` between attempts."""
        lines = install_cmd_content.split('\n')
        retry_block = []
        in_retry_loop = False
        
        for line in lines:
            if 'for /L %%i in (1,1,8)' in line:
                in_retry_loop = True
            if in_retry_loop:
                retry_block.append(line)
                if line.strip() == ')' and len(retry_block) > 5:
                    break
        
        retry_content = '\n'.join(retry_block)
        assert 'timeout /t 2' in retry_content, \
            "Retry loop should have 'timeout /t 2' between attempts"
        
        print("✓ NEW: Retry loop has 'timeout /t 2' between attempts")

    def test_retry_loop_inside_install_root_check(self, install_cmd_content):
        """NEW: Retry loop is inside the `if exist %INSTALL_ROOT%` cleanup block."""
        lines = install_cmd_content.split('\n')
        
        install_root_check_idx = None
        retry_loop_idx = None
        
        for i, line in enumerate(lines):
            if 'if exist "%INSTALL_ROOT%"' in line and install_root_check_idx is None:
                install_root_check_idx = i
            if 'for /L %%i in (1,1,8)' in line:
                retry_loop_idx = i
        
        assert install_root_check_idx is not None, "Could not find 'if exist %INSTALL_ROOT%'"
        assert retry_loop_idx is not None, "Could not find retry loop"
        assert retry_loop_idx > install_root_check_idx, \
            f"Retry loop (line {retry_loop_idx}) should be inside 'if exist %INSTALL_ROOT%' block (line {install_root_check_idx})"
        
        print(f"✓ NEW: Retry loop is inside 'if exist %INSTALL_ROOT%' block")


class TestFinalGuard:
    """NEW: Final guard check with reboot message and exit code 32."""

    def test_final_guard_present(self, install_cmd_content):
        """NEW: install.cmd has final `if exist %INSTALL_ROOT%\agent.exe` guard."""
        # Should appear AFTER the retry loop
        assert 'if exist "%INSTALL_ROOT%\\agent.exe"' in install_cmd_content, \
            "Missing final guard 'if exist %INSTALL_ROOT%\\agent.exe'"
        
        print("✓ NEW: install.cmd has final guard check for agent.exe")

    def test_final_guard_has_reboot_message(self, install_cmd_content):
        """NEW: Final guard prints 'please REBOOT' message."""
        lines = install_cmd_content.split('\n')
        
        # Find the final guard block
        guard_block = []
        in_guard = False
        
        for line in lines:
            if 'if exist "%INSTALL_ROOT%\\agent.exe"' in line and 'for /L' not in line:
                in_guard = True
            if in_guard:
                guard_block.append(line)
                if 'exit /b' in line:
                    break
        
        guard_content = '\n'.join(guard_block).upper()
        assert 'REBOOT' in guard_content, \
            "Final guard should mention REBOOT in the error message"
        
        print("✓ NEW: Final guard has 'REBOOT' message")

    def test_final_guard_exits_with_code_32(self, install_cmd_content):
        """NEW: Final guard exits with code 32."""
        lines = install_cmd_content.split('\n')
        
        # Find the final guard block
        guard_block = []
        in_guard = False
        
        for line in lines:
            if 'if exist "%INSTALL_ROOT%\\agent.exe"' in line and 'for /L' not in line:
                in_guard = True
            if in_guard:
                guard_block.append(line)
                if 'exit /b' in line:
                    break
        
        guard_content = '\n'.join(guard_block)
        assert 'exit /b 32' in guard_content, \
            "Final guard should exit with code 32"
        
        print("✓ NEW: Final guard exits with code 32")


class TestWriteTest:
    """NEW: WRITE-TEST section before `pushd payload` with sentinel file and exit code 5."""

    def test_write_test_section_present(self, install_cmd_content):
        """NEW: install.cmd has WRITE-TEST section that creates sentinel file."""
        assert ".dt_writetest_" in install_cmd_content, \
            "Missing WRITE-TEST sentinel file (.dt_writetest_)"
        
        print("✓ NEW: install.cmd has WRITE-TEST section")

    def test_write_test_before_pushd(self, install_cmd_content):
        """NEW: WRITE-TEST section comes BEFORE `pushd payload`."""
        lines = install_cmd_content.split('\n')
        
        writetest_idx = None
        pushd_idx = None
        
        for i, line in enumerate(lines):
            if '.dt_writetest_' in line and writetest_idx is None:
                writetest_idx = i
            if 'pushd "%SCRIPT_DIR%payload"' in line or 'pushd payload' in line:
                pushd_idx = i
        
        assert writetest_idx is not None, "Could not find WRITE-TEST section"
        assert pushd_idx is not None, "Could not find 'pushd payload'"
        assert writetest_idx < pushd_idx, \
            f"WRITE-TEST (line {writetest_idx}) should come BEFORE 'pushd payload' (line {pushd_idx})"
        
        print(f"✓ NEW: WRITE-TEST (line {writetest_idx}) comes before 'pushd payload' (line {pushd_idx})")

    def test_write_test_creates_install_root(self, install_cmd_content):
        """NEW: WRITE-TEST creates %INSTALL_ROOT% if missing."""
        lines = install_cmd_content.split('\n')
        
        # Find WRITE-TEST section
        writetest_section = []
        in_writetest = False
        
        for line in lines:
            if 'if not exist "%INSTALL_ROOT%"' in line and 'mkdir' in line:
                in_writetest = True
            if in_writetest:
                writetest_section.append(line)
                if 'pushd' in line:
                    break
        
        writetest_content = '\n'.join(writetest_section)
        assert 'mkdir "%INSTALL_ROOT%"' in writetest_content or 'mkdir %INSTALL_ROOT%' in writetest_content, \
            "WRITE-TEST should create %INSTALL_ROOT% if missing"
        
        print("✓ NEW: WRITE-TEST creates %INSTALL_ROOT% if missing")

    def test_write_test_grants_administrators_access(self, install_cmd_content):
        """NEW: WRITE-TEST grants Administrators full control before testing."""
        lines = install_cmd_content.split('\n')
        
        # Find WRITE-TEST section (before pushd)
        writetest_section = []
        for i, line in enumerate(lines):
            if '.dt_writetest_' in line:
                # Grab context around the write test
                writetest_section = lines[max(0, i-10):i+10]
                break
        
        writetest_content = '\n'.join(writetest_section)
        assert 'icacls' in writetest_content and 'S-1-5-32-544' in writetest_content, \
            "WRITE-TEST should grant Administrators (S-1-5-32-544) full control"
        
        print("✓ NEW: WRITE-TEST grants Administrators full control")

    def test_write_test_has_diagnostic_message(self, install_cmd_content):
        """NEW: WRITE-TEST has actionable diagnostic mentioning Controlled Folder Access / Group Policy / AppLocker."""
        lines = install_cmd_content.split('\n')
        
        # Find the write-test failure block
        writetest_fail_block = []
        in_fail_block = False
        
        for line in lines:
            if 'if not exist "!__WRITE_TEST!"' in line or 'if not exist "%__WRITE_TEST%"' in line:
                in_fail_block = True
            if in_fail_block:
                writetest_fail_block.append(line)
                if 'exit /b' in line:
                    break
        
        fail_content = '\n'.join(writetest_fail_block).upper()
        
        # Should mention at least one of these
        has_diagnostic = any(keyword in fail_content for keyword in [
            'CONTROLLED FOLDER ACCESS',
            'GROUP POLICY',
            'APPLOCKER',
        ])
        
        assert has_diagnostic, \
            "WRITE-TEST failure message should mention Controlled Folder Access / Group Policy / AppLocker"
        
        print("✓ NEW: WRITE-TEST has actionable diagnostic message")

    def test_write_test_exits_with_code_5(self, install_cmd_content):
        """NEW: WRITE-TEST exits with code 5 if write fails."""
        lines = install_cmd_content.split('\n')
        
        # Find the write-test failure block
        writetest_fail_block = []
        in_fail_block = False
        
        for line in lines:
            if 'if not exist "!__WRITE_TEST!"' in line or 'if not exist "%__WRITE_TEST%"' in line:
                in_fail_block = True
            if in_fail_block:
                writetest_fail_block.append(line)
                if 'exit /b' in line:
                    break
        
        fail_content = '\n'.join(writetest_fail_block)
        assert 'exit /b 5' in fail_content, \
            "WRITE-TEST should exit with code 5 on failure"
        
        print("✓ NEW: WRITE-TEST exits with code 5 on failure")


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "--maxfail=1"])
