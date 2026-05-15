"""Session bootstrap memory layers.

Provides two layers that `core/sessions.py::_build_base_prompt` composes
into the system prompt of every new session, after the soul block:

1. Standing rules (vector store, tier=standing)
2. Decay-weighted recent memory (vector store, tier=contextual, top-20)

Identity (the soul) is loaded by `core/sessions.py::_fetch_soul_sync`.
Rotation carry-forward is loaded by `core/sessions.py::_fetch_session_memory`.
"""
from __future__ import annotations

import os
from typing import Any

import requests

LUCENT_URL = os.environ.get("LUCENT_URL_SELF", "http://127.0.0.1:8425")
LUCENT_BEARER = os.environ.get("LUCENT_BEARER_TOKEN", "")
_AUTH_HEADERS = {"Authorization": f"Bearer {LUCENT_BEARER}"} if LUCENT_BEARER else {}

# Caps — chars/4 ≈ tokens. Budget bounds, not strict.
STANDING_RULES_CHAR_CAP = 2000   # ~500 tokens
RECENT_MEMORY_CHAR_CAP = 6000    # ~1500 tokens

REQUEST_TIMEOUT = 5  # seconds — bootstrap should never hang


def load_standing_rules() -> str:
    """Vector entries with tier=standing, flat-bullet block, ~500 token cap."""
    entries = _list_entries()
    standing = [e for e in entries if e.get("tier") == "standing"]
    if not standing:
        return ""
    bullets = "\n".join(f"- {e.get('content', '').strip()}" for e in standing)
    bullets = _truncate(bullets, STANDING_RULES_CHAR_CAP)
    return f"<standing-rules>\n{bullets}\n</standing-rules>"


def load_decay_weighted_recent() -> str:
    """Top-20 contextual rows by recency decay."""
    try:
        resp = requests.get(
            f"{LUCENT_URL}/memory/recent-decayed",
            params={"limit": 20},
            headers=_AUTH_HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        rows = resp.json()
    except Exception:
        return ""
    if not isinstance(rows, list) or not rows:
        return ""

    parts: list[str] = []
    for row in rows:
        cls = row.get("data_class", "?")
        content = (row.get("content") or "").strip().replace("\n", " ")
        score = row.get("score", 0.0)
        parts.append(f"- ({cls}) {content} [score={score:.2f}]")
    body = _truncate("\n".join(parts), RECENT_MEMORY_CHAR_CAP)
    return f"<recent-memory>\n{body}\n</recent-memory>"


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    head = text[:max_chars]
    if "\n" in head:
        head = head.rsplit("\n", 1)[0]
    return f"{head}\n…"


def _list_entries() -> list[dict[str, Any]]:
    try:
        resp = requests.get(
            f"{LUCENT_URL}/memory/list",
            params={"limit": 100},
            headers=_AUTH_HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    entries = data.get("entries")
    return entries if isinstance(entries, list) else []
