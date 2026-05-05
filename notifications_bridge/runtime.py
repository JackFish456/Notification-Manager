from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
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
    graph_polling_enabled: bool = True
    on_quit_application: Callable[[], None] | None = field(default=None)
