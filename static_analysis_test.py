#!/usr/bin/env python3
"""
Static Analysis of Installer Source Files
Verifies the 5-step fix pattern for Bug #2 (config.json write permission issues)
"""
import re
import sys
from pathlib import Path
from typing import List, Tuple

class InstallerSourceAnalyzer:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failures = []

    def log_test(self, name: str, passed: bool, details: str = ""):
        """Log test result"""
        self.tests_run += 1
        if passed:
            self.tests_passed += 1
            print(f"  ✅ {name}")
            if details:
                print(f"     {details}")
        else:
            self.tests_failed += 1
            self.failures.append(f"{name}: {details}")
            print(f"  ❌ {name}")
            if details:
                print(f"     {details}")

    def check_pattern(self, content: str, pattern: str, description: str, file_name: str) -> bool:
        """Check if a pattern exists in the content"""
        if re.search(pattern, content, re.IGNORECASE | re.MULTILINE | re.DOTALL):
            self.log_test(description, True, f"Found in {file_name}")
            return True
        else:
            self.log_test(description, False, f"NOT found in {file_name}")
            return False

    def analyze_nsis(self, file_path: Path) -> bool:
        """Analyze DigitalTwinAgentSetup.nsi"""
        print("\n" + "="*70)
        print("ANALYZING: DigitalTwinAgentSetup.nsi (NSIS Script)")
        print("="*70)
        
        content = file_path.read_text(encoding='utf-8')
        all_ok = True
        
        # 1. Robust ProgramData resolution with fallbacks
        patterns = [
            (r'ReadEnvStr.*ProgramData', "ProgramData env var read"),
            (r'ReadEnvStr.*ALLUSERSPROFILE', "ALLUSERSPROFILE fallback"),
            (r'ReadEnvStr.*SystemDrive', "SystemDrive fallback"),
            (r'C:\\ProgramData', "Hardcoded C:\\ProgramData fallback"),
        ]
        for pattern, desc in patterns:
            if not self.check_pattern(content, pattern, f"1. {desc}", "NSIS"):
                all_ok = False
        
        # 2. CreateDirRecursive function with verification
        if not self.check_pattern(content, r'Function\s+CreateDirRecursive', "2. CreateDirRecursive function", "NSIS"):
            all_ok = False
        if not self.check_pattern(content, r'CreateDirectory.*\$9', "2. CreateDirectory call", "NSIS"):
            all_ok = False
        if not self.check_pattern(content, r'IfFileExists.*\$9', "2. Directory existence check", "NSIS"):
            all_ok = False
        
        # 3. Canary write test (.perm-check.tmp)
        if not self.check_pattern(content, r'\.perm-check\.tmp', "3. Canary file (.perm-check.tmp)", "NSIS"):
            all_ok = False
        if not self.check_pattern(content, r'FileOpen.*\.perm-check\.tmp.*w', "3. Canary write", "NSIS"):
            all_ok = False
        if not self.check_pattern(content, r'FileOpen.*\.perm-check\.tmp.*r', "3. Canary read-back", "NSIS"):
            all_ok = False
        if not self.check_pattern(content, r'digital-twin-perm-check', "3. Canary content verification", "NSIS"):
            all_ok = False
        
        # 4. config.json validation
        if not self.check_pattern(content, r'Delete.*config\.json', "4. Delete old config.json", "NSIS"):
            all_ok = False
        if not self.check_pattern(content, r'FileOpen.*config\.json.*w', "4. Write config.json", "NSIS"):
            all_ok = False
        if not self.check_pattern(content, r'IfFileExists.*config\.json', "4. config.json existence check", "NSIS"):
            all_ok = False
        if not self.check_pattern(content, r'FileOpen.*config\.json.*r', "4. config.json read-back", "NSIS"):
            all_ok = False
        if not self.check_pattern(content, r'StrLen.*\$R7', "4. config.json non-empty check", "NSIS"):
            all_ok = False
        
        # 5. Error messages mentioning "service NOT registered"
        if not self.check_pattern(content, r'service.*NOT.*registered', "5. Error: service NOT registered", "NSIS"):
            all_ok = False
        if not self.check_pattern(content, r'MessageBox.*MB_ICONSTOP', "5. Error MessageBox with ICONSTOP", "NSIS"):
            all_ok = False
        
        return all_ok

    def analyze_cmd(self, file_path: Path) -> bool:
        """Analyze install_helpers.cmd"""
        print("\n" + "="*70)
        print("ANALYZING: install_helpers.cmd (MSI CustomAction)")
        print("="*70)
        
        content = file_path.read_text(encoding='utf-8')
        all_ok = True
        
        # 1. Robust ProgramData resolution
        patterns = [
            (r'%ProgramData%', "ProgramData env var"),
            (r'%ALLUSERSPROFILE%', "ALLUSERSPROFILE fallback"),
            (r'%SystemDrive%', "SystemDrive fallback"),
            (r'C:\\ProgramData', "Hardcoded C:\\ProgramData fallback"),
        ]
        for pattern, desc in patterns:
            if not self.check_pattern(content, pattern, f"1. {desc}", "CMD"):
                all_ok = False
        
        # 2. Directory creation with verification
        if not self.check_pattern(content, r'mkdir.*PROGDATA', "2. mkdir command", "CMD"):
            all_ok = False
        if not self.check_pattern(content, r'if not exist.*PROGDATA', "2. Directory existence check", "CMD"):
            all_ok = False
        if not self.check_pattern(content, r'exit /b 10', "2. Exit code 10 (mkdir failed)", "CMD"):
            all_ok = False
        
        # 3. Canary write test
        if not self.check_pattern(content, r'\.perm-check\.tmp', "3. Canary file (.perm-check.tmp)", "CMD"):
            all_ok = False
        if not self.check_pattern(content, r'>.*PERM_CHECK.*echo', "3. Canary write", "CMD"):
            all_ok = False
        if not self.check_pattern(content, r'set /p.*PERM_READBACK.*<', "3. Canary read-back", "CMD"):
            all_ok = False
        if not self.check_pattern(content, r'digital-twin-perm-check', "3. Canary content", "CMD"):
            all_ok = False
        if not self.check_pattern(content, r'exit /b 11', "3. Exit code 11 (write denied)", "CMD"):
            all_ok = False
        if not self.check_pattern(content, r'exit /b 12', "3. Exit code 12 (read-back failed)", "CMD"):
            all_ok = False
        
        # 4. config.json validation
        if not self.check_pattern(content, r'del.*config\.json', "4. Delete old config.json", "CMD"):
            all_ok = False
        if not self.check_pattern(content, r'>.*config\.json', "4. Write config.json", "CMD"):
            all_ok = False
        if not self.check_pattern(content, r'if not exist.*config\.json', "4. config.json existence check", "CMD"):
            all_ok = False
        if not self.check_pattern(content, r'for %%A in.*config\.json.*%%~zA', "4. config.json size check", "CMD"):
            all_ok = False
        if not self.check_pattern(content, r'type.*config\.json', "4. config.json readability check", "CMD"):
            all_ok = False
        if not self.check_pattern(content, r'exit /b 13', "4. Exit code 13 (file vanished)", "CMD"):
            all_ok = False
        if not self.check_pattern(content, r'exit /b 14', "4. Exit code 14 (empty write)", "CMD"):
            all_ok = False
        if not self.check_pattern(content, r'exit /b 15', "4. Exit code 15 (read-locked)", "CMD"):
            all_ok = False
        
        # 5. Guard rail in :svc_install refusing service registration
        if not self.check_pattern(content, r':svc_install', "5. :svc_install section", "CMD"):
            all_ok = False
        if not self.check_pattern(content, r'if not exist.*config\.json.*refusing', "5. Guard rail: refuse service without config.json", "CMD"):
            all_ok = False
        if not self.check_pattern(content, r'exit /b 25', "5. Exit code 25 (config missing)", "CMD"):
            all_ok = False
        
        return all_ok

    def analyze_inno(self, file_path: Path) -> bool:
        """Analyze DigitalTwinAgent.iss"""
        print("\n" + "="*70)
        print("ANALYZING: DigitalTwinAgent.iss (Inno Setup Script)")
        print("="*70)
        
        content = file_path.read_text(encoding='utf-8')
        all_ok = True
        
        # 1. WriteBootstrapConfig function
        if not self.check_pattern(content, r'procedure WriteBootstrapConfig', "1. WriteBootstrapConfig procedure", "Inno"):
            all_ok = False
        
        # 2. ForceDirectories with return check
        if not self.check_pattern(content, r'ForceDirectories\(DirPath\)', "2. ForceDirectories call", "Inno"):
            all_ok = False
        if not self.check_pattern(content, r'if not ForceDirectories', "2. ForceDirectories return check", "Inno"):
            all_ok = False
        if not self.check_pattern(content, r'DirExists\(DirPath\)', "2. DirExists post-check", "Inno"):
            all_ok = False
        
        # 3. Canary write test
        if not self.check_pattern(content, r'\.perm-check\.tmp', "3. Canary file (.perm-check.tmp)", "Inno"):
            all_ok = False
        if not self.check_pattern(content, r'SaveStringsToFile\(TmpPath', "3. Canary write (SaveStringsToFile)", "Inno"):
            all_ok = False
        if not self.check_pattern(content, r'LoadStringsFromFile\(TmpPath', "3. Canary read-back (LoadStringsFromFile)", "Inno"):
            all_ok = False
        if not self.check_pattern(content, r'digital-twin-perm-check', "3. Canary content", "Inno"):
            all_ok = False
        
        # 4. config.json validation
        if not self.check_pattern(content, r'DeleteFile\(ProgramDataConfigPath\)', "4. Delete old config.json", "Inno"):
            all_ok = False
        if not self.check_pattern(content, r'SaveStringsToFile\(ProgramDataConfigPath', "4. Write config.json", "Inno"):
            all_ok = False
        if not self.check_pattern(content, r'FileExists\(ProgramDataConfigPath\)', "4. config.json existence check", "Inno"):
            all_ok = False
        if not self.check_pattern(content, r'LoadStringsFromFile\(ProgramDataConfigPath', "4. config.json read-back", "Inno"):
            all_ok = False
        if not self.check_pattern(content, r'Length\(ReadBack\)', "4. config.json non-empty check", "Inno"):
            all_ok = False
        
        # 5. Error messages with mbError and "service NOT registered"
        if not self.check_pattern(content, r'mbError', "5. Error MsgBox with mbError", "Inno"):
            all_ok = False
        if not self.check_pattern(content, r'service.*NOT.*registered', "5. Error: service NOT registered", "Inno"):
            all_ok = False
        if not self.check_pattern(content, r'Abort', "5. Abort on failure", "Inno"):
            all_ok = False
        
        # 6. ACL tightening only after validation
        if not self.check_pattern(content, r'icacls.*\(OI\)\(CI\)', "6. ACL with (OI)(CI) inheritance", "Inno"):
            all_ok = False
        
        return all_ok

    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*70)
        print("STATIC ANALYSIS SUMMARY")
        print("="*70)
        print(f"Total checks: {self.tests_run}")
        print(f"Passed: {self.tests_passed}")
        print(f"Failed: {self.tests_failed}")
        
        if self.failures:
            print("\n❌ FAILED CHECKS:")
            for failure in self.failures:
                print(f"  - {failure}")
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        print(f"\nSuccess rate: {success_rate:.1f}%")
        print("="*70)
        
        return self.tests_failed == 0


def main():
    print("="*70)
    print("Digital Twin Platform - Installer Source Static Analysis")
    print("Verifying Bug #2 fixes (config.json write permission handling)")
    print("="*70)
    
    analyzer = InstallerSourceAnalyzer()
    
    # Analyze all three installer source files
    nsis_path = Path("/app/agent/installer/msi/DigitalTwinAgentSetup.nsi")
    cmd_path = Path("/app/agent/installer/msi/install_helpers.cmd")
    inno_path = Path("/app/agent/installer/inno/DigitalTwinAgent.iss")
    
    all_ok = True
    
    if nsis_path.exists():
        if not analyzer.analyze_nsis(nsis_path):
            all_ok = False
    else:
        print(f"\n❌ File not found: {nsis_path}")
        all_ok = False
    
    if cmd_path.exists():
        if not analyzer.analyze_cmd(cmd_path):
            all_ok = False
    else:
        print(f"\n❌ File not found: {cmd_path}")
        all_ok = False
    
    if inno_path.exists():
        if not analyzer.analyze_inno(inno_path):
            all_ok = False
    else:
        print(f"\n❌ File not found: {inno_path}")
        all_ok = False
    
    # Print summary
    all_passed = analyzer.print_summary()
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
