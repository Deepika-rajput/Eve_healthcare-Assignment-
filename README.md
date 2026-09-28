# EVE Healthcare — Diagnostic Booking API

A backend REST API for **diagnostic centres, test bookings and simulated payments**, built with **FastAPI, SQLAlchemy and MySQL**. The focus is correctness: authorization, booking state transitions, and an idempotent payment webhook.

## Tech stack

FastAPI · SQLAlchemy 2.0 · MySQL (PyMySQL) · JWT (python-jose) + bcrypt (passlib) · pytest + httpx · Docker / docker-compose

## Run locally-to run this locally on system

### Option A: Docker (app + MySQL)

```bash
docker compose up --build
```

API: `http://localhost:8000` · Swagger UI: `http://localhost:8000/docs`

### Option B: Python venv 

```bash
python -m venv venv
venv\Scripts\activate          # Windows  (Linux/macOS: source venv/bin/activate)
pip install -r requirements.txt
cp .env.example .env           # Windows: copy .env.example .env
```

Then choose a database in `.env`:

- **MySQL:** `docker compose up -d db`, then use `DATABASE_URL=mysql+pymysql://root:root@localhost:3306/eve_healthcare`
- **SQLite (zero setup):** `DATABASE_URL=sqlite:///./eve_healthcare.db`

```bash
uvicorn app.main:app --reload
```

Tables are created automatically on startup.

### Run the tests

```bash
python -m pytest -v
```

39 tests, run against in-memory SQLite (no MySQL needed).

## API endpoints

Protected endpoints need `Authorization: Bearer <token>`. In Swagger UI, use the **Authorize** button (email as username).

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/auth/signup` | No | Create an account |
| POST | `/auth/login` | No | JSON login, returns JWT |
| POST | `/auth/token` | No | OAuth2 form login (used by Swagger's Authorize) |
| POST | `/centres/` | Yes | Create a diagnostic centre |
| GET | `/centres/?skip=0&limit=20` | No | List centres with their tests (paginated) |
| GET | `/centres/{id}` | No | Get one centre |
| POST | `/centres/{id}/tests` | Yes | Add a test (name, price) to a centre |
| GET | `/centres/{id}/tests?skip=0&limit=20` | No | List a centre's tests (paginated) |
| POST | `/bookings/` | Yes | Book a test (starts `PENDING`) |
| GET | `/bookings/?skip=0&limit=20` | Yes | List my bookings (paginated) |
| GET | `/bookings/{id}` | Yes | Get one of my bookings |
| POST | `/bookings/{id}/cancel` | Yes | Cancel a `PENDING` / `CONFIRMED` booking |
| POST | `/payments/` | Yes | Simulate paying for a booking (SUCCESS or FAILED) |
| POST | `/payments/webhook/` | No* | Payment-provider status callback (idempotent) |

\* Real providers sign webhooks (HMAC) rather than send a user JWT. See assumptions.

### Example requests

```bash
# Sign up, then log in
curl -X POST localhost:8000/auth/signup -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"test12345"}'
curl -X POST localhost:8000/auth/login -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"test12345"}'

# Create a centre and add a test  (TOKEN = access_token from login)
curl -X POST localhost:8000/centres/ -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"City Diagnostic Centre","location":"New Delhi"}'
curl -X POST localhost:8000/centres/1/tests -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"Blood Test","price":500}'

# Book, then pay
curl -X POST localhost:8000/bookings/ -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"test_id":1,"appointment_datetime":"2026-12-01T10:00:00"}'
curl -X POST localhost:8000/payments/ -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"booking_id":1}'

# Webhook (safe to send repeatedly)
curl -X POST localhost:8000/payments/webhook/ -H "Content-Type: application/json" \
  -d '{"event_id":"evt_abc123","booking_id":1,"status":"SUCCESS"}'
```

## Database design

```
users ─< bookings >─ diagnostic_tests >─ diagnostic_centres
              │
              └─< payments

webhook_events   (ledger of processed provider event_ids)
```

- **users**: unique email, bcrypt password hash.
- **diagnostic_centres**: name, location. One centre has many tests.
- **diagnostic_tests**: belongs to one centre, with `price` as `NUMERIC(10,2)`. Money is never stored as a float.
- **bookings**: user, test, centre, appointment time, status enum (`PENDING`, `CONFIRMED`, `FAILED`, `CANCELLED`). `amount` is copied from the test price at booking time, so later price changes don't rewrite history. `centre_id` is stored on the booking for the same reason.
- **payments**: one row per payment record. `provider_event_id` is unique.
- **webhook_events**: unique `event_id`, raw payload, received time.

### Booking state rules

```
PENDING   -> CONFIRMED  (payment SUCCESS)
PENDING   -> FAILED     (payment FAILED)
FAILED    -> CONFIRMED  (late/retried SUCCESS)
PENDING | CONFIRMED -> CANCELLED (user)
CONFIRMED -> FAILED     rejected (a FAILED event can never undo a confirmed booking)
CANCELLED -> anything   rejected
```

## How webhook idempotency works

`POST /payments/webhook/` (see `app/services/payment_service.py`):

1. Lock the booking row (`SELECT ... FOR UPDATE`) so concurrent events for one booking are serialized.
2. Insert the `event_id` into `webhook_events` and `flush()`. The unique constraint makes a repeated event fail here, before any state is touched.
3. On a duplicate: roll back and return `200 {"status": "already_processed"}`. No new payment row, no booking change, and the provider stops retrying.
4. Otherwise: apply the state transition, create the payment row and commit. The event record, payment and booking update commit as **one transaction**, so a crash can't leave a half-applied state.
5. A new SUCCESS event for an already-confirmed booking creates no second payment. A conflicting event returns `409`. An unknown booking returns `404`.

Covered in `tests/test_webhook_idempotency.py` (same event replayed 3 times gives exactly one payment and one ledger row).

## Edge cases handled

- Invalid or missing input returns `422` (Pydantic validation: email format, password of at least 8 characters, price above 0, non-empty names)
- Bad or expired JWT returns `401`. Wrong password and unknown email return the same message (no user enumeration)
- Duplicate signup returns `409` (including the race where two requests register at once)
- Accessing or paying for someone else's booking returns `403`
- Invalid booking, test or centre IDs return `404`
- Past appointment times are rejected with `400` (timezone-aware and naive datetimes both handled)
- Paying for a non-`PENDING` booking, or cancelling a terminal booking, returns `400`
- Failed payments mark the booking `FAILED`
- Duplicate webhook events are safely ignored (see above)

## Assumptions

- Any authenticated user can create centres and tests, because there is no admin role in the assignment scope. Booking data is strictly scoped to its owner.
- The webhook has no JWT. A real provider authenticates with an HMAC signature over the raw body, which I did not implement because there is no real provider secret. It would be one added check before parsing.
- `POST /payments/` (synchronous mock, about 85% success) and the webhook (asynchronous provider callback) are modelled as separate paths, as they are with real gateways.
- Tables are created with `create_all()` at startup, not migrations, to keep scope small.
- Cancellation is allowed any time before the appointment while the booking is `PENDING` or `CONFIRMED`. No cutoff window was specified.
- Double-booking of the same slot is not prevented, since slot capacity was not specified.
- Tests use in-memory SQLite. `SELECT ... FOR UPDATE` is a no-op there but is honoured on MySQL/PostgreSQL.

## What I would improve with more time

- **Alembic migrations** instead of `create_all()`.
- **HMAC signature verification** on the webhook, plus a timestamp check to prevent replay.
- **Role-based access** (admin/staff) for managing centres and tests.
- **Slot capacity / double-booking prevention** with a constraint or availability table.
- **Retry handling with Celery + Redis:** process webhooks asynchronously with backoff and a dead-letter queue.
- **Redis caching** for the read-mostly centres list, invalidated on writes.
- **Rate limiting** on login and the webhook, and **structured JSON logging** with request IDs.
- **PostgreSQL** (preferred in the brief) and a CI pipeline running the tests.
- Refresh tokens and stronger password rules.
