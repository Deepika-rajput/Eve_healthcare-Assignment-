from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.dependencies import get_current_user
from app.services.payment_service import DuplicateWebhookEvent, apply_webhook_event, process_payment

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/", response_model=schemas.PaymentOut, status_code=status.HTTP_201_CREATED)
def make_payment(
    payload: schemas.PaymentCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    booking = db.get(models.Booking, payload.booking_id)
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    if booking.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your booking")

    try:
        payment = process_payment(db, booking)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return payment


@router.post("/webhook/", status_code=status.HTTP_200_OK)
def payment_webhook(
    payload: schemas.WebhookPayload,
    db: Session = Depends(get_db),
):
    """
    Simulated payment-provider webhook. It intentionally does not use a
    user JWT; a real provider would authenticate this endpoint with an HMAC
    signature or equivalent provider-specific mechanism.

    The endpoint is idempotent by provider event_id and protects booking
    state from conflicting/out-of-order payment updates.
    """
    try:
        payment = apply_webhook_event(
            db,
            event_id=payload.event_id,
            booking_id=payload.booking_id,
            status=payload.status,
            raw_payload=payload.model_dump_json(),
        )
    except DuplicateWebhookEvent:
        return {"status": "already_processed"}
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    return {"status": "ok", "payment_id": payment.id if payment else None}
