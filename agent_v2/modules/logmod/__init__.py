"""Module 14: Logging.

Public API:
    configure_agent_logging(level=logging.INFO) -> Path
    configure_installer_logging() -> Path
"""
from .setup import configure_agent_logging, configure_installer_logging  # noqa: F401

__all__ = ["configure_agent_logging", "configure_installer_logging"]
