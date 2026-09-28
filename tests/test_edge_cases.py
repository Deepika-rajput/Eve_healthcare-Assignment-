from datetime import datetime, timedelta

import pytest

HUGE = 10**25  # far beyond any database integer column


def _future():
    return (datetime.utcnow() + timedelta(days=2)).isoformat()


@pytest.mark.parametrize("path", ["/centres/{}", "/centres/{}/tests"])
def test_public_get_with_absurd_id_is_422_not_500(client, path):
    assert client.get(path.format(HUGE)).status_code == 422


def test_invalid_ids_are_rejected_cleanly(client, auth_headers):
    assert client.get(f"/bookings/{HUGE}", headers=auth_headers).status_code == 422
    assert client.get("/bookings/0", headers=auth_headers).status_code == 422
    assert client.post(f"/bookings/{HUGE}/cancel", headers=auth_headers).status_code == 422
    assert client.post("/payments/", json={"booking_id": HUGE}, headers=auth_headers).status_code == 422
    assert client.post(
        "/bookings/", json={"test_id": HUGE, "appointment_datetime": _future()}, headers=auth_headers
    ).status_code == 422
    assert client.post(
        f"/centres/{HUGE}/tests", json={"name": "x", "price": 1}, headers=auth_headers
    ).status_code == 422


def test_webhook_rejects_absurd_or_invalid_payloads(client):
    ok = {"event_id": "e1", "booking_id": 1, "status": "SUCCESS"}
    assert client.post("/payments/webhook/", json={**ok, "booking_id": HUGE}).status_code == 422
    assert client.post("/payments/webhook/", json={**ok, "booking_id": 0}).status_code == 422
    assert client.post("/payments/webhook/", json={**ok, "status": "MAYBE"}).status_code == 422
    assert client.post("/payments/webhook/", json={**ok, "event_id": ""}).status_code == 422
    assert client.post("/payments/webhook/").status_code == 422


def test_login_email_is_case_insensitive(client):
    client.post("/auth/signup", json={"email": "Case@Example.com", "password": "password123"})
    resp = client.post("/auth/login", json={"email": "case@example.COM", "password": "password123"})
    assert resp.status_code == 200


def test_cancelled_booking_rejects_webhook_and_payment(client, auth_headers, sample_test):
    booking = client.post(
        "/bookings/",
        json={"test_id": sample_test["id"], "appointment_datetime": _future()},
        headers=auth_headers,
    ).json()
    client.post(f"/bookings/{booking['id']}/cancel", headers=auth_headers)

    hook = client.post(
        "/payments/webhook/",
        json={"event_id": "late_evt", "booking_id": booking["id"], "status": "SUCCESS"},
    )
    assert hook.status_code == 409
    assert client.post("/payments/", json={"booking_id": booking["id"]}, headers=auth_headers).status_code == 400
    assert client.get(f"/bookings/{booking['id']}", headers=auth_headers).json()["status"] == "CANCELLED"
