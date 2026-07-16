"""Agent installer download endpoint (v3 — Windows EXE only).

The ONLY supported customer install flow is:

    Dashboard  ->  "Download Agent"  ->  DigitalTwinAgentSetup_DT-XXXX-YYYY.exe
                                          |
                                          v  (double-click, UAC prompt)
                                Install + Service + Pair + Verify
                                          |
                                          v
                              Device appears online in the dashboard

We do NOT ship PowerShell installers, MSI packages, portable ZIPs, or any
"bring-your-own-Python" fallback. The self-contained EXE is produced by
``.github/workflows/build-agent-installer.yml`` on a Windows runner, then
either dropped into ``/app/dist/DigitalTwinAgentSetup.exe`` on the backend
host or fetched at request time from the configured GitHub Release URL.

The download endpoint atomically:
  1. Mints a fresh single-use DT-XXXX-YYYY pairing code for the caller's org
     (calling the same code path the dashboard uses for /api/enrollment/codes).
  2. Streams the compiled EXE back with the code encoded in the filename:
        DigitalTwinAgentSetup_<CODE>.exe
     The installer parses its own argv[0] filename to recover the code, so no
     accompanying JSON, sidecar, or query prompt is needed on the target box.
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
import re
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, StreamingResponse

from ..config import settings
from ..database import get_db
from ..deps import audit_log, get_current_user, require_role
from ..models import ROLE_HIERARCHY
from ..security import generate_enrollment_code
from ..utils import serialize, utcnow

log = logging.getLogger("dta.agent_installer")

router = APIRouter(prefix="/agent/installer", tags=["agent"])

# Local dist directory used by both `agent_v2/build/build.ps1` (developer
# workstations) and the GitHub Actions Windows-runner workflow (release CI).
INSTALLER_PATH = Path(os.environ.get("AGENT_INSTALLER_PATH", "/app/dist/DigitalTwinAgentSetup.exe"))

# Companion binaries expected to sit next to the installer. When both are
# present the /download endpoint serves a self-contained ZIP bundle instead
# of a bare EXE, so operators never see the "agent.exe missing next to
# installer.exe" runtime error from installer/file_layout.py.
AGENT_EXE_PATH       = Path(os.environ.get("AGENT_EXE_PATH",       "/app/dist/agent.exe"))
UNINSTALLER_EXE_PATH = Path(os.environ.get("UNINSTALLER_EXE_PATH", "/app/dist/uninstaller.exe"))

# Public URL of THIS backend as seen from the customer's browser / target
# Windows machine. Baked into the auto-generated install.cmd launcher and
# bundle.json in the download ZIP so the installer knows where to pair,
# even when the frozen agent.exe was built without DIGITAL_TWIN_BACKEND_URL
# at PyInstaller time (which is the case for the artifacts currently on
# this deployment). Explicit env override wins over any header sniffing so
# operators can point a bundle at a canonical DNS name even when the
# dashboard is reached via a preview subdomain.
PUBLIC_BACKEND_URL_ENV = os.environ.get("PUBLIC_BACKEND_URL", "").rstrip("/")


def _resolve_public_backend_url(request: Request) -> str:
    """Best-effort determination of the URL a customer's Windows machine
    should use to reach THIS backend. Priority (highest wins):

      1. Explicit PUBLIC_BACKEND_URL env var (operator override).
      2. Origin header (browsers always send this on same-origin fetches).
      3. Forwarded / X-Forwarded-Host + X-Forwarded-Proto (K8s ingress).
      4. request.base_url (ASGI's parse of scheme+host+port).

    Falls back to a clearly-fake sentinel if none of the above yield a
    plausible https URL - the installer will then surface an actionable
    error instead of hanging on getaddrinfo.
    """
    if PUBLIC_BACKEND_URL_ENV:
        return PUBLIC_BACKEND_URL_ENV

    origin = (request.headers.get("origin") or "").rstrip("/")
    if origin.startswith("http"):
        return origin

    fwd_host = request.headers.get("x-forwarded-host")
    fwd_proto = request.headers.get("x-forwarded-proto", "https")
    if fwd_host:
        return f"{fwd_proto}://{fwd_host}".rstrip("/")

    base = str(request.base_url).rstrip("/")
    if base:
        return base
    return "https://backend.invalid"

# Optional: URL of the latest DigitalTwinAgentSetup.exe published as a GitHub
# release asset. When the local EXE is missing, the backend transparently
# fetches this URL and caches the file to INSTALLER_PATH.
GITHUB_RELEASE_URL: Optional[str] = os.environ.get("AGENT_INSTALLER_RELEASE_URL") or None

INSTALLER_VERSION_HINT = os.environ.get("AGENT_INSTALLER_VERSION", "2.1.0")

_CODE_RE = re.compile(r"^DT-[A-Z0-9]{4}-[A-Z0-9]{4}$")


# ---------------------------------------------------------------------------
# Download token helpers — used by /download-init + native browser downloads.
#
# Native downloads (window.location = /download?token=...) cannot send an
# Authorization header, so we accept a short-lived signed JWT via the
# ?token= query parameter INSTEAD. The token is minted by /download-init
# and is bound to the user + org that created it.
# ---------------------------------------------------------------------------
DL_TOKEN_TTL_SECONDS = 300  # 5 minutes — enough time to click "Download".


def _mint_download_token(user_id: str, org_id: str, role: str, code: str, label: Optional[str]) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "org_id": org_id,
        "role": role,
        "code": code,
        "label": label or "",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=DL_TOKEN_TTL_SECONDS)).timestamp()),
        "type": "installer_download",
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


async def _resolve_user_for_download(
    request: Request,
    token: Optional[str],
) -> tuple[dict, Optional[str]]:
    """Return (user_doc, prebound_code) for the download.

    Order of precedence:
      1. `?token=<jwt>` query param signed by /download-init (native browser
         download flow — can't send Authorization headers on window.location).
      2. `Authorization: Bearer <access_token>` header (legacy path, still
         used by the fetch() based download that shows in-app progress).
    """
    if token:
        try:
            payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        except Exception as exc:
            raise HTTPException(status_code=401, detail=f"Invalid or expired download token ({exc})")
        if payload.get("type") != "installer_download":
            raise HTTPException(status_code=401, detail="Wrong token type for installer download")
        db = get_db()
        user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
        if not user or not user.get("is_active", True):
            raise HTTPException(status_code=401, detail="User not found for download token")
        if user.get("org_id") != payload.get("org_id"):
            raise HTTPException(status_code=401, detail="Token org mismatch")
        # Enforce role >= technician (same as /download's require_role).
        if ROLE_HIERARCHY.get(user.get("role", "viewer"), 0) < ROLE_HIERARCHY["technician"]:
            raise HTTPException(status_code=403, detail="Requires role >= technician")
        return user, payload.get("code")

    # No query token — fall back to Authorization header via get_current_user.
    from ..deps import bearer_scheme

    creds = await bearer_scheme(request)
    if not creds or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing bearer token or ?token= query param")
    try:
        from ..security import decode_token as _decode
        payload = _decode(creds.credentials)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Not an access token")
    db = get_db()
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
    if not user or not user.get("is_active", True):
        raise HTTPException(status_code=401, detail="User not found")
    if ROLE_HIERARCHY.get(user.get("role", "viewer"), 0) < ROLE_HIERARCHY["technician"]:
        raise HTTPException(status_code=403, detail="Requires role >= technician")
    return user, None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _fetch_release_if_needed() -> Optional[Path]:
    """If the local EXE is missing and a GitHub release URL is configured,
    download the release asset once and cache it under INSTALLER_PATH."""
    if INSTALLER_PATH.exists():
        return INSTALLER_PATH
    if not GITHUB_RELEASE_URL:
        return None
    try:
        INSTALLER_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = INSTALLER_PATH.with_suffix(".exe.part")
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            async with client.stream("GET", GITHUB_RELEASE_URL) as r:
                r.raise_for_status()
                with tmp.open("wb") as fh:
                    async for chunk in r.aiter_bytes(1024 * 1024):
                        fh.write(chunk)
        tmp.replace(INSTALLER_PATH)
        log.info("[installer] cached release asset to %s (%d bytes)", INSTALLER_PATH, INSTALLER_PATH.stat().st_size)
        return INSTALLER_PATH
    except Exception as exc:  # noqa: BLE001
        log.error("[installer] failed to fetch release EXE: %s", exc)
        return None


def _sha256(path: Path) -> str:
    """Cache the SHA-256 of the installer keyed by (mtime, size). Real EXEs
    are ~40 MB, so recomputing on every /info hit would be wasteful."""
    st = path.stat()
    key = (str(path), st.st_mtime_ns, st.st_size)
    cached = _SHA256_CACHE.get(key)
    if cached is not None:
        return cached
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    digest = h.hexdigest()
    _SHA256_CACHE.clear()  # single-entry cache — one installer path
    _SHA256_CACHE[key] = digest
    return digest


_SHA256_CACHE: dict[tuple, str] = {}


async def _mint_pairing_code(db, org_id: str, actor_email: str, label: Optional[str] = None) -> str:
    """Create a single-use DT-XXXX-XXXX code (matches /api/enrollment/codes)."""
    code = generate_enrollment_code()
    now = utcnow()
    expires_at = now + timedelta(minutes=settings.ENROLLMENT_CODE_TTL_MINUTES)
    doc = {
        "id": str(uuid.uuid4()),
        "org_id": org_id,
        "code": code,
        "label": label,
        "used": False,
        "used_at": None,
        "used_by_device_id": None,
        "created_by": actor_email,
        "created_at": serialize(now),
        "expires_at": serialize(expires_at),
        "issued_via": "agent_installer_download",
    }
    await db.enrollment_codes.insert_one(doc)
    return code


# ---------------------------------------------------------------------------
# GET /api/agent/installer/info
# ---------------------------------------------------------------------------
@router.get("/info")
async def installer_info(current_user=Depends(get_current_user)):
    """Return metadata about the currently-shipping installer.

    The dashboard uses this to decide whether the Download Agent button
    should be enabled and to display the version + size to operators.
    """
    exe = await _fetch_release_if_needed()
    if exe is None or not exe.exists():
        return {
            "available": False,
            "reason": (
                "DigitalTwinAgentSetup.exe has not been published yet. "
                "Push a git tag (v*.*.*) or run the 'Build Windows Agent Installer' "
                "GitHub Actions workflow to produce it."
            ),
            "filename": "DigitalTwinAgentSetup.exe",
            "version": INSTALLER_VERSION_HINT,
            "size": 0,
            "sha256": None,
            "updated_at": None,
            "source": "github-actions",
        }
    st = exe.stat()
    # If the operator has also published agent.exe (and optionally
    # uninstaller.exe) into /app/dist, the download endpoint will ship a
    # self-contained ZIP. Advertise that so the dashboard can render the
    # right instructions ("unzip, then double-click the .exe inside") and
    # the total download size.
    is_bundle = AGENT_EXE_PATH.exists()
    bundle_size = st.st_size
    if is_bundle:
        bundle_size += AGENT_EXE_PATH.stat().st_size
        if UNINSTALLER_EXE_PATH.exists():
            bundle_size += UNINSTALLER_EXE_PATH.stat().st_size
    return {
        "available": True,
        "filename": exe.name,
        "version": INSTALLER_VERSION_HINT,
        "size": st.st_size,
        "sha256": _sha256(exe),
        "updated_at": serialize(datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)),
        "source": "release" if GITHUB_RELEASE_URL else "local",
        "bundle": is_bundle,
        "bundle_size": bundle_size if is_bundle else st.st_size,
        "bundle_contents": (
            [exe.name, AGENT_EXE_PATH.name] + (
                [UNINSTALLER_EXE_PATH.name] if UNINSTALLER_EXE_PATH.exists() else []
            )
        ) if is_bundle else [exe.name],
        "download_extension": "zip" if is_bundle else "exe",
    }


# ---------------------------------------------------------------------------
# POST /api/agent/installer/download-init
#
# Mints a one-time short-lived download JWT + pairing code the frontend can
# hand to a NATIVE browser download (window.location = /download?token=...).
# Native downloads stream straight to disk via the browser's download
# manager — no JS-side blob buffering, no re-render storms on every 1 MiB
# chunk. This eliminates the "downloading half then dies" symptom that used
# to hit large (200 MB+) bundle transfers on real user networks.
# ---------------------------------------------------------------------------
@router.post("/download-init")
async def download_init(
    label: Optional[str] = None,
    current_user=Depends(require_role("technician")),
):
    exe = await _fetch_release_if_needed()
    if exe is None or not exe.exists():
        raise HTTPException(
            status_code=503,
            detail=(
                "DigitalTwinAgentSetup.exe is not available on this backend yet. "
                "Trigger the 'Build Windows Agent Installer' GitHub Actions workflow "
                "or push a v*.*.* tag; once the artifact is published to /app/dist/ "
                "or the AGENT_INSTALLER_RELEASE_URL, this download will succeed."
            ),
        )
    db = get_db()
    code = await _mint_pairing_code(db, current_user["org_id"], current_user["email"], label)
    token = _mint_download_token(
        current_user["id"], current_user["org_id"], current_user.get("role", "technician"),
        code, label,
    )
    is_bundle = AGENT_EXE_PATH.exists()
    filename = (
        f"DigitalTwinAgentSetup_{code}.zip" if is_bundle
        else f"DigitalTwinAgentSetup_{code}.exe"
    )
    return {
        "download_token": token,
        "expires_in": DL_TOKEN_TTL_SECONDS,
        "pairing_code": code,
        "filename": filename,
        "is_bundle": is_bundle,
    }


# ---------------------------------------------------------------------------
# GET /api/agent/installer/download
# ---------------------------------------------------------------------------
@router.get("/download")
async def download_installer(
    request: Request,
    label: Optional[str] = None,
    token: Optional[str] = Query(default=None, description="Download JWT from /download-init (native browser download flow)"),
):
    """Stream ``DigitalTwinAgentSetup_<code>.exe`` for one-click install.

    Auth: either an ``Authorization: Bearer <access_token>`` header (used by
    the fetch()+progress-bar flow) OR a ``?token=<jwt>`` query parameter
    issued by :func:`download_init` (used by native browser downloads that
    cannot set request headers).

    Flow:
      1. Mint a fresh single-use pairing code for the caller's org (or
         reuse the one embedded in a download JWT, if present).
      2. Locate the compiled EXE (local dist or cached GitHub release).
      3. Stream it back with ``Content-Disposition`` set to
         ``DigitalTwinAgentSetup_DT-XXXX-XXXX.exe`` — the installer parses
         its own filename to recover the pairing code, so the customer
         experience is literally download-and-double-click.
    """
    current_user, prebound_code = await _resolve_user_for_download(request, token)
    exe = await _fetch_release_if_needed()
    if exe is None or not exe.exists():
        raise HTTPException(
            status_code=503,
            detail=(
                "DigitalTwinAgentSetup.exe is not available on this backend yet. "
                "Trigger the 'Build Windows Agent Installer' GitHub Actions workflow "
                "or push a v*.*.* tag; once the artifact is published to /app/dist/ "
                "or the AGENT_INSTALLER_RELEASE_URL, this download will succeed."
            ),
        )

    db = get_db()
    # If the caller came through /download-init the pairing code is already
    # in the token — reuse it so the /verify polling side of the dialog
    # doesn't get a different code than what's baked into the filename.
    if prebound_code:
        code = prebound_code
    else:
        code = await _mint_pairing_code(db, current_user["org_id"], current_user["email"], label)

    # ------------------------------------------------------------------
    # Bundle mode: agent.exe (and optionally uninstaller.exe) is present
    # next to the installer in /app/dist. Ship a ZIP so file_layout.py's
    # copy_agent_files() finds agent.exe next to the installer at extract
    # time. The installer inside the zip is renamed to embed the pairing
    # code so it can still parse it from argv[0].
    # ------------------------------------------------------------------
    if AGENT_EXE_PATH.exists():
        installer_arcname = f"DigitalTwinAgentSetup_{code}.exe"
        public_url = _resolve_public_backend_url(request)

        # install.cmd — the actual thing the user should double-click.
        # It launches the installer .exe with the correct --api-url so
        # pairing hits THIS backend rather than the placeholder URL that
        # was frozen into the EXE at PyInstaller time (when
        # DIGITAL_TWIN_BACKEND_URL was not set at build).
        #
        # 2026-07-16 hardening — three additions on top of the original
        # one-liner ``start "" "%INSTALLER%" --api-url ...``:
        #
        #   1. **UAC self-elevation up-front.** The installer EXE is
        #      built with ``uac_admin=False`` (baking requireAdministrator
        #      into its manifest triggers a UAC dialog BEFORE the Python
        #      interpreter is ready, which hangs CI); at runtime it self-
        #      elevates via ``ShellExecuteW("runas", ...)``. But
        #      ``IsUserAnAdmin()`` returns True on systems where UAC is
        #      relaxed OR the user is in the Administrators group without
        #      an elevated token, so the self-elevation gets skipped and
        #      the copy step later fails with ``PermissionError: [Errno
        #      13] Permission denied: 'C:\\Program Files\\DigitalTwin\\
        #      agent.exe'`` (2026-07-16 field report). Requesting UAC
        #      from install.cmd itself — via ``powershell Start-Process
        #      -Verb RunAs`` — guarantees a real elevated token before
        #      the installer even starts.
        #
        #   2. **Stop any existing DigitalTwinAgent service + kill lingering
        #      agent.exe processes.** If the customer is reinstalling on
        #      top of a previous install the service is still running
        #      and it holds ``agent.exe`` open with a share-deny-write
        #      lock, so the copy step fails even for an admin process.
        #      ``sc stop`` + ``taskkill /F`` releases the lock.
        #
        #   3. **Pause at the end.** A cmd window that vanishes hides any
        #      failure diagnostic the installer wrote to stderr; the
        #      pause gives the operator time to read it.
        install_cmd_bytes = (
            "@echo off\r\n"
            "REM ============================================================\r\n"
            "REM  Digital Twin Agent - one-click installer launcher\r\n"
            "REM  Generated by the backend at download time so the pairing\r\n"
            "REM  step hits the right server no matter how the underlying\r\n"
            "REM  agent.exe was built.\r\n"
            "REM ============================================================\r\n"
            "setlocal EnableExtensions EnableDelayedExpansion\r\n"
            'set "SCRIPT_DIR=%~dp0"\r\n'
            f'set "BACKEND_URL={public_url}"\r\n'
            f'set "INSTALLER=%SCRIPT_DIR%payload\\{installer_arcname}"\r\n'
            'set "INSTALL_ROOT=%ProgramFiles%\\DigitalTwin"\r\n'
            "\r\n"
            "REM --- Sanity check: installer .exe must sit inside payload\\ next\r\n"
            "REM     to this .cmd. If the user forgot to extract the ZIP or\r\n"
            "REM     extracted install.cmd separately from the payload folder,\r\n"
            "REM     bail out with a clear message.\r\n"
            'if not exist "%INSTALLER%" (\r\n'
            "    echo.\r\n"
            "    echo [!] Installer not found at:\r\n"
            "    echo         %INSTALLER%\r\n"
            "    echo.\r\n"
            "    echo     Did you extract the whole ZIP into one folder?\r\n"
            "    echo     Right-click the .zip -> Extract All..., then\r\n"
            "    echo     double-click install.cmd from the extracted folder.\r\n"
            "    echo.\r\n"
            "    pause\r\n"
            "    exit /b 1\r\n"
            ")\r\n"
            "\r\n"
            "REM --- Self-elevate: relaunch this script under UAC if we are\r\n"
            "REM     not already an administrator. Probe elevation with\r\n"
            "REM     `fsutil dirty query %SYSTEMDRIVE%` (requires\r\n"
            "REM     SeManageVolumePrivilege, granted only to elevated admins).\r\n"
            "REM     It has no side effects and works even when LanmanServer is\r\n"
            "REM     disabled (which breaks the older `net session` probe).\r\n"
            "REM\r\n"
            "REM     If not elevated, use PowerShell's Start-Process -Verb RunAs\r\n"
            "REM     to relaunch THIS .cmd under UAC. That's a single line, has no\r\n"
            "REM     quoting pitfalls, and works on every Windows 8+ SKU without\r\n"
            "REM     needing ExecutionPolicy overrides (Start-Process itself is\r\n"
            "REM     not affected by ExecutionPolicy, only .ps1 script invocation\r\n"
            "REM     is). Replaces an older VBS bridge that occasionally emitted\r\n"
            "REM     'The system cannot find the path specified. / Input Error:\r\n"
            "REM     There is no script file specified.' on machines where the\r\n"
            "REM     nested `^&` escaping inside the parenthesized if-block was\r\n"
            "REM     mis-tokenized by cmd.exe (2026-07-16 field report).\r\n"
            ">nul 2>&1 fsutil dirty query %SYSTEMDRIVE%\r\n"
            "if %errorlevel% neq 0 (\r\n"
            "    echo Requesting administrator privileges via UAC ...\r\n"
            "    powershell -NoProfile -Command \"Start-Process -FilePath 'cmd.exe' -ArgumentList '/c',([char]34 + '%~f0' + [char]34) -Verb RunAs\"\r\n"
            "    exit /b\r\n"
            ")\r\n"
            "\r\n"
            "echo.\r\n"
            "echo [+] Elevated. Preparing to install Digital Twin Agent ...\r\n"
            "echo     Target directory: %INSTALL_ROOT%\r\n"
            "echo.\r\n"
            "\r\n"
            "REM ------------------------------------------------------------------\r\n"
            "REM  Drain any pre-existing install so the copy step of the frozen\r\n"
            "REM  installer can overwrite agent.exe in Program Files.\r\n"
            "REM\r\n"
            "REM  The service is registered with a `restart/5000` recovery\r\n"
            "REM  policy, so a naive `sc stop` + `taskkill` gets the process\r\n"
            "REM  killed BUT the Service Control Manager restarts it 5 seconds\r\n"
            "REM  later — which is exactly the window the installer needs to\r\n"
            "REM  copy files. That's what produced the field-reported\r\n"
            "REM  PermissionError even AFTER the earlier elevation fix landed.\r\n"
            "REM\r\n"
            "REM  Correct order:\r\n"
            "REM    1. sc stop     — request a clean shutdown\r\n"
            "REM    2. sc delete   — UNREGISTER the service so SCM stops\r\n"
            "REM                     trying to restart it\r\n"
            "REM    3. taskkill    — force-kill any lingering agent.exe /\r\n"
            "REM                     uninstaller.exe / DigitalTwinAgent.exe\r\n"
            "REM    4. retry-loop  — attempt to `del` the target agent.exe\r\n"
            "REM                     up to ~15 s (2s between tries) so we\r\n"
            "REM                     don't race Windows Defender / SCM\r\n"
            "REM                     completion.\r\n"
            "REM    5. takeown +   — fix any restrictive DACLs / read-only\r\n"
            "REM       icacls +      attributes from a botched prior install\r\n"
            "REM       attrib\r\n"
            "REM    6. rmdir       — best-effort clean slate\r\n"
            "REM ------------------------------------------------------------------\r\n"
            ">nul 2>&1 sc query DigitalTwinAgent\r\n"
            "if %errorlevel% equ 0 (\r\n"
            "    echo Stopping and unregistering existing DigitalTwinAgent service ...\r\n"
            "    >nul 2>&1 sc stop DigitalTwinAgent\r\n"
            "    >nul 2>&1 timeout /t 5 /nobreak\r\n"
            "    >nul 2>&1 sc delete DigitalTwinAgent\r\n"
            "    >nul 2>&1 timeout /t 2 /nobreak\r\n"
            ")\r\n"
            "REM --- Kill any stragglers holding agent.exe open. Includes the\r\n"
            "REM     PythonService.exe wrapper name that pywin32 registers.\r\n"
            "for %%P in (agent.exe uninstaller.exe DigitalTwinAgent.exe PythonService.exe) do >nul 2>&1 taskkill /F /IM %%P /T\r\n"
            "\r\n"
            "REM ------------------------------------------------------------------\r\n"
            "REM  Reset ACLs on a pre-existing install directory so the copy step\r\n"
            "REM  inside the installer .exe can overwrite the binaries. If a\r\n"
            "REM  previous run left %INSTALL_ROOT% owned by SYSTEM or with\r\n"
            "REM  restrictive DACLs, even an elevated Administrator process gets\r\n"
            "REM  PermissionError on shutil.copy2. `takeown` transfers ownership\r\n"
            "REM  to the current admin, `icacls /reset` restores inheritance,\r\n"
            "REM  `icacls /grant Administrators:F` guarantees full write access,\r\n"
            "REM  and finally `attrib -R /S` clears any read-only bits.\r\n"
            "REM  All are wrapped in >nul so a first-install (no folder yet)\r\n"
            "REM  doesn't spam \"file not found\" errors.\r\n"
            "REM ------------------------------------------------------------------\r\n"
            'if exist "%INSTALL_ROOT%" (\r\n'
            "    echo Existing install directory found - resetting permissions ...\r\n"
            "    >nul 2>&1 takeown /F \"%INSTALL_ROOT%\" /R /D Y\r\n"
            "    >nul 2>&1 icacls \"%INSTALL_ROOT%\" /reset /T /C /Q\r\n"
            "    >nul 2>&1 icacls \"%INSTALL_ROOT%\" /grant *S-1-5-32-544:(OI)(CI)F /T /C /Q\r\n"
            "    >nul 2>&1 attrib -R -S -H \"%INSTALL_ROOT%\\*\" /S /D\r\n"
            "\r\n"
            "    REM Retry deleting agent.exe up to 8 x 2 s = 16 s to survive\r\n"
            "    REM Defender scans / SCM stop-pending / thumbnail-cache locks.\r\n"
            "    for /L %%i in (1,1,8) do (\r\n"
            "        if exist \"%INSTALL_ROOT%\\agent.exe\" (\r\n"
            "            >nul 2>&1 del /F /Q \"%INSTALL_ROOT%\\agent.exe\"\r\n"
            "            if exist \"%INSTALL_ROOT%\\agent.exe\" (\r\n"
            "                echo   ... agent.exe still locked, retry %%i/8\r\n"
            "                >nul 2>&1 timeout /t 2 /nobreak\r\n"
            "            )\r\n"
            "        )\r\n"
            "    )\r\n"
            "\r\n"
            "    REM Best-effort: remove the folder outright so the installer\r\n"
            "    REM starts from a clean slate. `rmdir /S /Q` respects locked\r\n"
            "    REM files (they'll simply remain) and does not error out.\r\n"
            "    >nul 2>&1 rmdir /S /Q \"%INSTALL_ROOT%\"\r\n"
            "\r\n"
            "    REM Final guard: if agent.exe is STILL there, abort with a\r\n"
            "    REM clear message so the user isn't left staring at the raw\r\n"
            "    REM PermissionError traceback.\r\n"
            "    if exist \"%INSTALL_ROOT%\\agent.exe\" (\r\n"
            "        echo.\r\n"
            "        echo [!] Could not remove %INSTALL_ROOT%\\agent.exe -\r\n"
            "        echo     it is being held open by another process.\r\n"
            "        echo     Please REBOOT and run install.cmd again.\r\n"
            "        echo.\r\n"
            "        pause\r\n"
            "        exit /b 32\r\n"
            "    )\r\n"
            ")\r\n"
            "\r\n"
            "REM ------------------------------------------------------------------\r\n"
            "REM  Pre-create the install directory ourselves (elevated) with a\r\n"
            "REM  known-good ACL. That way when the installer's internal\r\n"
            "REM  copy_agent_files() calls destination.mkdir(exist_ok=True) it\r\n"
            "REM  becomes a no-op and the subsequent shutil.copy2 opens agent.exe\r\n"
            "REM  in a directory that we KNOW is writable by Administrators.\r\n"
            "REM\r\n"
            "REM  If we cannot write here even after the takeown/rmdir cleanup,\r\n"
            "REM  something outside our control (Enterprise policy / AppLocker /\r\n"
            "REM  Defender's Controlled Folder Access) is blocking Program Files\r\n"
            "REM  writes and no amount of install.cmd cleverness will unblock it.\r\n"
            "REM  Bail out with a diagnostic message instead of letting the user\r\n"
            "REM  stare at a Python traceback in the GUI dialog.\r\n"
            "REM ------------------------------------------------------------------\r\n"
            "if not exist \"%INSTALL_ROOT%\" mkdir \"%INSTALL_ROOT%\" >nul 2>&1\r\n"
            ">nul 2>&1 icacls \"%INSTALL_ROOT%\" /grant *S-1-5-32-544:(OI)(CI)F /T /C /Q\r\n"
            "set \"__WRITE_TEST=%INSTALL_ROOT%\\.dt_writetest_%RANDOM%.tmp\"\r\n"
            "( echo write_test ) > \"!__WRITE_TEST!\" 2>nul\r\n"
            "if not exist \"!__WRITE_TEST!\" (\r\n"
            "    echo.\r\n"
            "    echo [!] Cannot write to %INSTALL_ROOT% even after UAC elevation.\r\n"
            "    echo.\r\n"
            "    echo     This usually means one of:\r\n"
            "    echo       * Windows Defender's \"Controlled Folder Access\" is\r\n"
            "    echo         blocking Program Files modifications by unknown\r\n"
            "    echo         publishers. Temporarily disable it under\r\n"
            "    echo         Windows Security -^> Virus ^& threat protection\r\n"
            "    echo         -^> Manage ransomware protection.\r\n"
            "    echo       * A Group Policy / AppLocker / SRP rule restricts\r\n"
            "    echo         non-MSI writes to Program Files. Contact your IT\r\n"
            "    echo         administrator.\r\n"
            "    echo       * Your account, though marked \"Administrator\", is\r\n"
            "    echo         not actually elevated (rare - happens when UAC\r\n"
            "    echo         is set to \"Never notify\" with a broken filter).\r\n"
            "    echo         Log out and log back in, then rerun install.cmd.\r\n"
            "    echo.\r\n"
            "    pause\r\n"
            "    exit /b 5\r\n"
            ")\r\n"
            ">nul 2>&1 del /F /Q \"!__WRITE_TEST!\"\r\n"
            "echo   ... write access to %INSTALL_ROOT% confirmed.\r\n"
            "\r\n"
            "echo.\r\n"
            "echo Launching installer against %BACKEND_URL% ...\r\n"
            "\r\n"
            "REM ------------------------------------------------------------------\r\n"
            "REM  DPAPI CREDENTIAL BOOTSTRAP\r\n"
            "REM ------------------------------------------------------------------\r\n"
            "REM  The frozen agent.exe reads its device credentials from Windows\r\n"
            "REM  Credential Manager (LocalMachine scope, target=\r\n"
            "REM  \"DigitalTwin/AgentCredentials\") — not from JSON files under\r\n"
            "REM  ProgramData. But the frozen installer.exe never writes DPAPI:\r\n"
            "REM  its DeviceCredentials.save() only writes device.json +\r\n"
            "REM  credentials.json. Result: the running Windows Service boots,\r\n"
            "REM  can't find DPAPI credentials, and sits in \"unpaired-idle\"\r\n"
            "REM  mode forever — the device appears in the dashboard from the\r\n"
            "REM  pair call but never actually reports telemetry.\r\n"
            "REM\r\n"
            "REM  Rather than rebuild the frozen binaries, install.cmd itself\r\n"
            "REM  now performs the pair handshake via PowerShell + writes the\r\n"
            "REM  DPAPI blob directly with a P/Invoke stub against advapi32!\r\n"
            "REM  CredWriteW, and then invokes the installer with --no-pair so\r\n"
            "REM  the frozen installer only does the copy + service-register\r\n"
            "REM  half of the pipeline and doesn't try (and fail) to double-\r\n"
            "REM  consume the pairing code.\r\n"
            "REM\r\n"
            "REM  Everything the PowerShell block below writes is scoped to the\r\n"
            "REM  LocalMachine so the Windows Service (running as LOCAL SYSTEM)\r\n"
            "REM  can decrypt it after reboot without a logged-in user.\r\n"
            "REM ------------------------------------------------------------------\r\n"
            f'set "__PAIRING_CODE={code}"\r\n'
            "set \"__PS_BRIDGE=%TEMP%\\dt-pair-%RANDOM%.ps1\"\r\n"
            "set \"__PS_OUT=%TEMP%\\dt-pair-%RANDOM%.out.json\"\r\n"
            "\r\n"
            "( \r\n"
            "  echo $ErrorActionPreference = 'Stop'\r\n"
            "  echo $backendUrl = $env:DT_BACKEND_URL\r\n"
            "  echo $pairCode  = $env:DT_PAIR_CODE\r\n"
            "  echo $outPath   = $env:DT_OUT_PATH\r\n"
            "  echo try {\r\n"
            "  echo   $hostname = $env:COMPUTERNAME\r\n"
            "  echo   $machineGuid = ''\r\n"
            "  echo   try { $machineGuid = ^(Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Cryptography' -Name MachineGuid -ErrorAction Stop^).MachineGuid } catch { }\r\n"
            "  echo   $osInfo = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue\r\n"
            "  echo   $osName = if ^($osInfo^) { $osInfo.Caption } else { 'Windows' }\r\n"
            "  echo   $osVersion = if ^($osInfo^) { $osInfo.Version } else { '' }\r\n"
            "  echo   $mac = ''\r\n"
            "  echo   try {\r\n"
            "  echo     $adapter = Get-NetAdapter -ErrorAction Stop ^| Where-Object { $_.Status -eq 'Up' -and $_.HardwareInterface } ^| Select-Object -First 1\r\n"
            "  echo     if ^($adapter^) { $mac = ^($adapter.MacAddress -replace '-',':'^).ToLower() }\r\n"
            "  echo   } catch { }\r\n"
            "  echo   $ipAddress = ''\r\n"
            "  echo   try {\r\n"
            "  echo     $ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop ^| Where-Object { $_.IPAddress -notlike '169.254.*' -and $_.IPAddress -ne '127.0.0.1' } ^| Select-Object -First 1\r\n"
            "  echo     if ^($ip^) { $ipAddress = $ip.IPAddress }\r\n"
            "  echo   } catch { }\r\n"
            "  echo   $payload = @{ \r\n"
            "  echo     pairing_code = $pairCode\r\n"
            "  echo     hostname = $hostname\r\n"
            "  echo     machine_guid = $machineGuid\r\n"
            "  echo     os_name = $osName\r\n"
            "  echo     os_version = $osVersion\r\n"
            "  echo     agent_version = '2.1.0'\r\n"
            "  echo     installer_version = '2.1.0'\r\n"
            "  echo     mac_address = $mac\r\n"
            "  echo     ip_address = $ipAddress\r\n"
            "  echo     hardware_fingerprint = $machineGuid\r\n"
            "  echo   } ^| ConvertTo-Json -Compress\r\n"
            "  echo   Write-Host \"[dt] pairing with $backendUrl ...\"\r\n"
            "  echo   $resp = Invoke-RestMethod -Uri ^(\"$backendUrl/api/agent/pair\"^) -Method Post -ContentType 'application/json' -Body $payload -TimeoutSec 30\r\n"
            "  echo   if ^(-not $resp.device_id -or -not $resp.device_api_key^) { throw 'pair response missing device_id or device_api_key' }\r\n"
            "  echo   Write-Host ^(\"[dt] paired device_id=\" + $resp.device_id + \" org_id=\" + $resp.org_id^)\r\n"
            "  echo   $credBlobObj = @{ \r\n"
            "  echo     device_id = $resp.device_id\r\n"
            "  echo     device_api_key = $resp.device_api_key\r\n"
            "  echo     org_id = $resp.org_id\r\n"
            "  echo     backend_url = $backendUrl\r\n"
            "  echo     ws_url = $resp.ws_url\r\n"
            "  echo   } ^| ConvertTo-Json -Compress\r\n"
            "  echo.\r\n"
            "  echo   $sig = @^\"\r\n"
            "  echo using System;\r\n"
            "  echo using System.Runtime.InteropServices;\r\n"
            "  echo public class CredMan {\r\n"
            "  echo   [StructLayout^(LayoutKind.Sequential, CharSet=CharSet.Unicode^)]\r\n"
            "  echo   public struct Cred {\r\n"
            "  echo     public UInt32 Flags; public UInt32 Type; public IntPtr TargetName; public IntPtr Comment;\r\n"
            "  echo     public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;\r\n"
            "  echo     public UInt32 CredentialBlobSize; public IntPtr CredentialBlob;\r\n"
            "  echo     public UInt32 Persist; public UInt32 AttributeCount; public IntPtr Attributes;\r\n"
            "  echo     public IntPtr TargetAlias; public IntPtr UserName;\r\n"
            "  echo   }\r\n"
            "  echo   [DllImport^(\"advapi32.dll\", SetLastError=true, EntryPoint=\"CredWriteW\", CharSet=CharSet.Unicode^)]\r\n"
            "  echo   public static extern bool CredWrite^([In] ref Cred c, [In] UInt32 flags^);\r\n"
            "  echo }\r\n"
            "  echo \"@\r\n"
            "  echo   Add-Type -TypeDefinition $sig -Language CSharp\r\n"
            "  echo   $blobBytes = [System.Text.Encoding]::Unicode.GetBytes^($credBlobObj^)\r\n"
            "  echo   $blobPtr = [System.Runtime.InteropServices.Marshal]::AllocHGlobal^($blobBytes.Length^)\r\n"
            "  echo   [System.Runtime.InteropServices.Marshal]::Copy^($blobBytes, 0, $blobPtr, $blobBytes.Length^)\r\n"
            "  echo   $target = 'DigitalTwin/AgentCredentials'\r\n"
            "  echo   $targetPtr = [System.Runtime.InteropServices.Marshal]::StringToHGlobalUni^($target^)\r\n"
            "  echo   $userPtr = [System.Runtime.InteropServices.Marshal]::StringToHGlobalUni^('digitaltwin-agent'^)\r\n"
            "  echo   $c = New-Object CredMan+Cred\r\n"
            "  echo   $c.Flags = 0\r\n"
            "  echo   $c.Type = 1\r\n"
            "  echo   $c.TargetName = $targetPtr\r\n"
            "  echo   $c.CredentialBlobSize = [UInt32]$blobBytes.Length\r\n"
            "  echo   $c.CredentialBlob = $blobPtr\r\n"
            "  echo   $c.Persist = 2\r\n"
            "  echo   $c.UserName = $userPtr\r\n"
            "  echo   $ok = [CredMan]::CredWrite^([ref]$c, 0^)\r\n"
            "  echo   [System.Runtime.InteropServices.Marshal]::FreeHGlobal^($blobPtr^)\r\n"
            "  echo   [System.Runtime.InteropServices.Marshal]::FreeHGlobal^($targetPtr^)\r\n"
            "  echo   [System.Runtime.InteropServices.Marshal]::FreeHGlobal^($userPtr^)\r\n"
            "  echo   if ^(-not $ok^) { throw ^(\"CredWrite failed rc=\" + [System.Runtime.InteropServices.Marshal]::GetLastWin32Error^(^)^) }\r\n"
            "  echo   Write-Host '[dt] DPAPI credential written to LocalMachine'\r\n"
            "  echo   $out = @{ ok = $true; device_id = $resp.device_id; org_id = $resp.org_id; ws_url = $resp.ws_url } ^| ConvertTo-Json -Compress\r\n"
            "  echo   [System.IO.File]::WriteAllText^($outPath, $out, [System.Text.Encoding]::UTF8^)\r\n"
            "  echo   exit 0\r\n"
            "  echo } catch {\r\n"
            "  echo   $err = $_.Exception.Message\r\n"
            "  echo   Write-Host \"[dt] pair-bridge FAILED: $err\"\r\n"
            "  echo   $out = @{ ok = $false; error = $err } ^| ConvertTo-Json -Compress\r\n"
            "  echo   try { [System.IO.File]::WriteAllText^($outPath, $out, [System.Text.Encoding]::UTF8^) } catch { }\r\n"
            "  echo   exit 1\r\n"
            "  echo }\r\n"
            ") > \"!__PS_BRIDGE!\"\r\n"
            "\r\n"
            "set \"DT_BACKEND_URL=%BACKEND_URL%\"\r\n"
            "set \"DT_PAIR_CODE=%__PAIRING_CODE%\"\r\n"
            "set \"DT_OUT_PATH=!__PS_OUT!\"\r\n"
            "powershell -NoProfile -ExecutionPolicy Bypass -File \"!__PS_BRIDGE!\"\r\n"
            "set BRIDGE_RC=%errorlevel%\r\n"
            ">nul 2>&1 del \"!__PS_BRIDGE!\"\r\n"
            "\r\n"
            "if %BRIDGE_RC% neq 0 (\r\n"
            "    echo.\r\n"
            "    echo [!] Pair-bridge failed. See PowerShell output above for details.\r\n"
            "    echo     The installer will run anyway but the device will stay\r\n"
            "    echo     offline until pairing is re-attempted.\r\n"
            "    echo.\r\n"
            ")\r\n"
            "\r\n"
            "pushd \"%SCRIPT_DIR%payload\"\r\n"
            "if %BRIDGE_RC% equ 0 (\r\n"
            "    echo   ... DPAPI credentials in place, running installer with --no-pair.\r\n"
            f'    call ".\\{installer_arcname}" --api-url "%BACKEND_URL%" --no-pair --silent\r\n'
            ") else (\r\n"
            "    echo   ... falling back to installer-native pair flow.\r\n"
            f'    call ".\\{installer_arcname}" --api-url "%BACKEND_URL%"\r\n'
            ")\r\n"
            "set INSTALL_RC=%errorlevel%\r\n"
            "popd\r\n"
            ">nul 2>&1 del \"!__PS_OUT!\"\r\n"
            "\r\n"
            "echo.\r\n"
            "if %INSTALL_RC% equ 0 (\r\n"
            "    echo Installer finished successfully. You can close this window.\r\n"
            ") else (\r\n"
            "    echo Installer exited with code %INSTALL_RC%.\r\n"
            "    echo Check the log path printed above for details.\r\n"
            ")\r\n"
            "pause\r\n"
            "endlocal\r\n"
            "exit /b %INSTALL_RC%\r\n"
        ).encode("utf-8")

        # Machine-readable manifest. Newer installer builds may look for
        # this file next to themselves and use its backend_url directly,
        # removing the need for the install.cmd wrapper.
        bundle_manifest = {
            "schema_version": 2,
            "pairing_code": code,
            "backend_url": public_url,
            "layout": "payload-subfolder",
            "installer": f"payload/{installer_arcname}",
            "agent": "payload/agent.exe",
            "uninstaller": "payload/uninstaller.exe" if UNINSTALLER_EXE_PATH.exists() else None,
            "entrypoint": "install.cmd",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        import json as _json  # local — keep top-of-file imports minimal
        bundle_json_bytes = _json.dumps(bundle_manifest, indent=2).encode("utf-8")

        readme_bytes = (
            "Digital Twin Agent - Installer bundle\r\n"
            "======================================\r\n\r\n"
            f"Pairing code   : {code}\r\n"
            f"Backend URL    : {public_url}\r\n\r\n"
            "**********************************************************\r\n"
            "*  IMPORTANT:  Double-click ONLY  install.cmd            *\r\n"
            "*  Do NOT run anything inside the payload\\ subfolder      *\r\n"
            "*  directly - it will fail with a permission error.       *\r\n"
            "**********************************************************\r\n\r\n"
            "How to install:\r\n"
            "  1. Extract the WHOLE ZIP into one folder\r\n"
            "     (right-click the .zip -> Extract All...).\r\n"
            "     After extract you should see:\r\n"
            "         install.cmd                <- double-click this\r\n"
            "         README.txt                 (this file)\r\n"
            "         bundle.json\r\n"
            "         payload\\...               <- do not open, do not\r\n"
            "                                     double-click, install.cmd\r\n"
            "                                     handles it for you.\r\n"
            "  2. Double-click install.cmd from the extracted folder.\r\n"
            "  3. Accept the UAC prompt when Windows asks for admin.\r\n"
            "     install.cmd forces the UAC dialog up-front so the\r\n"
            "     installer starts with a real administrator token and\r\n"
            "     can write to C:\\Program Files\\DigitalTwin.\r\n"
            "  4. The installer will copy the service into Program Files,\r\n"
            "     register the DigitalTwinAgent Windows service, pair with\r\n"
            "     the backend using the code above, and confirm success.\r\n\r\n"
            "Silent / GPO mass-deploy (advanced):\r\n"
            f'    payload\\{installer_arcname} --silent \\\r\n'
            f'        --api-url "{public_url}"\r\n'
            "  (You must launch it from an already-elevated cmd or MDT/SCCM\r\n"
            "   task sequence - the .exe itself no longer self-elevates.)\r\n\r\n"
            "Files in this ZIP:\r\n"
            "  install.cmd                       - double-click this\r\n"
            "  README.txt                        - this file\r\n"
            "  bundle.json                       - machine-readable manifest\r\n"
            "  payload\\                          - installer internals:\r\n"
            f"      {installer_arcname}\r\n"
            "      agent.exe                     - Windows service binary\r\n"
        ).encode("utf-8")
        if UNINSTALLER_EXE_PATH.exists():
            readme_bytes += b"      uninstaller.exe               - run to remove\r\n"
        readme_bytes += b"\r\nFor support, contact your Digital Twin administrator.\r\n"

        include_uninstaller = UNINSTALLER_EXE_PATH.exists()
        contents_meta = [f"payload/{installer_arcname}", "payload/agent.exe"] + (
            ["payload/uninstaller.exe"] if include_uninstaller else []
        )

        # ------------------------------------------------------------------
        # ASSEMBLE-THEN-SERVE STRATEGY
        # ------------------------------------------------------------------
        # We used to stream the ZIP straight from a Python generator into
        # an ASGI StreamingResponse with chunked transfer encoding. That
        # approach had two crippling failure modes on real networks:
        #
        #   1. NO CONTENT-LENGTH: Browsers cannot show a real progress
        #      bar or a reliable "download stalled" hint without a
        #      Content-Length header. Chrome in particular has been
        #      observed to abandon chunked downloads that lack it after
        #      an internal idle threshold, leaving the user with a
        #      truncated file and no error.
        #
        #   2. NO RANGE / RESUME: Chunked responses can't be paused or
        #      resumed. A single flaky wifi hiccup at 60% throws away
        #      the entire 200 MB transfer — the download appears to
        #      just "stop halfway".
        #
        # The fix: materialise the ZIP to a small on-disk cache under
        # /tmp/dt-installer-cache/<pairing-code>.zip and then serve it
        # via FileResponse. FastAPI/Starlette's FileResponse emits an
        # accurate Content-Length, supports HTTP Range requests (so the
        # browser can resume interrupted downloads), and lets ingress
        # proxies buffer/serve efficiently. The one-time write is
        # ~1-2 s for a 200 MB bundle on this pod's SSD.
        # ------------------------------------------------------------------
        cache_dir = Path("/tmp/dt-installer-cache")
        cache_dir.mkdir(parents=True, exist_ok=True)
        zip_name = f"DigitalTwinAgentSetup_{code}.zip"
        zip_path = cache_dir / zip_name
        tmp_path = cache_dir / f"{zip_name}.part-{uuid.uuid4().hex}"

        # ZIP_STORED = no compression: EXEs are already opaque binaries
        # so compression gives ~0% ratio and just burns CPU + time.
        #
        # 2026-07-16 hardening — the installer .exe and its agent.exe /
        # uninstaller.exe siblings are now packaged INSIDE a ``payload/``
        # subfolder. That has two customer-facing benefits:
        #
        #   * Users cannot double-click the installer .exe from the root
        #     of the extracted ZIP by mistake — only install.cmd sits
        #     there. Double-clicking the raw .exe bypasses install.cmd's
        #     UAC self-elevation, service-stop, and ACL-reset logic, and
        #     produces the "PermissionError: [Errno 13] Permission
        #     denied: 'C:\\Program Files\\DigitalTwin\\agent.exe'" that
        #     was field-reported in 2026-07-16.
        #   * The ``payload/`` name clearly signals to the user that
        #     these files are internal to the installer and shouldn't be
        #     run directly.
        #
        # install.cmd knows to cd into ``payload\`` before invoking the
        # .exe. The installer's file_layout.copy_agent_files() looks for
        # agent.exe next to sys.executable, which will be inside
        # ``payload\`` — that invariant still holds.
        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
            zf.writestr("install.cmd", install_cmd_bytes)
            zf.writestr("bundle.json", bundle_json_bytes)
            zf.writestr("README.txt", readme_bytes)
            # NB: forward slashes are legal in ZIP member names and are
            # interpreted as directory separators by every mainstream
            # Windows ZIP extractor (Explorer built-in, 7-Zip, WinRAR).
            zf.write(str(exe), arcname=f"payload/{installer_arcname}")
            zf.write(str(AGENT_EXE_PATH), arcname="payload/agent.exe")
            if include_uninstaller:
                zf.write(str(UNINSTALLER_EXE_PATH), arcname="payload/uninstaller.exe")
        tmp_path.replace(zip_path)
        final_size = zip_path.stat().st_size

        # Housekeeping: purge cached ZIPs older than 1 h so the cache
        # doesn't grow unbounded across many pairing codes.
        cutoff = datetime.now(timezone.utc).timestamp() - 3600
        for old in cache_dir.glob("DigitalTwinAgentSetup_*.zip"):
            try:
                if old.stat().st_mtime < cutoff:
                    old.unlink(missing_ok=True)
            except FileNotFoundError:
                pass

        await audit_log(
            db, current_user["org_id"], current_user, "agent_installer.download",
            target=code,
            metadata={
                "filename": zip_name,
                "mode": "bundle-file",
                "contents": contents_meta,
                "size": final_size,
            },
        )
        log.info(
            "[installer] SERVING %s (%d bytes) to user=%s org=%s (contents=%s)",
            zip_name, final_size, current_user["email"], current_user["org_id"], contents_meta,
        )
        return FileResponse(
            path=str(zip_path),
            media_type="application/zip",
            filename=zip_name,
            headers={
                "Cache-Control": "no-store",
                "X-Pairing-Code": code,
                "X-Installer-Version": INSTALLER_VERSION_HINT,
                "X-Bundle-Mode": "zip-file",
                # Content-Length is set automatically by FileResponse.
                # Accept-Ranges is set automatically by Starlette so the
                # browser can resume interrupted downloads mid-transfer.
            },
        )

    # ------------------------------------------------------------------
    # Legacy single-EXE mode (agent.exe not published beside installer).
    # Kept for backward compatibility; operator must manually place
    # agent.exe next to the downloaded installer before running it.
    # ------------------------------------------------------------------
    await audit_log(
        db, current_user["org_id"], current_user, "agent_installer.download",
        target=code, metadata={"filename": exe.name, "size": exe.stat().st_size, "mode": "single"},
    )
    filename = f"DigitalTwinAgentSetup_{code}.exe"
    log.info("[installer] served %s (%d bytes) to user=%s org=%s", filename, exe.stat().st_size,
             current_user["email"], current_user["org_id"])
    return FileResponse(
        path=str(exe),
        media_type="application/vnd.microsoft.portable-executable",
        filename=filename,
        headers={
            "Cache-Control": "no-store",
            "X-Pairing-Code": code,
            "X-Installer-Version": INSTALLER_VERSION_HINT,
            "X-Bundle-Mode": "single",
        },
    )


# ---------------------------------------------------------------------------
# GET /api/agent/installer/verify?code=DT-XXXX-XXXX
#   Polled by the dashboard while the operator installs the agent so we can
#   flip the "Waiting..." card to "Device is online" without a manual refresh.
# ---------------------------------------------------------------------------
@router.get("/verify")
async def verify_installer_progress(code: str, current_user=Depends(get_current_user)):
    code = (code or "").strip().upper()
    if not _CODE_RE.match(code):
        raise HTTPException(status_code=400, detail="Malformed pairing code")
    db = get_db()
    tok = await db.enrollment_codes.find_one(
        {"code": code, "org_id": current_user["org_id"]},
        {"_id": 0, "code": 1, "used": 1, "used_at": 1, "used_by_device_id": 1, "expires_at": 1},
    )
    if not tok:
        raise HTTPException(status_code=404, detail="Unknown pairing code")
    device = None
    if tok.get("used_by_device_id"):
        device = await db.devices.find_one(
            {"id": tok["used_by_device_id"], "org_id": current_user["org_id"]},
            {"_id": 0, "id": 1, "hostname": 1, "status": 1, "online": 1, "last_seen": 1},
        )
    return {
        "code": code,
        "paired": bool(tok.get("used")),
        "device": device,
        "expires_at": tok.get("expires_at"),
    }
