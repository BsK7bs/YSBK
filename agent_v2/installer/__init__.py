"""Module 1: Windows Installer.

UAC-elevated installer that:
  * loads ``bootstrap.dta`` sidecar (via ``modules.enrollment``);
  * pairs with the backend (``modules.enrollment.pair``);
  * persists credentials (``modules.auth.store``);
  * writes non-sensitive config (``modules.core.save_config``);
  * copies binaries into ``C:\\Program Files\\DigitalTwin`` (``file_layout``);
  * registers the Windows Service (``modules.service.registrar``);
  * verifies end-to-end (``verifier``) before showing ✔.

Everything except ``__main__.py`` and ``gui.py`` is thin glue over the runtime
modules — the installer contains no domain logic of its own.
"""
