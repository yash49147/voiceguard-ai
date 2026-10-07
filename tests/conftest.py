import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

TEST_DB = Path("data/test_voiceguard.db")

# Always use an isolated test database.
TEST_DB.parent.mkdir(parents=True, exist_ok=True)

if TEST_DB.exists():
    TEST_DB.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"

os.environ["JWT_SECRET_KEY"] = (
    "test-secret-key-for-pytest-only"
)


from app.main import app  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session():
    session: Session = SessionLocal()

    try:
        yield session
    finally:
        session.close()