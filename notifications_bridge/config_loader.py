from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

from notifications_bridge.paths import config_path, project_root

logger = logging.getLogger(__name__)


def ensure_config_exists() -> Path:
    """Copy config.example.json to config.json if missing."""
    root = project_root()
    dst = config_path()
    if dst.exists():
        return dst
    example = root / "config.example.json"
    if not example.exists():
        raise FileNotFoundError(f"Missing {example} and {dst}")
    shutil.copy(example, dst)
    return dst


def merge_and_save_config(updates: dict[str, Any]) -> None:
    """Merge keys into config.json and write atomically (best-effort)."""
    path = config_path()
    if not path.exists():
        ensure_config_exists()
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("config.json root must be an object")
    data.update(updates)
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    tmp.replace(path)


def load_config() -> dict:
    path = config_path()
    if not path.exists():
        ensure_config_exists()
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"config.json is not valid JSON ({e}).") from e
    if not isinstance(data, dict):
        raise ValueError("config.json must contain a JSON object at the root.")
    client_id = data.get("client_id", "").strip()
    if not client_id:
        raise ValueError(
            "Set client_id in config.json (Azure AD application / public client ID)."
        )
    if client_id == "00000000-0000-0000-0000-000000000000":
        logger.warning(
            "client_id is still the placeholder; Graph sign-in will fail until you set a real "
            "Azure AD public client ID in config.json (tray will still run)."
        )
    tenant_id = (data.get("tenant_id") or "organizations").strip()
    poll = int(data.get("poll_interval_seconds") or 60)
    poll = max(15, min(poll, 600))
    toast_app_id = (data.get("toast_app_id") or "NotificationManager").strip()
    use_top_overlay = bool(data.get("use_top_overlay", False))
    overlay_width = int(data.get("overlay_width") or 360)
    overlay_width = max(280, min(overlay_width, 520))
    overlay_height = int(data.get("overlay_height") or 92)
    overlay_height = max(64, min(overlay_height, 200))
    overlay_top_margin = int(data.get("overlay_top_margin") or 10)
    overlay_dwell_ms = int(float(data.get("overlay_dwell_seconds") or 5.5) * 1000)
    overlay_dwell_ms = max(1500, min(overlay_dwell_ms, 120_000))
    try:
        overlay_opacity = float(data.get("overlay_opacity", 0.96))
    except (TypeError, ValueError):
        overlay_opacity = 0.96
    overlay_opacity = max(0.35, min(1.0, overlay_opacity))
    overlay_enter_ms = int(data.get("overlay_enter_ms") or 220)
    overlay_exit_ms = int(data.get("overlay_exit_ms") or 260)
    return {
        "client_id": client_id,
        "tenant_id": tenant_id,
        "poll_interval_seconds": poll,
        "toast_app_id": toast_app_id,
        "use_top_overlay": use_top_overlay,
        "overlay_width": overlay_width,
        "overlay_height": overlay_height,
        "overlay_top_margin": overlay_top_margin,
        "overlay_dwell_ms": overlay_dwell_ms,
        "overlay_opacity": overlay_opacity,
        "overlay_enter_ms": overlay_enter_ms,
        "overlay_exit_ms": overlay_exit_ms,
    }
