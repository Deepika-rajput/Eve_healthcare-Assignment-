import random
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models


def simulate_gateway_call() -> models.PaymentStatus:
    """Simulate a payment gateway with an 85% success rate."""
    return models.PaymentStatus.SUCCESS if random.random() < 0.85 else models.PaymentStatus.FAILED


def _locked_booking(db: Session, booking_id: int) -> models.Booking:
    # FOR UPDATE prevents two concurrent payment/webhook requests from both
    # observing PENDING and applying conflicting state changes on databases
    # that support row-level locking (e.g. MySQL/PostgreSQL).
    booking = (
        db.query(models.Booking)
        .filter(models.Booking.id == booking_id)
        .with_for_update()
        .first()
    )
    if not booking:
        raise LookupError(f"Booking {booking_id} not found")
    return booking


def _apply_status(booking: models.Booking, result: models.PaymentStatus) -> None:
    """Apply a payment result without allowing a terminal booking to regress."""
    if booking.status == models.BookingStatus.CANCELLED:
        raise ValueError(f"Booking {booking.id} is CANCELLED and cannot receive a payment")

    if booking.status == models.BookingStatus.CONFIRMED:
        if result == models.PaymentStatus.FAILED:
            raise ValueError(f"Booking {booking.id} is already CONFIRMED; a FAILED event cannot regress it")
        return

    if booking.status == models.BookingStatus.PENDING:
        booking.status = (
            models.BookingStatus.CONFIRMED
            if result == models.PaymentStatus.SUCCESS
            else models.BookingStatus.FAILED
        )
        return

    # FAILED is terminal for the current payment attempt, but a later SUCCESS
    # can represent a retry/late provider confirmation. Keep that transition
    # one-way so FAILED never overwrites a confirmed booking.
    if booking.status == models.BookingStatus.FAILED and result == models.PaymentStatus.SUCCESS:
        booking.status = models.BookingStatus.CONFIRMED


def process_payment(db: Session, booking: models.Booking) -> models.Payment:
    """Process one synchronous simulated payment for a PENDING booking."""
    booking = _locked_booking(db, booking.id)

    if booking.status != models.BookingStatus.PENDING:
        raise ValueError(f"Booking {booking.id} is not PENDING (currently {booking.status.value})")

    result = simulate_gateway_call()
    event_id = f"sim_{uuid.uuid4().hex}"

    payment = models.Payment(
        booking_id=booking.id,
        amount=booking.amount,
        status=result,
        provider_event_id=event_id,
    )
    _apply_status(booking, result)
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


class DuplicateWebhookEvent(Exception):
    """Raised when a provider event_id has already been processed."""


def apply_webhook_event(
    db: Session, event_id: str, booking_id: int, status: models.PaymentStatus, raw_payload: str
) -> models.Payment | None:
    """Atomically record and apply an idempotent payment webhook."""
    booking = _locked_booking(db, booking_id)

    webhook_record = models.WebhookEvent(event_id=event_id, payload=raw_payload)
    db.add(webhook_record)

    try:
        # Flush first: the unique event_id constraint makes concurrent/replayed
        # delivery safe before any payment or booking mutation is committed.
        db.flush()
    except IntegrityError:
        db.rollback()
        raise DuplicateWebhookEvent(event_id)

    # If the booking is already confirmed, a repeated/new SUCCESS event should
    # not manufacture another payment row. A conflicting FAILED event is
    # rejected by _apply_status and therefore cannot corrupt the booking.
    if booking.status == models.BookingStatus.CONFIRMED and status == models.PaymentStatus.SUCCESS:
        payment = (
            db.query(models.Payment)
            .filter(models.Payment.booking_id == booking.id)
            .order_by(models.Payment.id.desc())
            .first()
        )
        db.commit()
        return payment

    _apply_status(booking, status)

    payment = models.Payment(
        booking_id=booking.id,
        amount=booking.amount,
        status=status,
        provider_event_id=event_id,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment
