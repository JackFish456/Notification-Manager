from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from tkinter import END, scrolledtext, ttk

from notifications_bridge.graph_auth import acquire_token
from notifications_bridge.paths import config_path, log_path
from notifications_bridge.runtime import AppRuntime

logger = logging.getLogger(__name__)


class MiniCliWindow:
    """Small command palette (Tk) opened from the tray."""

    _instance: MiniCliWindow | None = None

    def __init__(self, rt: AppRuntime) -> None:
        self._rt = rt
        self._win = None
        self._out = None
        self._in = None
        self._build()

    @classmethod
    def open_or_focus(cls, rt: AppRuntime) -> None:
        def go() -> None:
            if cls._instance is not None:
                try:
                    if cls._instance._win.winfo_exists():
                        cls._instance._win.deiconify()
                        cls._instance._win.lift()
                        cls._instance._win.focus_force()
                        return
                except Exception:
                    cls._instance = None
            cls._instance = MiniCliWindow(rt)
            cls._instance._print(
                "Graph Teams notify — mini CLI. Type `help` and press Enter.\n"
            )

        rt.root.after(0, go)

    def _build(self) -> None:
        import tkinter as tk

        rt = self._rt
        self._win = tk.Toplevel(rt.root)
        self._win.title("Notify bridge — CLI")
        self._win.geometry("520x360")
        self._win.minsize(420, 260)
        try:
            self._win.attributes("-topmost", True)
        except tk.TclError:
            pass

        outer = ttk.Frame(self._win, padding=8)
        outer.pack(fill="both", expand=True)

        self._out = scrolledtext.ScrolledText(
            outer,
            height=14,
            wrap="word",
            font=("Consolas", 10),
            state="disabled",
        )
        self._out.pack(fill="both", expand=True, pady=(0, 6))

        row = ttk.Frame(outer)
        row.pack(fill="x")
        ttk.Label(row, text=">").pack(side="left")
        self._in = ttk.Entry(row, font=("Consolas", 10))
        self._in.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self._in.bind("<Return>", self._on_enter)
        self._in.focus_set()

        self._win.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self) -> None:
        try:
            self._win.destroy()
        except Exception:
            pass
        MiniCliWindow._instance = None

    def _print(self, text: str) -> None:
        if not self._out:
            return
        self._out.configure(state="normal")
        self._out.insert(END, text)
        self._out.see(END)
        self._out.configure(state="disabled")

    def _on_enter(self, _event=None) -> None:
        if not self._in:
            return
        line = self._in.get().strip()
        self._in.delete(0, END)
        if not line:
            return
        self._print(f"> {line}\n")
        parts = line.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        self._dispatch(cmd, arg)

    def _dispatch(self, cmd: str, arg: str) -> None:
        if cmd in ("help", "?"):
            self._print(
                "Commands:\n"
                "  help          — this list\n"
                "  status        — sign-in + config summary\n"
                "  poll          — run one Graph poll now\n"
                "  auth          — interactive Microsoft sign-in\n"
                "  log [n]       — tail last n lines of bridge.log (default 40)\n"
                "  config        — open config.json\n"
                "  data          — open local data folder\n"
                "  clear         — clear this window\n"
                "  exit / close  — close CLI (tray keeps running)\n"
            )
            return
        if cmd in ("exit", "close", "quit"):
            self._on_close()
            return
        if cmd == "clear":
            if self._out is not None:
                self._out.configure(state="normal")
                self._out.delete("1.0", END)
                self._out.configure(state="disabled")
            return
        if cmd == "status":
            self._cmd_status()
            return
        if cmd == "poll":
            self._cmd_poll()
            return
        if cmd == "auth":
            self._cmd_auth()
            return
        if cmd == "log":
            self._cmd_log(arg)
            return
        if cmd == "config":
            self._cmd_open_path(config_path())
            return
        if cmd == "data":
            from notifications_bridge.paths import app_data_dir

            self._cmd_open_path(app_data_dir())
            return
        self._print(f"Unknown command `{cmd}`. Try `help`.\n")

    def _cmd_status(self) -> None:
        rt = self._rt
        accs = rt.msal_app.get_accounts()
        names = ", ".join(a.get("username", "?") for a in accs) or "(none)"
        overlay = bool(rt.cfg.get("use_top_overlay"))
        self._print(
            f"Signed-in accounts: {names}\n"
            f"use_top_overlay: {overlay}\n"
            f"poll_interval_seconds: {rt.cfg.get('poll_interval_seconds')}\n"
            f"config: {config_path()}\n"
            f"log: {log_path()}\n"
        )
        import notifications_bridge.app as appmod

        ts = getattr(appmod, "_last_poll_ok_at", None)
        if ts:
            self._print(
                f"last successful poll: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))}\n"
            )
        else:
            self._print("last successful poll: (not yet)\n")

    def _cmd_poll(self) -> None:
        self._print("poll: starting…\n")

        def work() -> None:
            try:
                from notifications_bridge.app import _poll_cycle
                from notifications_bridge.paths import state_path as state_file_path

                _poll_cycle(
                    self._rt.msal_app,
                    self._rt.cache_path,
                    self._rt.notifier,
                    state_file_path(),
                )
                msg = "poll: done.\n"
            except Exception as e:
                msg = f"poll: failed — {e!r}\n"
                logger.exception("CLI poll failed")

            def done() -> None:
                try:
                    inst = MiniCliWindow._instance
                    if inst is not None and inst._out is not None:
                        inst._print(msg)
                except Exception:
                    pass

            self._rt.root.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def _cmd_auth(self) -> None:
        self._print("auth: opening browser if needed…\n")

        def work() -> None:
            try:
                acquire_token(self._rt.msal_app, self._rt.cache_path, interactive=True)
                msg = "auth: OK (token cached).\n"
            except Exception as e:
                msg = f"auth: failed — {e!r}\n"
                logger.exception("CLI auth failed")

            def done() -> None:
                try:
                    inst = MiniCliWindow._instance
                    if inst is not None and inst._out is not None:
                        inst._print(msg)
                except Exception:
                    pass

            self._rt.root.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def _cmd_log(self, arg: str) -> None:
        n = 40
        if arg.strip().isdigit():
            n = max(1, min(500, int(arg.strip())))
        p = log_path()
        if not p.exists():
            self._print(f"log: file not found: {p}\n")
            return
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            tail = lines[-n:]
            self._print("".join(line + "\n" for line in tail))
        except Exception as e:
            self._print(f"log: read failed — {e!r}\n")

    def _cmd_open_path(self, path: Path) -> None:
        import os
        import subprocess

        p = str(path)
        try:
            os.startfile(p)  # type: ignore[attr-defined]
            self._print(f"opened: {p}\n")
        except Exception:
            subprocess.run(["explorer", p], check=False)
            self._print(f"tried explorer: {p}\n")
