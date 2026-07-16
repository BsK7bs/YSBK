# Digital Twin Platform — PRD

## Original Problem Statement
1. Import the YSBK-main.zip verbatim into `/app/`; get it fully functional end-to-end.
2. Replace the PowerShell + Python-prerequisite install flow with a professional Windows installer (`DigitalTwinAgentSetup.exe`) built via **GitHub Actions Windows runner**. Dashboard exposes a single **Download Agent** button; the installer auto-pairs, registers the service, verifies enrollment, and shows a success screen only after the device is confirmed online.

## What Was Done

### 2026-01-16 — Session 1: Import & bring-up
- Full YSBK-main archive imported verbatim; platform `.env` files preserved.
- All backend + frontend deps installed; bootstrap admin seeded.
- End-to-end verified: `/api/health` OK → login → dashboard → live WebSocket.

### 2026-01-16 — Session 2: PyInstaller EXE + GitHub Actions pipeline
- **Legacy code removed**
  - `backend/app/routers/agent_installer.py` PowerShell script generator → replaced with EXE-serving router.
  - `/app/agent/` (Python zipapp legacy tree) → deleted.
  - `agent_v2/modules/enrollment/bootstrap.py` (bootstrap.dta sidecar flow) → deleted.
  - `frontend/src/components/DownloadInstallerDialog.jsx` (broken bootstrap-token UI) → deleted.
  - `common/paths.py::bundled_bootstrap_dta()` helper → deleted.
- **New backend endpoints** (`/api/agent/installer/*`)
  - `GET /info` — availability, version, size, SHA256.
  - `GET /download` — mints DT-XXXX-YYYY code, streams `DigitalTwinAgentSetup_<code>.exe`, code echoed via `X-Pairing-Code` header.
  - `GET /verify?code=…` — dashboard polls this while operator installs on target box.
  - Falls back to `AGENT_INSTALLER_RELEASE_URL` (GitHub release asset) when local `/app/dist/DigitalTwinAgentSetup.exe` is missing.
- **New installer entry** (`agent_v2/installer/__main__.py`)
  - Parses pairing code from own filename (regex `DT-[A-Z0-9]{4}-[A-Z0-9]{4}`).
  - Pipeline: elevate → dirs → copy → register service → start → pair → persist creds → verify online → success.
  - Success screen shown **only after** verification passes; hard-fails with clear error dialog otherwise.
- **New pairing client** (`agent_v2/modules/enrollment/pairing.py`)
  - Calls `POST /api/agent/pair` (matches backend contract) with hardware snapshot.
  - Persists `device.json` + `credentials.json` under `ProgramData\DigitalTwin`.
- **GitHub Actions workflow** (`.github/workflows/build-agent-installer.yml`)
  - `windows-latest` runner, Python 3.11 x64, PyInstaller 6.6.0.
  - Triggers: `push tag v*.*.*` (auto-attaches to matching GitHub Release) and `workflow_dispatch` (manual + optional custom backend URL).
  - Bakes `DIGITAL_TWIN_BACKEND_URL` into the EXE at build time.
  - Uploads workflow artifact + release asset + SHA256.
- **build.ps1 updated** — `-BackendUrl` param, CI-compatible, produces canonical `DigitalTwinAgentSetup.exe` in `<repo>\dist\`.
- **Dashboard UX** — Old `EnrollDeviceDialog` (multi-tab, PowerShell one-liner, MSI, ZIP) replaced with single "Download Agent" dialog that (1) checks availability, (2) downloads on click, (3) live-polls verify endpoint, (4) shows success card when the device appears in the fleet.
- **Documentation** — README rewritten with the new install flow, endpoints, and CI publish process.

## Auth Credentials
- `admin@digitaltwin.com` / `ChangeMe!2026` — see `/app/memory/test_credentials.md`.

## Backlog / Next Actions
- Publish the first `v2.1.0` tag to trigger the GitHub Actions build (or run it via workflow_dispatch).
- Configure the `DIGITAL_TWIN_BACKEND_URL` repo secret in GitHub to bake the SaaS URL.
- Optional: sign the EXE with an Authenticode certificate in the CI workflow to eliminate SmartScreen prompts.
- Optional: legacy tests under `/app/backend/backend_test.py` and `/app/tests/` reference the deleted PowerShell endpoints and bootstrap tokens — they need refactoring to hit the new `/api/agent/installer/*` surface.
