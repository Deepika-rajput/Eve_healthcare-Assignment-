from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.database import Base, engine
from app.routers import auth, bookings, centres, payments


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Dev-only convenience: creates tables if they don't exist, on app
    # startup rather than at import time (so importing this module -- e.g.
    # from tests -- doesn't require a live DB connection). A real
    # deployment would use Alembic migrations instead (see README).
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="EVE Healthcare - Diagnostic Booking API",
    description="""
## Diagnostic Booking & Payment API

Backend service for managing diagnostic centres, tests, bookings,
simulated payments, and payment webhooks.

(featuring JWT authentication, diagnostic centre & test management,
test bookings, simulated payments, idempotent payment webhooks,
and secure booking authorization.)
""",
    version="1.0.0",
    contact={
        "name": "Backend API",
    },
    openapi_tags=[
        {
            "name": "auth",
            "description": "User registration and JWT authentication",
        },
        {
            "name": "centres",
            "description": "Diagnostic centres and available tests",
        },
        {
            "name": "bookings",
            "description": "Diagnostic test booking operations",
        },
        {
            "name": "payments",
            "description": "Simulated payments and payment webhooks",
        },
    ],
    lifespan=lifespan,
)


# API routers
app.include_router(auth.router)
app.include_router(centres.router)
app.include_router(bookings.router)
app.include_router(payments.router)


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}