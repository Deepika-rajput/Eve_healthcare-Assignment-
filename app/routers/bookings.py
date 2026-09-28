from datetime import datetime, timezone
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.dependencies import get_current_user
from app.schemas import MAX_ID

router = APIRouter(prefix="/bookings", tags=["bookings"])

# Statuses from which a booking can still be cancelled.
CANCELLABLE_STATUSES = {models.BookingStatus.PENDING, models.BookingStatus.CONFIRMED}


@router.post("/", response_model=schemas.BookingOut, status_code=status.HTTP_201_CREATED)
def create_booking(
    payload: schemas.BookingCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    test = db.get(models.DiagnosticTest, payload.test_id)
    if not test:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diagnostic test not found")

    if payload.appointment_datetime.tzinfo is not None:
        appointment = payload.appointment_datetime.astimezone(timezone.utc).replace(tzinfo=None)
    else:
        appointment = payload.appointment_datetime

    if appointment <= datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Appointment must be in the future"
        )

    booking = models.Booking(
        user_id=current_user.id,
        test_id=test.id,
        centre_id=test.centre_id,
        appointment_datetime=appointment,
        amount=test.price,
        status=models.BookingStatus.PENDING,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


@router.get("/", response_model=List[schemas.BookingOut])
def list_my_bookings(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return (
        db.query(models.Booking)
        .filter(models.Booking.user_id == current_user.id)
        .order_by(models.Booking.id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def _get_owned_booking(booking_id: int, db: Session, current_user: models.User) -> models.Booking:
    booking = db.get(models.Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    if booking.user_id != current_user.id:
        # 403, not a leaked 404 -- the booking exists, they just can't touch it.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your booking")
    return booking


@router.get("/{booking_id}", response_model=schemas.BookingOut)
def get_booking(
    booking_id: Annotated[int, Path(ge=1, le=MAX_ID)],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _get_owned_booking(booking_id, db, current_user)


@router.post("/{booking_id}/cancel", response_model=schemas.BookingOut)
def cancel_booking(
    booking_id: Annotated[int, Path(ge=1, le=MAX_ID)],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    booking = _get_owned_booking(booking_id, db, current_user)

    if booking.status not in CANCELLABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel a booking in status {booking.status.value}",
        )

    booking.status = models.BookingStatus.CANCELLED
    db.commit()
    db.refresh(booking)
    return booking
