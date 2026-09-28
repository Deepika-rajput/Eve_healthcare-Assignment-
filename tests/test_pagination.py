from datetime import datetime, timedelta, timezone


def _make_centres(client, auth_headers, n):
    for i in range(n):
        client.post(
            "/centres/",
            json={"name": f"Centre {i}", "location": f"Location {i}"},
            headers=auth_headers,
        )


def test_centres_pagination_limit_and_skip(client, auth_headers):
    _make_centres(client, auth_headers, 5)

    first = client.get("/centres/?limit=2").json()
    assert [c["name"] for c in first] == ["Centre 0", "Centre 1"]

    second = client.get("/centres/?skip=2&limit=2").json()
    assert [c["name"] for c in second] == ["Centre 2", "Centre 3"]

    tail = client.get("/centres/?skip=4&limit=10").json()
    assert [c["name"] for c in tail] == ["Centre 4"]


def test_centres_pagination_keeps_all_tests_per_centre(client, auth_headers):
    centre = client.post(
        "/centres/", json={"name": "Big Centre", "location": "X"}, headers=auth_headers
    ).json()
    for i in range(3):
        client.post(
            f"/centres/{centre['id']}/tests",
            json={"name": f"Test {i}", "price": 100 + i},
            headers=auth_headers,
        )

    result = client.get("/centres/?limit=1").json()
    assert len(result) == 1
    assert len(result[0]["tests"]) == 3  # LIMIT must not truncate the joined tests


def test_invalid_pagination_params_rejected(client):
    assert client.get("/centres/?limit=0").status_code == 422
    assert client.get("/centres/?limit=1000").status_code == 422
    assert client.get("/centres/?skip=-1").status_code == 422


def test_bookings_pagination(client, auth_headers, sample_test):
    future = (datetime.utcnow() + timedelta(days=3)).isoformat()
    for _ in range(3):
        client.post(
            "/bookings/",
            json={"test_id": sample_test["id"], "appointment_datetime": future},
            headers=auth_headers,
        )

    page = client.get("/bookings/?limit=2", headers=auth_headers).json()
    assert len(page) == 2
    rest = client.get("/bookings/?skip=2&limit=2", headers=auth_headers).json()
    assert len(rest) == 1


def test_booking_accepts_timezone_aware_datetime(client, auth_headers, sample_test):
    """Regression: comparing an aware and a naive datetime used to raise a 500."""
    future = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()  # has +00:00
    resp = client.post(
        "/bookings/",
        json={"test_id": sample_test["id"], "appointment_datetime": future},
        headers=auth_headers,
    )
    assert resp.status_code == 201


def test_booking_rejects_past_timezone_aware_datetime(client, auth_headers, sample_test):
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    resp = client.post(
        "/bookings/",
        json={"test_id": sample_test["id"], "appointment_datetime": past},
        headers=auth_headers,
    )
    assert resp.status_code == 400
