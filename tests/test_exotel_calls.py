import httpx
import pytest
from sqlalchemy import select

from app.api import exotel_calls
from app.db.models import Call, ExotelCallMapping, User


def register_and_login(client, email, password="TestPassword123!"):
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "full_name": "Exotel Test User",
            "password": password,
        },
    )
    assert response.status_code == 201

    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200

    return response.json()["access_token"]


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def configure_exotel(monkeypatch):
    values = {
        "exotel_enabled": True,
        "exotel_account_sid": "test-account",
        "exotel_api_key": "test-api-key",
        "exotel_api_token": "test-api-token",
        "exotel_base_url": "https://api.in.exotel.com",
        "exotel_caller_id": "08000000000",
        "exotel_stream_url": "wss://voiceguard.example/api/ws/exotel",
        "exotel_stream_token": "test-stream-token",
        "exotel_status_callback_url": (
            "https://voiceguard.example/api/webhooks/exotel/status"
        ),
        "exotel_webhook_token": "test-webhook-token",
    }

    for name, value in values.items():
        monkeypatch.setattr(exotel_calls.settings, name, value)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeAsyncClient:
    def __init__(self, *args, response_payload=None, error=None, **kwargs):
        self.response_payload = response_payload
        self.error = error
        self.request_args = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def post(self, *args, **kwargs):
        self.request_args = (args, kwargs)

        if self.error:
            raise self.error

        return FakeResponse(self.response_payload)


def get_user_call(db_session, email):
    user = db_session.scalar(
        select(User).where(User.email == email)
    )
    assert user is not None

    return db_session.scalar(
        select(Call).where(Call.user_id == user.id)
    )


def test_outbound_call_rejected_when_exotel_disabled(
    client, monkeypatch
):
    monkeypatch.setattr(exotel_calls.settings, "exotel_enabled", False)

    token = register_and_login(client, "exotel-disabled@example.com")

    response = client.post(
        "/api/exotel/calls",
        json={"destination_number": "+14155552671"},
        headers=auth_header(token),
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Exotel integration is disabled"


def test_outbound_call_rejected_with_incomplete_configuration(
    client, monkeypatch
):
    configure_exotel(monkeypatch)
    monkeypatch.setattr(
        exotel_calls.settings, "exotel_stream_token", None
    )

    token = register_and_login(client, "exotel-config@example.com")

    response = client.post(
        "/api/exotel/calls",
        json={"destination_number": "+14155552671"},
        headers=auth_header(token),
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Exotel configuration is incomplete"


def test_outbound_call_rejects_invalid_destination(client):
    token = register_and_login(client, "exotel-invalid-number@example.com")

    response = client.post(
        "/api/exotel/calls",
        json={"destination_number": "12345"},
        headers=auth_header(token),
    )

    assert response.status_code == 422


def test_outbound_call_saves_provider_mapping(
    client, db_session, monkeypatch
):
    configure_exotel(monkeypatch)
    token = register_and_login(client, "exotel-success@example.com")

    fake_client = FakeAsyncClient(
        response_payload={
            "Call": {
                "Sid": "exotel-test-call-001",
                "Status": "queued",
            }
        }
    )
    monkeypatch.setattr(
        exotel_calls.httpx,
        "AsyncClient",
        lambda *args, **kwargs: fake_client,
    )

    response = client.post(
        "/api/exotel/calls",
        json={"destination_number": "+14155552671"},
        headers=auth_header(token),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["provider"] == "exotel"
    assert body["provider_call_id"] == "exotel-test-call-001"
    assert body["status"] == "queued"

    call = get_user_call(db_session, "exotel-success@example.com")
    assert call is not None
    assert call.status == "active"

    mapping = db_session.scalar(
        select(ExotelCallMapping).where(
            ExotelCallMapping.call_id == call.id,
            ExotelCallMapping.provider == "exotel",
        )
    )
    assert mapping is not None
    assert mapping.provider_call_id == "exotel-test-call-001"

    args, kwargs = fake_client.request_args
    assert args[0].endswith("/v1/Accounts/test-account/Calls/connect")
    assert kwargs["data"]["StreamType"] == "bidirectional"
    assert "sample-rate=16000" in kwargs["data"]["StreamUrl"]
    assert kwargs["auth"] == ("test-api-key", "test-api-token")


def test_outbound_call_marks_call_failed_on_provider_error(
    client, db_session, monkeypatch
):
    configure_exotel(monkeypatch)
    token = register_and_login(client, "exotel-provider-error@example.com")

    fake_client = FakeAsyncClient(
        error=httpx.ConnectError("simulated provider outage")
    )
    monkeypatch.setattr(
        exotel_calls.httpx,
        "AsyncClient",
        lambda *args, **kwargs: fake_client,
    )

    response = client.post(
        "/api/exotel/calls",
        json={"destination_number": "+14155552671"},
        headers=auth_header(token),
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Exotel call initiation failed"

    call = get_user_call(db_session, "exotel-provider-error@example.com")
    assert call is not None
    assert call.status == "failed"
    assert call.ended_at is not None

    mapping = db_session.scalar(
        select(ExotelCallMapping).where(
            ExotelCallMapping.call_id == call.id
        )
    )
    assert mapping is None


def test_outbound_call_rejects_provider_response_without_sid(
    client, db_session, monkeypatch
):
    configure_exotel(monkeypatch)
    token = register_and_login(client, "exotel-no-sid@example.com")

    fake_client = FakeAsyncClient(
        response_payload={"Call": {"Status": "queued"}}
    )
    monkeypatch.setattr(
        exotel_calls.httpx,
        "AsyncClient",
        lambda *args, **kwargs: fake_client,
    )

    response = client.post(
        "/api/exotel/calls",
        json={"destination_number": "+14155552671"},
        headers=auth_header(token),
    )

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "Exotel returned an invalid call identifier"
    )

    call = get_user_call(db_session, "exotel-no-sid@example.com")
    assert call is not None
    assert call.status == "failed"

    mapping = db_session.scalar(
        select(ExotelCallMapping).where(
            ExotelCallMapping.call_id == call.id
        )
    )
    assert mapping is None
