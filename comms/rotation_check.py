"""Stop-hook logic: detect rotation threshold, summarize the transcript via
three focused Ollama calls, INSERT the assembled body into the
``session_memory`` table, and rotate the gateway via ``POST /command /clear``.

Replaces the bash-based ``~/.claude/hooks/rotation_check.sh``. The bash entry
remains as a thin one-line wrapper that execs ``.venv/bin/python`` on
``~/.claude/hooks/rotation_check.py``.

Reads the Stop event JSON from stdin (passed through by the hook entry).
"""

from __future__ import annotations

import datetime
import json
import os
import sqlite3
import time
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_DIR = Path("/home/daniel/Storage/hive_mind_skippy")
SESSIONS_DB = PROJECT_DIR / "sessions.db"
LOG_DIR = PROJECT_DIR / "data" / "auto-remember"
LOG_FILE = LOG_DIR / "rotation.log"

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://192.168.4.64:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_ROTATION_MODEL", "gpt-oss:20b-32k")
GATEWAY_URL = os.environ.get("SKIPPY_GATEWAY_URL", "http://127.0.0.1:8421")
THRESHOLD_TOKENS = int(os.environ.get("ROTATION_TOKEN_THRESHOLD", "300000"))
CHARS_PER_TOKEN = int(os.environ.get("CHARS_PER_TOKEN", "4"))
TRANSCRIPT_TAIL_CHARS = int(os.environ.get("ROTATION_TRANSCRIPT_TAIL", "60000"))


# ---------------------------------------------------------------------------
# logging + env
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(msg: str) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(f"[{_now_iso()}] {msg}\n")
    except Exception:
        pass


def _load_env() -> None:
    env_path = PROJECT_DIR / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


# ---------------------------------------------------------------------------
# transcript parsing
# ---------------------------------------------------------------------------

def _read_turns(transcript_path: Path, n: int | None = None) -> list[dict]:
    turns: list[dict] = []
    try:
        raw = transcript_path.read_text()
    except Exception as exc:
        _log(f"transcript read failed: {exc}")
        return turns
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except Exception:
            continue
        kind = ev.get("type")
        if kind not in ("user", "assistant"):
            continue
        msg = ev.get("message") or {}
        content = msg.get("content")
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            parts = [
                c.get("text", "")
                for c in content
                if isinstance(c, dict) and c.get("type") == "text"
            ]
            text = "\n".join(p for p in parts if p)
        else:
            text = ""
        if text:
            turns.append({"role": kind, "text": text})
    return turns[-n:] if n else turns


def _transcript_blob(transcript_path: Path) -> str:
    """Concatenated user/assistant text, tail-capped for Ollama context."""
    body = "\n\n".join(f"## {t['role']}\n{t['text']}" for t in _read_turns(transcript_path))
    return body[-TRANSCRIPT_TAIL_CHARS:]


# ---------------------------------------------------------------------------
# sessions.db lookup
# ---------------------------------------------------------------------------

def _lookup_gateway_session(sid: str) -> dict | None:
    con = None
    try:
        con = sqlite3.connect(str(SESSIONS_DB))
        con.row_factory = sqlite3.Row
        row = con.execute(
            """
            SELECT s.id          AS gateway_id,
                   s.owner_type, s.owner_ref, s.model, s.mind_id, s.status,
                   s.claude_sid,
                   a.client_type, a.client_ref
              FROM sessions s
              LEFT JOIN active_sessions a ON s.id = a.session_id
             WHERE s.claude_sid = ? OR s.id = ?
            """,
            (sid, sid),
        ).fetchone()
        return dict(row) if row else None
    except Exception as exc:
        _log(f"sessions.db lookup failed: {exc}")
        return None
    finally:
        if con is not None:
            try:
                con.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Ollama — three focused structured calls
# ---------------------------------------------------------------------------

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
    "additionalProperties": False,
}

PROJECT_SCHEMA = {
    "type": "object",
    "properties": {
        "active": {"type": "boolean"},
        "goal": {"type": "string"},
        "success_criteria": {"type": "array", "items": {"type": "string"}},
        "current_step": {"type": "string"},
        "notes": {"type": "string"},
    },
    "required": ["active"],
    "additionalProperties": False,
}

STATE_SCHEMA = {
    "type": "object",
    "properties": {
        "files_edited": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "what_changed": {"type": "string"},
                },
                "required": ["path", "what_changed"],
                "additionalProperties": False,
            },
        },
        "recent_edits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "line_range": {"type": "string"},
                    "summary": {"type": "string"},
                },
                "required": ["path", "summary"],
                "additionalProperties": False,
            },
        },
        "in_flight_work": {"type": "array", "items": {"type": "string"}},
        "decisions_made": {"type": "array", "items": {"type": "string"}},
        "open_questions": {"type": "array", "items": {"type": "string"}},
        "next_step": {"type": "string"},
    },
    "required": ["next_step"],
    "additionalProperties": False,
}

SUMMARY_PROMPT = (
    "Summarize the following session transcript into a 2-3 sentence paragraph "
    "capturing the gist. Be concrete — real file paths, real decisions. Skip pleasantries.\n\n"
    "### Transcript\n{transcript}"
)
PROJECT_PROMPT = (
    "From the following session transcript, identify the concrete project (if any) in flight. "
    "If there is one, return active=true with goal, success criteria, current step, and any notes. "
    "If there isn't a coherent project under way (ops or chitchat), return active=false.\n\n"
    "### Transcript\n{transcript}"
)
STATE_PROMPT = (
    "From the following session transcript, extract the concrete working state: "
    "files edited (with what changed), recent line-range edits, in-flight work items, "
    "decisions made, open questions, and the single most important next step. "
    "Be specific. Use empty arrays when nothing applies. Do not invent files or decisions.\n\n"
    "### Transcript\n{transcript}"
)


def _ollama_structured(prompt: str, schema: dict, retries: int = 1) -> dict | None:
    payload = json.dumps(
        {
            "model": OLLAMA_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "format": schema,
            "stream": False,
            "options": {"temperature": 0.2},
        }
    ).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                raw = resp.read().decode()
            data = json.loads(raw)
            content = data.get("message", {}).get("content", "")
            return json.loads(content)
        except Exception as exc:
            _log(f"ollama call failed attempt={attempt + 1}: {exc}")
    return None


# ---------------------------------------------------------------------------
# DB write + gateway rotate
# ---------------------------------------------------------------------------

def _insert_session_memory(
    mind_id: str,
    mind_name: str,
    client_ref: str,
    session_id: str,
    body: dict,
) -> bool:
    body_json = json.dumps(body)
    last_exc: Exception | None = None
    for attempt in range(5):
        con = None
        try:
            con = sqlite3.connect(str(SESSIONS_DB), timeout=10.0, isolation_level=None)
            con.execute("BEGIN IMMEDIATE")
            con.execute(
                """
                INSERT INTO session_memory (mind_id, mind_name, client_ref, session_id, body)
                VALUES (?, ?, ?, ?, ?)
                """,
                (mind_id, mind_name, client_ref, session_id, body_json),
            )
            con.execute("COMMIT")
            return True
        except sqlite3.OperationalError as exc:
            last_exc = exc
            if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                _log(f"session_memory insert busy attempt={attempt + 1}: {exc}")
                time.sleep(0.5 * (2 ** attempt))
                continue
            _log(f"session_memory insert failed: {exc}")
            return False
        except Exception as exc:
            _log(f"session_memory insert failed: {exc}")
            return False
        finally:
            if con is not None:
                try:
                    con.close()
                except Exception:
                    pass
    _log(f"session_memory insert gave up after retries: {last_exc}")
    return False


def _gateway_clear(
    owner_type: str, owner_ref: str, client_ref: str, mind_id: str
) -> tuple[bool, str]:
    payload = json.dumps(
        {
            "content": "/clear",
            "owner_type": owner_type,
            "owner_ref": owner_ref,
            "client_ref": client_ref,
            "mind_id": mind_id,
        }
    ).encode()
    req = urllib.request.Request(
        f"{GATEWAY_URL}/command",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            resp_body = resp.read().decode()
        data = json.loads(resp_body)
        new_sid = data.get("id") or data.get("session_id")
        err = data.get("error")
        if not new_sid or err:
            return False, f"err={err} resp={resp_body[:300]}"
        return True, new_sid
    except Exception as exc:
        return False, f"exception={exc}"


# ---------------------------------------------------------------------------
# entry
# ---------------------------------------------------------------------------

def run(event: dict) -> None:
    if os.environ.get("HIVEMIND_GROUP_SESSION") or os.environ.get("ROTATION_SPAWN"):
        return

    _load_env()

    session_id = event.get("session_id") or ""
    transcript_path_str = event.get("transcript_path") or ""
    if not session_id or not transcript_path_str:
        return
    transcript_path = Path(transcript_path_str)
    if not transcript_path.is_file():
        return

    bytes_ = transcript_path.stat().st_size
    est_tokens = bytes_ // CHARS_PER_TOKEN
    if est_tokens < THRESHOLD_TOKENS:
        return

    meta = _lookup_gateway_session(session_id)
    if not meta or meta.get("status") == "closed" or not meta.get("client_ref"):
        if os.environ.get("ROTATION_DEBUG"):
            _log(
                f"threshold crossed sid={session_id} tokens={est_tokens} "
                f"meta={meta} — skip"
            )
        return

    owner_type = meta["owner_type"]
    owner_ref = meta["owner_ref"]
    client_ref = meta["client_ref"]
    mind_id = os.environ["MIND_ID"]
    mind_name = os.environ.get("MIND_NAME", "skippy")
    gateway_id = meta["gateway_id"]

    transcript_blob = _transcript_blob(transcript_path)
    last_turns = _read_turns(transcript_path, n=6)

    summary_resp = _ollama_structured(
        SUMMARY_PROMPT.format(transcript=transcript_blob), SUMMARY_SCHEMA
    )
    project_resp = _ollama_structured(
        PROJECT_PROMPT.format(transcript=transcript_blob), PROJECT_SCHEMA
    )
    state_resp = _ollama_structured(
        STATE_PROMPT.format(transcript=transcript_blob), STATE_SCHEMA
    )

    body: dict[str, Any] = {
        "written_at": _now_iso(),
        "summary": (summary_resp or {}).get("summary"),
        "project": project_resp,
        "files_edited": (state_resp or {}).get("files_edited", []),
        "recent_edits": (state_resp or {}).get("recent_edits", []),
        "in_flight_work": (state_resp or {}).get("in_flight_work", []),
        "decisions_made": (state_resp or {}).get("decisions_made", []),
        "open_questions": (state_resp or {}).get("open_questions", []),
        "next_step": (state_resp or {}).get("next_step"),
        "last_turns": last_turns,
    }

    if not _insert_session_memory(mind_id, mind_name, client_ref, gateway_id, body):
        _log(f"FAIL insert gateway_id={gateway_id} client_ref={client_ref}")
        return

    ok, info = _gateway_clear(owner_type, owner_ref, client_ref, mind_id)
    if not ok:
        _log(f"FAIL clear gateway_id={gateway_id} client_ref={client_ref} info={info}")
        return

    _log(
        f"ROTATED gateway_id={gateway_id} new={info} client_ref={client_ref} "
        f"mind_id={mind_id} est_tokens={est_tokens}"
    )
