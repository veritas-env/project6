"""Shared fixtures.

Database: APP_TEST_DATABASE_URL if set (CI uses a Postgres service), otherwise a
throwaway local cluster (tests/pgtemp.py). Redis: fakeredis.

`world` seeds travellers alice, bob and mallory, admin `root`, two flights (f1, f2),
and one confirmed booking for alice on f1.
"""

from __future__ import annotations

import os
import secrets
import uuid
from dataclasses import dataclass, field

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from tests.pgtemp import TempPostgres

TABLES = ["alerts", "security_events", "bookings", "flights", "users"]


@pytest.fixture(scope="session")
def pg_url():
    url = os.environ.get("APP_TEST_DATABASE_URL")
    pg = None
    if not url:
        pg = TempPostgres()
        url = pg.start()
    from alembic import command
    from alembic.config import Config

    here = os.path.dirname(__file__)
    cfg = Config(os.path.join(here, "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(here, "..", "migrations"))
    cfg.attributes["url"] = url
    command.upgrade(cfg, "head")
    yield url
    if pg:
        pg.stop()


@pytest.fixture
def settings(pg_url, tmp_path):
    from app.core.config import Settings

    return Settings(env="test", database_url=pg_url, secret_key=secrets.token_urlsafe(48),
                    upload_dir=str(tmp_path / "uploads"), max_upload_bytes=64 * 1024)


@pytest.fixture
def app(settings):
    engine = create_engine(settings.database_url)
    with engine.begin() as c:
        c.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))
    engine.dispose()
    from app.main import create_app

    application = create_app(settings, fakeredis.FakeRedis())
    yield application
    application.state.engine.dispose()


def make_client(app, raise_errors: bool = True) -> TestClient:
    return TestClient(app, base_url="https://testserver", raise_server_exceptions=raise_errors)


@dataclass
class Actor:
    name: str
    email: str
    password: str
    id: uuid.UUID
    client: TestClient | None = None
    csrf: str = ""

    def login(self, app) -> "Actor":
        self.client = make_client(app)
        r = self.client.post("/api/v1/auth/login", json={"email": self.email, "password": self.password})
        assert r.status_code == 200, r.text
        self.csrf = r.json()["csrf_token"]
        self.client.headers["X-CSRF-Token"] = self.csrf
        return self


@dataclass
class World:
    actors: dict = field(default_factory=dict)
    ids: dict = field(default_factory=dict)

    def __getattr__(self, name):
        d = self.__dict__
        if name in d.get("actors", {}):
            return d["actors"][name]
        if name in d.get("ids", {}):
            return d["ids"][name]
        raise AttributeError(name)


def new_password() -> str:
    return "Lab-" + secrets.token_urlsafe(18)


@pytest.fixture
def world(app) -> World:
    from datetime import datetime, timedelta, timezone

    from app.core.security import hash_password
    from app.models import Booking, Flight, User

    maker = app.state.sessionmaker
    w = World()
    now = datetime.now(timezone.utc)
    with maker() as s:
        for name in ["alice", "bob", "mallory", "root"]:
            pw = new_password()
            u = User(email=f"{name}@lab.test", display_name=name.title(), password_hash=hash_password(pw),
                     is_platform_admin=(name == "root"))
            s.add(u)
            s.flush()
            w.actors[name] = Actor(name, u.email, pw, u.id)
        f1 = Flight(flight_number="TE101", origin="LHR", destination="JFK", departs_at=now + timedelta(days=20),
                    arrives_at=now + timedelta(days=20, hours=8), cabin="economy", price_cents=35000, seats_total=180, seats_booked=0)
        f2 = Flight(flight_number="TE202", origin="LHR", destination="CDG", departs_at=now + timedelta(days=10),
                    arrives_at=now + timedelta(days=10, hours=1), cabin="economy", price_cents=8000, seats_total=180, seats_booked=0)
        s.add_all([f1, f2])
        s.flush()
        w.ids["flight1"] = f1.id
        w.ids["flight2"] = f2.id
        s.commit()
    for a in w.actors.values():
        a.login(app)
    r = w.alice.client.post("/api/v1/bookings", json={"flight_id": str(w.ids["flight1"]), "passengers": 1, "contact_email": "alice@lab.test"})
    assert r.status_code == 201, r.text
    w.ids["booking_a"] = uuid.UUID(r.json()["id"])
    return w


def points(w, who="alice") -> int:
    return getattr(w, who).client.get("/api/v1/auth/me").json()["user"]["loyalty_points"]


def events(app, type_=None) -> list:
    from sqlalchemy import select
    from app.models import SecurityEvent
    with app.state.sessionmaker() as s:
        stmt = select(SecurityEvent).order_by(SecurityEvent.id)
        if type_:
            stmt = stmt.where(SecurityEvent.type == type_)
        return list(s.scalars(stmt))


def alerts(app, rule=None) -> list:
    from sqlalchemy import select
    from app.models import Alert
    with app.state.sessionmaker() as s:
        stmt = select(Alert).order_by(Alert.id)
        if rule:
            stmt = stmt.where(Alert.rule == rule)
        return list(s.scalars(stmt))
