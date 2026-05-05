from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

import pystray
import requests
from PIL import Image, ImageDraw

from notifications_bridge.config_loader import ensure_config_exists, load_config
from notifications_bridge.graph_auth import acquire_token, build_msal_app, sign_out
from notifications_bridge.graph_poll import format_toast, latest_message, list_chats
from notifications_bridge.mini_cli import MiniCliWindow
from notifications_bridge.paths import (
    app_data_dir,
    config_path,
    log_path,
    state_path as state_file_path,
    token_cache_path,
)
from notifications_bridge.runtime import AppRuntime
from notifications_bridge.state_store import AppState
from notifications_bridge.toast_service import ToastService

logger = logging.getLogger(__name__)

_stop = threading.Event()
_poll_thread: threading.Thread | None = None
_last_poll_ok_at: float | None = None
_placeholder_poll_notice_logged = False


def _setup_logging() -> None:
    log_path().parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.FileHandler(log_path(), encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(fh)
    root.addHandler(sh)


def _tray_image() -> Image.Image:
    """Monitor-style tray icon: screen + accent dot (pink, not yellow)."""
    img = Image.new("RGB", (64, 64), (28, 28, 30))
    d = ImageDraw.Draw(img)
    # stand
    d.rectangle((26, 54, 37, 58), fill=(72, 72, 76))
    # bezel
    d.rounded_rectangle((6, 8, 57, 48), radius=5, fill=(52, 52, 56))
    # screen (cool neutral; was easy to tint yellow on some themes)
    d.rounded_rectangle((11, 13, 52, 43), radius=3, fill=(225, 232, 242))
    # notification badge — pink instead of classic yellow dot
    pink = (236, 72, 153)
    d.ellipse((40, 30, 52, 42), fill=pink, outline=(255, 182, 218), width=1)
    return img


def _open_in_explorer(path: str) -> None:
    try:
        os.startfile(path)  # type: ignore[attr-defined]
    except Exception:
        subprocess.run(["explorer", path], check=False)


def _open_config() -> None:
    p = str(config_path())
    try:
        os.startfile(p)  # type: ignore[attr-defined]
    except Exception:
        subprocess.run(["notepad", p], check=False)


def _poll_cycle(app, cache_path, notifier: Any, state_file: Path) -> None:
    try:
        token = acquire_token(app, cache_path, interactive=False)
    except RuntimeError:
        logger.info("Silent auth unavailable; opening interactive sign-in if needed.")
        token = acquire_token(app, cache_path, interactive=True)

    state = AppState.load(state_file)
    chats = list_chats(token)

    for chat in chats:
        chat_id = chat.get("id")
        if not chat_id:
            continue
        try:
            updated = chat.get("lastUpdatedDateTime")
            prev = state.chats.get(chat_id)

            if not state.initialized:
                msg = latest_message(token, chat_id)
                mid = msg.get("id") if msg else None
                state.chats[chat_id] = {
                    "last_message_id": mid,
                    "last_updated": updated,
                }
                continue

            if prev is None:
                msg = latest_message(token, chat_id)
                mid = msg.get("id") if msg else None
                state.chats[chat_id] = {
                    "last_message_id": mid,
                    "last_updated": updated,
                }
                continue

            prev_updated = prev.get("last_updated")
            prev_mid = prev.get("last_message_id")
            if updated == prev_updated:
                continue

            msg = latest_message(token, chat_id)
            if not msg:
                state.chats[chat_id] = {
                    "last_message_id": prev_mid,
                    "last_updated": updated,
                }
                continue
            mid = msg.get("id")
            if mid and mid != prev_mid and prev_mid is not None:
                if msg.get("messageType") in (None, "message"):
                    title, body = format_toast(chat, msg)
                    notifier.show(title, body)
            state.chats[chat_id] = {
                "last_message_id": mid or prev_mid,
                "last_updated": updated,
            }
        except Exception:
            logger.exception("Skipping chat %s due to error", chat_id)
            continue

    if not state.initialized:
        state.initialized = True
        logger.info("Initial sync complete; future chat updates will raise toasts.")
    state.save(state_file)


def _poll_loop(
    app,
    cache_path,
    notifier: Any,
    interval: int,
    *,
    graph_polling_enabled: bool,
) -> None:
    global _last_poll_ok_at, _placeholder_poll_notice_logged
    while not _stop.is_set():
        if not graph_polling_enabled:
            if not _placeholder_poll_notice_logged:
                logger.warning(
                    "Graph polling is paused: set a real Azure client_id in config.json and restart "
                    "(tray and Mini CLI stay available)."
                )
                _placeholder_poll_notice_logged = True
            for _ in range(interval):
                if _stop.is_set():
                    break
                time.sleep(1)
            continue
        try:
            _poll_cycle(app, cache_path, notifier, state_file_path())
            _last_poll_ok_at = time.time()
        except requests.HTTPError as e:
            resp = e.response
            if resp is not None and resp.status_code == 401:
                logger.warning("401 from Graph; clearing silent auth may be needed (use tray Sign in).")
            else:
                logger.exception("HTTP error during poll")
        except Exception:
            logger.exception("Poll cycle failed")
        for _ in range(interval):
            if _stop.is_set():
                break
            time.sleep(1)


def _start_background_poll(
    app,
    cache_path,
    notifier: Any,
    interval: int,
    *,
    graph_polling_enabled: bool,
) -> None:
    global _poll_thread
    if _poll_thread and _poll_thread.is_alive():
        return

    def run() -> None:
        _poll_loop(
            app,
            cache_path,
            notifier,
            interval,
            graph_polling_enabled=graph_polling_enabled,
        )

    _poll_thread = threading.Thread(target=run, name="graph-poll", daemon=True)
    _poll_thread.start()


def run_tray(rt: AppRuntime) -> None:
    cfg = rt.cfg
    notifier = rt.notifier
    tk_root = rt.root
    msal_app = rt.msal_app
    cache_path = rt.cache_path

    def on_quit(icon, _item) -> None:
        _stop.set()
        icon.stop()
        try:
            tk_root.after(0, tk_root.quit)
        except Exception:
            logger.exception("Failed to stop Tk root")

    def on_sign_out(_icon, _item) -> None:
        try:
            sign_out(msal_app, cache_path)
            p = state_file_path()
            if p.exists():
                p.unlink()
            logger.info("Signed out; token cache and state cleared.")
        except Exception:
            logger.exception("Sign out failed")

    def on_open_data(_icon, _item) -> None:
        _open_in_explorer(str(app_data_dir()))

    def on_open_config(_icon, _item) -> None:
        _open_config()

    def on_help(_icon, _item) -> None:
        webbrowser.open(
            "https://github.com/AzureAD/microsoft-authentication-library-for-python/wiki"
        )

    def on_cli(_icon, _item) -> None:
        MiniCliWindow.open_or_focus(rt)

    menu = pystray.Menu(
        pystray.MenuItem("Mini CLI…", on_cli),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Open data folder", on_open_data),
        pystray.MenuItem("Edit config.json", on_open_config),
        pystray.MenuItem("Sign out", on_sign_out),
        pystray.MenuItem("MSAL help (browser)", on_help),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", on_quit),
    )

    icon = pystray.Icon(
        "graph_teams_notify",
        _tray_image(),
        "Graph Teams notify bridge",
        menu,
    )

    def setup(icon) -> None:
        _stop.clear()
        _start_background_poll(
            msal_app,
            cache_path,
            notifier,
            cfg["poll_interval_seconds"],
            graph_polling_enabled=rt.graph_polling_enabled,
        )
        icon.visible = True
        logger.info("Tray icon is running (check hidden icons ^ if you do not see it).")

    icon.run(setup=setup)


def main() -> None:
    _setup_logging()
    ensure_config_exists()

    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()
    try:
        root.update_idletasks()
    except tk.TclError:
        pass

    try:
        cfg = load_config()
    except ValueError as e:
        messagebox.showerror(
            "Notification Manager",
            f"{e}\n\nFile:\n{config_path()}",
        )
        root.destroy()
        return
    except Exception as e:
        messagebox.showerror(
            "Notification Manager",
            f"Could not load config:\n{e!r}\n\nFile:\n{config_path()}",
        )
        root.destroy()
        return

    cache_path = token_cache_path()
    msal_app = build_msal_app(cfg["client_id"], cfg["tenant_id"], cache_path)

    if cfg["use_top_overlay"]:
        from notifications_bridge.top_overlay import TopOverlayManager

        notifier = TopOverlayManager(
            root,
            width=cfg["overlay_width"],
            height=cfg["overlay_height"],
            top_margin=cfg["overlay_top_margin"],
            dwell_ms=cfg["overlay_dwell_ms"],
            enter_ms=cfg["overlay_enter_ms"],
            exit_ms=cfg["overlay_exit_ms"],
        )
    else:
        notifier = ToastService(cfg["toast_app_id"])

    placeholder = cfg["client_id"].strip() == "00000000-0000-0000-0000-000000000000"
    rt = AppRuntime(
        cfg=cfg,
        notifier=notifier,
        root=root,
        msal_app=msal_app,
        cache_path=cache_path,
        graph_polling_enabled=not placeholder,
    )
    threading.Thread(target=lambda: run_tray(rt), daemon=True, name="tray").start()
    root.mainloop()
