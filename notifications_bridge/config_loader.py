from __future__ import annotations

import json
import shutil
from pathlib import Path

from notifications_bridge.paths import config_path, project_root


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


def load_config() -> dict:
    path = config_path()
    if not path.exists():
        ensure_config_exists()
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    client_id = data.get("client_id", "").strip()
    if not client_id or client_id == "00000000-0000-0000-0000-000000000000":
        raise ValueError(
            "Set client_id in config.json (Azure AD application / public client ID)."
        )
    tenant_id = (data.get("tenant_id") or "organizations").strip()
    poll = int(data.get("poll_interval_seconds") or 60)
    poll = max(15, min(poll, 600))
    toast_app_id = (data.get("toast_app_id") or "GraphTeamsNotifyBridge").strip()
    return {
        "client_id": client_id,
        "tenant_id": tenant_id,
        "poll_interval_seconds": poll,
        "toast_app_id": toast_app_id,
    }
