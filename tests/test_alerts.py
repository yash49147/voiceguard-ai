from app.db.models import AlertEvent

from tests.test_audio import (
    auth_header,
    create_call,
    register_and_login,
    upload_chunk,
)


def test_list_alerts_requires_authentication(client):
    response = client.get("/api/alerts")

    assert response.status_code == 401


def test_get_alert_requires_authentication(client):
    response = client.get("/api/alerts/1")

    assert response.status_code == 401


def test_list_alerts_returns_only_current_users_alerts(
    client,
    db_session,
):
    token = register_and_login(client, "alerts_list@example.com")

    me_response = client.get(
        "/api/auth/me",
        headers=auth_header(token),
    )

    assert me_response.status_code == 200

    user_id = me_response.json()["id"]

    call_id = create_call(client, token)

    upload_response = upload_chunk(
        client,
        token,
        call_id,
        sequence_number=1,
    )

    chunk_id = upload_response.json()["id"]

    analysis_response = client.post(
        f"/api/calls/{call_id}/chunks/{chunk_id}/analyze",
        headers=auth_header(token),
    )

    assert analysis_response.status_code == 201

    analysis = analysis_response.json()

    # The current baseline classifier may produce a non-HIGH result.
    # Create a deterministic AlertEvent directly so the query API
    # can be tested independently of classifier output.
    alert = AlertEvent(
        analysis_id=analysis["id"],
        user_id=user_id,
        alert_level="HIGH",
        trust_score=10.0,
        ai_probability=90.0,
        notified=False,
    )

    db_session.add(alert)
    db_session.commit()
    db_session.refresh(alert)

    response = client.get(
        "/api/alerts",
        headers=auth_header(token),
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) >= 1

    for item in data:
        assert item["user_id"] == alert.user_id


def test_get_alert_returns_owned_alert(
    client,
    db_session,
):
    token = register_and_login(client, "alerts_owned@example.com")

    me_response = client.get(
        "/api/auth/me",
        headers=auth_header(token),
    )

    assert me_response.status_code == 200

    user_id = me_response.json()["id"]

    call_id = create_call(client, token)

    upload_response = upload_chunk(
        client,
        token,
        call_id,
        sequence_number=1,
    )

    chunk_id = upload_response.json()["id"]

    analysis_response = client.post(
        f"/api/calls/{call_id}/chunks/{chunk_id}/analyze",
        headers=auth_header(token),
    )

    assert analysis_response.status_code == 201

    analysis = analysis_response.json()

    alert = AlertEvent(
        analysis_id=analysis["id"],
        user_id=user_id,
        alert_level="HIGH",
        trust_score=5.0,
        ai_probability=95.0,
        notified=False,
    )

    db_session.add(alert)
    db_session.commit()
    db_session.refresh(alert)

    response = client.get(
        f"/api/alerts/{alert.id}",
        headers=auth_header(token),
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == alert.id
    assert data["analysis_id"] == alert.analysis_id
    assert data["alert_level"] == "HIGH"
    assert data["notified"] is False


def test_get_alert_does_not_allow_cross_user_access(
    client,
    db_session,
):
    token = register_and_login(client, "alerts_cross_user@example.com")

    call_id = create_call(client, token)

    upload_response = upload_chunk(
        client,
        token,
        call_id,
        sequence_number=1,
    )

    chunk_id = upload_response.json()["id"]

    analysis_response = client.post(
        f"/api/calls/{call_id}/chunks/{chunk_id}/analyze",
        headers=auth_header(token),
    )

    assert analysis_response.status_code == 201

    analysis = analysis_response.json()

    alert = AlertEvent(
        analysis_id=analysis["id"],
        user_id=999999,
        alert_level="HIGH",
        trust_score=10.0,
        ai_probability=90.0,
        notified=False,
    )

    db_session.add(alert)
    db_session.commit()
    db_session.refresh(alert)

    response = client.get(
        f"/api/alerts/{alert.id}",
        headers=auth_header(token),
    )

    assert response.status_code == 404


def test_acknowledge_owned_alert(
    client,
    db_session,
):
    token = register_and_login(
        client,
        "alert-ack-owned@example.com",
    )

    me_response = client.get(
        "/api/auth/me",
        headers=auth_header(token),
    )

    assert me_response.status_code == 200

    user_id = me_response.json()["id"]

    call_id = create_call(client, token)

    upload_response = upload_chunk(
        client,
        token,
        call_id,
        sequence_number=1,
    )

    chunk_id = upload_response.json()["id"]

    analysis_response = client.post(
        f"/api/calls/{call_id}/chunks/{chunk_id}/analyze",
        headers=auth_header(token),
    )

    assert analysis_response.status_code == 201

    analysis = analysis_response.json()

    alert = AlertEvent(
        analysis_id=analysis["id"],
        user_id=user_id,
        alert_level="HIGH",
        trust_score=10.0,
        ai_probability=90.0,
        notified=False,
        acknowledged=False,
    )

    db_session.add(alert)
    db_session.commit()
    db_session.refresh(alert)

    response = client.patch(
        f"/api/alerts/{alert.id}/acknowledge",
        headers=auth_header(token),
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == alert.id
    assert data["acknowledged"] is True
    assert data["notified"] is False


def test_acknowledge_alert_is_idempotent(
    client,
    db_session,
):
    token = register_and_login(
        client,
        "alert-ack-idempotent@example.com",
    )

    me_response = client.get(
        "/api/auth/me",
        headers=auth_header(token),
    )

    user_id = me_response.json()["id"]

    call_id = create_call(client, token)

    upload_response = upload_chunk(
        client,
        token,
        call_id,
        sequence_number=1,
    )

    chunk_id = upload_response.json()["id"]

    analysis_response = client.post(
        f"/api/calls/{call_id}/chunks/{chunk_id}/analyze",
        headers=auth_header(token),
    )

    assert analysis_response.status_code == 201

    analysis = analysis_response.json()

    alert = AlertEvent(
        analysis_id=analysis["id"],
        user_id=user_id,
        alert_level="HIGH",
        trust_score=10.0,
        ai_probability=90.0,
        notified=False,
        acknowledged=False,
    )

    db_session.add(alert)
    db_session.commit()
    db_session.refresh(alert)

    first_response = client.patch(
        f"/api/alerts/{alert.id}/acknowledge",
        headers=auth_header(token),
    )

    assert first_response.status_code == 200
    assert first_response.json()["acknowledged"] is True

    second_response = client.patch(
        f"/api/alerts/{alert.id}/acknowledge",
        headers=auth_header(token),
    )

    assert second_response.status_code == 200
    assert second_response.json()["acknowledged"] is True


def test_acknowledge_alert_requires_authentication(client):
    response = client.patch("/api/alerts/1/acknowledge")

    assert response.status_code == 401


def test_acknowledge_alert_does_not_allow_cross_user_access(
    client,
    db_session,
):
    # Create User A
    token_a = register_and_login(
        client,
        "alert-owner-a@example.com",
    )

    # Create User B
    token_b = register_and_login(
        client,
        "alert-owner-b@example.com",
    )

    # Get User B's ID
    me_response = client.get(
        "/api/auth/me",
        headers=auth_header(token_b),
    )

    assert me_response.status_code == 200

    user_b_id = me_response.json()["id"]

    # Create a call for User B
    call_id = create_call(client, token_b)

    # Upload an audio chunk for User B
    upload_response = upload_chunk(
        client,
        token_b,
        call_id,
        sequence_number=1,
    )

    assert upload_response.status_code == 201

    chunk_id = upload_response.json()["id"]

    # Analyze the chunk to create a real AudioAnalysis
    analysis_response = client.post(
        f"/api/calls/{call_id}/chunks/{chunk_id}/analyze",
        headers=auth_header(token_b),
    )

    assert analysis_response.status_code == 201

    analysis = analysis_response.json()

    # Create an alert owned by User B
    alert = AlertEvent(
        analysis_id=analysis["id"],
        user_id=user_b_id,
        alert_level="HIGH",
        trust_score=10.0,
        ai_probability=90.0,
        notified=False,
        acknowledged=False,
    )

    db_session.add(alert)
    db_session.commit()
    db_session.refresh(alert)

    # User A attempts to acknowledge User B's alert
    response = client.patch(
        f"/api/alerts/{alert.id}/acknowledge",
        headers=auth_header(token_a),
    )

    # Cross-user access must be rejected
    assert response.status_code == 404

    # Verify the alert was NOT acknowledged
    db_session.refresh(alert)

    assert alert.acknowledged is False