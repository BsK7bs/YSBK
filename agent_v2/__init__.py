"""Digital Twin Agent v2 — production-grade Windows agent.

See ``plan.md`` § Phase 7 for architecture. Top-level package layout:
  * ``common``       — shared helpers (paths, logging, sysinfo, version)
  * ``installer``    — UAC-elevated installer (separate binary)
  * ``agent``        — Windows Service runtime + collectors
  * ``uninstaller``  — clean removal utility
  * ``build``        — PyInstaller specs & Windows build script
"""
__version__ = "2.0.0"
