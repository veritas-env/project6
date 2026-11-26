"""A08 Integrity: clients can't set server-owned fields."""

from __future__ import annotations

import pytest

from tests.conftest import make_client


@pytest.mark.parametrize("extra", [{"amount_cents": 1}, {"points_earned": 99999}, {"status": "cancelled"}, {"reference": "HACKED"}, {"traveller_id": "00000000-0000-0000-0000-000000000000"}])
def test_booking_rejects_server_owned_fields(app, world, extra):
    body = {"flight_id": str(world.ids["flight2"]), "contact_email": "x@lab.test", **extra}
    assert world.alice.client.post("/api/v1/bookings", json=body).status_code == 422


def test_amount_and_points_computed_by_server(app, world):
    r = world.alice.client.post("/api/v1/bookings", json={"flight_id": str(world.ids["flight2"]), "contact_email": "x@lab.test"})
    assert r.json()["amount_cents"] == 8000 and r.json()["points_earned"] == 80


def test_login_rejects_extra_fields(app, world):
    r = make_client(app).post("/api/v1/auth/login", json={"email": world.bob.email, "password": world.bob.password, "is_platform_admin": True})
    assert r.status_code == 422


def test_register_cannot_grant_points_or_admin(app, world):
    r = make_client(app).post("/api/v1/auth/register", json={"email": "new@lab.test", "display_name": "N", "password": "Brand-new-Passphrase-42", "loyalty_points": 9999})
    assert r.status_code == 422
