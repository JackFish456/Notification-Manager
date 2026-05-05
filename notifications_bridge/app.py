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
from notifications_bridge.paths import (
    app_data_dir,
    config_path,
    log_path,
    state_path as state_file_path,
    token_cache_path,
)
from notifications_bridge.state_store import AppState
from notifications_bridge.toast_service import ToastService

logger = logging.getLogger(__name__)

_stop = threading.Event()
_poll_thread: threading.Thread | None = None


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
    img = Image.new("RGB", (64, 64), (0, 120, 212))
    d = ImageDraw.Draw(img)
    d.rectangle((12, 12, 51, 51), outline=(255, 255, 255), width=2)
    d.text((24, 18), "T", fill=(255, 255, 255))
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

    if not state.initialized:
        state.initialized = True
        logger.info("Initial sync complete; future chat updates will raise toasts.")
    state.save(state_file)


def _poll_loop(app, cache_path, notifier: Any, interval: int) -> None:
    while not _stop.is_set():
        try:
            _poll_cycle(app, cache_path, notifier, state_file_path())
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


def _start_background_poll(app, cache_path, notifier: Any, interval: int) -> None:
    global _poll_thread
    if _poll_thread and _poll_thread.is_alive():
        return

    def run() -> None:
        _poll_loop(app, cache_path, notifier, interval)

    _poll_thread = threading.Thread(target=run, name="graph-poll", daemon=True)
    _poll_thread.start()


def run_tray(cfg: dict, notifier: Any, tk_root: Any | None) -> None:
    cache_path = token_cache_path()
    msal_app = build_msal_app(cfg["client_id"], cfg["tenant_id"], cache_path)

    def on_quit(icon, _item) -> None:
        _stop.set()
        icon.stop()
        if tk_root is not None:
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

    menu = pystray.Menu(
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
        )
        icon.visible = True

    icon.run(setup=setup)


def main() -> None:
    _setup_logging()
    ensure_config_exists()
    cfg = load_config()

    if cfg["use_top_overlay"]:
        import tkinter as tk

        from notifications_bridge.top_overlay import TopOverlayManager

        root = tk.Tk()
        root.withdraw()
        notifier = TopOverlayManager(
            root,
            width=cfg["overlay_width"],
            height=cfg["overlay_height"],
            top_margin=cfg["overlay_top_margin"],
            dwell_ms=cfg["overlay_dwell_ms"],
            enter_ms=cfg["overlay_enter_ms"],
            exit_ms=cfg["overlay_exit_ms"],
        )
        threading.Thread(
            target=lambda: run_tray(cfg, notifier, root),
            daemon=True,
            name="tray",
        ).start()
        root.mainloop()
    else:
        notifier = ToastService(cfg["toast_app_id"])
        run_tray(cfg, notifier, None)
