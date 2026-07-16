"""Module 4: Authentication.

DPAPI-backed credential storage. Public API:

    from agent_v2.modules.auth import StoredCredentials, store, load, delete

On Windows uses ``win32cred`` (LocalMachine DPAPI scope). On other platforms
falls back to a 0600-locked JSON file under ProgramData for developer builds
and CI — the actual production agent always runs on Windows.
"""
from .credentials import StoredCredentials, CredentialError, store, load, delete  # noqa: F401

__all__ = ["StoredCredentials", "CredentialError", "store", "load", "delete"]
