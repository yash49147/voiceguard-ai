from tests.test_calls import register_and_login, auth_header
import pytest
from starlette.websockets import WebSocketDisconnect

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