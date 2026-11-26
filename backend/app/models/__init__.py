"""TravelEase data model. Travellers own their own bookings; flights are shared
synthetic inventory. Money is integer pence; loyalty is integer points."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

BOOKING_STATUSES = ("confirmed", "cancelled")
CABINS = ("economy", "premium", "business")


class Base(DeclarativeBase):
    pass


def _uuid() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, default=uuid.uuid4)


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def _in(col: str, values: tuple[str, ...], name: str) -> CheckConstraint:
    return CheckConstraint(f"{col} IN ({', '.join(repr(v) for v in values)})", name=name)


class User(Base):
    """A traveller (or, with is_platform_admin, the ops/security admin)."""

    __tablename__ = "users"
    id: Mapped[uuid.UUID] = _uuid()
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    is_platform_admin: Mapped[bool] = mapped_column(default=False, nullable=False)
    loyalty_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _now()
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="users_email_lowercase"),
        CheckConstraint("loyalty_points >= 0", name="users_points_nonneg"),
    )


class Flight(Base):
    __tablename__ = "flights"
    id: Mapped[uuid.UUID] = _uuid()
    flight_number: Mapped[str] = mapped_column(String(8), nullable=False)
    origin: Mapped[str] = mapped_column(String(3), nullable=False)       # IATA code
    destination: Mapped[str] = mapped_column(String(3), nullable=False)
    departs_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    arrives_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cabin: Mapped[str] = mapped_column(String(10), nullable=False, default="economy")
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    seats_total: Mapped[int] = mapped_column(Integer, nullable=False, default=180)
    seats_booked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    __table_args__ = (
        _in("cabin", CABINS, "flights_cabin_valid"),
        CheckConstraint("price_cents >= 0 AND seats_booked >= 0 AND seats_booked <= seats_total", name="flights_amounts_valid"),
        CheckConstraint("origin ~ '^[A-Z]{3}$' AND destination ~ '^[A-Z]{3}$' AND origin <> destination", name="flights_route_valid"),
        Index("ix_flights_route", "origin", "destination", "departs_at"),
    )


class Booking(Base):
    __tablename__ = "bookings"
    id: Mapped[uuid.UUID] = _uuid()
    reference: Mapped[str] = mapped_column(String(6), unique=True, nullable=False)
    traveller_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    flight_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("flights.id", ondelete="RESTRICT"), nullable=False)
    passengers: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    points_earned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="confirmed")
    contact_email: Mapped[str] = mapped_column(String(254), nullable=False)
    created_at: Mapped[datetime] = _now()
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        _in("status", BOOKING_STATUSES, "bookings_status_valid"),
        CheckConstraint("passengers BETWEEN 1 AND 9 AND amount_cents >= 0", name="bookings_amounts_valid"),
        Index("ix_bookings_traveller", "traveller_id"),
    )


class SecurityEvent(Base):
    """Append-only. A database trigger rejects UPDATE and DELETE (see migration)."""

    __tablename__ = "security_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = _now()
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column()
    ip: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    __table_args__ = (Index("ix_security_events_type_at", "type", "at"),)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = _now()
    rule: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    summary: Mapped[str] = mapped_column(String(300), nullable=False)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("security_events.id"))
    dedupe_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("status IN ('open','acknowledged')", name="alerts_status_valid"),)
