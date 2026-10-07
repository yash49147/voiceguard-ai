from pathlib import Path

import numpy as np
import pytest

from app.db.models import AudioAnalysis, AudioChunk
from app.ml.classifier import VoiceClassifier
from app.ml.model_manager import ModelManager
from tests.test_audio_features import create_test_wav
from app.db.models import AlertEvent
from app.db.database import SessionLocal

from tests.test_audio import (
    auth_header,
    create_call,
    create_wav_bytes,
    register_and_login,
    upload_chunk,
)


def test_analyze_audio_chunk(client):
    token = register_and_login(
        client,
        "analysis-success@example.com",
    )

    call_id = create_call(client, token)

    upload_response = upload_chunk(
        client,
        token,
        call_id,
        sequence_number=1,
    )

    assert upload_response.status_code == 201

    chunk_id = upload_response.json()["id"]

    response = client.post(
        f"/api/calls/{call_id}/chunks/{chunk_id}/analyze",
        headers=auth_header(token),
    )

    assert response.status_code == 201

    data = response.json()

    assert data["id"] > 0
    assert data["chunk_id"] == chunk_id

    assert 0.0 <= data["ai_probability"] <= 1.0
    assert 0.0 <= data["human_probability"] <= 1.0
    assert 0.0 <= data["synthetic_probability"] <= 1.0

    assert data["label"] in (
        "human",
        "synthetic",
    )

    assert data["feature_count"] == 38
    assert data["created_at"] is not None


def test_cannot_analyze_same_chunk_twice(client):
    token = register_and_login(
        client,
        "analysis-duplicate@example.com",
    )

    call_id = create_call(client, token)

    upload_response = upload_chunk(
        client,
        token,
        call_id,
        sequence_number=1,
    )

    assert upload_response.status_code == 201

    chunk_id = upload_response.json()["id"]

    first = client.post(
        f"/api/calls/{call_id}/chunks/{chunk_id}/analyze",
        headers=auth_header(token),
    )

    assert first.status_code == 201

    second = client.post(
        f"/api/calls/{call_id}/chunks/{chunk_id}/analyze",
        headers=auth_header(token),
    )

    assert second.status_code == 409
    assert "already been analyzed" in second.json()["detail"]


def test_user_cannot_analyze_another_users_chunk(client):
    token_a = register_and_login(
        client,
        "analysis-user-a@example.com",
    )

    token_b = register_and_login(
        client,
        "analysis-user-b@example.com",
    )

    call_id = create_call(client, token_a)

    upload_response = upload_chunk(
        client,
        token_a,
        call_id,
        sequence_number=1,
    )

    assert upload_response.status_code == 201

    chunk_id = upload_response.json()["id"]

    response = client.post(
        f"/api/calls/{call_id}/chunks/{chunk_id}/analyze",
        headers=auth_header(token_b),
    )

    assert response.status_code == 404


def test_analyze_nonexistent_chunk(client):
    token = register_and_login(
        client,
        "analysis-missing@example.com",
    )

    call_id = create_call(client, token)

    response = client.post(
        f"/api/calls/{call_id}/chunks/999999/analyze",
        headers=auth_header(token),
    )

    assert response.status_code == 404


def test_analysis_requires_authentication(client):
    response = client.post(
        "/api/calls/1/chunks/1/analyze",
    )

    assert response.status_code in (401, 403)

def test_analysis_persists_trust_score_and_alert_level(client):
    token = register_and_login(
        client,
        "analysis-trust-score@example.com",
    )

    call_id = create_call(client, token)

    upload_response = upload_chunk(
        client,
        token,
        call_id,
        sequence_number=1,
    )

    assert upload_response.status_code == 201

    chunk_id = upload_response.json()["id"]

    response = client.post(
        f"/api/calls/{call_id}/chunks/{chunk_id}/analyze",
        headers=auth_header(token),
    )

    assert response.status_code == 201

    data = response.json()

    assert "trust_score" in data
    assert "alert_level" in data

    assert 0.0 <= data["trust_score"] <= 100.0
    assert data["alert_level"] in {
        "SAFE",
        "LOW",
        "MEDIUM",
        "HIGH",
    }

    assert round(
        100.0 - (data["ai_probability"] * 100.0),
        2,
    ) == data["trust_score"]

    assert "is_high_risk" in data
    assert isinstance(data["is_high_risk"], bool)

    expected_high_risk = data["alert_level"] == "HIGH"
    assert data["is_high_risk"] == expected_high_risk


def test_analysis_alert_level_matches_ai_probability(client):
    token = register_and_login(
        client,
        "analysis-alert-level@example.com",
    )

    call_id = create_call(client, token)

    upload_response = upload_chunk(
        client,
        token,
        call_id,
        sequence_number=1,
    )

    assert upload_response.status_code == 201

    chunk_id = upload_response.json()["id"]

    response = client.post(
        f"/api/calls/{call_id}/chunks/{chunk_id}/analyze",
        headers=auth_header(token),
    )

    assert response.status_code == 201

    data = response.json()

    ai_probability = data["ai_probability"]
    alert_level = data["alert_level"]

    # ai_probability is represented as 0.0–1.0.
    # TrustScoreService converts it to a percentage internally.
    ai_percentage = ai_probability * 100.0

    if ai_percentage < 20:
        assert alert_level == "SAFE"
    elif ai_percentage < 50:
        assert alert_level == "LOW"
    elif ai_percentage < 75:
        assert alert_level == "MEDIUM"
    else:
        assert alert_level == "HIGH"


def test_analysis_should_notify_matches_alert_policy(
    client,
):
    token = register_and_login(
        client,
        "notify@example.com",
    )

    call_id = create_call(client, token)

    upload_response = upload_chunk(
        client,
        token,
        call_id,
        sequence_number=1,
    )

    assert upload_response.status_code == 201

    chunk_id = upload_response.json()["id"]

    response = client.post(
        f"/api/calls/{call_id}/chunks/{chunk_id}/analyze",
        headers=auth_header(token),
    )

    assert response.status_code == 201

    data = response.json()

    assert "should_notify" in data
    assert isinstance(data["should_notify"], bool)

    expected_should_notify = data["alert_level"] == "HIGH"

    assert data["should_notify"] == expected_should_notify


def test_high_risk_analysis_creates_alert_event(client):
    token = register_and_login(
        client,
        "alert-event-high@example.com",
    )

    call_id = create_call(client, token)

    upload_response = upload_chunk(
        client,
        token,
        call_id,
        sequence_number=1,
    )

    chunk_id = upload_response.json()["id"]

    response = client.post(
        f"/api/calls/{call_id}/chunks/{chunk_id}/analyze",
        headers=auth_header(token),
    )

    assert response.status_code == 201

    data = response.json()

    db_session = SessionLocal()

    try:
        alert_event = (
            db_session.query(AlertEvent)
            .filter(
                AlertEvent.analysis_id == data["id"]
            )
            .one_or_none()
        )

        if data["alert_level"] == "HIGH":
            assert alert_event is not None
            assert alert_event.user_id is not None
            assert alert_event.alert_level == "HIGH"
            assert alert_event.trust_score == data["trust_score"]
            assert alert_event.ai_probability == data["ai_probability"]
            assert alert_event.notified is False
        else:
            assert alert_event is None
    finally:
        db_session.close()

def test_non_high_analysis_does_not_create_alert_event(client):
    token = register_and_login(
        client,
        "alert-event-non-high@example.com",
    )

    call_id = create_call(client, token)

    upload_response = upload_chunk(
        client,
        token,
        call_id,
        sequence_number=1,
    )

    chunk_id = upload_response.json()["id"]

    response = client.post(
        f"/api/calls/{call_id}/chunks/{chunk_id}/analyze",
        headers=auth_header(token),
    )

    assert response.status_code == 201

    data = response.json()

    db_session = SessionLocal()

    try:
        alert_event = (
            db_session.query(AlertEvent)
            .filter(
                AlertEvent.analysis_id == data["id"]
            )
            .one_or_none()
        )

        if data["alert_level"] != "HIGH":
            assert alert_event is None
    finally:
        db_session.close()
