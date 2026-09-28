def test_signup_success(client):
    resp = client.post(
        "/auth/signup", json={"email": "a@example.com", "password": "password123", "full_name": "A"}
    )
    assert resp.status_code == 201
    assert resp.json()["email"] == "a@example.com"
    assert "hashed_password" not in resp.json()  # never leak the hash


def test_signup_duplicate_email_rejected(client):
    client.post("/auth/signup", json={"email": "a@example.com", "password": "password123"})
    resp = client.post("/auth/signup", json={"email": "a@example.com", "password": "different123"})
    assert resp.status_code == 409


def test_login_wrong_password_rejected(client):
    client.post("/auth/signup", json={"email": "a@example.com", "password": "password123"})
    resp = client.post("/auth/login", json={"email": "a@example.com", "password": "wrongpassword"})
    assert resp.status_code == 401


def test_login_unknown_email_same_error_as_wrong_password(client):
    """The API shouldn't reveal whether an email is registered."""
    resp = client.post("/auth/login", json={"email": "ghost@example.com", "password": "whatever123"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid email or password"


def test_protected_route_rejects_missing_token(client):
    resp = client.get("/bookings/")
    assert resp.status_code == 401


def test_protected_route_rejects_garbage_token(client):
    resp = client.get("/bookings/", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


def test_swagger_oauth_token_endpoint_works(client):
    client.post(
        "/auth/signup",
        json={"email": "swagger@example.com", "password": "password123"},
    )
    resp = client.post(
        "/auth/token",
        data={"username": "swagger@example.com", "password": "password123"},
    )
    assert resp.status_code == 200
    assert resp.json()["token_type"] == "bearer"
    assert resp.json()["access_token"]
