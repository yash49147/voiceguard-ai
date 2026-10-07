import uuid


def register_and_login(client):
    email = f"profile-{uuid.uuid4().hex}@example.com"

    register_response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "full_name": "Profile User",
            "password": "StrongPassword123!",
        },
    )

    assert register_response.status_code == 201

    login_response = client.post(
        "/api/auth/login",
        json={
            "email": email,
            "password": "StrongPassword123!",
        },
    )

    assert login_response.status_code == 200

    data = login_response.json()

    return data["access_token"], email


def test_get_my_profile(client):
    token, email = register_and_login(client)

    response = client.get(
        "/api/users/me",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["email"] == email
    assert data["full_name"] == "Profile User"
    assert data["is_active"] is True


def test_get_profile_without_token(client):
    response = client.get("/api/users/me")

    assert response.status_code == 401


def test_update_my_profile(client):
    token, email = register_and_login(client)

    response = client.patch(
        "/api/users/me",
        headers={
            "Authorization": f"Bearer {token}",
        },
        json={
            "full_name": "Updated Profile User",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["full_name"] == "Updated Profile User"


def test_update_profile_without_token(client):
    response = client.patch(
        "/api/users/me",
        json={
            "full_name": "Unauthorized User",
        },
    )

    assert response.status_code == 401


def test_change_password(client):
    token, email = register_and_login(client)

    response = client.patch(
        "/api/users/me/password",
        headers={
            "Authorization": f"Bearer {token}",
        },
        json={
            "current_password": "StrongPassword123!",
            "new_password": "NewStrongPassword456!",
        },
    )

    assert response.status_code == 204

    login_response = client.post(
        "/api/auth/login",
        json={
            "email": email,
            "password": "NewStrongPassword456!",
        },
    )

    assert login_response.status_code == 200


def test_change_password_rejects_wrong_current_password(client):
    token, email = register_and_login(client)

    response = client.patch(
        "/api/users/me/password",
        headers={
            "Authorization": f"Bearer {token}",
        },
        json={
            "current_password": "WrongPassword123!",
            "new_password": "NewStrongPassword456!",
        },
    )

    assert response.status_code == 400


def test_change_password_rejects_same_password(client):
    token, email = register_and_login(client)

    response = client.patch(
        "/api/users/me/password",
        headers={
            "Authorization": f"Bearer {token}",
        },
        json={
            "current_password": "StrongPassword123!",
            "new_password": "StrongPassword123!",
        },
    )

    assert response.status_code == 400