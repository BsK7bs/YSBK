"""pywin32 ServiceFramework subclass — hosts the Agent Core orchestrator."""
from __future__ import annotations

import logging
import os
import sys
import threading
import traceback
from datetime import datetime

log = logging.getLogger("dta.service.framework")


def _service_startup_debug(message: str) -> None:
    """Best-effort write to a file that captures early service-startup
    activity BEFORE the normal logging pipeline is available.

    If pywin32 crashes before ``configure_agent_logging()`` runs — or if
    SCM kills the process for hitting the 30s timeout — the rotating
    agent log never gets written. This tiny append-only file guarantees
    that at least the last-known state of the service host is visible
    from Explorer, so operators/CI can diagnose 1053 timeouts without
    attaching a debugger.

    Path: %ProgramData%\\DigitalTwin\\logs\\service-startup.log
    """
    try:
        base = os.environ.get("PROGRAMDATA") or r"C:\\ProgramData"
        log_dir = os.path.join(base, "DigitalTwin", "logs")
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "service-startup.log"), "a", encoding="utf-8") as fh:
            ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            fh.write(f"{ts} | {message}\n")
    except Exception:
        # Never let logging break the service.
        pass


def launch_service() -> int:
    """Entry point called when SCM launches ``agent.exe --run-service``.

    Fix (2026-07): the previous implementation called
    ``win32serviceutil.HandleCommandLine`` which is the *command-line
    management* helper (verbs: install / remove / debug / start / stop).
    It does not implement the SCM handshake — when SCM launched the
    frozen EXE with our ``--run-service`` token, HandleCommandLine saw
    an unknown verb, printed its usage banner and exited. SCM waited
    30s for SERVICE_RUNNING, timed out, and reported error 1053:
    "The service did not respond to the start or control request in a
    timely fashion."

    The correct pattern for a PyInstaller-frozen service host is to
    call ``servicemanager.StartServiceCtrlDispatcher`` directly. That
    hands the current thread to the SCM's control dispatcher, which
    then calls ``SvcDoRun`` on our ServiceFramework subclass. Inside
    ``ServiceFramework.SvcRun`` (the framework's private wrapper),
    pywin32 automatically reports SERVICE_RUNNING to SCM before
    dispatching to our SvcDoRun — so the 30s timer stops as soon as
    the dispatcher is up.
    """
    if sys.platform != "win32":
        raise SystemExit("launch_service() is Windows-only")

    _service_startup_debug(
        f"launch_service() invoked; argv={sys.argv!r}; frozen={getattr(sys, 'frozen', False)}"
    )

    try:
        import servicemanager       # type: ignore
    except ImportError as exc:
        _service_startup_debug(f"FATAL: servicemanager import failed: {exc}")
        raise

    try:
        # servicemanager.Initialize registers the service with the event
        # log so SvcDoRun's log messages surface in Event Viewer even
        # before configure_agent_logging() attaches its file handler.
        servicemanager.Initialize()
        _service_startup_debug("servicemanager.Initialize() OK")

        # PrepareToHostSingle tells the dispatcher which ServiceFramework
        # subclass to instantiate. Must be called before
        # StartServiceCtrlDispatcher.
        servicemanager.PrepareToHostSingle(DigitalTwinAgentService)
        _service_startup_debug(
            f"PrepareToHostSingle(DigitalTwinAgentService) OK; "
            f"svc_name={DigitalTwinAgentService._svc_name_}"
        )

        # BLOCKING: yields the thread to the Windows SCM until SvcStop
        # is signalled. Inside the dispatcher pywin32 will:
        #   1. Call DigitalTwinAgentService.__init__(args)
        #   2. Call ReportServiceStatus(SERVICE_START_PENDING)
        #   3. Call SvcDoRun()
        #   4. Call ReportServiceStatus(SERVICE_RUNNING) automatically
        #      before SvcDoRun starts, satisfying SCM's 30s timer.
        _service_startup_debug("about to call StartServiceCtrlDispatcher() (blocks)")
        servicemanager.StartServiceCtrlDispatcher()
        _service_startup_debug("StartServiceCtrlDispatcher() returned cleanly")
        return 0
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        _service_startup_debug(
            f"FATAL launch_service crash: {exc.__class__.__name__}: {exc}\n"
            + "".join(traceback.format_exc())
        )
        raise


if sys.platform == "win32":
    import asyncio
    import win32event       # type: ignore
    import win32service     # type: ignore
    import win32serviceutil # type: ignore

    from ..logmod import configure_agent_logging
    from ...common.paths import SERVICE_DESCRIPTION, SERVICE_DISPLAY_NAME, SERVICE_NAME

    class DigitalTwinAgentService(win32serviceutil.ServiceFramework):
        _svc_name_ = SERVICE_NAME
        _svc_display_name_ = SERVICE_DISPLAY_NAME
        _svc_description_ = SERVICE_DESCRIPTION

        def __init__(self, args):
            _service_startup_debug(f"DigitalTwinAgentService.__init__ args={args!r}")
            win32serviceutil.ServiceFramework.__init__(self, args)
            self._stop_evt = win32event.CreateEvent(None, 0, 0, None)
            self._async_stop: asyncio.Event | None = None
            self._loop: asyncio.AbstractEventLoop | None = None
            self._thread: threading.Thread | None = None

        def SvcStop(self):
            log.info("SvcStop — SCM requested stop")
            _service_startup_debug("SvcStop called by SCM")
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self._stop_evt)
            if self._loop and self._async_stop:
                self._loop.call_soon_threadsafe(self._async_stop.set)

        def SvcDoRun(self):
            # STEP 1 — tell SCM we are RUNNING within the first few
            # milliseconds. pywin32's ServiceFramework.SvcRun *does*
            # auto-signal this, but we do it again explicitly and
            # BEFORE any heavy work so a slow import in
            # configure_agent_logging() or the Orchestrator thread
            # can never blow the 30s timer.
            try:
                self.ReportServiceStatus(win32service.SERVICE_RUNNING)
                _service_startup_debug("SvcDoRun: reported SERVICE_RUNNING to SCM")
            except Exception as exc:  # noqa: BLE001
                _service_startup_debug(f"SvcDoRun: ReportServiceStatus RUNNING failed: {exc}")

            try:
                configure_agent_logging()
                log.info("SvcDoRun: logging configured")
                _service_startup_debug("SvcDoRun: configure_agent_logging OK")
            except Exception as exc:  # noqa: BLE001
                # Logging failure must not kill the service — we already
                # said RUNNING, so SCM is happy; we just carry on.
                _service_startup_debug(f"SvcDoRun: configure_agent_logging FAILED: {exc}")

            log.info("SvcDoRun: starting orchestrator thread")
            self._thread = threading.Thread(target=self._run_asyncio, daemon=True)
            self._thread.start()
            _service_startup_debug("SvcDoRun: orchestrator thread started; waiting for stop event")

            win32event.WaitForSingleObject(self._stop_evt, win32event.INFINITE)
            log.info("SvcDoRun: joining orchestrator")
            _service_startup_debug("SvcDoRun: stop event set; joining orchestrator")
            if self._thread:
                self._thread.join(timeout=15)
            _service_startup_debug("SvcDoRun: exit")

        def _run_asyncio(self):
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._async_stop = asyncio.Event()
            try:
                from ..core.orchestrator import Orchestrator
                orch = Orchestrator()
                self._loop.run_until_complete(orch.run(self._async_stop))
            except Exception as exc:  # noqa: BLE001
                log.exception("orchestrator crashed: %s", exc)
                _service_startup_debug(
                    f"orchestrator crashed: {exc.__class__.__name__}: {exc}\n"
                    + "".join(traceback.format_exc())
                )
            finally:
                try:
                    self._loop.close()
                except Exception:
                    pass
else:
    class DigitalTwinAgentService:  # type: ignore
        pass
