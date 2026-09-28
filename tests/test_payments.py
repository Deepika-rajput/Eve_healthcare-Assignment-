from datetime import datetime, timedelta
from unittest.mock import patch

from app.models import PaymentStatus


def _create_booking(client, auth_headers, sample_test):
    appointment = (datetime.utcnow() + timedelta(days=3)).isoformat()
    resp = client.post(
        "/bookings/", json={"test_id": sample_test["id"], "appointment_datetime": appointment}, headers=auth_headers
    )
    return resp.json()


def test_payment_success_confirms_booking(client, auth_headers, sample_test):
    booking = _create_booking(client, auth_headers, sample_test)

    with patch("app.services.payment_service.simulate_gateway_call", return_value=PaymentStatus.SUCCESS):
        resp = client.post("/payments/", json={"booking_id": booking["id"]}, headers=auth_headers)

    assert resp.status_code == 201
    assert resp.json()["status"] == "SUCCESS"

    booking_check = client.get(f"/bookings/{booking['id']}", headers=auth_headers)
    assert booking_check.json()["status"] == "CONFIRMED"


def test_payment_failure_marks_booking_failed(client, auth_headers, sample_test):
    booking = _create_booking(client, auth_headers, sample_test)

    with patch("app.services.payment_service.simulate_gateway_call", return_value=PaymentStatus.FAILED):
        resp = client.post("/payments/", json={"booking_id": booking["id"]}, headers=auth_headers)

    assert resp.status_code == 201
    assert resp.json()["status"] == "FAILED"

    booking_check = client.get(f"/bookings/{booking['id']}", headers=auth_headers)
    assert booking_check.json()["status"] == "FAILED"


def test_cannot_pay_for_non_pending_booking_twice(client, auth_headers, sample_test):
    booking = _create_booking(client, auth_headers, sample_test)

    with patch("app.services.payment_service.simulate_gateway_call", return_value=PaymentStatus.SUCCESS):
        client.post("/payments/", json={"booking_id": booking["id"]}, headers=auth_headers)

    # Booking is now CONFIRMED, not PENDING -- a second payment attempt must be rejected.
    resp = client.post("/payments/", json={"booking_id": booking["id"]}, headers=auth_headers)
    assert resp.status_code == 400


def test_cannot_pay_for_someone_elses_booking(client, auth_headers, sample_test):
    booking = _create_booking(client, auth_headers, sample_test)

    client.post("/auth/signup", json={"email": "other@example.com", "password": "password123"})
    other_login = client.post("/auth/login", json={"email": "other@example.com", "password": "password123"})
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}

    resp = client.post("/payments/", json={"booking_id": booking["id"]}, headers=other_headers)
    assert resp.status_code == 403


def test_pay_for_invalid_booking_id(client, auth_headers):
    resp = client.post("/payments/", json={"booking_id": 99999}, headers=auth_headers)
    assert resp.status_code == 404
