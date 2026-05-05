from __future__ import annotations

import logging
from pathlib import Path

import msal

logger = logging.getLogger(__name__)

GRAPH_SCOPE = ["Chat.Read", "User.Read"]


def _persist_cache(cache: msal.SerializableTokenCache, path: Path) -> None:
    if cache.has_state_changed:
        path.write_text(cache.serialize(), encoding="utf-8")


def build_msal_app(client_id: str, tenant_id: str, cache_path: Path) -> msal.PublicClientApplication:
    cache = msal.SerializableTokenCache()
    if cache_path.exists():
        try:
            cache.deserialize(cache_path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed to deserialize token cache; starting fresh")

    authority = f"https://login.microsoftonline.com/{tenant_id}"
    return msal.PublicClientApplication(
        client_id,
        authority=authority,
        token_cache=cache,
    )


def acquire_token(
    app: msal.PublicClientApplication, cache_path: Path, *, interactive: bool
) -> str:
    cache = app.token_cache  # type: ignore[assignment]
    accounts = app.get_accounts()
    result = None
    if accounts:
        result = app.acquire_token_silent(GRAPH_SCOPE, account=accounts[0])

    if isinstance(result, dict) and result.get("access_token"):
        _persist_cache(cache, cache_path)
        return result["access_token"]

    if isinstance(result, dict) and result.get("error"):
        logger.info(
            "Silent token failed: %s — %s",
            result.get("error"),
            (result.get("error_description") or "")[:200],
        )

    if not interactive:
        raise RuntimeError("No valid access token; interactive sign-in required.")

    logger.info("Starting interactive sign-in (browser window)")
    result = app.acquire_token_interactive(GRAPH_SCOPE)
    if not isinstance(result, dict) or not result.get("access_token"):
        err = (
            (result or {}).get("error_description")
            or (result or {}).get("error")
            or "unknown"
        )
        raise RuntimeError(f"Sign-in failed: {err}")
    _persist_cache(cache, cache_path)
    return result["access_token"]


def sign_out(app: msal.PublicClientApplication, cache_path: Path) -> None:
    for a in app.get_accounts():
        app.remove_account(a)
    if cache_path.exists():
        cache_path.unlink()
