"""Disable Windows' own toast banners for Microsoft Teams (HKCU notification settings).

Graph / Notification Manager can still show its overlay; this only mutes the duplicate
OS-level Teams notifications when their app IDs appear under the standard registry path.
"""

from __future__ import annotations

import logging
import winreg

logger = logging.getLogger(__name__)

_SETTINGS = r"Software\Microsoft\Windows\CurrentVersion\Notifications\Settings"


def _is_teams_notification_app_id(name: str) -> bool:
    n = name.lower()
    if "msteams" in n:
        return True
    if "microsoftteams" in n:
        return True
    if "squirrel.teams" in n or n.startswith("com.squirrel.teams"):
        return True
    if "ms-teams" in n:
        return True
    # Store / AUMID style: ...!MSTeams or similar
    if n.endswith("!msteams"):
        return True
    return False


def disable_teams_windows_notifications() -> tuple[list[str], list[str]]:
    """Set ``Enabled`` = 0 for Teams-related subkeys. Returns (updated, skipped_errors)."""

    updated: list[str] = []
    errors: list[str] = []

    try:
        parent = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _SETTINGS, 0, winreg.KEY_READ)
    except OSError as e:
        logger.warning("Cannot open notification settings: %s", e)
        return updated, [str(e)]

    i = 0
    try:
        while True:
            try:
                sub = winreg.EnumKey(parent, i)
            except OSError:
                break
            i += 1
            if not _is_teams_notification_app_id(sub):
                continue
            path = f"{_SETTINGS}\\{sub}"
            try:
                with winreg.CreateKeyEx(
                    winreg.HKEY_CURRENT_USER,
                    path,
                    0,
                    winreg.KEY_SET_VALUE,
                ) as key:
                    winreg.SetValueEx(key, "Enabled", 0, winreg.REG_DWORD, 0)
                updated.append(sub)
                logger.info("Disabled Windows notifications registry entry: %s", sub)
            except OSError as e:
                err = f"{sub}: {e}"
                errors.append(err)
                logger.warning("%s", err)
    finally:
        try:
            parent.Close()
        except Exception:
            pass

    return updated, errors
