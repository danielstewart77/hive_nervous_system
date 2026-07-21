"""When a session's conversation id gets recorded.

It used to be written only on the ``result`` event — the end of the turn.
Anything asking "what conversation is this session on?" during a long turn
got nothing, and the web terminal's attach passes that answer through as
``resume_sid``. An empty answer makes the mind mint a fresh id, so clicking
a busy session in the terminal opened a blank chat next to a conversation
that was very much alive.

The id now lands from the first event that carries one.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from unittest.mock import patch

from comms.models import ModelRegistry, Provider
from comms.sessions import SessionManager


def _registry() -> ModelRegistry:
    return ModelRegistry({"anthropic": Provider(name="anthropic")}, {"opus": "anthropic"})


async def _make_manager(tmp: str) -> SessionManager:
    os.environ["SESSIONS_DB_PATH"] = os.path.join(tmp, "sessions.db")
    mgr = SessionManager(_registry())
    await mgr.start()
    return mgr


async def _seed(mgr: SessionManager, session_id: str = "sess-turn") -> str:
    now = time.time()
    await mgr._db.execute(
        """INSERT INTO sessions (id, owner_type, owner_ref, model, created_at, last_active,
                                 status, mind_id, summary)
           VALUES (?, 'telegram', '123', 'opus', ?, ?, 'running', 'ada', 'new chat')""",
        (session_id, now, now),
    )
    await mgr._db.commit()
    mgr._procs[session_id] = {"_mind_url": "http://mind.test:8420"}
    mgr._mind_ids[session_id] = "ada"
    return session_id


class _SseResponse:
    """A 200 streaming response over a canned list of events."""

    def __init__(self, events, on_event=None):
        self.status = 200
        self._events = events
        self._on_event = on_event

    @property
    def content(self):
        return self._lines()

    async def _lines(self):
        for event in self._events:
            yield ("data: " + json.dumps(event) + "\n").encode()
            if self._on_event:
                await self._on_event(event)

    async def text(self):
        return ""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _fake_session_class(response):
    class _FakeClientSession:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def post(self, url, **kwargs):
            return response

    return _FakeClientSession


def _drain(mgr, sid, response):
    async def go():
        with patch("aiohttp.ClientSession", _fake_session_class(response)):
            return [e async for e in mgr.send_message(sid, "hello")]

    return go()


async def _stored_sid(mgr: SessionManager, session_id: str) -> str | None:
    cur = await mgr._db.execute(
        "SELECT claude_sid FROM sessions WHERE id = ?", (session_id,)
    )
    row = await cur.fetchone()
    return row["claude_sid"] if row else None


def test_sid_is_recorded_from_the_init_event_not_the_result() -> None:
    async def scenario() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mgr = await _make_manager(tmp)
            try:
                sid = await _seed(mgr)
                seen: list[str | None] = []

                async def after(event):
                    # Snapshot what a concurrent attach would have been told.
                    seen.append(await _stored_sid(mgr, sid))

                response = _SseResponse(
                    [
                        {"type": "system", "subtype": "init", "session_id": "conv-1"},
                        {"type": "assistant", "message": {"content": "working"}},
                        {"type": "result", "session_id": "conv-1"},
                    ],
                    on_event=after,
                )
                await _drain(mgr, sid, response)

                # Recorded after the very first event, long before the result.
                assert seen[0] == "conv-1"
                assert await _stored_sid(mgr, sid) == "conv-1"
            finally:
                await mgr.shutdown()

    asyncio.run(scenario())


def test_sid_still_lands_when_only_the_result_carries_it() -> None:
    async def scenario() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mgr = await _make_manager(tmp)
            try:
                sid = await _seed(mgr)
                response = _SseResponse([
                    {"type": "assistant", "message": {"content": "hi"}},
                    {"type": "result", "session_id": "conv-2"},
                ])
                await _drain(mgr, sid, response)

                assert await _stored_sid(mgr, sid) == "conv-2"
            finally:
                await mgr.shutdown()

    asyncio.run(scenario())


def test_events_without_a_session_id_leave_the_recorded_one_alone() -> None:
    async def scenario() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mgr = await _make_manager(tmp)
            try:
                sid = await _seed(mgr)
                await mgr._db.execute(
                    "UPDATE sessions SET claude_sid = 'conv-existing' WHERE id = ?", (sid,)
                )
                await mgr._db.commit()

                response = _SseResponse([
                    {"type": "assistant", "message": {"content": "hi"}},
                    {"type": "result"},
                ])
                await _drain(mgr, sid, response)

                assert await _stored_sid(mgr, sid) == "conv-existing"
            finally:
                await mgr.shutdown()

    asyncio.run(scenario())
