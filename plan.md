# Digital Twin Platform — plan.md

## 1) Objectives
- Prove the **core workflow** works end-to-end: org/user auth → enrollment code → device enrollment → device API key auth → WebSocket telemetry → device list/digital twin reads with strict tenant isolation. ✅
- Build a production-ready MVP SaaS: premium UI + multi-tenant RBAC + device monitoring + alerts + notifications + remote actions (permissioned) + audit logs. ✅
- Ship a **completely new production-grade Windows Agent architecture (Phase 7)** — separate installer + service, per-org signed bootstrap installer, native pywin32 service, DPAPI credential storage, zero manual config. **30-second onboarding** from install → dashboard.

---

## Phases 1–6 — status (frozen from previous iterations)
- Phase 1 (Core POC): ✅ Completed
- Phase 2 (V1 App Development): ✅ Completed
- Phase 3 (Agent V1 — legacy Windows-first): ✅ Completed *(now being fully replaced by Phase 7)*
- Phase 4 (Hardening + Scale): 🟡 Partially completed
- Phase 5 (Health Score Engine V1): ✅ Completed (38/38 tests)
- Phase 6 (Alert Engine V1 + Notification Center + Software Policy): 🟡 In progress

---

## Phase 7 — Agent v2 (Complete Rewrite — Production-Grade)

### 7.1 Goal
Within **30 seconds** after installation + pairing, a newly installed computer must automatically appear in the Digital Twin dashboard and begin streaming live telemetry. Onboarding must be as reliable and simple as Datadog / CrowdStrike / NinjaOne. **Everything is driven by backend APIs — no manual JSON, no ACL manipulation, no NSSM, no config.enc.**

### 7.2 Non-negotiable design decisions (locked by product owner)
| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **Per-organization custom installer** downloaded from dashboard | End user runs one EXE, zero prompts, zero pairing codes |
| 2 | **PyInstaller single-EXE** (Python) | Reuse existing modular collectors |
| 3 | **Native `pywin32` / `win32serviceutil`** Windows Service | No NSSM. SCM-native. Auto-recovery. |
| 4 | **DPAPI / Windows Credential Manager** for secrets | Native OS crypto, per-machine, no plain-text tokens |
| 5 | **Installer and Agent are SEPARATE binaries** | Installer only bootstraps & registers service; Agent owns runtime |

### 7.3 Onboarding flow (30-second target)
```
Admin (Dashboard)                       Endpoint machine
────────────────────                    ────────────────
1. Click "Download Installer"           
   → Backend generates per-org         
     BootstrapToken (JWT, single-use   
     or multi-use, org-scoped, TTL)    
2. Backend builds/serves               
   DigitalTwinAgentSetup.exe with      
   the token + backend URL             
   embedded via config sidecar         
                                       3. User double-clicks EXE
                                       4. Installer:
                                          a. Elevates (UAC)
                                          b. Extracts agent.exe → C:\Program Files\DigitalTwin
                                          c. Registers Windows Service (pywin32)
                                          d. Calls POST /api/agents/pair
                                              → receives device_id + device_api_key
                                          e. Persists creds via DPAPI to Credential Manager
                                          f. Starts service
                                          g. Verifies enrollment (GET /api/agents/{id}/verify)
                                          h. Shows ✔ or clear error dialog
                                       5. Service (agent.exe) starts:
                                          - Reads DPAPI creds
                                          - Opens WS /ws/agent
                                          - Streams heartbeat + telemetry
                                       6. Device appears on dashboard within ~5-10s
```

### 7.4 Backend contract (new)

**Collections**
- `bootstrap_tokens` — `{ id, org_id, jwt_token, label, created_by, created_at, expires_at, max_uses, use_count, revoked, single_use }`
- `agent_diagnostics` — `{ device_id, org_id, ts, installer_version, agent_version, service_status, ws_state, last_heartbeat, last_telemetry, last_error, ip, mac, os }`

**Endpoints (all under `/api/installers/*` and `/api/agents/*`)**

Admin-only (JWT auth):
- `POST /api/installers/tokens` → create BootstrapToken `{ label, single_use, max_uses?, ttl_hours }` → returns token id + short label
- `GET /api/installers/tokens` → list active tokens
- `DELETE /api/installers/tokens/{id}` → revoke
- `GET /api/installers/download` (query: `token_id`) → returns `DigitalTwinAgentSetup.exe` with `bootstrap.dta` sidecar (or streams a wrapper containing token). Falls back to portable ZIP w/ config sidecar when Windows build not present.
- `GET /api/installers/config?token_id=` → JSON `{ bootstrap_token, backend_url }` (sidecar payload — used by installer at runtime if no baked config)
- `GET /api/installers/agents` (query: `token_id?`) → list devices enrolled via a token (for admin visibility)

Installer/agent-facing (no JWT — uses BootstrapToken then device_api_key):
- `POST /api/agents/pair` — body `{ bootstrap_token, hostname, os_name, os_version, hardware_id, mac_address, ip_address, cpu, ram_gb, disk_gb, serial_number, installer_version, agent_version }` → `{ device_id, device_api_key, ws_url, backend_url }`
- `POST /api/agents/verify` — body `{ device_id, device_api_key }` → `{ ok, enrolled_at, ws_url }`
- `POST /api/agents/diagnostics` — body `{ device_id, device_api_key, diagnostics }` → `{ ok }`
- `GET /api/agents/{device_id}/diagnostics` (admin JWT) → latest diagnostics doc for the device

### 7.5 Client architecture — `/app/agent_v2/` (16 independent modules)
```
agent_v2/
├── common/                       # shared utilities (paths, versions, sysinfo)
├── installer/                    # 1. Windows Installer (separate binary)
│   ├── __main__.py               #    orchestrates 8-step install
│   ├── gui.py                    #    tkinter wizard
│   ├── file_layout.py            #    copies binaries into Program Files
│   └── verifier.py               #    post-install verification
├── modules/                      # 15 runtime modules (independent packages)
│   ├── core/                     # 2. Agent Core  — orchestrator + config
│   ├── enrollment/               # 3. Enrollment  — bootstrap + pair
│   ├── auth/                     # 4. Authentication — DPAPI credential store
│   ├── telemetry/                # 5. Telemetry Engine
│   ├── inventory/                # 6. Inventory Engine
│   ├── health/                   # 7. Health Engine (client-side pre-score)
│   ├── prediction/               # 8. Prediction Engine (trend hints)
│   ├── alerts/                   # 9. Alert Engine (client-side thresholds)
│   ├── remote_actions/           # 10. Remote Actions executor
│   ├── ws_client/                # 11. WebSocket Client (resilient)
│   ├── offline_queue/            # 12. Offline Queue (on-disk)
│   ├── diagnostics/              # 13. Diagnostics uploader
│   ├── logmod/                   # 14. Logging setup
│   ├── self_healing/             # 15. Watchdog / recovery
│   ├── service/                  # 16. Windows Service (registrar + framework)
│   └── collectors_bridge.py      #     bridge to legacy modular collectors
├── agent/__main__.py             #     thin shim → modules.core.main
├── uninstaller/__main__.py       #     matching uninstaller
└── build/                        #     PyInstaller specs + build.ps1
```

Design contract: **no module imports another module's internals**. All
inter-module dependencies flow through the ``__init__.py`` public API of the
importee and are constructor-injected by the Agent Core orchestrator.

### 7.6 Local state layout on Windows
- **Program files (read-only)**: `C:\Program Files\DigitalTwin\`
  - `installer.exe`, `agent.exe`, `uninstaller.exe`, `LICENSE.txt`, `README.txt`
- **ProgramData (writable, non-sensitive)**: `C:\ProgramData\DigitalTwin\`
  - `config.json` — `{ log_level, telemetry_interval, backend_url }` (no secrets)
  - `logs\agent-YYYYMMDD.log`
  - `logs\installer-YYYYMMDD.log`
  - `diagnostics.json` — last local snapshot for support
  - `queue\` — offline queue directory
- **DPAPI / Credential Manager (secure per-machine)**
  - Target: `DigitalTwin/AgentCredentials`
  - Payload: JSON `{ device_id, device_api_key }` encrypted with `LocalMachine` DPAPI scope

### 7.7 Windows Service registration (via pywin32)
- Service name: `DigitalTwinAgent`
- Display name: `Digital Twin Agent`
- Start type: `AUTO_START` (with delayed start)
- Recovery: restart on 1st, 2nd, and subsequent failures (via `sc failure ... reset=86400`)
- Runs as: `LocalSystem`
- Uses `win32serviceutil.ServiceFramework`:
  - `SvcDoRun` → runs asyncio main loop
  - `SvcStop` → graceful cancel of asyncio tasks, closes WS

### 7.8 Installer verification steps (all must PASS before showing ✔ success)
1. Prerequisites — Windows ≥ 10, .NET already present (no install required for Python EXE)
2. Files extracted successfully to Program Files
3. Windows Service registered
4. `/api/agents/pair` returned `device_id`
5. DPAPI store wrote credential and reads back correctly
6. Service started (SCM query state == RUNNING)
7. Service opened a WS connection (verified via `/api/agents/{id}/verify` + last_seen check within 30s)
8. Diagnostics snapshot uploaded successfully

If ANY step fails, installer displays a clear labelled error, dumps full log to `%TEMP%\digitaltwin-install-<ts>.log`, and exits with a non-zero code. **No silent failures.**

### 7.9 Diagnostics page (dashboard)
Per-device diagnostics tab shows (from `/api/agents/{device_id}/diagnostics`):
- Enrollment status ✔ / ✖
- Windows Service status (RUNNING / STOPPED / PAUSED)
- Last heartbeat timestamp (relative)
- Backend connectivity (HTTPS OK / FAILED)
- WebSocket connectivity (state + last close code/reason)
- Last telemetry upload timestamp
- Last error (message + stack trace excerpt)
- Agent version, Installer version, OS, Hostname
- Reload / Download logs / Restart service (via existing remote actions)

### 7.10 Cleanup of legacy code (removed / deprecated)
- Old `/api/installer/*` endpoints (install.ps1, install.bat, DigitalTwinAgentSetup.exe, agent-bundle.zip, enroll-link) → **removed**
- Old `/api/enrollment/enroll` endpoint (public device endpoint) → **removed** (still keep `/enrollment/codes/*` for CSV bulk import & QR)
- Old `agent/digital_twin_agent/*` (config.enc / NSSM / ACL manipulation) → **retained on disk for reference only, no longer loaded by backend or docs**
- Frontend `DevicesPage` "Enrollment Codes / One-liner / QR" section → **replaced** by "Download Custom Installer" panel + per-token management

### 7.11 Phase 7 user stories
1. **As an Admin**, I click "Download Custom Installer" in the dashboard, select single-use or multi-use, and receive a signed EXE that I can email to any employee.
2. **As an Employee (endpoint user)**, I double-click the EXE, click Install, and 30 seconds later my machine appears on the dashboard streaming live metrics — I entered nothing.
3. **As an Admin**, if enrollment fails I get an actionable error dialog with a "Copy logs" button, and no service is left behind in a half-broken state.
4. **As an Admin**, I open the Diagnostics tab for a device and see enrollment/service/WS/heartbeat/last-error at a glance.
5. **As an Admin**, I can revoke a bootstrap token in one click and prevent further enrollments without breaking existing devices.
6. **As an Auditor**, every enrollment via a bootstrap token is recorded in the audit log with token id + label + hardware id.

### 7.12 Phase 7 exit gate
- Backend endpoints all pass automated tests (positive + negative + revoked-token + expired-token + reuse-of-single-use paths)
- PyInstaller build script produces two Windows PE executables (installer.exe, agent.exe) — verified via `build.ps1 --check`
- Documentation covers Windows build, install, uninstall, upgrade
- Dashboard shows real device < 30s after `installer.exe` completes on a clean Windows 10/11 VM

---

## Next Actions (immediate)
1. Implement backend `/api/installers/*` and `/api/agents/*` per section 7.4
2. Deprecate & remove legacy `installer.py` and public `/enrollment/enroll`
3. Build `/app/agent_v2/` codebase (installer + agent, DPAPI, pywin32)
4. Frontend: new "Download Installer" and per-device Diagnostics UI
5. Backend end-to-end tests via testing_agent_v3
6. README with Windows build instructions
