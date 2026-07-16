"""Windows path constants for installed files.

Only non-sensitive files live under ``ProgramData``; secrets (device_api_key)
are stored via DPAPI/Credential Manager (see ``agent/credentials.py``).
"""
import os
import sys
from pathlib import Path

SERVICE_NAME = "DigitalTwinAgent"
SERVICE_DISPLAY_NAME = "Digital Twin Agent"
SERVICE_DESCRIPTION = (
    "Streams live telemetry, inventory, and health assessments to the "
    "Digital Twin Platform. Enables remote diagnostics and safe remote actions."
)
CREDENTIAL_TARGET = "DigitalTwin/AgentCredentials"


def program_files_dir() -> Path:
    """Return ``C:\\Program Files\\DigitalTwin`` — read-only install root."""
    base = os.environ.get("ProgramFiles", r"C:\Program Files")
    return Path(base) / "DigitalTwin"


def program_data_dir() -> Path:
    """Return ``C:\\ProgramData\\DigitalTwin`` — writable non-sensitive state."""
    base = os.environ.get("ProgramData", r"C:\ProgramData")
    return Path(base) / "DigitalTwin"


def log_dir() -> Path:
    return program_data_dir() / "logs"


def queue_dir() -> Path:
    return program_data_dir() / "queue"


def diagnostics_path() -> Path:
    return program_data_dir() / "diagnostics.json"


def config_path() -> Path:
    return program_data_dir() / "config.json"


def installer_temp_dir() -> Path:
    base = os.environ.get("TEMP") or os.environ.get("TMP") or r"C:\Windows\Temp"
    return Path(base)


def ensure_data_dirs() -> None:
    for p in (program_data_dir(), log_dir(), queue_dir()):
        p.mkdir(parents=True, exist_ok=True)


def running_frozen() -> bool:
    """True when running as a PyInstaller-produced EXE."""
    return getattr(sys, "frozen", False)
