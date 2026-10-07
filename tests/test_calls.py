def register_and_login(client, email, password="TestPassword123!"):
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "full_name": "Call Test User",
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


def test_create_call(client):
    token = register_and_login(
        client,
        "call-create@example.com",
    )

    response = client.post(
        "/api/calls",
        headers=auth_header(token),
    )

    assert response.status_code == 201

    data = response.json()

    assert data["id"] > 0
    assert data["status"] == "active"
    assert data["started_at"] is not None
    assert data["ended_at"] is None
    assert data["created_at"] is not None


def test_list_calls(client):
    token = register_and_login(
        client,
        "call-list@example.com",
    )

    client.post(
        "/api/calls",
        headers=auth_header(token),
    )

    response = client.get(
        "/api/calls",
        headers=auth_header(token),
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["status"] == "active"


def test_get_call(client):
    token = register_and_login(
        client,
        "call-get@example.com",
    )

    create_response = client.post(
        "/api/calls",
        headers=auth_header(token),
    )

    call_id = create_response.json()["id"]

    response = client.get(
        f"/api/calls/{call_id}",
        headers=auth_header(token),
    )

    assert response.status_code == 200
    assert response.json()["id"] == call_id


def test_end_call(client):
    token = register_and_login(
        client,
        "call-end@example.com",
    )

    create_response = client.post(
        "/api/calls",
        headers=auth_header(token),
    )

    call_id = create_response.json()["id"]

    response = client.patch(
        f"/api/calls/{call_id}/end",
        headers=auth_header(token),
    )

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "completed"
    assert data["ended_at"] is not None


def test_cannot_end_call_twice(client):
    token = register_and_login(
        client,
        "call-double-end@example.com",
    )

    create_response = client.post(
        "/api/calls",
        headers=auth_header(token),
    )

    call_id = create_response.json()["id"]

    first = client.patch(
        f"/api/calls/{call_id}/end",
        headers=auth_header(token),
    )

    assert first.status_code == 200

    second = client.patch(
        f"/api/calls/{call_id}/end",
        headers=auth_header(token),
    )

    assert second.status_code == 409


def test_call_requires_authentication(client):
    response = client.post("/api/calls")

    assert response.status_code in (401, 403)


def test_user_cannot_access_another_users_call(client):
    token_a = register_and_login(
        client,
        "call-user-a@example.com",
    )

    token_b = register_and_login(
        client,
        "call-user-b@example.com",
    )

    create_response = client.post(
        "/api/calls",
        headers=auth_header(token_a),
    )

    call_id = create_response.json()["id"]

    response = client.get(
        f"/api/calls/{call_id}",
        headers=auth_header(token_b),
    )

    assert response.status_code == 404