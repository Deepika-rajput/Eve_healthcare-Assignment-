from datetime import datetime, timedelta


def _future_iso(days=3):
    return (datetime.utcnow() + timedelta(days=days)).isoformat()


def test_create_booking_success(client, auth_headers, sample_test):
    resp = client.post(
        "/bookings/",
        json={"test_id": sample_test["id"], "appointment_datetime": _future_iso()},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "PENDING"
    assert body["amount"] == sample_test["price"]


def test_create_booking_rejects_past_appointment(client, auth_headers, sample_test):
    past = (datetime.utcnow() - timedelta(days=1)).isoformat()
    resp = client.post(
        "/bookings/", json={"test_id": sample_test["id"], "appointment_datetime": past}, headers=auth_headers
    )
    assert resp.status_code == 400


def test_create_booking_invalid_test_id(client, auth_headers):
    resp = client.post(
        "/bookings/", json={"test_id": 99999, "appointment_datetime": _future_iso()}, headers=auth_headers
    )
    assert resp.status_code == 404


def test_user_cannot_view_another_users_booking(client, auth_headers, sample_test):
    booking_resp = client.post(
        "/bookings/",
        json={"test_id": sample_test["id"], "appointment_datetime": _future_iso()},
        headers=auth_headers,
    )
    booking_id = booking_resp.json()["id"]

    # Second user
    client.post("/auth/signup", json={"email": "other@example.com", "password": "password123"})
    other_login = client.post("/auth/login", json={"email": "other@example.com", "password": "password123"})
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}

    resp = client.get(f"/bookings/{booking_id}", headers=other_headers)
    assert resp.status_code == 403


def test_cancel_booking(client, auth_headers, sample_test):
    booking_resp = client.post(
        "/bookings/",
        json={"test_id": sample_test["id"], "appointment_datetime": _future_iso()},
        headers=auth_headers,
    )
    booking_id = booking_resp.json()["id"]

    resp = client.post(f"/bookings/{booking_id}/cancel", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "CANCELLED"

    # Cancelling again should fail -- already terminal.
    resp2 = client.post(f"/bookings/{booking_id}/cancel", headers=auth_headers)
    assert resp2.status_code == 400


def test_cancel_nonexistent_booking(client, auth_headers):
    resp = client.post("/bookings/99999/cancel", headers=auth_headers)
    assert resp.status_code == 404


def test_unauthenticated_cannot_create_centre(client):
    resp = client.post(
        "/centres/", json={"name": "City Diagnostics", "location": "MG Road"}
    )
    assert resp.status_code == 401
