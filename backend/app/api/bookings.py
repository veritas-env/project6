"""Bookings. A traveller books a flight (seats are reserved, loyalty points are
awarded) and can cancel a confirmed booking (seats and money are released).

Loyalty: a booking earns 1 point per whole pound of the fare, credited when the
booking is confirmed so the traveller sees the reward immediately.
"""

from __future__ import annotations

import secrets
import string
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..models import Booking, Flight, User
from ..schemas import BookingIn, BookingOut
from ..services import audit
from .deps import current_user
from .flights import flight_out

router = APIRouter(prefix="/api/v1/bookings", tags=["bookings"])
REF_ALPHABET = string.ascii_uppercase + string.digits


def _ref() -> str:
    return "".join(secrets.choice(REF_ALPHABET) for _ in range(6))


def points_for(amount_cents: int) -> int:
    return amount_cents // 100  # 1 point per pound


def booking_out(db: Session, b: Booking) -> BookingOut:
    f = db.get(Flight, b.flight_id)
    return BookingOut(id=b.id, reference=b.reference, flight=flight_out(f), passengers=b.passengers,
                      amount_cents=b.amount_cents, points_earned=b.points_earned, status=b.status,
                      contact_email=b.contact_email, created_at=b.created_at, cancelled_at=b.cancelled_at)


def _own(db: Session, request: Request, user: User, booking_id: uuid.UUID, lock: bool = False) -> Booking:
    stmt = select(Booking).where(Booking.id == booking_id, Booking.traveller_id == user.id)
    b = db.scalar(stmt.with_for_update() if lock else stmt)
    if b is None:
        audit.record(request, "authz.denied", actor=user.id, severity="medium", detail={"path": request.url.path, "reason": "not_owner"})
        raise HTTPException(404, "not_found")
    return b


@router.get("", response_model=list[BookingOut])
def my_bookings(user: User = Depends(current_user), db: Session = Depends(get_db),
                limit: int = Query(default=100, ge=1, le=300)) -> list[BookingOut]:
    rows = db.scalars(select(Booking).where(Booking.traveller_id == user.id).order_by(Booking.created_at.desc()).limit(limit))
    return [booking_out(db, b) for b in rows]


@router.post("", response_model=BookingOut, status_code=201)
def book(body: BookingIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> BookingOut:
    flight = db.scalar(select(Flight).where(Flight.id == body.flight_id).with_for_update())
    if flight is None:
        raise HTTPException(404, "flight_not_found")
    if flight.seats_total - flight.seats_booked < body.passengers:
        raise HTTPException(409, "not_enough_seats")
    amount = flight.price_cents * body.passengers
    points = points_for(amount)
    flight.seats_booked += body.passengers
    me = db.get(User, user.id, with_for_update=True)
    me.loyalty_points += points
    b = Booking(reference=_ref(), traveller_id=user.id, flight_id=flight.id, passengers=body.passengers,
                amount_cents=amount, points_earned=points, contact_email=body.contact_email)
    db.add(b)
    db.commit()
    db.refresh(b)
    audit.record(request, "booking.points_awarded", actor=user.id, detail={"reference": b.reference, "points": points})
    return booking_out(db, b)


@router.get("/{booking_id}", response_model=BookingOut)
def get_booking(booking_id: uuid.UUID, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> BookingOut:
    return booking_out(db, _own(db, request, user, booking_id))


@router.post("/{booking_id}/cancel", response_model=BookingOut)
def cancel(booking_id: uuid.UUID, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> BookingOut:
    from datetime import datetime, timezone

    b = _own(db, request, user, booking_id, lock=True)
    if b.status != "confirmed":
        raise HTTPException(409, "already_cancelled")
    flight = db.scalar(select(Flight).where(Flight.id == b.flight_id).with_for_update())
    flight.seats_booked = max(0, flight.seats_booked - b.passengers)
    b.status = "cancelled"
    b.cancelled_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(b)
    audit.record(request, "booking.cancelled", actor=user.id, detail={"reference": b.reference})
    return booking_out(db, b)
