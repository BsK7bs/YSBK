"""Rotating file logging for installer + agent runtime.

Design:
  * Installer logs land in ``%TEMP%\\digitaltwin-install-<ts>.log`` — owned by
    the invoking admin. No ACL games.
  * Agent logs land in ``C:\\ProgramData\\DigitalTwin\\logs\\agent-YYYYMMDD.log``
    with rotation (10 MB × 7 files).
  * Both mirror to stderr so pywin32 forwards output to the Windows Event Log.
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
from datetime import datetime
from pathlib import Path

from ...common import paths

_FMT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


def _root(level: int = logging.INFO) -> logging.Logger:
    r = logging.getLogger()
    r.setLevel(level)
    for h in list(r.handlers):
        r.removeHandler(h)
    return r


def configure_installer_logging() -> Path:
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    log_file = paths.installer_temp_dir() / f"digitaltwin-install-{ts}.log"
    r = _root()
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(logging.Formatter(_FMT))
    r.addHandler(fh)
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(logging.Formatter(_FMT))
    r.addHandler(sh)
    logging.getLogger("dta.installer").info("installer logging → %s", log_file)
    return log_file


def configure_agent_logging(level: int = logging.INFO) -> Path:
    paths.ensure_data_dirs()
    log_file = paths.log_dir() / f"agent-{datetime.utcnow().strftime('%Y%m%d')}.log"
    r = _root(level)
    fh = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=7, encoding="utf-8",
    )
    fh.setFormatter(logging.Formatter(_FMT))
    r.addHandler(fh)
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(logging.Formatter(_FMT))
    r.addHandler(sh)
    logging.getLogger("dta.agent").info("agent logging → %s", log_file)
    return log_file
