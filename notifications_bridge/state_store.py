from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_lock = threading.Lock()


@dataclass
class AppState:
    initialized: bool = False
    chats: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> AppState:
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        chats = raw.get("chats") or {}
        if not isinstance(chats, dict):
            chats = {}
        return cls(initialized=bool(raw.get("initialized")), chats=chats)

    def save(self, path: Path) -> None:
        with _lock:
            path.write_text(
                json.dumps(
                    {"initialized": self.initialized, "chats": self.chats},
                    indent=2,
                ),
                encoding="utf-8",
            )
