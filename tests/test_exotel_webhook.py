from sqlalchemy import select

from app.api import exotel_webhook
from app.db.models import Call, ExotelCallMapping, User


TEST_TOKEN = "test-exotel-webhook-token"


def prepare_mapped_call(
    client,
    db_session,
    email,
    provider_call_id,
):
    registration = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "full_name": "Exotel Webhook Test",
            "password": "TestPassword123!",
        },
    )
    assert registration.status_code == 201

    login = client.post(
        "/api/auth/login",
        json={
            "email": email,
            "password": "TestPassword123!",
        },
    )
    assert login.status_code == 200

    token = login.json()["access_token"]

    response = client.post(
        "/api/calls",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201

    call_id = response.json()["id"]

    user = db_session.scalar(
        select(User).where(User.email == email)
    )
    call = db_session.scalar(
        select(Call).where(Call.id == call_id)
    )

    assert user is not None
    assert call is not None

    db_session.add(
        ExotelCallMapping(
            call_id=call.id,
            provider="exotel",
            provider_call_id=provider_call_id,
        )
    )
    db_session.commit()

    return call_id


def enable_test_webhook(monkeypatch):
    monkeypatch.setattr(
        exotel_webhook.settings,
        "exotel_enabled",
        True,
    )
    monkeypatch.setattr(
        exotel_webhook.settings,
        "exotel_webhook_token",
        TEST_TOKEN,
    )


def test_webhook_rejects_invalid_token(
    client,
    db_session,
    monkeypatch,
):
    enable_test_webhook(monkeypatch)

    response = client.post(
        "/api/webhooks/exotel/status?token=wrong-token",
        json={
            "CallSid": "unknown-call",
            "CallStatus": "completed",
        },
    )

    assert response.status_code == 401


def test_webhook_rejects_unknown_provider_call(
    client,
    monkeypatch,
):
    enable_test_webhook(monkeypatch)

    response = client.post(
        f"/api/webhooks/exotel/status?token={TEST_TOKEN}",
        json={
            "CallSid": "unknown-call",
            "CallStatus": "completed",
        },
    )

    assert response.status_code == 404


def test_webhook_completes_mapped_call(
    client,
    db_session,
    monkeypatch,
):
    enable_test_webhook(monkeypatch)

    call_id = prepare_mapped_call(
        client,
        db_session,
        "exotel-webhook-complete@example.com",
        "exo-call-complete-001",
    )

    response = client.post(
        f"/api/webhooks/exotel/status?token={TEST_TOKEN}",
        json={
            "CallSid": "exo-call-complete-001",
            "CallStatus": "completed",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"

    db_session.expire_all()
    call = db_session.get(Call, call_id)

    assert call is not None
    assert call.status == "completed"
    assert call.ended_at is not None


def test_duplicate_terminal_callback_does_not_reopen_call(
    client,
    db_session,
    monkeypatch,
):
    enable_test_webhook(monkeypatch)

    call_id = prepare_mapped_call(
        client,
        db_session,
        "exotel-webhook-duplicate@example.com",
        "exo-call-duplicate-001",
    )

    url = (
        f"/api/webhooks/exotel/status?token={TEST_TOKEN}"
    )
    payload = {
        "CallSid": "exo-call-duplicate-001",
        "CallStatus": "completed",
    }

    first = client.post(url, json=payload)
    assert first.status_code == 200

    db_session.expire_all()
    call = db_session.get(Call, call_id)
    assert call is not None
    original_ended_at = call.ended_at

    second = client.post(url, json=payload)
    assert second.status_code == 200
    assert second.json()["duplicate_or_stale"] is True

    db_session.expire_all()
    call = db_session.get(Call, call_id)

    assert call is not None
    assert call.status == "completed"
    assert call.ended_at == original_ended_at


def test_webhook_accepts_form_encoded_callback(
    client,
    db_session,
    monkeypatch,
):
    enable_test_webhook(monkeypatch)

    prepare_mapped_call(
        client,
        db_session,
        "exotel-webhook-form@example.com",
        "exo-call-form-001",
    )

    response = client.post(
        f"/api/webhooks/exotel/status?token={TEST_TOKEN}",
        data={
            "CallSid": "exo-call-form-001",
            "CallStatus": "no-answer",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "no-answer"

def test_webhook_activates_initiating_call(
    client,
    db_session,
    monkeypatch,
):
    enable_test_webhook(monkeypatch)

    call_id = prepare_mapped_call(
        client,
        db_session,
        "exotel-webhook-initiating-active@example.com",
        "exo-call-initiating-active-001",
    )

    db_session.expire_all()
    call = db_session.get(Call, call_id)
    assert call is not None
    call.status = "initiating"
    db_session.commit()

    response = client.post(
        f"/api/webhooks/exotel/status?token={TEST_TOKEN}",
        json={
            "CallSid": "exo-call-initiating-active-001",
            "CallStatus": "ringing",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "active"

    db_session.expire_all()
    call = db_session.get(Call, call_id)
    assert call is not None
    assert call.status == "active"
    assert call.ended_at is None


def test_webhook_terminates_initiating_call(
    client,
    db_session,
    monkeypatch,
):
    enable_test_webhook(monkeypatch)

    call_id = prepare_mapped_call(
        client,
        db_session,
        "exotel-webhook-initiating-terminal@example.com",
        "exo-call-initiating-terminal-001",
    )

    db_session.expire_all()
    call = db_session.get(Call, call_id)
    assert call is not None
    call.status = "initiating"
    db_session.commit()

    response = client.post(
        f"/api/webhooks/exotel/status?token={TEST_TOKEN}",
        json={
            "CallSid": "exo-call-initiating-terminal-001",
            "CallStatus": "completed",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"

    db_session.expire_all()
    call = db_session.get(Call, call_id)
    assert call is not None
    assert call.status == "completed"
    assert call.ended_at is not None
