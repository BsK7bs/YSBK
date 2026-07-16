"""Module 2: Agent Core.

Single source of truth for the runtime lifecycle. The Core:
  * loads DPAPI credentials (via ``modules.auth``);
  * builds each engine with explicit dependencies (no peer imports);
  * hosts them as asyncio tasks and supervises via the Watchdog;
  * shuts everything down cleanly when the stop event fires.

Public API:
    class Orchestrator:
        async run(stop_event) -> int
        def build() -> None
    main() -> int
"""
from .orchestrator import Orchestrator, main  # noqa: F401
from .config import load_config, save_config  # noqa: F401

__all__ = ["Orchestrator", "main", "load_config", "save_config"]
