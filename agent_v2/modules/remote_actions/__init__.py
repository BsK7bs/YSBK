"""Module 10: Remote Actions.

Handles incoming ``{"type":"action", ...}`` frames delivered over the WS.
Each action kind maps to a safe, permission-checked executor. Results are
reported back over the same WS as ``{"type":"action_result"}``.

Current V1 kinds: ``refresh_inventory``, ``collect_diagnostic``,
``restart_agent``. Additional destructive kinds (restart/shutdown/kill_process
etc.) must be explicitly enabled per-org on the server — the client-side
executor whitelists them here.
"""
from .executor import RemoteActionExecutor  # noqa: F401

__all__ = ["RemoteActionExecutor"]
