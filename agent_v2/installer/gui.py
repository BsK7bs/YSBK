"""tkinter GUI wrapper — progress → success (only after verify) or error.

The wizard shows:
  1. An indeterminate progress bar while ``execute`` runs, with the current
     step name updated in real-time.
  2. A green "Success" screen ONLY when execute() completed every step
     (install → service → pair → verify online).
  3. A red "Installation failed" screen with the step name + reason on ANY
     failure. The installer NEVER silently exits.

Falls back to CLI when tkinter is unavailable (LocalSystem service contexts,
Windows Server Core, headless MSI deploys).
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger("dta.installer.gui")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def run_wizard(execute: Callable[[Callable[[str], None]], dict], log_file: Optional[Path] = None) -> int:
    """Run ``execute`` inside a Tk progress window. Returns 0 on full success."""
    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError:
        log.info("tkinter unavailable — running installer in CLI mode")
        return _cli_execute(execute, log_file)

    state: dict = {"phase": "running", "result": None, "error": None}

    root = tk.Tk()
    root.title("Digital Twin Agent — Installer")
    root.geometry("560x300")
    root.resizable(False, False)
    root.configure(bg="#0f1220")

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("Dt.TFrame", background="#0f1220")
    style.configure("Dt.TLabel", background="#0f1220", foreground="#e6e8f0")
    style.configure("Dt.Title.TLabel", background="#0f1220", foreground="#ffffff",
                    font=("Segoe UI", 15, "bold"))
    style.configure("Dt.Sub.TLabel", background="#0f1220", foreground="#8f95b2", font=("Segoe UI", 10))
    style.configure("Dt.OK.TLabel", background="#0f1220", foreground="#4ade80",
                    font=("Segoe UI", 15, "bold"))
    style.configure("Dt.Fail.TLabel", background="#0f1220", foreground="#f87171",
                    font=("Segoe UI", 15, "bold"))
    style.configure("Dt.Horizontal.TProgressbar", troughcolor="#1a1d33", background="#3b82f6",
                    bordercolor="#1a1d33", lightcolor="#3b82f6", darkcolor="#3b82f6")

    outer = ttk.Frame(root, style="Dt.TFrame")
    outer.pack(fill="both", expand=True, padx=28, pady=24)

    title_var = tk.StringVar(value="Installing Digital Twin Agent")
    subtitle_var = tk.StringVar(value="This will complete in about 30 seconds.")
    status_var = tk.StringVar(value="Starting…")

    title = ttk.Label(outer, textvariable=title_var, style="Dt.Title.TLabel")
    title.pack(anchor="w")
    subtitle = ttk.Label(outer, textvariable=subtitle_var, style="Dt.Sub.TLabel", wraplength=500)
    subtitle.pack(anchor="w", pady=(4, 18))

    progress = ttk.Progressbar(outer, mode="indeterminate", length=500,
                               style="Dt.Horizontal.TProgressbar")
    progress.pack(fill="x")
    progress.start(10)

    status = ttk.Label(outer, textvariable=status_var, style="Dt.TLabel", wraplength=500)
    status.pack(anchor="w", pady=(12, 0))

    close_btn = ttk.Button(outer, text="Close", command=root.destroy, state="disabled")
    close_btn.pack(anchor="e", side="bottom")

    def _progress_cb(msg: str) -> None:
        log.info(msg)
        root.after(0, status_var.set, msg)

    def _finish_ui(success: bool, message: str, extra: str = "") -> None:
        progress.stop()
        progress.pack_forget()
        title.configure(style="Dt.OK.TLabel" if success else "Dt.Fail.TLabel")
        title_var.set("Installation complete" if success else "Installation failed")
        subtitle_var.set(message)
        status_var.set(extra)
        close_btn.configure(state="normal")

    def _worker():
        try:
            result = execute(_progress_cb)
            state["result"] = result or {}
        except Exception as exc:  # noqa: BLE001
            state["error"] = str(exc)
            log.exception("installer worker failed")
        finally:
            if state["error"]:
                extra = f"Log: {log_file}" if log_file else ""
                root.after(0, _finish_ui, False, state["error"], extra)
                state["phase"] = "failed"
            else:
                r = state["result"] or {}
                snap = r.get("snapshot") or {}
                extra = ""
                host = snap.get("hostname") or r.get("hostname")
                if host:
                    extra = f"Device \u2018{host}\u2019 is now streaming telemetry."
                root.after(0, _finish_ui, True,
                           "Digital Twin Agent is installed and the device is online in your dashboard.",
                           extra)
                state["phase"] = "succeeded"

    threading.Thread(target=_worker, daemon=True).start()
    root.mainloop()

    return 0 if state["phase"] == "succeeded" else 1


def show_error(message: str, log_file: Optional[Path], silent: bool = False) -> int:
    """Display a standalone error dialog when we bail out before entering the wizard."""
    if silent:
        import sys as _sys
        _sys.stderr.write(f"[installer] ERROR: {message}\n")
        if log_file:
            _sys.stderr.write(f"[installer] Log: {log_file}\n")
        return 1
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        detail = f"{message}\n\nLog: {log_file}" if log_file else message
        messagebox.showerror("Digital Twin Agent — Installer", detail)
        root.destroy()
    except Exception:
        print(f"[installer] ERROR: {message}")  # noqa: T201
    return 1


# ---------------------------------------------------------------------------
# CLI fallback
# ---------------------------------------------------------------------------
def _cli_execute(execute: Callable[[Callable[[str], None]], dict], log_file: Optional[Path]) -> int:
    def cb(msg: str):
        print(f"[installer] {msg}", flush=True)  # noqa: T201

    try:
        execute(cb)
    except Exception as exc:  # noqa: BLE001
        print(f"[installer] FAILED: {exc}", flush=True)  # noqa: T201
        if log_file:
            print(f"[installer] Log: {log_file}", flush=True)  # noqa: T201
        return 1
    print("[installer] Installation complete — the device is online.", flush=True)  # noqa: T201
    return 0
