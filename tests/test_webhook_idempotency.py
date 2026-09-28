from datetime import datetime, timedelta

from app import models


def _create_booking(client, auth_headers, sample_test):
    appointment = (datetime.utcnow() + timedelta(days=3)).isoformat()
    resp = client.post(
        "/bookings/", json={"test_id": sample_test["id"], "appointment_datetime": appointment}, headers=auth_headers
    )
    return resp.json()


def test_webhook_confirms_booking(client, auth_headers, sample_test, db_session):
    booking = _create_booking(client, auth_headers, sample_test)

    resp = client.post(
        "/payments/webhook/",
        json={"event_id": "evt_001", "booking_id": booking["id"], "status": "SUCCESS"},
    )
    assert resp.status_code == 200

    booking_check = client.get(f"/bookings/{booking['id']}", headers=auth_headers)
    assert booking_check.json()["status"] == "CONFIRMED"

    payments = db_session.query(models.Payment).filter_by(booking_id=booking["id"]).all()
    assert len(payments) == 1


def test_webhook_is_idempotent_on_replay(client, auth_headers, sample_test, db_session):
    """
    Core requirement from the assignment: firing the same webhook event
    multiple times must not create duplicate payments or corrupt state.
    """
    booking = _create_booking(client, auth_headers, sample_test)
    event = {"event_id": "evt_replay_001", "booking_id": booking["id"], "status": "SUCCESS"}

    for _ in range(3):
        resp = client.post("/payments/webhook/", json=event)
        assert resp.status_code == 200

    payments = db_session.query(models.Payment).filter_by(booking_id=booking["id"]).all()
    assert len(payments) == 1, "duplicate webhook delivery must not create duplicate payments"

    webhook_events = db_session.query(models.WebhookEvent).filter_by(event_id="evt_replay_001").all()
    assert len(webhook_events) == 1

    booking_check = client.get(f"/bookings/{booking['id']}", headers=auth_headers)
    assert booking_check.json()["status"] == "CONFIRMED"


def test_webhook_failed_status_marks_booking_failed(client, auth_headers, sample_test):
    booking = _create_booking(client, auth_headers, sample_test)

    resp = client.post(
        "/payments/webhook/",
        json={"event_id": "evt_002", "booking_id": booking["id"], "status": "FAILED"},
    )
    assert resp.status_code == 200

    booking_check = client.get(f"/bookings/{booking['id']}", headers=auth_headers)
    assert booking_check.json()["status"] == "FAILED"


def test_webhook_different_events_both_apply(client, auth_headers, sample_test, db_session):
    """Two distinct event_ids for two distinct bookings should both go through normally."""
    booking_1 = _create_booking(client, auth_headers, sample_test)
    booking_2 = _create_booking(client, auth_headers, sample_test)

    client.post(
        "/payments/webhook/",
        json={"event_id": "evt_a", "booking_id": booking_1["id"], "status": "SUCCESS"},
    )
    client.post(
        "/payments/webhook/",
        json={"event_id": "evt_b", "booking_id": booking_2["id"], "status": "FAILED"},
    )

    assert client.get(f"/bookings/{booking_1['id']}", headers=auth_headers).json()["status"] == "CONFIRMED"
    assert client.get(f"/bookings/{booking_2['id']}", headers=auth_headers).json()["status"] == "FAILED"


def test_webhook_invalid_booking_id(client):
    resp = client.post(
        "/payments/webhook/", json={"event_id": "evt_003", "booking_id": 99999, "status": "SUCCESS"}
    )
    assert resp.status_code == 404


def test_webhook_malformed_payload_rejected(client):
    resp = client.post("/payments/webhook/", json={"event_id": "evt_004"})  # missing fields
    assert resp.status_code == 400 or resp.status_code == 422


def test_new_success_event_after_confirmation_does_not_duplicate_payment(
    client, auth_headers, sample_test, db_session
):
    booking = _create_booking(client, auth_headers, sample_test)
    event1 = {"event_id": "evt_success_1", "booking_id": booking["id"], "status": "SUCCESS"}
    event2 = {"event_id": "evt_success_2", "booking_id": booking["id"], "status": "SUCCESS"}

    assert client.post("/payments/webhook/", json=event1).status_code == 200
    assert client.post("/payments/webhook/", json=event2).status_code == 200

    payments = db_session.query(models.Payment).filter_by(booking_id=booking["id"]).all()
    assert len(payments) == 1
    assert client.get(f"/bookings/{booking['id']}", headers=auth_headers).json()["status"] == "CONFIRMED"


def test_failed_webhook_cannot_regress_confirmed_booking(client, auth_headers, sample_test, db_session):
    booking = _create_booking(client, auth_headers, sample_test)

    assert client.post(
        "/payments/webhook/",
        json={"event_id": "evt_confirmed", "booking_id": booking["id"], "status": "SUCCESS"},
    ).status_code == 200

    resp = client.post(
        "/payments/webhook/",
        json={"event_id": "evt_late_failed", "booking_id": booking["id"], "status": "FAILED"},
    )
    assert resp.status_code == 409

    booking_check = client.get(f"/bookings/{booking['id']}", headers=auth_headers)
    assert booking_check.json()["status"] == "CONFIRMED"
