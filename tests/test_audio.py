import io
import wave


def create_wav_bytes(
    duration_seconds=5,
    sample_rate=16000,
    channels=1,
):
    frame_count = int(
        duration_seconds * sample_rate
    )

    audio_data = b"\x00\x00" * frame_count * channels

    buffer = io.BytesIO()

    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(audio_data)

    buffer.seek(0)

    return buffer


def register_and_login(client, email):
    password = "TestPassword123!"

    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "full_name": "Audio Test User",
            "password": password,
        },
    )

    assert response.status_code == 201

    response = client.post(
        "/api/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )

    assert response.status_code == 200

    return response.json()["access_token"]


def auth_header(token):
    return {
        "Authorization": f"Bearer {token}",
    }


def create_call(client, token):
    response = client.post(
        "/api/calls",
        headers=auth_header(token),
    )

    assert response.status_code == 201

    return response.json()["id"]


def upload_chunk(
    client,
    token,
    call_id,
    sequence_number,
    duration_seconds=5,
):
    audio = create_wav_bytes(
        duration_seconds=duration_seconds
    )

    return client.post(
        f"/api/calls/{call_id}/chunks",
        params={
            "sequence_number": sequence_number,
        },
        headers=auth_header(token),
        files={
            "file": (
                f"chunk_{sequence_number}.wav",
                audio,
                "audio/wav",
            )
        },
    )


def test_upload_five_second_audio_chunk(client):
    token = register_and_login(
        client,
        "audio-upload@example.com",
    )

    call_id = create_call(client, token)

    response = upload_chunk(
        client,
        token,
        call_id,
        sequence_number=1,
    )

    assert response.status_code == 201

    data = response.json()

    assert data["call_id"] == call_id
    assert data["sequence_number"] == 1
    assert data["duration_ms"] == 5000
    assert data["sample_rate"] == 16000
    assert data["channels"] == 1
    assert data["audio_format"] == "wav"
    assert data["file_size_bytes"] > 0


def test_reject_short_audio_chunk(client):
    token = register_and_login(
        client,
        "audio-short@example.com",
    )

    call_id = create_call(client, token)

    response = upload_chunk(
        client,
        token,
        call_id,
        sequence_number=1,
        duration_seconds=3,
    )

    assert response.status_code == 400
    assert "approximately 5 seconds" in response.json()["detail"]


def test_reject_long_audio_chunk(client):
    token = register_and_login(
        client,
        "audio-long@example.com",
    )

    call_id = create_call(client, token)

    response = upload_chunk(
        client,
        token,
        call_id,
        sequence_number=1,
        duration_seconds=7,
    )

    assert response.status_code == 400
    assert "approximately 5 seconds" in response.json()["detail"]


def test_reject_duplicate_chunk_sequence(client):
    token = register_and_login(
        client,
        "audio-duplicate@example.com",
    )

    call_id = create_call(client, token)

    first = upload_chunk(
        client,
        token,
        call_id,
        sequence_number=1,
    )

    assert first.status_code == 201

    second = upload_chunk(
        client,
        token,
        call_id,
        sequence_number=1,
    )

    assert second.status_code == 409


def test_reject_audio_for_ended_call(client):
    token = register_and_login(
        client,
        "audio-ended@example.com",
    )

    call_id = create_call(client, token)

    response = client.patch(
        f"/api/calls/{call_id}/end",
        headers=auth_header(token),
    )

    assert response.status_code == 200

    response = upload_chunk(
        client,
        token,
        call_id,
        sequence_number=1,
    )

    assert response.status_code == 409


def test_user_cannot_upload_to_another_users_call(client):
    token_a = register_and_login(
        client,
        "audio-user-a@example.com",
    )

    token_b = register_and_login(
        client,
        "audio-user-b@example.com",
    )

    call_id = create_call(client, token_a)

    response = upload_chunk(
        client,
        token_b,
        call_id,
        sequence_number=1,
    )

    assert response.status_code == 404


def test_audio_requires_authentication(client):
    audio = create_wav_bytes()

    response = client.post(
        "/api/calls/1/chunks",
        params={
            "sequence_number": 1,
        },
        files={
            "file": (
                "chunk.wav",
                audio,
                "audio/wav",
            )
        },
    )

    assert response.status_code in (401, 403)