"""Synthetic demo data for TravelEase: travellers, a flight schedule, and some bookings.
Every name and figure is invented. Used by `python -m app.cli seed-demo`."""

from __future__ import annotations

import random
import secrets
import string
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .core.security import hash_password
from .models import Booking, Flight, User

DOMAIN = "travelease.lab"
AIRPORTS = ["LHR", "JFK", "CDG", "AMS", "DXB", "SIN", "FRA", "MAD", "BCN", "LIS", "DUB", "EDI"]
ROUTES = [("LHR", "JFK", 35000, 480), ("LHR", "CDG", 8000, 75), ("LHR", "AMS", 7000, 70), ("LHR", "DXB", 42000, 400),
          ("LHR", "MAD", 11000, 140), ("LHR", "DUB", 6000, 80), ("CDG", "JFK", 38000, 490), ("AMS", "SIN", 65000, 780),
          ("LHR", "BCN", 9500, 130), ("LHR", "EDI", 5500, 85), ("LHR", "FRA", 8500, 100), ("LHR", "LIS", 10000, 160)]
CABINS = [("economy", 1.0, 150), ("premium", 1.8, 24), ("business", 3.2, 20)]
TRAVELLERS = [("scanner-t1", "Alex Morgan"), ("scanner-t2", "Jamie Lee"), ("priya.shah", "Priya Shah"),
              ("tom.becker", "Tom Becker"), ("nora.walsh", "Nora Walsh"), ("david.osei", "David Osei")]


def _ref() -> str:
    return "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))


def seed_demo(s: Session, upload_dir=None, seed: int = 2026) -> dict[str, str]:
    if s.scalar(select(User.id).limit(1)) is not None:
        raise RuntimeError("database already has users; reset it first")
    rnd = random.Random(seed)
    now = datetime.now(timezone.utc)
    passwords: dict[str, str] = {}

    def user(local, name, admin=False):
        pw = "Lab-" + secrets.token_urlsafe(18)
        u = User(email=f"{local}@{DOMAIN}", display_name=name, password_hash=hash_password(pw), is_platform_admin=admin)
        s.add(u)
        s.flush()
        passwords[u.email] = pw
        return u

    user("platform-admin", "Platform Administrator", admin=True)
    travellers = [user(local, name) for local, name in TRAVELLERS]

    flights = []
    for day in range(1, 60):
        depart_day = now + timedelta(days=day)
        for origin, dest, base, mins in rnd.sample(ROUTES, k=rnd.randint(3, 6)):
            cabin, mult, seats = rnd.choice(CABINS)
            hour = rnd.randint(6, 21)
            departs = depart_day.replace(hour=hour, minute=rnd.choice([0, 15, 30, 45]), second=0, microsecond=0)
            f = Flight(flight_number=f"TE{rnd.randint(100, 999)}", origin=origin, destination=dest, departs_at=departs,
                       arrives_at=departs + timedelta(minutes=mins), cabin=cabin,
                       price_cents=int(base * mult * rnd.uniform(0.85, 1.25)), seats_total=seats, seats_booked=0)
            s.add(f)
            flights.append(f)
    s.flush()

    for _ in range(rnd.randint(30, 45)):
        t = rnd.choice(travellers)
        f = rnd.choice(flights)
        pax = rnd.randint(1, 3)
        if f.seats_total - f.seats_booked < pax:
            continue
        amount = f.price_cents * pax
        points = amount // 100
        f.seats_booked += pax
        t.loyalty_points += points
        s.add(Booking(reference=_ref(), traveller_id=t.id, flight_id=f.id, passengers=pax, amount_cents=amount,
                      points_earned=points, contact_email=t.email,
                      created_at=now - timedelta(days=rnd.randint(0, 20))))
    s.commit()
    return passwords
