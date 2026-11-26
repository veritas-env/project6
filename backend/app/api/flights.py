"""Flight search (shared synthetic inventory)."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..models import Flight, User
from ..schemas import Cabin, FlightOut
from .deps import current_user

router = APIRouter(prefix="/api/v1/flights", tags=["flights"])


def flight_out(f: Flight) -> FlightOut:
    return FlightOut(id=f.id, flight_number=f.flight_number, origin=f.origin, destination=f.destination,
                     departs_at=f.departs_at, arrives_at=f.arrives_at, cabin=f.cabin, price_cents=f.price_cents,
                     seats_available=f.seats_total - f.seats_booked)


@router.get("", response_model=list[FlightOut])
def search_flights(
    _: User = Depends(current_user),
    db: Session = Depends(get_db),
    origin: str | None = Query(default=None, pattern=r"^[A-Za-z]{3}$"),
    destination: str | None = Query(default=None, pattern=r"^[A-Za-z]{3}$"),
    on: date | None = None,
    cabin: Cabin | None = None,
    limit: int = Query(default=100, ge=1, le=300),
) -> list[FlightOut]:
    stmt = select(Flight).where(Flight.departs_at >= datetime.now(timezone.utc))
    if origin:
        stmt = stmt.where(Flight.origin == origin.upper())
    if destination:
        stmt = stmt.where(Flight.destination == destination.upper())
    if on:
        start = datetime.combine(on, time.min, timezone.utc)
        end = datetime.combine(on, time.max, timezone.utc)
        stmt = stmt.where(Flight.departs_at >= start, Flight.departs_at <= end)
    if cabin:
        stmt = stmt.where(Flight.cabin == cabin)
    return [flight_out(f) for f in db.scalars(stmt.order_by(Flight.departs_at).limit(limit))]
