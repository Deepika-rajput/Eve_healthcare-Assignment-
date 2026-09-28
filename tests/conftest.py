import os

# Must happen before any `app.*` import: app.database builds its engine
# from this at import time. Pointing it at SQLite too means the app's own
# startup (table creation in the lifespan hook) never needs a real MySQL
# instance to run the test suite. The actual test data goes through the
# separate `engine`/`TestingSessionLocal` below via the get_db override.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

# Tests run against SQLite in-memory rather than the real MySQL instance:
# no external service needed to run `pytest`, and each test gets a fresh
# schema. Application code is DB-agnostic through SQLAlchemy, so this is
# a faithful stand-in for the real thing.
#
# StaticPool is required here: plain SQLite-in-memory hands out a brand
# new, empty database per connection, so without pinning every session to
# the *same* underlying connection, table-creation and queries would each
# silently land in a different, unrelated in-memory DB.
TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture()
def db_session():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(client):
    """Signs up + logs in a fresh user, returns Authorization headers."""
    client.post(
        "/auth/signup",
        json={"email": "patient@example.com", "password": "supersecret123", "full_name": "Test Patient"},
    )
    resp = client.post("/auth/login", json={"email": "patient@example.com", "password": "supersecret123"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def sample_test(client, auth_headers):
    """Creates a centre + one diagnostic test, returns the test's id and price."""
    centre_resp = client.post(
        "/centres/", json={"name": "City Diagnostics", "location": "MG Road"}, headers=auth_headers
    )
    centre_id = centre_resp.json()["id"]

    test_resp = client.post(
        f"/centres/{centre_id}/tests",
        json={"name": "Complete Blood Count", "price": 499.0},
        headers=auth_headers,
    )
    return test_resp.json()
