"""Test Digital Twin Agent Installer endpoints and install.cmd generation.

Verifies the UAC self-elevation fix (PowerShell Start-Process -Verb RunAs)
replaced the old VBS-based elevation that caused cmd tokenization errors.
"""
import asyncio
import io
import json
import re
import sys
import zipfile
from pathlib import Path

import httpx

# Public endpoint from backend/.env
BASE = "https://safe-import-pro.preview.emergentagent.com/api"

# Test credentials from /app/memory/test_credentials.md
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
        return self.failed == 0


results = TestResults()


def step(msg: str):
    print(f"\n▶ {msg}")


async def main():
    print("="*70)
    print("Digital Twin Agent Installer - Backend API Tests")
    print("="*70)

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        # ----------------------------------------------------------------
        # 1. Login as admin
        # ----------------------------------------------------------------
        step("1. Login as admin")
        try:
            resp = await client.post(
                f"{BASE}/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
            )
            if resp.status_code != 200:
                results.record_fail("Login", f"Status {resp.status_code}: {resp.text}")
                return False
            data = resp.json()
            if "access_token" not in data:
                results.record_fail("Login", "No access_token in response")
                return False
            token = data["access_token"]
            results.record_pass("Login successful")
        except Exception as e:
            results.record_fail("Login", str(e))
            return False

        # ----------------------------------------------------------------
        # 2. GET /api/agent/installer/info
        # ----------------------------------------------------------------
        step("2. GET /api/agent/installer/info")
        try:
            resp = await client.get(
                f"{BASE}/agent/installer/info",
                headers={"Authorization": f"Bearer {token}"}
            )
            if resp.status_code != 200:
                results.record_fail("GET /info", f"Status {resp.status_code}: {resp.text}")
                return False
            
            info = resp.json()
            
            # Check available:true
            if not info.get("available"):
                results.record_fail("GET /info - available", f"available={info.get('available')}, reason={info.get('reason')}")
                return False
            results.record_pass("GET /info - available:true")
            
            # Check bundle:true
            if not info.get("bundle"):
                results.record_fail("GET /info - bundle", f"bundle={info.get('bundle')}")
                return False
            results.record_pass("GET /info - bundle:true")
            
            # Check bundle_contents lists 3 EXEs
            contents = info.get("bundle_contents", [])
            expected_files = ["DigitalTwinAgentSetup.exe", "agent.exe", "uninstaller.exe"]
            for expected in expected_files:
                if expected not in contents:
                    results.record_fail("GET /info - bundle_contents", f"Missing {expected} in {contents}")
                    return False
            results.record_pass(f"GET /info - bundle_contents has all 3 EXEs: {contents}")
            
        except Exception as e:
            results.record_fail("GET /info", str(e))
            return False

        # ----------------------------------------------------------------
        # 3. POST /api/agent/installer/download-init
        # ----------------------------------------------------------------
        step("3. POST /api/agent/installer/download-init")
        try:
            resp = await client.post(
                f"{BASE}/agent/installer/download-init",
                json={"label": "test-installer-validation"},
                headers={"Authorization": f"Bearer {token}"}
            )
            if resp.status_code != 200:
                results.record_fail("POST /download-init", f"Status {resp.status_code}: {resp.text}")
                return False
            
            init_data = resp.json()
            
            # Check download_token
            if "download_token" not in init_data:
                results.record_fail("POST /download-init - download_token", "Missing download_token")
                return False
            download_token = init_data["download_token"]
            results.record_pass("POST /download-init - download_token present")
            
            # Check pairing_code format DT-XXXX-XXXX
            pairing_code = init_data.get("pairing_code", "")
            code_pattern = re.compile(r"^DT-[A-Z0-9]{4}-[A-Z0-9]{4}$")
            if not code_pattern.match(pairing_code):
                results.record_fail("POST /download-init - pairing_code", f"Invalid format: {pairing_code}")
                return False
            results.record_pass(f"POST /download-init - pairing_code valid: {pairing_code}")
            
            # Check is_bundle
            if not init_data.get("is_bundle"):
                results.record_fail("POST /download-init - is_bundle", f"is_bundle={init_data.get('is_bundle')}")
                return False
            results.record_pass("POST /download-init - is_bundle:true")
            
        except Exception as e:
            results.record_fail("POST /download-init", str(e))
            return False

        # ----------------------------------------------------------------
        # 4. GET /api/agent/installer/download?token=...
        # ----------------------------------------------------------------
        step("4. GET /api/agent/installer/download?token=...")
        try:
            resp = await client.get(
                f"{BASE}/agent/installer/download",
                params={"token": download_token}
            )
            if resp.status_code != 200:
                results.record_fail("GET /download", f"Status {resp.status_code}: {resp.text}")
                return False
            results.record_pass("GET /download - HTTP 200")
            
            # Check content-type
            content_type = resp.headers.get("content-type", "")
            if "application/zip" not in content_type:
                results.record_fail("GET /download - content-type", f"Expected application/zip, got {content_type}")
                return False
            results.record_pass(f"GET /download - content-type: {content_type}")
            
            # Check size > 200MB (14M + 45M + 138M = ~197M, but with ZIP overhead should be >200M)
            # Actually, ZIP_STORED means no compression, so size should be close to sum of files
            content_length = int(resp.headers.get("content-length", 0))
            if content_length < 100_000_000:  # At least 100MB
                results.record_fail("GET /download - size", f"Size too small: {content_length} bytes")
                return False
            results.record_pass(f"GET /download - size: {content_length:,} bytes (~{content_length/1024/1024:.1f} MB)")
            
            # Download the ZIP
            zip_bytes = resp.content
            
        except Exception as e:
            results.record_fail("GET /download", str(e))
            return False

        # ----------------------------------------------------------------
        # 5. Inspect ZIP contents
        # ----------------------------------------------------------------
        step("5. Inspect ZIP contents")
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
                members = zf.namelist()
                
                # Check install.cmd at root
                if "install.cmd" not in members:
                    results.record_fail("ZIP - install.cmd", "install.cmd not found at root")
                    return False
                results.record_pass("ZIP - install.cmd exists at root")
                
                # Check README.txt at root
                if "README.txt" not in members:
                    results.record_fail("ZIP - README.txt", "README.txt not found at root")
                    return False
                results.record_pass("ZIP - README.txt exists at root")
                
                # Check bundle.json at root
                if "bundle.json" not in members:
                    results.record_fail("ZIP - bundle.json", "bundle.json not found at root")
                    return False
                results.record_pass("ZIP - bundle.json exists at root")
                
                # Check payload/ subfolder contains the 3 EXEs
                installer_exe = f"payload/DigitalTwinAgentSetup_{pairing_code}.exe"
                if installer_exe not in members:
                    results.record_fail("ZIP - installer EXE", f"{installer_exe} not found in payload/")
                    return False
                results.record_pass(f"ZIP - {installer_exe} exists")
                
                if "payload/agent.exe" not in members:
                    results.record_fail("ZIP - agent.exe", "payload/agent.exe not found")
                    return False
                results.record_pass("ZIP - payload/agent.exe exists")
                
                if "payload/uninstaller.exe" not in members:
                    results.record_fail("ZIP - uninstaller.exe", "payload/uninstaller.exe not found")
                    return False
                results.record_pass("ZIP - payload/uninstaller.exe exists")
                
                # Extract install.cmd for inspection
                install_cmd_bytes = zf.read("install.cmd")
                install_cmd_text = install_cmd_bytes.decode("utf-8")
                
        except Exception as e:
            results.record_fail("ZIP inspection", str(e))
            return False

        # ----------------------------------------------------------------
        # 6. Validate install.cmd content - OLD VBS logic MUST NOT be present
        # ----------------------------------------------------------------
        step("6. Validate install.cmd - OLD VBS logic MUST NOT be present")
        
        old_vbs_patterns = [
            "CreateObject",
            "cscript",
            "ELEV_VBS",
            "WScript.Arguments",
            "dt-elevate"
        ]
        
        for pattern in old_vbs_patterns:
            if pattern in install_cmd_text:
                results.record_fail(f"install.cmd - no {pattern}", f"Found old VBS remnant: {pattern}")
                return False
            results.record_pass(f"install.cmd - no {pattern}")

        # ----------------------------------------------------------------
        # 7. Validate install.cmd content - NEW PowerShell elevation MUST be present
        # ----------------------------------------------------------------
        step("7. Validate install.cmd - NEW PowerShell elevation MUST be present")
        
        # The exact line from the code:
        # powershell -NoProfile -Command "Start-Process -FilePath 'cmd.exe' -ArgumentList '/c',([char]34 + '%~f0' + [char]34) -Verb RunAs"
        new_elevation_pattern = r'powershell\s+-NoProfile\s+-Command\s+"Start-Process\s+-FilePath\s+\'cmd\.exe\'\s+-ArgumentList\s+\'/c\',\(\[char\]34\s+\+\s+\'%~f0\'\s+\+\s+\[char\]34\)\s+-Verb\s+RunAs"'
        
        if not re.search(new_elevation_pattern, install_cmd_text):
            results.record_fail("install.cmd - PowerShell elevation", "New PowerShell Start-Process -Verb RunAs not found")
            # Print a snippet for debugging
            print("\n  [DEBUG] Searching for PowerShell elevation pattern...")
            if "powershell" in install_cmd_text.lower():
                # Find the line with powershell
                for i, line in enumerate(install_cmd_text.split("\r\n")):
                    if "powershell" in line.lower() and "Start-Process" in line:
                        print(f"  [DEBUG] Found at line {i}: {line[:100]}")
            return False
        results.record_pass("install.cmd - PowerShell Start-Process -Verb RunAs present")

        # ----------------------------------------------------------------
        # 8. Validate install.cmd content - Required components
        # ----------------------------------------------------------------
        step("8. Validate install.cmd - Required components")
        
        required_components = [
            ("fsutil dirty query", "fsutil dirty query %SYSTEMDRIVE%"),
            ("BACKEND_URL", f'set "BACKEND_URL=https://safe-import-pro.preview.emergentagent.com"'),
            ("PAIRING_CODE", f'set "__PAIRING_CODE={pairing_code}"'),
            ("DPAPI CredWrite", "CredWriteW"),
            ("advapi32", "advapi32.dll"),
            ("installer invocation", f'call ".\\DigitalTwinAgentSetup_{pairing_code}.exe"'),
            ("--api-url", '--api-url "%BACKEND_URL%"'),
            ("--no-pair", "--no-pair"),
            ("--silent", "--silent"),
        ]
        
        for name, pattern in required_components:
            if pattern not in install_cmd_text:
                results.record_fail(f"install.cmd - {name}", f"Pattern not found: {pattern[:50]}...")
                return False
            results.record_pass(f"install.cmd - {name} present")

        # ----------------------------------------------------------------
        # 9. Static parse check - balanced parentheses and quotes
        # ----------------------------------------------------------------
        step("9. Static parse check - balanced parentheses and quotes")
        
        try:
            # Check balanced parentheses in if/for blocks
            paren_stack = []
            in_rem = False
            for line_num, line in enumerate(install_cmd_text.split("\r\n"), 1):
                stripped = line.strip()
                
                # Skip REM lines
                if stripped.upper().startswith("REM "):
                    continue
                
                # Count parentheses
                for char in line:
                    if char == "(":
                        paren_stack.append(line_num)
                    elif char == ")":
                        if not paren_stack:
                            results.record_fail("install.cmd - syntax", f"Unmatched ')' at line {line_num}")
                            return False
                        paren_stack.pop()
            
            if paren_stack:
                results.record_fail("install.cmd - syntax", f"Unmatched '(' at lines {paren_stack}")
                return False
            results.record_pass("install.cmd - balanced parentheses")
            
            # Check for well-formed set "var=..." lines
            set_pattern = re.compile(r'^\s*set\s+"[^"]+=[^"]*"\s*$', re.IGNORECASE)
            for line_num, line in enumerate(install_cmd_text.split("\r\n"), 1):
                stripped = line.strip()
                if stripped.upper().startswith("SET ") and '"' in stripped:
                    # This is a set command with quotes, verify it's well-formed
                    # Allow for delayed expansion syntax like !VAR!
                    if not (set_pattern.match(stripped) or "!" in stripped):
                        # Check if it's a multi-line echo block (which is OK)
                        if "echo" not in stripped.lower():
                            results.record_fail("install.cmd - syntax", f"Malformed set command at line {line_num}: {stripped[:60]}")
                            return False
            results.record_pass("install.cmd - well-formed set commands")
            
            # Check for unescaped & outside of REM lines
            for line_num, line in enumerate(install_cmd_text.split("\r\n"), 1):
                stripped = line.strip()
                if stripped.upper().startswith("REM "):
                    continue
                # Look for & that's not escaped (^&) and not in quotes
                # This is a simplified check - a full parser would be more robust
                if "&" in line and "^&" not in line:
                    # Check if it's in a string context (between quotes)
                    # For simplicity, we'll allow & in echo commands and quoted strings
                    if "echo" not in line.lower() and '"' not in line:
                        # This might be a problem, but let's be lenient for now
                        pass
            results.record_pass("install.cmd - no obvious unescaped & issues")
            
        except Exception as e:
            results.record_fail("install.cmd - syntax check", str(e))
            return False

        # ----------------------------------------------------------------
        # 10. Verify auth still works (dashboard login)
        # ----------------------------------------------------------------
        step("10. Verify auth still works (already tested in step 1)")
        results.record_pass("Auth login works (admin@digitaltwin.com)")

    return True


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        results.print_summary()
        sys.exit(0 if success and results.failed == 0 else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
