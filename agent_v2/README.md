# Digital Twin Agent v2 — Modular Architecture

Production-grade Windows agent + installer built as **16 independent modules**.
See [`../plan.md`](../plan.md) § Phase 7 for design rationale.

## The 16 modules

| # | Module                    | Responsibility                                              |
|---|---------------------------|-------------------------------------------------------------|
| 1 | `installer/`              | UAC-elevated installer (separate binary)                    |
| 2 | `modules/core/`           | **Agent Core** — orchestrator + config                     |
| 3 | `modules/enrollment/`     | `bootstrap.dta` loader + `/api/agents/pair` client          |
| 4 | `modules/auth/`           | DPAPI-backed credential store                               |
| 5 | `modules/telemetry/`      | Metrics collection + framing + push loop                    |
| 6 | `modules/inventory/`      | Hardware + software inventory refresh                       |
| 7 | `modules/health/`         | Client-side health scoring (belt-and-braces vs backend)     |
| 8 | `modules/prediction/`     | Client-side trend hints                                     |
| 9 | `modules/alerts/`         | Client-side threshold alerts                                |
|10 | `modules/remote_actions/` | Handles incoming action requests over WS                    |
|11 | `modules/ws_client/`      | Resilient WebSocket transport                               |
|12 | `modules/offline_queue/`  | On-disk rolling queue for offline periods                   |
|13 | `modules/diagnostics/`    | Snapshots + uploads to `/api/agents/diagnostics`            |
|14 | `modules/logmod/`         | Rotating file + stderr log setup                            |
|15 | `modules/self_healing/`   | Watchdog / heartbeat supervision / auto-restart             |
|16 | `modules/service/`        | pywin32 Windows Service registrar + framework               |

**Design contract:** no module imports another module's internals. All
inter-module dependencies flow through public `__init__.py` APIs and are
constructor-injected by the Agent Core orchestrator.

## Tree

```
agent_v2/
├── common/          # shared utilities (paths, versions, sysinfo)
├── installer/       # module 1  (separate binary)
├── modules/         # modules 2–16
│   ├── core/            # 2. Agent Core (orchestrator + config)
│   ├── enrollment/     # 3. Enrollment
│   ├── auth/           # 4. Authentication (DPAPI)
│   ├── telemetry/      # 5. Telemetry Engine
│   ├── inventory/      # 6. Inventory Engine
│   ├── health/         # 7. Health Engine
│   ├── prediction/     # 8. Prediction Engine
│   ├── alerts/         # 9. Alert Engine
│   ├── remote_actions/ # 10. Remote Actions
│   ├── ws_client/      # 11. WebSocket Client
│   ├── offline_queue/  # 12. Offline Queue
│   ├── diagnostics/    # 13. Diagnostics
│   ├── logmod/         # 14. Logging
│   ├── self_healing/   # 15. Self Healing (watchdog)
│   ├── service/        # 16. Windows Service (registrar + framework)
│   └── collectors_bridge.py
├── agent/__main__.py            # thin shim → modules.core.main
├── uninstaller/__main__.py
└── build/                        # PyInstaller specs + build.ps1
```

## Building (Windows 10 / 11, x64)

1. Prereqs: Python 3.11 x64, git, PowerShell 5.1+.
2. `cd agent_v2\build && powershell -ExecutionPolicy Bypass -File .\build.ps1 -Clean`
3. Artifacts appear in `<repo>\dist\`:
   * `DigitalTwinAgentSetup.exe`
   * `agent.exe`
   * `uninstaller.exe`
   * `DigitalTwinAgent-v2.0.0-windows-x64.zip`

## Dev testing (Linux + Windows without a compiled EXE)

```bash
# Terminal 1 — backend already running under supervisor
cd /app
PYTHONPATH=. python -m agent_v2.installer --bootstrap /path/to/bootstrap.dta --install-dir /tmp/DigitalTwin-dev
# Then run the agent in the foreground:
PYTHONPATH=. python -m agent_v2.agent
```

On non-Windows the DPAPI store falls back to `%ProgramData%/DigitalTwin/credentials.dev.json` (0600),
and service registration is skipped. Every module is otherwise exercised identically.

## Extending

Each module ships an `__init__.py` that names its public API in `__all__`.
To add a new module:

1. Create `agent_v2/modules/<name>/` with `__init__.py` + implementation files.
2. Expose the public class/functions in `__init__.py`.
3. Wire it up **only** in `modules/core/orchestrator.py` — no peer imports.
4. Add its heartbeat name to the watchdog registration.

## Onboarding flow (recap)

1. Admin → dashboard → **Devices → Download Installer**.
2. Dashboard mints a bootstrap token via `POST /api/installers/tokens` and packages the ZIP with `bootstrap.dta`.
3. User right-clicks the EXE → **Run as administrator**.
4. Installer runs the 8-step flow (elevate → sidecar → pair → DPAPI → config → register service → start → verify).
5. Device online in **< 30 seconds**. If ANY step fails the installer surfaces a clear error and a full log path.
