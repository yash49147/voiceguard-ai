import base64
import json
from unittest.mock import Mock

import pytest
from starlette.websockets import WebSocketDisconnect
from sqlalchemy import select

from app.api import exotel_stream
from app.db.models import Call, ExotelCallMapping, User
from app.services.streaming import CHUNK_SIZE_BYTES


TOKEN = "test-exotel-stream-token"
ACCOUNT_SID = "AC-test-account"


def configure_stream(monkeypatch):
    monkeypatch.setattr(exotel_stream.settings, "exotel_enabled", True)
    monkeypatch.setattr(
        exotel_stream.settings,
        "exotel_stream_token",
        TOKEN,
    )
    monkeypatch.setattr(
        exotel_stream.settings,
        "exotel_account_sid",
        ACCOUNT_SID,
    )


def make_mapped_call(client, db_session, email, provider_call_id):
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "full_name": "Exotel Stream Test",
            "password": "TestPassword123!",
        },
    )
    assert response.status_code == 201

    user = db_session.scalar(
        select(User).where(User.email == email)
    )
    assert user is not None

    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    call = Call(
        user_id=user.id,
        status="active",
        started_at=now,
        created_at=now,
    )
    db_session.add(call)
    db_session.flush()

    db_session.add(
        ExotelCallMapping(
            call_id=call.id,
            provider="exotel",
            provider_call_id=provider_call_id,
        )
    )
    db_session.commit()

    return call.id


def start_event(provider_call_id):
    return {
        "event": "start",
        "start": {
            "call_sid": provider_call_id,
            "account_sid": ACCOUNT_SID,
            "stream_sid": "MZ-test-stream",
            "media_format": {
                "encoding": "audio/x-raw",
                "sample_rate": "16000",
                "bit_rate": "16",
            },
        },
    }


def test_stream_rejects_invalid_token(client, monkeypatch):
    configure_stream(monkeypatch)

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            "/api/ws/exotel?token=wrong-token"
        ):
            pass


def test_stream_rejects_unknown_call_id(client, monkeypatch):
    configure_stream(monkeypatch)

    with client.websocket_connect(
        f"/api/ws/exotel?token={TOKEN}"
    ) as websocket:
        websocket.send_text(json.dumps({"event": "connected"}))
        websocket.send_text(json.dumps(start_event("unknown-call")))

        with pytest.raises(WebSocketDisconnect):
            websocket.receive_text()


def test_stream_processes_complete_five_second_chunk(
    client,
    db_session,
    monkeypatch,
):
    configure_stream(monkeypatch)

    call_id = make_mapped_call(
        client,
        db_session,
        "exotel-stream-valid@example.com",
        "exo-stream-call-001",
    )

    processor = Mock()
    processor.process_chunk.return_value = {"sequence_number": 1}

    monkeypatch.setattr(
        exotel_stream,
        "StreamingChunkProcessor",
        lambda db: processor,
    )

    audio = b"\x00" * CHUNK_SIZE_BYTES
    payload = base64.b64encode(audio).decode("ascii")

    with client.websocket_connect(
        f"/api/ws/exotel?token={TOKEN}"
    ) as websocket:
        websocket.send_text(json.dumps({"event": "connected"}))
        websocket.send_text(
            json.dumps(start_event("exo-stream-call-001"))
        )
        websocket.send_text(
            json.dumps(
                {
                    "event": "media",
                    "media": {
                        "payload": payload,
                    },
                }
            )
        )
        websocket.send_text(json.dumps({"event": "stop"}))

    processor.process_chunk.assert_called_once()
    kwargs = processor.process_chunk.call_args.kwargs

    assert kwargs["call_id"] == call_id
    assert kwargs["sequence_number"] == 1
    assert kwargs["pcm_audio"] == audio


def test_stream_rejects_wrong_sample_rate(
    client,
    db_session,
    monkeypatch,
):
    configure_stream(monkeypatch)

    make_mapped_call(
        client,
        db_session,
        "exotel-stream-rate@example.com",
        "exo-stream-call-002",
    )

    event = start_event("exo-stream-call-002")
    event["start"]["media_format"]["sample_rate"] = "8000"

    with client.websocket_connect(
        f"/api/ws/exotel?token={TOKEN}"
    ) as websocket:
        websocket.send_text(json.dumps({"event": "connected"}))
        websocket.send_text(json.dumps(event))

        with pytest.raises(WebSocketDisconnect):
            websocket.receive_text()


def test_stream_rejects_invalid_base64_audio(
    client,
    db_session,
    monkeypatch,
):
    configure_stream(monkeypatch)

    make_mapped_call(
        client,
        db_session,
        "exotel-stream-audio@example.com",
        "exo-stream-call-003",
    )

    with client.websocket_connect(
        f"/api/ws/exotel?token={TOKEN}"
    ) as websocket:
        websocket.send_text(json.dumps({"event": "connected"}))
        websocket.send_text(
            json.dumps(start_event("exo-stream-call-003"))
        )
        websocket.send_text(
            json.dumps(
                {
                    "event": "media",
                    "media": {"payload": "not-valid-base64!"},
                }
            )
        )

        with pytest.raises(WebSocketDisconnect):
            websocket.receive_text()
