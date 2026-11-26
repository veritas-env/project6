"""Request and response bodies. Every input is length- and format-bounded and
unknown fields are rejected."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[A-Za-z0-9.-]{1,189}\.[A-Za-z]{2,24}$")
Cabin = Literal["economy", "premium", "business"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def normalize_email(v: str) -> str:
    v = v.strip().lower()
    if len(v) > 254 or not _EMAIL_RE.match(v):
        raise ValueError("invalid email address")
    return v


# --- auth -----------------------------------------------------------------------

class LoginIn(StrictModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return normalize_email(v)


class RegisterIn(StrictModel):
    email: str = Field(max_length=254)
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return normalize_email(v)


class PasswordChangeIn(StrictModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    is_platform_admin: bool
    loyalty_points: int = 0


class SessionOut(BaseModel):
    user: UserOut
    csrf_token: str


# --- flights ------------------------------------------------------------------------

class FlightOut(BaseModel):
    id: uuid.UUID
    flight_number: str
    origin: str
    destination: str
    departs_at: datetime
    arrives_at: datetime
    cabin: str
    price_cents: int
    seats_available: int


# --- bookings -----------------------------------------------------------------------

class BookingIn(StrictModel):
    flight_id: uuid.UUID
    passengers: int = Field(default=1, ge=1, le=9)
    contact_email: str = Field(max_length=254)

    @field_validator("contact_email")
    @classmethod
    def _email(cls, v: str) -> str:
        return normalize_email(v)


class BookingOut(BaseModel):
    id: uuid.UUID
    reference: str
    flight: FlightOut
    passengers: int
    amount_cents: int
    points_earned: int
    status: str
    contact_email: str
    created_at: datetime
    cancelled_at: datetime | None


# --- platform admin -------------------------------------------------------------

class EventOut(BaseModel):
    id: int
    at: datetime
    type: str
    severity: str
    actor_user_id: uuid.UUID | None
    ip: str | None
    request_id: str | None
    detail: dict


class AlertOut(BaseModel):
    id: int
    at: datetime
    rule: str
    severity: str
    summary: str
    event_id: int | None
    status: str
