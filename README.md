# Digital Twin Platform

FastAPI + MongoDB backend, React 19 dashboard, and a native Windows desktop
agent (PyInstaller EXE). The **only** supported install path is:

```
Dashboard  →  Download Agent  →  DigitalTwinAgentSetup_<code>.exe
                                       │
                                       ▼  double-click (UAC prompt)
                                 Install + Service + Pair + Verify
                                       │
                                       ▼
                             Device appears online
```

There is no PowerShell installer, no Python prerequisite on the target, no
bootstrap sidecar, and no `pip install` on customer machines.

## Publishing the Windows installer

`DigitalTwinAgentSetup.exe` is produced by
[`.github/workflows/build-agent-installer.yml`](.github/workflows/build-agent-installer.yml)
on a `windows-latest` runner:

- **Automatic**: push a tag matching `v*.*.*` → workflow runs → EXE is
  attached to the matching GitHub Release.
- **Manual**: run the `Build Windows Agent Installer` workflow from the
  Actions tab (optionally overriding the backend URL).

For local dev builds on a Windows box:

```powershell
powershell -ExecutionPolicy Bypass -File agent_v2\build\build.ps1 `
    -Clean `
    -BackendUrl "https://cloud.digitaltwin.example"
```

Drop the produced `DigitalTwinAgentSetup.exe` into `/app/dist/` on the
backend host (or set `AGENT_INSTALLER_RELEASE_URL` to a public release asset
URL) and the dashboard's **Download Agent** button will start serving it
immediately.

## Endpoints (installer)

| Method | Path                                            | Purpose                                                                                 |
|--------|-------------------------------------------------|-----------------------------------------------------------------------------------------|
| GET    | `/api/agent/installer/info`                     | Version, size, SHA256, availability.                                                    |
| GET    | `/api/agent/installer/download?label=…`         | Mints a fresh DT-XXXX-YYYY code, streams `DigitalTwinAgentSetup_<code>.exe`.            |
| GET    | `/api/agent/installer/verify?code=DT-…`         | Poll while the operator installs; returns `{paired, device}` when the device is online. |

## Installer contract

The installer parses the pairing code from its own filename (regex
`DT-[A-Z0-9]{4}-[A-Z0-9]{4}`), then performs:

1. Elevate (UAC).
2. Create `%ProgramData%\DigitalTwin`.
3. Copy binaries into `%ProgramFiles%\DigitalTwin`.
4. Register + start the `DigitalTwinAgent` Windows Service.
5. `POST /api/agent/pair` with the code + hardware snapshot.
6. Persist `device.json` + `credentials.json` (DPAPI-protected).
7. Poll the backend until the device is confirmed online.
8. Show a success screen — **only after** verification succeeds.

If any step fails the installer stops, shows an error dialog with the
failing step + reason, and never silently continues.

## Local development

```bash
# Backend
cd backend && pip install -r requirements.txt
python seed_admin.py        # bootstrap admin@digitaltwin.com / ChangeMe!2026
sudo supervisorctl restart backend

# Frontend
cd frontend && yarn install --ignore-engines
sudo supervisorctl restart frontend
```
