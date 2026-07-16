"""agent_v2.modules — the 16 independent runtime modules.

Module catalogue (see plan.md § Phase 7.2):

    1. installer           (top-level — separate binary lifecycle)
    2. core                Agent Core — orchestrator; owns lifecycle of all engines
    3. enrollment          bootstrap.dta loader + /api/agents/pair client
    4. auth                DPAPI-backed credential store
    5. telemetry           metrics collection + framing + push loop
    6. inventory           hardware + software inventory refresh
    7. health              client-side health scoring (backend has authoritative)
    8. prediction          client-side prediction hints
    9. alerts              client-side alert evaluation (belt-and-braces vs backend)
   10. remote_actions      handles incoming action requests over WS
   11. ws_client           resilient WebSocket transport
   12. offline_queue       on-disk queue for offline periods
   13. diagnostics         collects + uploads periodic diagnostic snapshots
   14. logmod              logging setup (avoids stdlib-name collision)
   15. self_healing        watchdog / recovery / heartbeat supervision
   16. service             pywin32 Windows Service registrar + framework

All modules expose stable public APIs via their ``__init__.py`` files. No
module imports another module's *internals* — dependencies are injected by the
Agent Core orchestrator.
"""
