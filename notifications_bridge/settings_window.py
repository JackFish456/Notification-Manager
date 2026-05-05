from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk

from notifications_bridge.config_loader import merge_and_save_config
from notifications_bridge.runtime import AppRuntime
from notifications_bridge.top_overlay import TopOverlayManager

logger = logging.getLogger(__name__)


class SettingsWindow:
    _instance: SettingsWindow | None = None

    def __init__(self, rt: AppRuntime) -> None:
        self._rt = rt
        self._win: tk.Toplevel | None = None
        self._opacity_scale: tk.Scale | None = None
        self._dwell_scale: tk.Scale | None = None
        self._opacity_label: ttk.Label | None = None
        self._dwell_label: ttk.Label | None = None
        self._build()

    @classmethod
    def open_or_focus(cls, rt: AppRuntime) -> None:
        def go() -> None:
            if cls._instance is not None:
                try:
                    if cls._instance._win is not None and cls._instance._win.winfo_exists():
                        cls._instance._win.deiconify()
                        cls._instance._win.lift()
                        cls._instance._win.focus_force()
                        cls._instance._sync_from_runtime()
                        return
                except Exception:
                    cls._instance = None
            cls._instance = SettingsWindow(rt)

        rt.root.after(0, go)

    def _sync_from_runtime(self) -> None:
        cfg = self._rt.cfg
        op = int(round(float(cfg.get("overlay_opacity", 0.96)) * 100))
        dwell = float(cfg.get("overlay_dwell_ms", 5500)) / 1000.0
        if self._opacity_scale is not None:
            self._opacity_scale.set(op)
        if self._dwell_scale is not None:
            self._dwell_scale.set(dwell)
        self._refresh_labels()

    def _refresh_labels(self) -> None:
        if self._opacity_label and self._opacity_scale:
            self._opacity_label.configure(text=f"{int(self._opacity_scale.get())}% opaque")
        if self._dwell_label and self._dwell_scale:
            self._dwell_label.configure(text=f"{float(self._dwell_scale.get()):.1f} s on screen")

    def _build(self) -> None:
        rt = self._rt
        cfg = rt.cfg

        self._win = tk.Toplevel(rt.root)
        self._win.title("Notification Manager — Customize")
        self._win.geometry("440x280")
        self._win.minsize(400, 240)
        try:
            self._win.attributes("-topmost", True)
        except tk.TclError:
            pass

        outer = ttk.Frame(self._win, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            outer,
            text=(
                "Tray: left-click the icon opens this window. Right-click opens the full menu. "
                "Opacity applies to the custom top banner (use_top_overlay)."
            ),
            wraplength=400,
            justify="left",
        ).pack(anchor="w", pady=(0, 12))

        op0 = int(round(float(cfg.get("overlay_opacity", 0.96)) * 100))
        dwell0 = float(cfg.get("overlay_dwell_ms", 5500)) / 1000.0

        f1 = ttk.Frame(outer)
        f1.pack(fill=tk.X, pady=(0, 6))
        row1 = ttk.Frame(f1)
        row1.pack(fill=tk.X)
        ttk.Label(row1, text="Banner opacity").pack(side=tk.LEFT)
        self._opacity_label = ttk.Label(row1, text="")
        self._opacity_label.pack(side=tk.RIGHT)
        self._opacity_scale = tk.Scale(
            f1,
            from_=35,
            to=100,
            orient=tk.HORIZONTAL,
            showvalue=0,
            length=360,
            command=lambda _v: self._refresh_labels(),
        )
        self._opacity_scale.set(op0)
        self._opacity_scale.pack(fill=tk.X, pady=(4, 0))

        f2 = ttk.Frame(outer)
        f2.pack(fill=tk.X, pady=(12, 6))
        row2 = ttk.Frame(f2)
        row2.pack(fill=tk.X)
        ttk.Label(row2, text="Time on screen").pack(side=tk.LEFT)
        self._dwell_label = ttk.Label(row2, text="")
        self._dwell_label.pack(side=tk.RIGHT)
        self._dwell_scale = tk.Scale(
            f2,
            from_=1.5,
            to=120.0,
            resolution=0.5,
            orient=tk.HORIZONTAL,
            showvalue=0,
            length=360,
            command=lambda _v: self._refresh_labels(),
        )
        self._dwell_scale.set(dwell0)
        self._dwell_scale.pack(fill=tk.X, pady=(4, 0))

        self._refresh_labels()

        btn_row = ttk.Frame(outer)
        btn_row.pack(fill=tk.X, pady=(18, 0))
        ttk.Button(btn_row, text="Save & apply", command=self._apply).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(btn_row, text="Close", command=self._on_close).pack(side=tk.RIGHT)

        self._win.protocol("WM_DELETE_WINDOW", self._on_close)

    def _apply(self) -> None:
        if self._opacity_scale is None or self._dwell_scale is None:
            return
        try:
            op_pct = float(self._opacity_scale.get())
        except tk.TclError:
            op_pct = 96.0
        try:
            dwell_sec = float(self._dwell_scale.get())
        except tk.TclError:
            dwell_sec = 5.5

        alpha = max(0.35, min(1.0, op_pct / 100.0))
        dwell_ms = max(1500, min(int(round(dwell_sec * 1000)), 120_000))

        try:
            merge_and_save_config(
                {
                    "overlay_opacity": round(alpha, 3),
                    "overlay_dwell_seconds": round(dwell_sec, 2),
                }
            )
        except Exception:
            logger.exception("Failed to write config.json")
            return

        self._rt.cfg["overlay_opacity"] = alpha
        self._rt.cfg["overlay_dwell_ms"] = dwell_ms
        if isinstance(self._rt.notifier, TopOverlayManager):
            self._rt.notifier.apply_overlay_settings(alpha=alpha, dwell_ms=dwell_ms)

    def _on_close(self) -> None:
        try:
            if self._win is not None:
                self._win.destroy()
        except Exception:
            pass
        SettingsWindow._instance = None
