from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk

from notifications_bridge.config_loader import merge_and_save_config
from notifications_bridge.runtime import AppRuntime
from notifications_bridge.top_overlay import TopOverlayManager

logger = logging.getLogger(__name__)

# Pale lavender panel (reference display app)
_WIN_BG = "#EFE8F5"
_BTN_BG = "#D8C8E8"
_BTN_BG_ACTIVE = "#C9B8DC"
_BTN_BORDER = "#1a1a1a"
_TEXT = "#000000"

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


def _try_win11_rounded_corners(w: tk.Misc) -> None:
    try:
        import ctypes
        from ctypes import wintypes

        hwnd = w.winfo_id()
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWCP_ROUND = 2
        pref = ctypes.c_uint(DWMWCP_ROUND)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            ctypes.c_uint(DWMWA_WINDOW_CORNER_PREFERENCE),
            ctypes.byref(pref),
            ctypes.sizeof(pref),
        )
    except Exception:
        pass


def _lavender_button(parent: tk.Misc, text: str, command) -> tk.Button:
    return tk.Button(
        parent,
        text=text,
        command=command,
        font=("Segoe UI", 10),
        bg=_BTN_BG,
        fg=_TEXT,
        activebackground=_BTN_BG_ACTIVE,
        activeforeground=_TEXT,
        relief=tk.FLAT,
        bd=0,
        highlightthickness=1,
        highlightbackground=_BTN_BORDER,
        highlightcolor=_BTN_BORDER,
        padx=14,
        pady=8,
    )


class SettingsWindow:
    _instance: SettingsWindow | None = None

    def __init__(self, rt: AppRuntime) -> None:
        self._rt = rt
        self._win: tk.Toplevel | None = None
        self._opacity_scale: tk.Scale | None = None
        self._dwell_combo: ttk.Combobox | None = None
        self._opacity_pct_label: tk.Label | None = None
        self._icon_photo: object | None = None
        self._rounded_applied = False
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
            self._dwell_combo.current(_nearest_dwell_index(dwell))
        self._refresh_opacity_label()

    def _refresh_opacity_label(self) -> None:
        if self._opacity_pct_label and self._opacity_scale:
            self._opacity_pct_label.configure(text=f"{int(self._opacity_scale.get())}%")

    def _on_map(self, _event=None) -> None:
        if self._rounded_applied or self._win is None:
            return
        self._rounded_applied = True
        _try_win11_rounded_corners(self._win)

    def _build(self) -> None:
        rt = self._rt
        cfg = rt.cfg

        self._win = tk.Toplevel(rt.root)
        self._win.title("Customize")
        self._win.geometry("320x280")
        self._win.minsize(300, 260)
        self._win.configure(bg=_WIN_BG)
        self._win.bind("<Map>", self._on_map)

        try:
            from PIL import ImageTk

            from notifications_bridge import app as appmod

            self._icon_photo = ImageTk.PhotoImage(appmod._tray_image())
            self._win.iconphoto(True, self._icon_photo)
        except Exception:
            logger.debug("Could not set window icon", exc_info=True)

        outer = tk.Frame(self._win, bg=_WIN_BG)
        outer.pack(fill=tk.BOTH, expand=True, padx=16, pady=14)
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_columnconfigure(1, weight=1)

        style = ttk.Style(self._win)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Lav.TCombobox",
            fieldbackground=_BTN_BG,
            background=_BTN_BG,
            foreground=_TEXT,
            arrowcolor=_TEXT,
            bordercolor=_BTN_BORDER,
            lightcolor=_BTN_BG,
            darkcolor=_BTN_BG,
            font=("Segoe UI", 10),
        )
        style.map("Lav.TCombobox", fieldbackground=[("readonly", _BTN_BG)])

        op0 = int(round(float(cfg.get("overlay_opacity", 0.96)) * 100))
        dwell0 = float(cfg.get("overlay_dwell_ms", 5500)) / 1000.0

        r = 0
        tk.Label(outer, text="Opacity", bg=_WIN_BG, fg=_TEXT, font=("Segoe UI", 10)).grid(
            row=r, column=0, columnspan=2, sticky="w", pady=(0, 2)
        )
        r += 1
        head = tk.Frame(outer, bg=_WIN_BG)
        head.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        self._opacity_scale = tk.Scale(
            head,
            from_=35,
            to=100,
            orient=tk.HORIZONTAL,
            showvalue=0,
            length=260,
            bg=_WIN_BG,
            fg=_TEXT,
            troughcolor=_BTN_BG,
            highlightthickness=0,
            bd=0,
            activebackground=_BTN_BG_ACTIVE,
            command=lambda _v: self._refresh_opacity_label(),
        )
        self._opacity_scale.set(op0)
        self._opacity_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._opacity_pct_label = tk.Label(
            head, text="", bg=_WIN_BG, fg=_TEXT, font=("Segoe UI", 10), width=5
        )
        self._opacity_pct_label.pack(side=tk.RIGHT, padx=(8, 0))
        r += 1

        tk.Label(outer, text="Time on screen", bg=_WIN_BG, fg=_TEXT, font=("Segoe UI", 10)).grid(
            row=r, column=0, sticky="w", pady=(14, 4)
        )
        self._dwell_combo = ttk.Combobox(
            outer,
            values=_DWELL_OPTIONS,
            state="readonly",
            width=11,
            style="Lav.TCombobox",
        )
        self._dwell_combo.grid(row=r, column=1, sticky="e", pady=(14, 4))
        self._dwell_combo.current(_nearest_dwell_index(dwell0))
        r += 1

        self._refresh_opacity_label()

        btn_apply = _lavender_button(outer, "Apply", self._apply)
        btn_close = _lavender_button(outer, "Close", self._on_close)
        btn_apply.grid(row=r, column=0, sticky="ew", padx=(0, 6), pady=(18, 6))
        btn_close.grid(row=r, column=1, sticky="ew", padx=(6, 0), pady=(18, 6))
        r += 1

        btn_quit = _lavender_button(outer, "Quit", self._quit_app)
        btn_quit.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(6, 0))

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

    def _quit_app(self) -> None:
        fn = self._rt.on_quit_application
        if fn is not None:
            fn()
        else:
            self._on_close()

    def _on_close(self) -> None:
        try:
            if self._win is not None:
                self._win.destroy()
        except Exception:
            pass
        SettingsWindow._instance = None
