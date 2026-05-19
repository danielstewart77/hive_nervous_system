"""Tests for comms.sms_inbound helpers."""

from __future__ import annotations

import hashlib
import hmac

import pytest

from comms.sms_inbound import (
    extract_message_fields,
    format_dispatch_content,
    verify_signature,
)


SECRET = "test-secret-32-bytes-or-whatever"


def _sign(body: bytes, timestamp: str, secret: str = SECRET) -> str:
    mac = hmac.new(secret.encode(), digestmod=hashlib.sha256)
    mac.update(body)
    mac.update(timestamp.encode())
    return mac.hexdigest()


# --- verify_signature -------------------------------------------------------


def test_verify_signature_accepts_valid_signature() -> None:
    body = b'{"event":"mms:downloaded"}'
    ts = "1779168000"
    sig = _sign(body, ts)
    assert verify_signature(body, ts, sig, SECRET) is True


def test_verify_signature_rejects_tampered_body() -> None:
    body = b'{"event":"mms:downloaded"}'
    ts = "1779168000"
    sig = _sign(body, ts)
    assert verify_signature(b'{"event":"sms:sent"}', ts, sig, SECRET) is False


def test_verify_signature_rejects_wrong_timestamp() -> None:
    body = b'{"event":"mms:downloaded"}'
    sig = _sign(body, "1779168000")
    assert verify_signature(body, "1779168999", sig, SECRET) is False


def test_verify_signature_rejects_wrong_secret() -> None:
    body = b'{"event":"mms:downloaded"}'
    ts = "1779168000"
    sig = _sign(body, ts, secret="different-secret")
    assert verify_signature(body, ts, sig, SECRET) is False


def test_verify_signature_accepts_uppercase_hex() -> None:
    body = b"hello"
    ts = "1"
    sig = _sign(body, ts).upper()
    assert verify_signature(body, ts, sig, SECRET) is True


@pytest.mark.parametrize(
    "body, ts, sig",
    [
        (b"", "1779168000", "deadbeef"),
        (b"x", "", "deadbeef"),
        (b"x", "1779168000", ""),
    ],
)
def test_verify_signature_rejects_empty_inputs(body: bytes, ts: str, sig: str) -> None:
    assert verify_signature(body, ts, sig, SECRET) is False


# --- extract_message_fields -------------------------------------------------


def test_extract_handles_nested_payload_shape() -> None:
    raw = {
        "event": "mms:downloaded",
        "deviceId": "abc123",
        "payload": {
            "messageId": "228",
            "phoneNumber": "+13466692364",
            "message": "Hello from Xiaolan",
            "receivedAt": "2026-05-19T08:06:54-05:00",
        },
    }
    fields = extract_message_fields(raw)
    assert fields["sender"] == "+13466692364"
    assert fields["text"] == "Hello from Xiaolan"
    assert fields["message_id"] == "228"
    assert fields["received_at"] == "2026-05-19T08:06:54-05:00"
    assert fields["event"] == "mms:downloaded"
    assert fields["device_id"] == "abc123"


def test_extract_handles_flat_payload_shape() -> None:
    raw = {
        "event": "sms:received",
        "phoneNumber": "+15551234567",
        "message": "hi",
        "messageId": "msg-1",
    }
    fields = extract_message_fields(raw)
    assert fields["sender"] == "+15551234567"
    assert fields["text"] == "hi"
    assert fields["message_id"] == "msg-1"


def test_extract_falls_back_through_aliases() -> None:
    raw = {
        "payload": {
            "sender": "+15551234567",
            "body": "fallback text",
            "id": "fallback-id",
            "createdAt": "2026-05-19T00:00:00Z",
        }
    }
    fields = extract_message_fields(raw)
    assert fields["sender"] == "+15551234567"
    assert fields["text"] == "fallback text"
    assert fields["message_id"] == "fallback-id"
    assert fields["received_at"] == "2026-05-19T00:00:00Z"


def test_extract_returns_none_for_missing_fields() -> None:
    raw = {"event": "mms:downloaded", "payload": {}}
    fields = extract_message_fields(raw)
    assert fields["sender"] is None
    assert fields["text"] is None
    assert fields["message_id"] is None
    assert fields["event"] == "mms:downloaded"


# --- format_dispatch_content ------------------------------------------------


def test_format_dispatch_content_uses_sender_and_text() -> None:
    out = format_dispatch_content("+15551234567", "hello world")
    assert "+15551234567" in out
    assert "hello world" in out
    assert out.startswith("Inbound SMS")


def test_format_dispatch_content_handles_missing_fields() -> None:
    out = format_dispatch_content(None, None)
    assert "unknown sender" in out
    assert "(no text in webhook payload)" in out


# --- /sms/inbound route -----------------------------------------------------
# Just the HMAC reject paths — happy-path dispatch requires broker_db and
# session_mgr fixtures the rest of comms doesn't have yet. First real
# delivery from the phone covers the happy path end-to-end.


def test_route_rejects_missing_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient
    monkeypatch.setenv("SMS_INBOUND_HMAC_SECRET", SECRET)
    from comms.server import app
    client = TestClient(app)
    resp = client.post("/sms/inbound", content=b'{"event":"x"}')
    assert resp.status_code == 401


def test_route_rejects_bad_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient
    monkeypatch.setenv("SMS_INBOUND_HMAC_SECRET", SECRET)
    from comms.server import app
    client = TestClient(app)
    resp = client.post(
        "/sms/inbound",
        content=b'{"event":"x"}',
        headers={"x-signature": "deadbeef", "x-timestamp": "1779168000"},
    )
    assert resp.status_code == 401


def test_route_returns_500_when_secret_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient
    monkeypatch.delenv("SMS_INBOUND_HMAC_SECRET", raising=False)
    from comms.server import app
    client = TestClient(app)
    resp = client.post("/sms/inbound", content=b'{"event":"x"}')
    assert resp.status_code == 500
