"""A01 Broken Access Control: every route needs a session, travellers only see their own
bookings, admin routes are hidden, CSRF is enforced."""

from __future__ import annotations

import re
import uuid

import pytest

from tests.conftest import make_client

PUBLIC = {("POST", "/api/v1/auth/login"), ("POST", "/api/v1/auth/register")}
ADMIN_PREFIX = "/api/v1/admin/"
BODIES = {
    ("POST", "/api/v1/bookings"): "BOOK",
    ("POST", "/api/v1/auth/password"): {"json": {"current_password": "x", "new_password": "y"}},
}


def operations(app):
    ops = []
    for path, item in app.openapi()["paths"].items():
        for method in item:
            if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                ops.append((method.upper(), path))
    return sorted(ops)


def fill(path, w):
    values = {"booking_id": w.ids["booking_a"], "alert_id": 1}
    def sub(m):
        if m.group(1) not in values:
            pytest.fail(f"no test value for {{{m.group(1)}}}")
        return str(values[m.group(1)])
    return re.sub(r"{(\w+)}", sub, path)


def call(client, method, path, template, w):
    body = BODIES.get((method, template), {})
    if body == "BOOK":
        body = {"json": {"flight_id": str(w.ids["flight2"]), "contact_email": "x@lab.test"}}
    return client.request(method, path, **body)


def test_route_table_is_known(app):
    assert len(operations(app)) >= 10


def test_every_non_public_route_requires_auth(app, world):
    anon = make_client(app)
    for method, path in operations(app):
        if (method, path) in PUBLIC:
            continue
        assert call(anon, method, fill(path, world), path, world).status_code == 401, f"{method} {path}"


def test_other_travellers_cannot_touch_my_bookings(app, world):
    for method, path in operations(app):
        if "{booking_id}" not in path:
            continue
        r = call(world.mallory.client, method, fill(path, world), path, world)
        assert r.status_code == 404, f"{method} {path} -> {r.status_code}"


def test_booking_list_is_per_user(app, world):
    assert world.mallory.client.get("/api/v1/bookings").json() == []
    assert len(world.alice.client.get("/api/v1/bookings").json()) == 1


def test_admin_routes_hidden_from_travellers(app, world):
    for method, path in operations(app):
        if not path.startswith(ADMIN_PREFIX):
            continue
        assert call(world.alice.client, method, fill(path, world), path, world).status_code == 404
    assert world.root.client.get("/api/v1/admin/alerts").status_code == 200


def test_csrf_required_on_writes(app, world):
    c = make_client(app)
    c.cookies = world.alice.client.cookies
    body = {"flight_id": str(world.ids["flight2"]), "contact_email": "x@lab.test"}
    assert c.post("/api/v1/bookings", json=body).status_code == 403
    assert c.post("/api/v1/bookings", json=body, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert c.post("/api/v1/bookings", json=body, headers={"X-CSRF-Token": world.alice.csrf}).status_code == 201


def test_csrf_token_of_another_session_rejected(app, world):
    c = make_client(app)
    c.cookies = world.alice.client.cookies
    r = c.post("/api/v1/bookings", json={"flight_id": str(world.ids["flight2"]), "contact_email": "x@lab.test"},
               headers={"X-CSRF-Token": world.bob.csrf})
    assert r.status_code == 403


@pytest.mark.parametrize("ctype", ["application/x-www-form-urlencoded", "text/plain"])
def test_cross_site_form_content_types_refused(app, world, ctype):
    r = world.alice.client.post("/api/v1/bookings", content=b"x=1", headers={"Content-Type": ctype})
    assert r.status_code == 415


def test_no_cors(app, world):
    r = world.alice.client.get("/api/v1/flights", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers


def test_unknown_ids(app, world):
    c = world.alice.client
    assert c.get(f"/api/v1/bookings/{uuid.uuid4()}").status_code == 404
    assert c.get("/api/v1/bookings/1%20OR%201=1").status_code == 422
