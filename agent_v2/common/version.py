"""Single source of truth for installer + agent versions and defaults.

BACKEND URL is embedded at build time. This is safe because:
  * Digital Twin is a SaaS — one backend URL for the whole cloud tenancy.
  * The backend URL is not a secret; every browser that loads the dashboard
    already knows it. Bootstrap tokens / pairing codes provide the security.

Build-time override:
    DIGITAL_TWIN_BACKEND_URL=https://staging.digitaltwin.cloud python -m PyInstaller ...
"""
import os

INSTALLER_VERSION = "2.1.0"
AGENT_VERSION = "2.1.0"
BUILD_CHANNEL = "stable"
USER_AGENT = f"DigitalTwinAgent/{AGENT_VERSION} ({BUILD_CHANNEL})"

# Fixed cloud backend for the SaaS. Overridable at build time via env var.
DEFAULT_BACKEND_URL: str = os.environ.get(
    "DIGITAL_TWIN_BACKEND_URL",
    "https://cloud.digitaltwin.example",  # replace with real prod URL at build
).rstrip("/")
