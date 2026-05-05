from __future__ import annotations

import logging
from collections import deque
from typing import Callable

logger = logging.getLogger(__name__)


class TopOverlayManager:
    """Thread-safe top-of-screen cards: slide down into place, dwell, slide up off-screen.

    Must be driven from the Tk main thread; call ``show`` from any thread (uses ``root.after``).
    """

    def __init__(
        self,
        root,
        *,
        width: int = 360,
        height: int = 92,
        top_margin: int = 10,
        dwell_ms: int = 5500,
        alpha: float = 0.96,
        enter_ms: int = 220,
        exit_ms: int = 260,
    ) -> None:
        self._root = root
        self._width = max(280, min(width, 520))
        self._height = max(64, min(height, 200))
        self._top_margin = max(0, top_margin)
        self._dwell_ms = max(1500, min(int(dwell_ms), 120_000))
        self._alpha = max(0.35, min(1.0, float(alpha)))
        self._enter_ms = max(80, enter_ms)
        self._exit_ms = max(80, exit_ms)
        self._queue: deque[tuple[str, str]] = deque()
        self._busy = False

    def apply_overlay_settings(
        self,
        *,
        alpha: float | None = None,
        dwell_ms: int | None = None,
    ) -> None:
        if alpha is not None:
            self._alpha = max(0.35, min(1.0, float(alpha)))
        if dwell_ms is not None:
            self._dwell_ms = max(1500, min(int(dwell_ms), 120_000))

    def show(self, title: str, body: str) -> None:
        def _enqueue() -> None:
            self._queue.append((title, body))
            self._pump()

        try:
            self._root.after(0, _enqueue)
        except Exception:
            logger.exception("Failed to schedule overlay")

    def _pump(self) -> None:
        if self._busy or not self._queue:
            return
        self._busy = True
        title, body = self._queue.popleft()
        self._run_card(title, body, on_done=self._on_card_done)

    def _on_card_done(self) -> None:
        self._busy = False
        self._pump()

    def _ease_out_cubic(self, t: float) -> float:
        t = max(0.0, min(1.0, t))
        p = 1.0 - t
        return 1.0 - p * p * p

    def _run_card(self, title: str, body: str, *, on_done: Callable[[], None]) -> None:
        import tkinter as tk
        from tkinter import font as tkfont

        sw = int(self._root.winfo_screenwidth())
        x = max(0, (sw - self._width) // 2)
        end_y = self._top_margin
        start_y = end_y - self._height - 24

        win = tk.Toplevel(self._root)
        win.overrideredirect(True)
        try:
            win.attributes("-topmost", True)
        except tk.TclError:
            pass
        try:
            win.attributes("-alpha", self._alpha)
        except tk.TclError:
            pass

        bg = "#2d2d2d"
        fg = "#f3f3f3"
        sub = "#c8c8c8"
        win.configure(bg=bg)

        outer = tk.Frame(win, bg=bg, padx=14, pady=10)
        outer.pack(fill=tk.BOTH, expand=True)

        title_font = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        body_font = tkfont.Font(family="Segoe UI", size=10)

        tk.Label(
            outer,
            text=title,
            font=title_font,
            fg=fg,
            bg=bg,
            anchor="w",
            justify="left",
            wraplength=self._width - 36,
        ).pack(fill=tk.X)

        tk.Label(
            outer,
            text=body,
            font=body_font,
            fg=sub,
            bg=bg,
            anchor="nw",
            justify="left",
            wraplength=self._width - 36,
        ).pack(fill=tk.BOTH, expand=True, pady=(4, 0))

        def destroy_and_done() -> None:
            try:
                win.destroy()
            except tk.TclError:
                pass
            on_done()

        def animate_exit() -> None:
            frames = max(6, int(self._exit_ms / 14))
            y0 = end_y

            def ease_in_cubic(t: float) -> float:
                t = max(0.0, min(1.0, t))
                return t * t * t

            y_end = y0 - self._height - self._top_margin - 40
            step = {"i": 0}

            def tick_exit() -> None:
                i = step["i"]
                if i >= frames:
                    destroy_and_done()
                    return
                t = ease_in_cubic((i + 1) / frames)
                y = int(y0 + (y_end - y0) * t)
                win.geometry(f"{self._width}x{self._height}+{x}+{y}")
                step["i"] = i + 1
                self._root.after(14, tick_exit)

            tick_exit()

        def animate_enter_then_dwell() -> None:
            frames = max(6, int(self._enter_ms / 14))
            step = {"i": 0}

            def tick_enter() -> None:
                i = step["i"]
                if i >= frames:
                    win.geometry(f"{self._width}x{self._height}+{x}+{end_y}")
                    self._root.after(self._dwell_ms, animate_exit)
                    return
                t = self._ease_out_cubic((i + 1) / frames)
                y = int(start_y + (end_y - start_y) * t)
                win.geometry(f"{self._width}x{self._height}+{x}+{y}")
                step["i"] = i + 1
                self._root.after(14, tick_enter)

            win.geometry(f"{self._width}x{self._height}+{x}+{start_y}")
            tick_enter()

        animate_enter_then_dwell()
