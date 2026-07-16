"""Module 13: Diagnostics.

Assembles + uploads periodic snapshots to ``/api/agents/diagnostics``. Also
persists a sanitised copy to ``ProgramData\\DigitalTwin\\diagnostics.json`` for
offline support inspection.
"""
from .engine import DiagnosticsEngine  # noqa: F401

__all__ = ["DiagnosticsEngine"]
