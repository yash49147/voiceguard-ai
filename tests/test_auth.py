import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Set testing configuration before importing the application.
TEST_DB = Path("data/test_voiceguard.db")

if TEST_DB.exists():
    TEST_DB.unlink()

os.environ["DATABASE_URL"] = (
    f"sqlite:///{TEST_DB.as_posix()}"
)

os.environ["JWT_SECRET_KEY"] = (
    "test-secret-key-for-pytest-only"
)

from app.main import app  # noqa: E402




def test_health_check(client):
    response = client.get("/health")

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "ok"


def test_register_user(client):
    response = client.post(
        "/api/auth/register",
        json={
            "email": "test@example.com",
            "full_name": "Test User",
            "password": "StrongPassword123!",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["email"] == "test@example.com"
    assert data["full_name"] == "Test User"
    assert "id" in data

    # Password must never appear in the API response.
    assert "password" not in data
    assert "password_hash" not in data


def test_duplicate_registration(client):
    response = client.post(
        "/api/auth/register",
        json={
            "email": "test@example.com",
            "full_name": "Another User",
            "password": "AnotherPassword123!",
        },
    )

    assert response.status_code == 409


def test_login(client):
    response = client.post(
        "/api/auth/login",
        json={
            "email": "test@example.com",
            "password": "StrongPassword123!",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["token_type"] == "bearer"
    assert isinstance(data["access_token"], str)
    assert len(data["access_token"]) > 20


def test_authenticated_me(client):
    login_response = client.post(
        "/api/auth/login",
        json={
            "email": "test@example.com",
            "password": "StrongPassword123!",
        },
    )

    token = login_response.json()["access_token"]

    response = client.get(
        "/api/auth/me",
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["email"] == "test@example.com"
    assert data["full_name"] == "Test User"


def test_invalid_password(client):
    response = client.post(
        "/api/auth/login",
        json={
            "email": "test@example.com",
            "password": "WrongPassword123!",
        },
    )

    assert response.status_code == 401


def test_me_without_token(client):
    response = client.get("/api/auth/me")

    assert response.status_code == 401