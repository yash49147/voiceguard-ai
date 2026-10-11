from tests.test_calls import register_and_login, auth_header
import pytest
from starlette.websockets import WebSocketDisconnect
from unittest.mock import Mock
from app.services.streaming import CHUNK_SIZE_BYTES


def create_call(client, token):
    response = client.post(
        "/api/calls",
        headers=auth_header(token),
    )

    assert response.status_code == 201

    return response.json()["id"]


def test_authenticated_owner_can_connect(client):
    token = register_and_login(
        client,
        "stream-owner@example.com",
    )

    call_id = create_call(client, token)

    with client.websocket_connect(
        f"/api/ws/calls/{call_id}?token={token}"
    ) as websocket:
        response = websocket.receive_json()

        assert response["type"] == "connected"
        assert response["call_id"] == call_id


def test_binary_frame_is_accepted(client):
    token = register_and_login(
        client,
        "stream-frame@example.com",
    )

    call_id = create_call(client, token)

    with client.websocket_connect(
        f"/api/ws/calls/{call_id}?token={token}"
    ) as websocket:
        connected = websocket.receive_json()

        assert connected["type"] == "connected"

        websocket.send_bytes(b"audio-frame")

        response = websocket.receive_json()

        assert response["type"] == "frame_received"
        assert response["frame_count"] == 1
        assert response["buffered_bytes"] == 11


def test_multiple_frames_accumulate(client):
    token = register_and_login(
        client,
        "stream-multiple@example.com",
    )

    call_id = create_call(client, token)

    with client.websocket_connect(
        f"/api/ws/calls/{call_id}?token={token}"
    ) as websocket:
        connected = websocket.receive_json()

        assert connected["type"] == "connected"

        frames = [
            b"12345",
            b"1234567",
            b"1234567890",
        ]

        for frame in frames:
            websocket.send_bytes(frame)

            response = websocket.receive_json()

            assert response["type"] == "frame_received"

        assert response["frame_count"] == 3
        assert response["buffered_bytes"] == 22


def test_another_user_cannot_connect_to_call(client):
    token_a = register_and_login(
        client,
        "stream-user-a@example.com",
    )

    token_b = register_and_login(
        client,
        "stream-user-b@example.com",
    )

    call_id = create_call(client, token_a)

    try:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(
                f"/api/ws/calls/{call_id}?token={token_b}"
            ):
                pass

        assert exc_info.value.code == 1008
    except Exception as exc:
        assert "1008" in str(exc)


def test_ended_call_cannot_accept_streaming(client):
    token = register_and_login(
        client,
        "stream-ended@example.com",
    )

    call_id = create_call(client, token)

    response = client.patch(
        f"/api/calls/{call_id}/end",
        headers=auth_header(token),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"

    try:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(
                f"/api/ws/calls/{call_id}?token={token}"
            ):
                pass

        assert exc_info.value.code == 1008
    except Exception as exc:
        assert "1008" in str(exc)


from app.services.streaming import (
    BYTES_PER_SECOND,
    CHUNK_SIZE_BYTES,
    StreamingSession,
)


def test_streaming_session_does_not_complete_before_5_seconds():
    session = StreamingSession(call_id=1, user_id=1)

    chunks = session.add_frame(b"x" * (CHUNK_SIZE_BYTES - 1))

    assert chunks == []
    assert session.buffered_bytes == CHUNK_SIZE_BYTES - 1


def test_streaming_session_completes_one_5_second_chunk():
    session = StreamingSession(call_id=1, user_id=1)

    chunks = session.add_frame(b"x" * CHUNK_SIZE_BYTES)

    assert len(chunks) == 1
    assert len(chunks[0]) == CHUNK_SIZE_BYTES
    assert session.buffered_bytes == 0
    assert session.chunk_sequence == 1


def test_streaming_session_handles_multiple_5_second_chunks():
    session = StreamingSession(call_id=1, user_id=1)

    chunks = session.add_frame(b"x" * (CHUNK_SIZE_BYTES * 2))

    assert len(chunks) == 2
    assert len(chunks[0]) == CHUNK_SIZE_BYTES
    assert len(chunks[1]) == CHUNK_SIZE_BYTES
    assert session.buffered_bytes == 0
    assert session.chunk_sequence == 2


def test_streaming_session_keeps_remainder_after_completed_chunk():
    session = StreamingSession(call_id=1, user_id=1)

    remainder = 10_000

    chunks = session.add_frame(
        b"x" * (CHUNK_SIZE_BYTES + remainder)
    )

    assert len(chunks) == 1
    assert len(chunks[0]) == CHUNK_SIZE_BYTES
    assert session.buffered_bytes == remainder
    assert session.chunk_sequence == 1


def test_streaming_session_accumulates_across_frames():
    session = StreamingSession(call_id=1, user_id=1)

    first = BYTES_PER_SECOND * 2
    second = BYTES_PER_SECOND * 3

    assert session.add_frame(b"x" * first) == []

    chunks = session.add_frame(b"x" * second)

    assert len(chunks) == 1
    assert len(chunks[0]) == CHUNK_SIZE_BYTES
    assert session.buffered_bytes == 0



def test_single_frame_processes_two_chunks_in_sequence(
    client, monkeypatch
):
    token = register_and_login(
        client,
        "stream-two-chunks@example.com",
    )
    call_id = create_call(client, token)

    processor = Mock()
    processor.process_chunk.side_effect = [
        {
            "sequence_number": 1,
            "chunk_id": 101,
            "analysis_id": 201,
        },
        {
            "sequence_number": 2,
            "chunk_id": 102,
            "analysis_id": 202,
        },
    ]

    monkeypatch.setattr(
        "app.api.streaming.StreamingChunkProcessor",
        lambda db: processor,
    )

    with client.websocket_connect(
        f"/api/ws/calls/{call_id}?token={token}"
    ) as websocket:
        assert websocket.receive_json()["type"] == "connected"

        websocket.send_bytes(b"\x00" * (CHUNK_SIZE_BYTES * 2))

        frame_event = websocket.receive_json()
        first_result = websocket.receive_json()
        second_result = websocket.receive_json()

    assert frame_event["type"] == "frame_received"
    assert first_result["type"] == "chunk_processed"
    assert second_result["type"] == "chunk_processed"

    assert first_result["sequence_number"] == 1
    assert second_result["sequence_number"] == 2

    assert [
        call.kwargs["sequence_number"]
        for call in processor.process_chunk.call_args_list
    ] == [1, 2]


def test_streaming_continues_after_chunk_processing_failure(
    client, monkeypatch
):
    token = register_and_login(
        client,
        "stream-recovery@example.com",
    )
    call_id = create_call(client, token)

    processor = Mock()
    processor.process_chunk.side_effect = [
        RuntimeError("Internal inference details"),
        {
            "sequence_number": 2,
            "chunk_id": 102,
            "analysis_id": 202,
        },
    ]

    monkeypatch.setattr(
        "app.api.streaming.StreamingChunkProcessor",
        lambda db: processor,
    )

    with client.websocket_connect(
        f"/api/ws/calls/{call_id}?token={token}"
    ) as websocket:
        assert websocket.receive_json()["type"] == "connected"

        websocket.send_bytes(b"\x00" * (CHUNK_SIZE_BYTES * 2))

        frame_event = websocket.receive_json()
        error_event = websocket.receive_json()
        success_event = websocket.receive_json()

        # Verify the same WebSocket connection remains usable.
        websocket.send_text("ping")
        pong_event = websocket.receive_json()

    assert frame_event["type"] == "frame_received"

    assert error_event["type"] == "chunk_processing_error"
    assert error_event["sequence_number"] == 1
    assert error_event["message"] == (
        "Unable to process audio chunk. Streaming will continue."
    )
    assert "Internal inference details" not in str(error_event)

    assert success_event["type"] == "chunk_processed"
    assert success_event["sequence_number"] == 2

    assert pong_event["type"] == "pong"

    assert [
        call.kwargs["sequence_number"]
        for call in processor.process_chunk.call_args_list
    ] == [1, 2]
