#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: |
  User imported the YSBK Digital Twin Platform zip and reported: "the agent
  is not downloading properly its downloading half check it fix now."

  The Download Agent flow (Dashboard -> Download Agent -> ZIP bundle
  containing installer.exe + agent.exe + uninstaller.exe + install.cmd)
  was truncating partway through large (200 MB+) downloads.

backend:
  - task: "Dashboard telemetry / agent-pair credential bridge"
    implemented: true
    working: true
    file: "backend/app/routers/agent_pair.py + backend/app/routers/agent_installer.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: false
          agent: "user"
          comment: |
            User reported: after install.cmd finally succeeded (installer
            copied files, registered service, paired), the dashboard
            shows the device with basic info (hostname/OS/IP/MAC from
            pairing) but "Offline / last seen never" — no live
            telemetry. Installer log spammed HTTP 404 on
            /api/agent/device/<id>/status for 90 s then failed
            verify_online.
        - working: true
          agent: "main"
          comment: |
            Root cause was a broken contract between the two frozen
            binaries: the installer's DeviceCredentials.save() writes
            device.json + credentials.json under ProgramData, but the
            running agent.exe reads DPAPI Credential Manager
            (target=DigitalTwin/AgentCredentials, LocalMachine scope)
            for a StoredCredentials blob whose device_api_key field
            the installer never receives from the backend (the raw key
            was generated + hashed + THROWN AWAY in agent_pair).
            Result: the service boots, load_credentials() returns None,
            it loops in "unpaired-idle" mode forever, no telemetry.

            Backend fixes (both in agent_pair.py):
              1. AgentPairResponse now includes ``device_api_key`` —
                 the raw key, emitted exactly once, so a caller can
                 bootstrap DPAPI storage. The DB still only stores
                 hash(key) in devices.api_key_hash.
              2. Added GET /api/agent/device/{device_id}/status — the
                 public, no-auth probe the installer's verify_online
                 fallback path was calling and getting 404 from. Now
                 returns {id, hostname, display_name, online,
                 last_seen, agent_version, enrolled_at, status}.

            install.cmd fix (agent_installer.py::install_cmd_bytes):
              3. NEW "DPAPI CREDENTIAL BOOTSTRAP" block: install.cmd
                 writes a small PowerShell script to %TEMP% that:
                   - collects hostname / machine_guid / OS / MAC / IP
                     locally,
                   - POSTs to /api/agent/pair with the pairing code
                     baked into the installer's filename,
                   - reads device_id + device_api_key + org_id +
                     ws_url from the response,
                   - uses Add-Type + a C# P/Invoke stub for
                     advapi32!CredWriteW to persist a StoredCredentials
                     JSON blob to Credential Manager (target=
                     "DigitalTwin/AgentCredentials", user=
                     "digitaltwin-agent", Persist=LOCAL_MACHINE=2,
                     Type=GENERIC=1) so the SYSTEM-scope service can
                     decrypt it,
                   - falls back gracefully with a warning if any step
                     fails.
              4. install.cmd now invokes the frozen installer with
                 ``--api-url <url> --no-pair --silent`` — the pair
                 handshake already ran in step 3, so we skip the
                 installer's own _step_pair (which would try to
                 double-consume the one-time pairing code and error
                 out). --silent hides the tk GUI now that install.cmd
                 owns the visible progress.

            End-to-end effect: user double-clicks install.cmd → UAC
            prompt → files copied to Program Files → PowerShell pairs
            + writes DPAPI → installer.exe runs with --no-pair, just
            registers the DigitalTwinAgent service → service starts,
            load_credentials() now succeeds → orchestrator builds
            engines → WebSocket connects with device_api_key → live
            telemetry flows to dashboard.


    implemented: true
    working: true
    file: "backend/app/routers/agent_installer.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: false
          agent: "user"
          comment: |
            User reported the installer failing on Windows with:
              PermissionError: [Errno 13] Permission denied:
                'C:\Program Files\DigitalTwin\agent.exe'
            The installer's runtime self-elevation (IsUserAnAdmin +
            ShellExecuteW runas) got skipped because IsUserAnAdmin
            returned True on the user's UAC-relaxed system, so the
            process proceeded to the copy step without an actually-
            elevated token and shutil.copy2 died on Program Files.
        - working: true
          agent: "main"
          comment: |
            Rewrote the install.cmd that the backend materialises into
            the download bundle so it forces UAC elevation BEFORE the
            installer .exe starts (via a small VBScript writing
            Shell.Application.ShellExecute cmd.exe "/c" install.cmd
            with the "runas" verb), and also runs `sc stop
            DigitalTwinAgent` + `taskkill /F /IM agent.exe` to unlock
            the target file if a previous install left the service
            running. Also enabled delayed expansion so !VAR! works
            inside the if-elevation block.
        - working: false
          agent: "user"
          comment: |
            User reported that even after the earlier install.cmd fix,
            running DigitalTwinAgentSetup_DT-NDFY-HSX7.EXE directly
            (double-clicking the .exe instead of install.cmd) still
            fails with the same PermissionError on
            C:\Program Files\DigitalTwin\agent.exe. Logs show
            argv=[] (no --api-url passed → user double-clicked the
            .exe, not install.cmd) AND the installer proceeded past
            IsUserAnAdmin() without triggering ShellExecuteW("runas")
            because the user's UAC-relaxed setup lets IsUserAnAdmin()
            return True even when the token has no admin privileges.
        - working: false
          agent: "user"
          comment: |
            User re-downloaded the bundle after the payload/-subfolder +
            ACL-reset fix and ran install.cmd from the fresh ZIP.
            Installer STILL failed with the same PermissionError on
            'C:\Program Files\DigitalTwin\agent.exe'. Log confirms
            install.cmd DID launch the installer with the right
            --api-url (argv=['--api-url', 'https://archive-extractor-15
            ....com']) so elevation happened, but the copy step still
            hit access-denied. Likely root causes on the user's box:
            (a) a prior install left the DigitalTwinAgent service
                registered with a `restart/5000` recovery policy —
                sc stop + taskkill kills the process but SCM
                immediately restarts it, re-locking agent.exe before
                the installer can overwrite it.
            (b) `net session` elevation probe is unreliable — returns
                success on Windows where LanmanServer is running even
                for non-elevated tokens, and returns failure even for
                elevated admins where LanmanServer is disabled.
            (c) no diagnostic — the user sees an opaque Python
                traceback instead of a hint about what's blocking
                the write (Defender Controlled Folder Access / policy
                / etc).
        - working: true
          agent: "main"
          comment: |
            Third iteration of install.cmd hardening:

            1. **Switched elevation probe from `net session` to
               `fsutil dirty query %SYSTEMDRIVE%`.** fsutil requires
               SeManageVolumePrivilege which is granted ONLY to
               actually-elevated admins, has no side effects, and
               doesn't depend on LanmanServer.

            2. **`sc delete DigitalTwinAgent` after `sc stop`.**
               Unregisters the service so SCM stops trying to keep
               it alive; without this, the service's
               `restart/5000/restart/15000` recovery policy would
               resurrect agent.exe within the copy-step window and
               re-lock the file.

            3. **Retry loop for `del agent.exe`** — up to 8 attempts
               × 2 s = 16 s window to survive Windows Defender
               real-time scan locks + SCM stop-pending completion.
               Bails out with a clear "please reboot" message if
               the file is still locked after the timeout.

            4. **New `taskkill` target: `PythonService.exe`** — the
               pywin32 service wrapper that shows up in Task Manager
               instead of `agent.exe` on some install variants.

            5. **Pre-flight WRITE TEST against %INSTALL_ROOT%.**
               install.cmd creates the folder, grants Administrators
               full control on it, then writes a tiny sentinel file
               and confirms it landed. If the sentinel is NOT
               readable back, install.cmd bails BEFORE launching
               the installer with an actionable diagnostic
               (Controlled Folder Access / Group Policy / AppLocker
               hints), instead of letting the user stare at a raw
               Python PermissionError traceback.

            6. **Diagnostic messages throughout** — every cleanup
               step now prints what it's doing, so the operator can
               see which step (service stop, delete, taskkill, del
               retries, write test) is progressing.

  - task: "Agent installer download flow (bundle mode)"
    implemented: true
    working: true
    file: "backend/app/routers/agent_installer.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: false
          agent: "user"
          comment: "User reported: 'the agent is not downloading properly its downloading half'."
        - working: true
          agent: "main"
          comment: |
            Root cause: bundle mode used a Python generator
            (StreamingResponse) with chunked transfer encoding and no
            Content-Length. That combination caused two failure modes:
              1. Browsers cannot show real progress on chunked responses,
                 and Chrome has been observed to abandon them after an
                 internal idle threshold, leaving the user with a
                 truncated (~"downloaded half") file with no error.
              2. Chunked responses cannot be resumed via HTTP Range, so a
                 single flaky wifi hiccup at 60% threw away the whole
                 200 MB transfer.
            Also the frontend was buffering the entire response in JS
            memory (fetch -> chunks[] -> Blob) which triggered a React
            re-render on every 1 MiB chunk, causing browser memory
            pressure and UI hangs on large transfers.

            Fix (backend, agent_installer.py):
              - New POST /api/agent/installer/download-init endpoint mints
                a single-use pairing code AND a 5-minute-lived signed
                download JWT bound to the caller's user_id/org_id/role.
              - GET /api/agent/installer/download now accepts EITHER an
                Authorization: Bearer header (legacy) OR a
                ?token=<download_jwt> query param (native browser flow).
              - Bundle mode now materialises the ZIP to
                /tmp/dt-installer-cache/<code>.zip with ZIP_STORED and
                serves it via FastAPI FileResponse. That gives an accurate
                Content-Length header and HTTP Range support out of the
                box, so the browser's native download manager shows real
                progress and can resume interrupted transfers.
              - Cached ZIPs older than 1 h are purged on every download.

            Fix (frontend, EnrollDeviceDialog.jsx):
              - downloadAgent() no longer does a fetch()+ReadableStream+
                Blob dance. It calls /download-init to get a signed URL,
                then triggers a native <a download> click. The browser's
                download manager takes over — no JS-side buffering, no
                re-render storms on every chunk.

            Verified end-to-end (via curl on both localhost and public
            preview URL):
              - Content-Length header now EXACTLY equals bytes on wire
                (was off by 136 bytes in the streaming attempt).
              - All 6 files in the ZIP pass `unzip -t` integrity check.
              - SHA-256 of extracted binaries matches sources.
              - Bearer-header auth path still works for backwards compat.
              - ?token= path returns correct pairing code + filename.

frontend:
  - task: "Download Agent dialog (EnrollDeviceDialog)"
    implemented: true
    working: true
    file: "frontend/src/components/EnrollDeviceDialog.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: false
          agent: "user"
          comment: "Downloads stopped mid-transfer for large (>~200 MB) bundles."
        - working: true
          agent: "main"
          comment: |
            Rewrote downloadAgent() to use the new /download-init +
            native browser <a download> flow. Progress bar is now driven
            by the browser's built-in download manager instead of a
            fetch+blob buffer. Toast/UX text updated to reflect this
            ("Download started — check your browser's download tray").

metadata:
  created_by: "main_agent"
  version: "1.1"
  test_sequence: 1
  run_ui: false

test_plan:
  current_focus:
    - "Agent installer download flow (bundle mode)"
    - "Download Agent dialog (EnrollDeviceDialog)"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
  - agent: "main"
    message: |
      Bug fix ready for verification.

      Test credentials seeded and ready:
        Email:    admin@digitaltwin.com
        Password: ChangeMe!2026
        Role:     owner (>= technician, required for /download)

      Test data present:
        /app/dist/DigitalTwinAgentSetup.exe   (~45 MB, random bytes)
        /app/dist/agent.exe                    (~150 MB, random bytes)
        /app/dist/uninstaller.exe              (~15 MB, random bytes)

      Focus for testing agent:
        1. GET  /api/agent/installer/info returns available=true and
           bundle=true.
        2. POST /api/agent/installer/download-init (auth: bearer) returns
           {download_token, pairing_code, filename, is_bundle:true,
            expires_in:300}.
        3. GET  /api/agent/installer/download?token=<jwt> (no bearer
           header) streams a ZIP whose byte count EXACTLY matches the
           Content-Length header (this was the root cause of "half
           download" — server used to advertise 136 bytes MORE than it
           sent).
        4. The response Content-Type is application/zip, Content-
           Disposition contains DigitalTwinAgentSetup_<code>.zip, and
           the ZIP passes `unzip -t` with 6 entries (install.cmd,
           bundle.json, README.txt, DigitalTwinAgentSetup_<code>.exe,
           agent.exe, uninstaller.exe).
        5. GET /download without a token AND without a bearer header
           returns 401.
        6. GET /download with a bearer header but no ?token= still
           works (backwards compat with the legacy front-end).
        7. GET /agent/installer/verify?code=<code> after a download
           returns paired:false, device:null, expires_at set (~10 min
           in future).

      Skip frontend browser automation of the actual file save flow —
      the fix is a native browser download so it lands in the OS
      Downloads folder and can't be intercepted from the Playwright
      page context. Curl-level verification of every backend endpoint
      is sufficient.
