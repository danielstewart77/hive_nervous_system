"""Hive Glass — gateway-side turn-hop feed.

The panel renders which hop a turn is stuck at; the gateway must emit an
event per hop (received, dispatched, first_output, replied, error) into a
memory ring plus live fan-out queues with a heartbeat.
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


async def _seed_running_session(mgr: SessionManager) -> str:
    session_id = "sess-glass"
    now = time.time()
    await mgr._db.execute(
        """INSERT INTO sessions (id, owner_type, owner_ref, model, created_at, last_active,
                                 status, mind_id, summary)
           VALUES (?, 'telegram', '123', 'opus', ?, ?, 'running', 'ada', 'existing chat')""",
        (session_id, now, now),
    )
    await mgr._db.commit()
    mgr._procs[session_id] = {"_mind_url": "http://mind.test:8420"}
    mgr._mind_ids[session_id] = "ada"
    return session_id


class _FakeStreamContent:
    def __init__(self, lines: list[bytes]):
        self._lines = list(lines)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._lines:
            raise StopAsyncIteration
        return self._lines.pop(0)


class _FakeResponse:
    def __init__(self, status: int, body: str = "", sse_lines: list[bytes] | None = None):
        self.status = status
        self._body = body
        self.content = _FakeStreamContent(sse_lines or [])

    async def text(self) -> str:
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeClientSession:
    response: _FakeResponse = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def post(self, url, **kwargs):
        return type(self).response


def test_glass_emit_ring_and_snapshot() -> None:
    async def scenario() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mgr = await _make_manager(tmp)
            try:
                mgr._mind_ids["s1"] = "ada"
                mgr.glass_emit("received", "s1", preview="hi")
                mgr.glass_emit("replied", "s1", elapsed=1.2, is_error=False)
                snap = mgr.glass_snapshot()
                assert [e["hop"] for e in snap] == ["received", "replied"]
                assert snap[0]["mind_id"] == "ada"
                assert snap[0]["preview"] == "hi"
                assert snap[1]["elapsed"] == 1.2
                assert all("ts" in e for e in snap)
            finally:
                await mgr.shutdown()

    asyncio.run(scenario())


def test_glass_stream_delivers_events_and_heartbeats() -> None:
    async def scenario() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mgr = await _make_manager(tmp)
            try:
                # Heartbeat when idle.
                mgr.EVENT_HEARTBEAT_SECONDS = 0.05
                stream = mgr.glass_stream()
                event = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
                assert event["hop"] == "ping"
                # Live event delivery.
                mgr.glass_emit("received", "s1", mind_id="ada")
                event = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
                assert event["hop"] == "received"
                await stream.aclose()
                assert not mgr._glass_queues
            finally:
                await mgr.shutdown()

    asyncio.run(scenario())


def test_send_message_emits_hops_on_success() -> None:
    async def scenario() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mgr = await _make_manager(tmp)
            try:
                sid = await _seed_running_session(mgr)
                result = json.dumps({"type": "result", "is_error": False})
                _FakeClientSession.response = _FakeResponse(
                    200, sse_lines=[f"data: {result}\n".encode()]
                )
                with patch("aiohttp.ClientSession", _FakeClientSession):
                    async for _ in mgr.send_message(sid, "hello"):
                        pass
                hops = [e["hop"] for e in mgr.glass_snapshot()]
                assert hops == ["received", "dispatched", "first_output", "replied"]
                replied = mgr.glass_snapshot()[-1]
                assert replied["is_error"] is False
                assert "elapsed" in replied
            finally:
                await mgr.shutdown()

    asyncio.run(scenario())


def test_send_message_emits_error_hop_on_mind_failure() -> None:
    async def scenario() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mgr = await _make_manager(tmp)
            try:
                sid = await _seed_running_session(mgr)
                _FakeClientSession.response = _FakeResponse(
                    500, body='{"error": "Process not running"}'
                )
                with patch("aiohttp.ClientSession", _FakeClientSession):
                    async for _ in mgr.send_message(sid, "hello"):
                        pass
                hops = [e["hop"] for e in mgr.glass_snapshot()]
                assert hops == ["received", "dispatched", "error"]
                assert "Process not running" in mgr.glass_snapshot()[-1]["detail"]
            finally:
                await mgr.shutdown()

    asyncio.run(scenario())
