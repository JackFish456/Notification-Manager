from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk

from notifications_bridge.config_loader import merge_and_save_config
from notifications_bridge.runtime import AppRuntime
from notifications_bridge.top_overlay import TopOverlayManager

logger = logging.getLogger(__name__)

# Preset dwell durations (seconds), aligned with config limits 1.5–120 s
_DWELL_SEC_VALUES: tuple[float, ...] = (
    1.5,
    2.0,
    3.0,
    4.0,
    5.0,
    6.0,
    8.0,
    10.0,
    12.0,
    15.0,
    20.0,
    30.0,
    45.0,
    60.0,
    90.0,
    120.0,
)


def _format_dwell_option(sec: float) -> str:
    if sec == int(sec):
        return f"{int(sec)} s"
    return f"{sec} s"


_DWELL_OPTIONS: tuple[str, ...] = tuple(_format_dwell_option(s) for s in _DWELL_SEC_VALUES)


def _nearest_dwell_index(sec: float) -> int:
    best_i = 0
    best_d = abs(_DWELL_SEC_VALUES[0] - sec)
    for i, v in enumerate(_DWELL_SEC_VALUES):
        d = abs(v - sec)
        if d < best_d:
            best_d = d
            best_i = i
    return best_i


def _apply_dark_style(root: tk.Tk | tk.Toplevel) -> ttk.Style:
    """Match top-overlay palette: dark panel, light text (internal display style)."""
    bg = "#2d2d2d"
    fg = "#f3f3f3"
    sub = "#a8a8a8"
    field = "#3d3d3d"
    root.configure(bg=bg)

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure("Display.TFrame", background=bg)
    style.configure("Display.TLabel", background=bg, foreground=fg, font=("Segoe UI", 10))
    style.configure("Display.TButton", background=field, foreground=fg, font=("Segoe UI", 10))
    style.map(
        "Display.TButton",
        background=[("active", "#4a4a4a"), ("pressed", "#555555")],
        foreground=[("disabled", sub)],
    )
    style.configure(
        "Display.TCombobox",
        fieldbackground=field,
        background=field,
        foreground=fg,
        arrowcolor=fg,
        font=("Segoe UI", 10),
    )
    style.map("Display.TCombobox", fieldbackground=[("readonly", field)])
    return style


class SettingsWindow:
    _instance: SettingsWindow | None = None

    def __init__(self, rt: AppRuntime) -> None:
        self._rt = rt
        self._win: tk.Toplevel | None = None
        self._opacity_scale: tk.Scale | None = None
        self._dwell_combo: ttk.Combobox | None = None
        self._opacity_label: ttk.Label | None = None
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
        if self._dwell_combo is not None:
            idx = _nearest_dwell_index(dwell)
            self._dwell_combo.current(idx)
        self._refresh_opacity_label()

    def _refresh_opacity_label(self) -> None:
        if self._opacity_label and self._opacity_scale:
            self._opacity_label.configure(text=f"{int(self._opacity_scale.get())}%")

    def _build(self) -> None:
        rt = self._rt
        cfg = rt.cfg

        self._win = tk.Toplevel(rt.root)
        self._win.title("Customize")
        self._win.geometry("360x200")
        self._win.minsize(320, 180)
        try:
            self._win.attributes("-topmost", True)
        except tk.TclError:
            pass

        _apply_dark_style(self._win)

        outer = ttk.Frame(self._win, padding=16, style="Display.TFrame")
        outer.pack(fill=tk.BOTH, expand=True)

        op0 = int(round(float(cfg.get("overlay_opacity", 0.96)) * 100))
        dwell0 = float(cfg.get("overlay_dwell_ms", 5500)) / 1000.0

        f1 = ttk.Frame(outer, style="Display.TFrame")
        f1.pack(fill=tk.X, pady=(0, 10))
        row1 = ttk.Frame(f1, style="Display.TFrame")
        row1.pack(fill=tk.X)
        ttk.Label(row1, text="Opacity", style="Display.TLabel").pack(side=tk.LEFT)
        self._opacity_label = ttk.Label(row1, text="", style="Display.TLabel")
        self._opacity_label.pack(side=tk.RIGHT)
        self._opacity_scale = tk.Scale(
            f1,
            from_=35,
            to=100,
            orient=tk.HORIZONTAL,
            showvalue=0,
            length=300,
            bg="#2d2d2d",
            fg="#f3f3f3",
            troughcolor="#404040",
            highlightthickness=0,
            bd=0,
            activebackground="#555555",
            command=lambda _v: self._refresh_opacity_label(),
        )
        self._opacity_scale.set(op0)
        self._opacity_scale.pack(fill=tk.X, pady=(6, 0))

        f2 = ttk.Frame(outer, style="Display.TFrame")
        f2.pack(fill=tk.X, pady=(8, 0))
        row2 = ttk.Frame(f2, style="Display.TFrame")
        row2.pack(fill=tk.X)
        ttk.Label(row2, text="Time on screen", style="Display.TLabel").pack(side=tk.LEFT)
        self._dwell_combo = ttk.Combobox(
            row2,
            values=_DWELL_OPTIONS,
            state="readonly",
            width=12,
            style="Display.TCombobox",
        )
        self._dwell_combo.pack(side=tk.RIGHT)
        self._dwell_combo.current(_nearest_dwell_index(dwell0))

        self._refresh_opacity_label()

        btn_row = ttk.Frame(outer, style="Display.TFrame")
        btn_row.pack(fill=tk.X, pady=(20, 0))
        ttk.Button(btn_row, text="Apply", command=self._apply, style="Display.TButton").pack(
            side=tk.RIGHT, padx=(8, 0)
        )
        ttk.Button(btn_row, text="Close", command=self._on_close, style="Display.TButton").pack(
            side=tk.RIGHT
        )

        self._win.protocol("WM_DELETE_WINDOW", self._on_close)

    def _apply(self) -> None:
        if self._opacity_scale is None or self._dwell_combo is None:
            return
        try:
            op_pct = float(self._opacity_scale.get())
        except tk.TclError:
            op_pct = 96.0

        idx = self._dwell_combo.current()
        if idx < 0:
            idx = _nearest_dwell_index(5.5)
        dwell_sec = _DWELL_SEC_VALUES[idx]

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
