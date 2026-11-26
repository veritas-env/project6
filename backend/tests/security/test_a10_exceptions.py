"""A10 Mishandling of Exceptional Conditions: failures are generic to the client, roll
back completely, and fail closed."""

from __future__ import annotations

import fakeredis
import pytest
from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.main import create_app
from app.models import Flight
from tests.conftest import make_client


@pytest.fixture
def faulty_app(settings):
    """The real app plus routes that fail in controlled ways."""
    app = create_app(settings, fakeredis.FakeRedis())

    @app.get("/api/test/boom")
    def boom():
        raise RuntimeError("secret internal detail: /srv/app/db.py line 42")

    @app.post("/api/test/half-write")
    def half_write(db: Session = Depends(get_db)):
        org = db.scalar(select(Flight))
        org.flight_number = "RB1ROLLBACK"
        db.flush()
        raise RuntimeError("fails after a write")

    @app.post("/api/test/half-write-http")
    def half_write_http(db: Session = Depends(get_db)):
        org = db.scalar(select(Flight))
        org.flight_number = "RB2ROLLBACK"
        db.flush()
        raise HTTPException(409, "conflict")

    yield app
    app.state.engine.dispose()


def test_unhandled_error_is_generic(faulty_app):
    r = make_client(faulty_app, raise_errors=False).get("/api/test/boom")
    assert r.status_code == 500
    body = r.json()
    assert body["error"] == "internal_error" and len(body["request_id"]) == 32
    assert "secret" not in r.text and "Traceback" not in r.text and ".py" not in r.text


@pytest.mark.parametrize("path", ["/api/test/half-write", "/api/test/half-write-http"])
def test_failed_request_rolls_back_everything(faulty_app, world, path):
    make_client(faulty_app, raise_errors=False).post(path)
    with faulty_app.state.sessionmaker() as s:
        titles = s.scalars(select(Flight.flight_number)).all()
    assert not any("RBROLLBACK" in t for t in titles)


def test_redis_outage_fails_closed(app, world):
    class Down:
        def __getattr__(self, _):
            def fail(*a, **k):
                raise ConnectionError("redis down")
            return fail

    app.state.session_store.r = Down()
    c = make_client(app, raise_errors=False)
    c.cookies = world.alice.client.cookies
    r = c.get("/api/v1/auth/me")
    assert r.status_code == 500  # never treated as "no session check needed"
    r = make_client(app, raise_errors=False).post("/api/v1/auth/login", json={"email": world.bob.email,
                                                                              "password": world.bob.password})
    assert r.status_code == 500 and "__Host-sid" not in r.headers.get("set-cookie", "")

def test_malformed_json_is_a_clean_400_class_error(app, world):
    r = world.alice.client.post("/api/v1/bookings", content=b'{"flight_id": ',
                                headers={"Content-Type": "application/json"})
    assert r.status_code == 422 and r.json()["error"] == "validation_error"

