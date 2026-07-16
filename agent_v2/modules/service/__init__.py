"""Module 16: Windows Service.

Two submodules:
  * ``registrar`` — pywin32-based install / remove / start / stop / query.
  * ``framework`` — ``win32serviceutil.ServiceFramework`` subclass that hosts
    the Agent Core orchestrator.
"""
from . import registrar  # noqa: F401
from . import framework  # noqa: F401

__all__ = ["registrar", "framework"]
