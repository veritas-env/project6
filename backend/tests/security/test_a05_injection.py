"""A05 Injection: filters are typed; output is JSON."""

from __future__ import annotations

import pytest


@pytest.mark.parametrize("param,value", [("origin", "LHR' OR 1=1"), ("cabin", "economy'--"), ("on", "2026-01-01' OR 1=1"), ("limit", "5;DROP")])
def test_flight_filters_are_typed(app, world, param, value):
    assert world.alice.client.get("/api/v1/flights", params={param: value}).status_code == 422


def test_contact_email_is_validated(app, world):
    r = world.alice.client.post("/api/v1/bookings", json={"flight_id": str(world.ids["flight2"]), "contact_email": "<script>"})
    assert r.status_code == 422


def test_output_is_json(app, world):
    r = world.alice.client.get("/api/v1/flights")
    assert r.headers["content-type"].startswith("application/json")
