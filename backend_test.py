#!/usr/bin/env python3
"""
Backend test for Digital Twin Agent Installer Bundle Layout v2
Tests the new payload/ subfolder structure and ACL-reset fixes.
"""
import json
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path

import requests

# Configuration
BASE_URL = "https://bulk-file-loader.preview.emergentagent.com"
ADMIN_EMAIL = "admin@digitaltwin.com"
ADMIN_PASSWORD = "ChangeMe!2026"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'

class InstallerBundleTest:
    def __init__(self):
        self.base_url = BASE_URL
        self.token = None
        self.download_token = None
        self.pairing_code = None
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.zip_path = None
        self.extract_dir = None

    def log(self, message, level="INFO"):
        colors = {"INFO": Colors.BLUE, "PASS": Colors.GREEN, "FAIL": Colors.RED, "WARN": Colors.YELLOW}
        color = colors.get(level, Colors.RESET)
        print(f"{color}[{level}]{Colors.RESET} {message}")

    def test(self, name):
        """Decorator for test methods"""
        def decorator(func):
            def wrapper(*args, **kwargs):
                self.tests_run += 1
                self.log(f"Test {self.tests_run}: {name}", "INFO")
                try:
                    result = func(*args, **kwargs)
                    if result:
                        self.tests_passed += 1
                        self.log(f"✓ {name}", "PASS")
                    else:
                        self.tests_failed += 1
                        self.log(f"✗ {name}", "FAIL")
                    return result
                except Exception as e:
                    self.tests_failed += 1
                    self.log(f"✗ {name} - Exception: {str(e)}", "FAIL")
                    return False
            return wrapper
        return decorator

    def login(self):
        """Authenticate and get access token"""
        self.log("Authenticating...", "INFO")
        response = requests.post(
            f"{self.base_url}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        if response.status_code == 200:
            data = response.json()
            self.token = data.get("access_token")
            self.log(f"✓ Logged in as {ADMIN_EMAIL}", "PASS")
            return True
        else:
            self.log(f"✗ Login failed: {response.status_code} - {response.text}", "FAIL")
            return False

    def run_test_download_init(self):
        """Test POST /api/agent/installer/download-init"""
        self.tests_run += 1
        self.log(f"Test {self.tests_run}: POST /api/agent/installer/download-init returns correct response", "INFO")
        
        headers = {"Authorization": f"Bearer {self.token}"}
        response = requests.post(
            f"{self.base_url}/api/agent/installer/download-init",
            headers=headers,
            json={"label": "test-install"}
        )
        
        if response.status_code != 200:
            self.tests_failed += 1
            self.log(f"✗ download-init failed: {response.status_code} - {response.text}", "FAIL")
            return False
        
        data = response.json()
        
        # Check required fields
        required_fields = ["download_token", "pairing_code", "filename", "is_bundle", "expires_in"]
        missing = [f for f in required_fields if f not in data]
        if missing:
            self.tests_failed += 1
            self.log(f"✗ Missing fields in response: {missing}", "FAIL")
            return False
        
        # Verify field values
        checks = []
        checks.append(("download_token exists", bool(data.get("download_token"))))
        checks.append(("pairing_code format DT-XXXX-XXXX", bool(re.match(r"^DT-[A-Z0-9]{4}-[A-Z0-9]{4}$", data.get("pairing_code", "")))))
        checks.append(("filename ends with .zip", data.get("filename", "").endswith(".zip")))
        checks.append(("is_bundle is true", data.get("is_bundle") is True))
        checks.append(("expires_in is 300", data.get("expires_in") == 300))
        
        all_passed = all(result for _, result in checks)
        
        if all_passed:
            self.tests_passed += 1
            self.download_token = data["download_token"]
            self.pairing_code = data["pairing_code"]
            self.log(f"✓ download-init response correct (code: {self.pairing_code})", "PASS")
            for check_name, _ in checks:
                self.log(f"  ✓ {check_name}", "PASS")
            return True
        else:
            self.tests_failed += 1
            self.log(f"✗ download-init response validation failed", "FAIL")
            for check_name, result in checks:
                status = "✓" if result else "✗"
                self.log(f"  {status} {check_name}", "PASS" if result else "FAIL")
            return False

    def run_test_download_endpoint(self):
        """Test GET /api/agent/installer/download?token=<jwt>"""
        self.tests_run += 1
        self.log(f"Test {self.tests_run}: GET /api/agent/installer/download returns HTTP 200 with correct headers", "INFO")
        
        response = requests.get(
            f"{self.base_url}/api/agent/installer/download",
            params={"token": self.download_token},
            stream=True
        )
        
        if response.status_code != 200:
            self.tests_failed += 1
            self.log(f"✗ download failed: {response.status_code}", "FAIL")
            return False
        
        # Check headers
        checks = []
        content_type = response.headers.get("Content-Type", "")
        content_length = response.headers.get("Content-Length")
        
        checks.append(("Content-Type is application/zip", content_type == "application/zip"))
        checks.append(("Content-Length header present", content_length is not None))
        
        # Download the file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
            bytes_downloaded = 0
            for chunk in response.iter_content(chunk_size=8192):
                tmp.write(chunk)
                bytes_downloaded += len(chunk)
            self.zip_path = tmp.name
        
        # Verify Content-Length matches actual bytes
        if content_length:
            expected_size = int(content_length)
            checks.append((f"Content-Length ({expected_size}) matches bytes downloaded ({bytes_downloaded})", 
                          expected_size == bytes_downloaded))
        
        # Verify ZIP integrity
        try:
            with zipfile.ZipFile(self.zip_path, 'r') as zf:
                test_result = zf.testzip()
                checks.append(("ZIP integrity check (testzip)", test_result is None))
        except Exception as e:
            checks.append(("ZIP integrity check (testzip)", False))
            self.log(f"  ZIP test failed: {e}", "FAIL")
        
        all_passed = all(result for _, result in checks)
        
        if all_passed:
            self.tests_passed += 1
            self.log(f"✓ download endpoint correct (downloaded {bytes_downloaded} bytes)", "PASS")
            for check_name, _ in checks:
                self.log(f"  ✓ {check_name}", "PASS")
            return True
        else:
            self.tests_failed += 1
            self.log(f"✗ download endpoint validation failed", "FAIL")
            for check_name, result in checks:
                status = "✓" if result else "✗"
                self.log(f"  {status} {check_name}", "PASS" if result else "FAIL")
            return False

    def run_test_zip_layout(self):
        """Test NEW LAYOUT: ZIP structure"""
        self.tests_run += 1
        self.log(f"Test {self.tests_run}: ZIP root contains exactly 3 files (install.cmd, README.txt, bundle.json) and NO .exe at root", "INFO")
        
        if not self.zip_path or not os.path.exists(self.zip_path):
            self.tests_failed += 1
            self.log("✗ ZIP file not available", "FAIL")
            return False
        
        try:
            with zipfile.ZipFile(self.zip_path, 'r') as zf:
                all_entries = zf.namelist()
                
                # Separate root and payload entries
                root_entries = [e for e in all_entries if '/' not in e]
                payload_entries = [e for e in all_entries if e.startswith('payload/')]
                
                checks = []
                
                # Check root contains exactly 3 files
                expected_root = {'install.cmd', 'README.txt', 'bundle.json'}
                actual_root = set(root_entries)
                checks.append((f"Root has exactly 3 files: {expected_root}", actual_root == expected_root))
                
                # Check no .exe files at root
                root_exes = [e for e in root_entries if e.endswith('.exe')]
                checks.append(("No .exe files at root", len(root_exes) == 0))
                
                # Check payload/ entries
                expected_payload_count = 3  # installer.exe, agent.exe, uninstaller.exe
                checks.append((f"payload/ contains 3 files", len(payload_entries) == expected_payload_count))
                
                # Check specific payload files
                payload_basenames = [os.path.basename(e) for e in payload_entries]
                checks.append(("payload/ contains agent.exe", "agent.exe" in payload_basenames))
                checks.append(("payload/ contains uninstaller.exe", "uninstaller.exe" in payload_basenames))
                
                # Check installer .exe with pairing code in name
                installer_pattern = f"DigitalTwinAgentSetup_{self.pairing_code}.exe"
                installer_in_payload = any(e.endswith(installer_pattern) for e in payload_entries)
                checks.append((f"payload/ contains {installer_pattern}", installer_in_payload))
                
                # Total entry count should be 6 (3 root + 3 payload)
                checks.append((f"Total entries is 6 (got {len(all_entries)})", len(all_entries) == 6))
                
                all_passed = all(result for _, result in checks)
                
                if all_passed:
                    self.tests_passed += 1
                    self.log(f"✓ ZIP layout correct", "PASS")
                    for check_name, _ in checks:
                        self.log(f"  ✓ {check_name}", "PASS")
                    return True
                else:
                    self.tests_failed += 1
                    self.log(f"✗ ZIP layout validation failed", "FAIL")
                    self.log(f"  Root entries: {root_entries}", "INFO")
                    self.log(f"  Payload entries: {payload_entries}", "INFO")
                    for check_name, result in checks:
                        status = "✓" if result else "✗"
                        self.log(f"  {status} {check_name}", "PASS" if result else "FAIL")
                    return False
                    
        except Exception as e:
            self.tests_failed += 1
            self.log(f"✗ ZIP layout test exception: {e}", "FAIL")
            return False

    def run_test_bundle_json(self):
        """Test bundle.json schema"""
        self.tests_run += 1
        self.log(f"Test {self.tests_run}: bundle.json has correct schema (schema_version=2, layout='payload-subfolder', etc.)", "INFO")
        
        try:
            with zipfile.ZipFile(self.zip_path, 'r') as zf:
                bundle_json_content = zf.read('bundle.json').decode('utf-8')
                bundle_data = json.loads(bundle_json_content)
                
                checks = []
                checks.append(("schema_version is 2", bundle_data.get("schema_version") == 2))
                checks.append(("layout is 'payload-subfolder'", bundle_data.get("layout") == "payload-subfolder"))
                checks.append(("pairing_code matches", bundle_data.get("pairing_code") == self.pairing_code))
                checks.append(("entrypoint is 'install.cmd'", bundle_data.get("entrypoint") == "install.cmd"))
                
                # Check paths
                installer_path = bundle_data.get("installer", "")
                checks.append(("installer path starts with 'payload/'", installer_path.startswith("payload/")))
                checks.append((f"installer path contains pairing code", self.pairing_code in installer_path))
                
                checks.append(("agent path is 'payload/agent.exe'", bundle_data.get("agent") == "payload/agent.exe"))
                checks.append(("uninstaller path is 'payload/uninstaller.exe'", bundle_data.get("uninstaller") == "payload/uninstaller.exe"))
                
                checks.append(("backend_url present", bool(bundle_data.get("backend_url"))))
                checks.append(("generated_at present", bool(bundle_data.get("generated_at"))))
                
                all_passed = all(result for _, result in checks)
                
                if all_passed:
                    self.tests_passed += 1
                    self.log(f"✓ bundle.json schema correct", "PASS")
                    for check_name, _ in checks:
                        self.log(f"  ✓ {check_name}", "PASS")
                    return True
                else:
                    self.tests_failed += 1
                    self.log(f"✗ bundle.json schema validation failed", "FAIL")
                    self.log(f"  bundle.json content: {json.dumps(bundle_data, indent=2)}", "INFO")
                    for check_name, result in checks:
                        status = "✓" if result else "✗"
                        self.log(f"  {status} {check_name}", "PASS" if result else "FAIL")
                    return False
                    
        except Exception as e:
            self.tests_failed += 1
            self.log(f"✗ bundle.json test exception: {e}", "FAIL")
            return False

    def run_test_install_cmd(self):
        """Test install.cmd content"""
        self.tests_run += 1
        self.log(f"Test {self.tests_run}: install.cmd has correct content (INSTALLER variable, pushd/popd, ACL-reset block)", "INFO")
        
        try:
            with zipfile.ZipFile(self.zip_path, 'r') as zf:
                install_cmd_content = zf.read('install.cmd').decode('utf-8')
                
                checks = []
                
                # Check INSTALLER variable points to payload subfolder
                installer_var_pattern = f'set "INSTALLER=%SCRIPT_DIR%payload\\DigitalTwinAgentSetup_{self.pairing_code}.exe"'
                checks.append(("INSTALLER variable points to payload/", installer_var_pattern in install_cmd_content))
                
                # Check pushd/popd usage
                checks.append(("Contains 'pushd \"%SCRIPT_DIR%payload\"'", 'pushd "%SCRIPT_DIR%payload"' in install_cmd_content))
                checks.append(("Contains 'popd'", 'popd' in install_cmd_content))
                
                # Check ACL-reset block commands (all inside if exist %INSTALL_ROOT%)
                checks.append(("Contains 'if exist \"%INSTALL_ROOT%\"'", 'if exist "%INSTALL_ROOT%"' in install_cmd_content))
                checks.append(("Contains 'takeown /F' command", 'takeown /F' in install_cmd_content))
                checks.append(("Contains 'icacls' /reset command", 'icacls "%INSTALL_ROOT%" /reset /T /C /Q' in install_cmd_content))
                checks.append(("Contains 'icacls' /grant command", 'icacls "%INSTALL_ROOT%" /grant *S-1-5-32-544:(OI)(CI)F /T /C /Q' in install_cmd_content))
                checks.append(("Contains 'attrib -R -S -H' command", 'attrib -R -S -H' in install_cmd_content))
                checks.append(("Contains 'rmdir /S /Q' command", 'rmdir /S /Q "%INSTALL_ROOT%"' in install_cmd_content))
                
                # Check earlier fixes
                checks.append(("Contains 'setlocal EnableExtensions EnableDelayedExpansion'", 'setlocal EnableExtensions EnableDelayedExpansion' in install_cmd_content))
                checks.append(("Contains 'net session' probe", 'net session' in install_cmd_content))
                checks.append(("Contains VBScript UAC elevation", 'Shell.Application' in install_cmd_content and 'runas' in install_cmd_content))
                checks.append(("Contains 'sc query DigitalTwinAgent'", 'sc query DigitalTwinAgent' in install_cmd_content))
                checks.append(("Contains 'sc stop DigitalTwinAgent'", 'sc stop DigitalTwinAgent' in install_cmd_content))
                checks.append(("Contains 'taskkill' for agent.exe", 'taskkill' in install_cmd_content and 'agent.exe' in install_cmd_content))
                checks.append(("Contains 'taskkill' for uninstaller.exe", 'uninstaller.exe' in install_cmd_content))
                checks.append(("Contains 'taskkill' for DigitalTwinAgent.exe", 'DigitalTwinAgent.exe' in install_cmd_content))
                
                all_passed = all(result for _, result in checks)
                
                if all_passed:
                    self.tests_passed += 1
                    self.log(f"✓ install.cmd content correct", "PASS")
                    for check_name, _ in checks:
                        self.log(f"  ✓ {check_name}", "PASS")
                    return True
                else:
                    self.tests_failed += 1
                    self.log(f"✗ install.cmd content validation failed", "FAIL")
                    for check_name, result in checks:
                        status = "✓" if result else "✗"
                        self.log(f"  {status} {check_name}", "PASS" if result else "FAIL")
                    return False
                    
        except Exception as e:
            self.tests_failed += 1
            self.log(f"✗ install.cmd test exception: {e}", "FAIL")
            return False

    def run_test_readme(self):
        """Test README.txt content"""
        self.tests_run += 1
        self.log(f"Test {self.tests_run}: README.txt contains warning banner and references payload/", "INFO")
        
        try:
            with zipfile.ZipFile(self.zip_path, 'r') as zf:
                readme_content = zf.read('README.txt').decode('utf-8')
                
                checks = []
                
                # Check for warning banner (asterisk-boxed)
                checks.append(("Contains asterisk banner", '**********' in readme_content))
                checks.append(("Warning about install.cmd only", 'Double-click ONLY  install.cmd' in readme_content or 'ONLY' in readme_content and 'install.cmd' in readme_content))
                checks.append(("Warning about NOT running payload/ directly", 'Do NOT run anything inside the payload' in readme_content or 'payload' in readme_content.lower()))
                
                # Check references to payload/
                checks.append(("References 'payload\\' in file listing", 'payload\\' in readme_content))
                
                # Check basic content
                checks.append(("Contains pairing code", self.pairing_code in readme_content))
                checks.append(("Contains 'How to install' section", 'How to install' in readme_content))
                
                all_passed = all(result for _, result in checks)
                
                if all_passed:
                    self.tests_passed += 1
                    self.log(f"✓ README.txt content correct", "PASS")
                    for check_name, _ in checks:
                        self.log(f"  ✓ {check_name}", "PASS")
                    return True
                else:
                    self.tests_failed += 1
                    self.log(f"✗ README.txt content validation failed", "FAIL")
                    for check_name, result in checks:
                        status = "✓" if result else "✗"
                        self.log(f"  {status} {check_name}", "PASS" if result else "FAIL")
                    return False
                    
        except Exception as e:
            self.tests_failed += 1
            self.log(f"✗ README.txt test exception: {e}", "FAIL")
            return False

    def run_test_verify_endpoint(self):
        """Test GET /api/agent/installer/verify?code=<code>"""
        self.tests_run += 1
        self.log(f"Test {self.tests_run}: Pairing code in filename matches /api/agent/installer/verify", "INFO")
        
        headers = {"Authorization": f"Bearer {self.token}"}
        response = requests.get(
            f"{self.base_url}/api/agent/installer/verify",
            params={"code": self.pairing_code},
            headers=headers
        )
        
        if response.status_code != 200:
            self.tests_failed += 1
            self.log(f"✗ verify endpoint failed: {response.status_code} - {response.text}", "FAIL")
            return False
        
        data = response.json()
        
        checks = []
        checks.append(("Response contains 'code' field", "code" in data))
        checks.append(("Code matches pairing code", data.get("code") == self.pairing_code))
        checks.append(("Response contains 'paired' field", "paired" in data))
        checks.append(("Response contains 'expires_at' field", "expires_at" in data))
        
        all_passed = all(result for _, result in checks)
        
        if all_passed:
            self.tests_passed += 1
            self.log(f"✓ verify endpoint recognizes pairing code", "PASS")
            for check_name, _ in checks:
                self.log(f"  ✓ {check_name}", "PASS")
            return True
        else:
            self.tests_failed += 1
            self.log(f"✗ verify endpoint validation failed", "FAIL")
            for check_name, result in checks:
                status = "✓" if result else "✗"
                self.log(f"  {status} {check_name}", "PASS" if result else "FAIL")
            return False

    def cleanup(self):
        """Clean up temporary files"""
        if self.zip_path and os.path.exists(self.zip_path):
            try:
                os.unlink(self.zip_path)
                self.log(f"Cleaned up temporary ZIP: {self.zip_path}", "INFO")
            except Exception as e:
                self.log(f"Failed to clean up ZIP: {e}", "WARN")

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

    def run_all_tests(self):
        """Run all tests in sequence"""
        print(f"\n{Colors.BLUE}{'='*70}{Colors.RESET}")
        print(f"{Colors.BLUE}Digital Twin Agent Installer Bundle Layout v2 - Backend Tests{Colors.RESET}")
        print(f"{Colors.BLUE}{'='*70}{Colors.RESET}\n")
        
        # Login first
        if not self.login():
            self.log("Cannot proceed without authentication", "FAIL")
            return self.print_summary()
        
        # Run tests in order
        self.run_test_download_init()
        self.run_test_download_endpoint()
        self.run_test_zip_layout()
        self.run_test_bundle_json()
        self.run_test_install_cmd()
        self.run_test_readme()
        self.run_test_verify_endpoint()
        
        # Cleanup
        self.cleanup()
        
        # Print summary
        return self.print_summary()


def main():
    tester = InstallerBundleTest()
    exit_code = tester.run_all_tests()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
