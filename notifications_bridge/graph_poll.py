from __future__ import annotations

import html
import logging
import re
from typing import Any
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

GRAPH = "https://graph.microsoft.com/v1.0"


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def list_chats(token: str) -> list[dict[str, Any]]:
    url = f"{GRAPH}/me/chats"
    params = {"$top": "50", "$select": "id,topic,lastUpdatedDateTime,chatType"}
    r = requests.get(url, headers=_headers(token), params=params, timeout=60)
    if r.status_code != 200:
        logger.error("list_chats failed: %s %s", r.status_code, r.text[:500])
        r.raise_for_status()
    data = r.json()
    return list(data.get("value") or [])


def latest_message(token: str, chat_id: str) -> dict[str, Any] | None:
    enc = quote(chat_id, safe="")
    url = f"{GRAPH}/me/chats/{enc}/messages"
    params = {"$top": "1", "$orderby": "createdDateTime desc"}
    r = requests.get(url, headers=_headers(token), params=params, timeout=60)
    if r.status_code != 200:
        logger.error("latest_message failed for chat %s: %s %s", chat_id, r.status_code, r.text[:500])
        r.raise_for_status()
    items = (r.json().get("value") or [])
    return items[0] if items else None


_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str | None) -> str:
    if not text:
        return ""
    plain = _TAG_RE.sub("", text)
    plain = html.unescape(plain)
    plain = " ".join(plain.split())
    return plain[:400]


def message_sender_name(msg: dict[str, Any]) -> str:
    body = msg.get("from") or {}
    user = body.get("user") or {}
    name = user.get("displayName")
    if name:
        return str(name)
    app = body.get("application") or {}
    if app.get("displayName"):
        return str(app["displayName"])
    return "Teams"


def format_toast(chat: dict[str, Any], msg: dict[str, Any]) -> tuple[str, str]:
    topic = chat.get("topic") or chat.get("chatType") or "Teams"
    title = f"Teams: {topic}"
    sender = message_sender_name(msg)
    preview = strip_html((msg.get("body") or {}).get("content"))
    if not preview:
        preview = "(no preview)"
    body = f"{sender}: {preview}"
    return title, body
