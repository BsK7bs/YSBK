"""Module 15: Self Healing.

Watchdog that supervises the other engines. Each loop registers a heartbeat;
if it stalls beyond ``max_silence`` the watchdog logs a warning and (in Phase
7.5 will) trigger a graceful restart of the corresponding task.
"""
from .watchdog import Watchdog  # noqa: F401

__all__ = ["Watchdog"]
