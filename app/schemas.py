from datetime import datetime
from decimal import Decimal
from typing import Annotated, List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import BookingStatus, PaymentStatus

# IDs are 32-bit auto-increment integers. Bounding them here turns absurd
# values (e.g. 10**25) into a clean 422 instead of a database overflow/500.
MAX_ID = 2_147_483_647
IdInt = Annotated[int, Field(gt=0, le=MAX_ID)]

# ---------- Auth ----------


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: Optional[str] = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: Optional[str] = None
    created_at: datetime


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------- Diagnostic Centres & Tests ----------


class TestCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)


class TestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    price: Decimal


class CentreCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    location: str = Field(min_length=1, max_length=255)


class CentreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    location: str
    tests: List[TestOut] = Field(default_factory=list)


# ---------- Bookings ----------


class BookingCreate(BaseModel):
    test_id: IdInt
    appointment_datetime: datetime


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    test_id: int
    centre_id: int
    appointment_datetime: datetime
    amount: Decimal
    status: BookingStatus
    created_at: datetime
    updated_at: datetime


# ---------- Payments ----------


class PaymentCreate(BaseModel):
    booking_id: IdInt


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    booking_id: int
    amount: Decimal
    status: PaymentStatus
    created_at: datetime


class WebhookPayload(BaseModel):
    """
    Shape of what a real payment provider would POST to our webhook.
    event_id is what makes retries safe to ignore.
    """

    event_id: str = Field(min_length=1, max_length=255)
    booking_id: IdInt
    status: PaymentStatus
