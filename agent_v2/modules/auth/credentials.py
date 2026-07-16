"""DPAPI credential store (Windows Credential Manager, LocalMachine scope).

Schema stored under target ``DigitalTwin/AgentCredentials``:

    {
      "device_id":       "...",
      "device_api_key":  "dtk_...",
      "org_id":          "...",
      "backend_url":     "https://...",
      "ws_url":          "wss://.../api/ws/agent"
    }

Why DPAPI: native OS crypto, per-machine scope so the service can decrypt
after reboot without a logged-in user, no third-party crypto library, no
shared secret to protect.
"""
from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict, dataclass
from typing import Optional

from ...common.paths import CREDENTIAL_TARGET, program_data_dir

log = logging.getLogger("dta.auth")


@dataclass
class StoredCredentials:
    device_id: str
    device_api_key: str
    org_id: str
    backend_url: str
    ws_url: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))

    @classmethod
    def from_json(cls, raw: str) -> "StoredCredentials":
        return cls(**json.loads(raw))


class CredentialError(Exception):
    pass


_ON_WINDOWS = sys.platform == "win32"
_FALLBACK = program_data_dir() / "credentials.dev.json"


def _win_store(creds: StoredCredentials) -> None:
    import win32cred  # type: ignore
    win32cred.CredWrite({
        "Type": win32cred.CRED_TYPE_GENERIC,
        "TargetName": CREDENTIAL_TARGET,
        "UserName": "digitaltwin-agent",
        "CredentialBlob": creds.to_json(),
        "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE,
    }, 0)
    log.info("credentials written to DPAPI (LocalMachine)")


def _win_load() -> Optional[StoredCredentials]:
    import win32cred  # type: ignore
    import pywintypes  # type: ignore
    try:
        row = win32cred.CredRead(CREDENTIAL_TARGET, win32cred.CRED_TYPE_GENERIC, 0)
    except pywintypes.error as exc:
        if getattr(exc, "winerror", None) == 1168:  # NOT_FOUND
            return None
        raise CredentialError(f"DPAPI read failed: {exc}") from exc
    blob = row.get("CredentialBlob")
    if isinstance(blob, bytes):
        try:
            text = blob.decode("utf-16-le").rstrip("\x00")
        except UnicodeDecodeError:
            text = blob.decode("utf-8", errors="replace").rstrip("\x00")
    else:
        text = str(blob)
    return StoredCredentials.from_json(text)


def _win_delete() -> None:
    import win32cred  # type: ignore
    import pywintypes  # type: ignore
    try:
        win32cred.CredDelete(CREDENTIAL_TARGET, win32cred.CRED_TYPE_GENERIC, 0)
    except pywintypes.error as exc:
        if getattr(exc, "winerror", None) != 1168:
            raise CredentialError(f"DPAPI delete failed: {exc}") from exc


def _fallback_store(creds: StoredCredentials) -> None:
    _FALLBACK.parent.mkdir(parents=True, exist_ok=True)
    _FALLBACK.write_text(creds.to_json(), encoding="utf-8")
    try:
        _FALLBACK.chmod(0o600)
    except OSError:
        pass
    log.warning("credentials → dev fallback %s (not DPAPI)", _FALLBACK)


def _fallback_load() -> Optional[StoredCredentials]:
    if not _FALLBACK.exists():
        return None
    return StoredCredentials.from_json(_FALLBACK.read_text(encoding="utf-8"))


def _fallback_delete() -> None:
    if _FALLBACK.exists():
        _FALLBACK.unlink()


def store(creds: StoredCredentials) -> None:
    if _ON_WINDOWS:
        try:
            return _win_store(creds)
        except ImportError as exc:
            raise CredentialError(f"pywin32 required on Windows: {exc}") from exc
    _fallback_store(creds)


def load() -> Optional[StoredCredentials]:
    if _ON_WINDOWS:
        try:
            return _win_load()
        except ImportError:
            log.warning("pywin32 missing — falling back for read")
    return _fallback_load()


def delete() -> None:
    if _ON_WINDOWS:
        try:
            _win_delete()
            return
        except ImportError:
            pass
    _fallback_delete()
