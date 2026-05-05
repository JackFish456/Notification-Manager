from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def app_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    d = Path(base) / "GraphTeamsNotifyBridge"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    return project_root() / "config.json"


def state_path() -> Path:
    return app_data_dir() / "state.json"


def log_path() -> Path:
    return app_data_dir() / "bridge.log"


def token_cache_path() -> Path:
    return app_data_dir() / "msal_token.bin"
