"""Module 3: Enrollment (v3 — pairing-code only).

The only supported enrollment path exchanges a DT-XXXX-YYYY pairing code
(embedded in the installer filename) for permanent device credentials via
``POST /api/agent/pair``. The legacy ``bootstrap.dta`` sidecar flow has been
removed.

Public API:
    from agent_v2.modules.enrollment import DeviceCredentials, PairError
    from agent_v2.modules.enrollment import pair, verify_online
"""
from .pairing import DeviceCredentials, PairError, pair, verify_online  # noqa: F401

__all__ = [
    "DeviceCredentials", "PairError", "pair", "verify_online",
]
