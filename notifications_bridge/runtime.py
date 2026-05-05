from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class AppRuntime:
    """Shared handles for tray, polling, and the mini CLI."""

    cfg: dict[str, Any]
    notifier: Any
    root: Any
    msal_app: Any
    cache_path: Path
