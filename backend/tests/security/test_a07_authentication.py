"""A07 Authentication Failures: generic errors, lockout, rate limits, session lifecycle."""

from __future__ import annotations

import json

import pytest

from app.core.security import token_digest
from app.core.sessions import SESSION_COOKIE
from tests.conftest import make_client


def login(app, email, password):
    return make_client(app).post("/api/v1/auth/login", json={"email": email, "password": password})


def test_unknown_user_and_wrong_password_look_identical(app, world):
    a = login(app, "nobody@lab.test", "Whatever-123456")
    b = login(app, world.bob.email, "Wrong-password-123")
    assert a.status_code == b.status_code == 401
    assert a.json()["error"] == b.json()["error"] == "invalid_credentials"


def test_email_is_case_insensitive(app, world):
    assert login(app, world.bob.email.upper(), world.bob.password).status_code == 200


def test_lockout_after_repeated_failures(app, world, settings):
    for _ in range(settings.login_max_failures):
        assert login(app, world.mallory.email, "Wrong-password-123").status_code == 401
    # Correct password is now refused, with the same generic error.
    r = login(app, world.mallory.email, world.mallory.password)
    assert r.status_code == 401 and r.json()["error"] == "invalid_credentials"


def test_ip_rate_limit(app, world, settings):
    c = make_client(app)
    codes = [c.post("/api/v1/auth/login", json={"email": f"x{i}@lab.test", "password": "Wrong-123456789"}).status_code
             for i in range(settings.login_ip_limit + 1)]
    assert codes[-1] == 429


def test_session_cookie_flags(app, world):
    r = login(app, world.bob.email, world.bob.password)
    cookies = r.headers.get_list("set-cookie")
    sid = next(c for c in cookies if c.startswith(SESSION_COOKIE + "="))
    low = sid.lower()
    assert "secure" in low and "httponly" in low and "samesite=lax" in low and "path=/" in low
    assert "domain=" not in low


def test_new_session_on_every_login(app, world):
    c = make_client(app)
    c.post("/api/v1/auth/login", json={"email": world.bob.email, "password": world.bob.password})
    first = c.cookies[SESSION_COOKIE]
    c.post("/api/v1/auth/login", json={"email": world.bob.email, "password": world.bob.password})
    second = c.cookies[SESSION_COOKIE]
    assert first != second
    stale = make_client(app)
    stale.cookies[SESSION_COOKIE] = first
    assert stale.get("/api/v1/auth/me").status_code == 401  # pre-login session was destroyed


def test_attacker_chosen_session_id_is_ignored(app, world):
    c = make_client(app)
    c.cookies[SESSION_COOKIE] = "attacker-chosen-value"
    r = c.post("/api/v1/auth/login", json={"email": world.bob.email, "password": world.bob.password})
    assert r.status_code == 200
    issued = r.cookies[SESSION_COOKIE]
    assert issued != "attacker-chosen-value" and len(issued) >= 43


def test_logout_invalidates_server_side(app, world):
    stolen = dict(world.bob.client.cookies)
    assert world.bob.client.post("/api/v1/auth/logout").status_code == 204
    replay = make_client(app)
    for k, v in stolen.items():
        replay.cookies[k] = v
    assert replay.get("/api/v1/auth/me").status_code == 401


def test_password_change_kills_other_sessions(app, world):
    other = make_client(app)
    other.post("/api/v1/auth/login", json={"email": world.bob.email, "password": world.bob.password})
    assert other.get("/api/v1/auth/me").status_code == 200
    old_cookie = world.bob.client.cookies[SESSION_COOKIE]
    r = world.bob.client.post("/api/v1/auth/password", json={"current_password": world.bob.password,
                                                             "new_password": "Brand-new-Passphrase-42"})
    assert r.status_code == 200, r.text
    assert other.get("/api/v1/auth/me").status_code == 401
    assert world.bob.client.cookies[SESSION_COOKIE] != old_cookie  # this one was rotated
    assert world.bob.client.get("/api/v1/auth/me").status_code == 200
    assert login(app, world.bob.email, world.bob.password).status_code == 401
    assert login(app, world.bob.email, "Brand-new-Passphrase-42").status_code == 200


@pytest.mark.parametrize("new", ["short1!", "password1234", "aaaaaaaaaaaaaaaa", "bob-is-my-name-123"])
def test_weak_passwords_rejected(app, world, new):
    r = world.bob.client.post("/api/v1/auth/password", json={"current_password": world.bob.password, "new_password": new})
    assert r.status_code == 422 and r.json()["error"] == "weak_password"


def test_password_change_needs_current_password(app, world):
    r = world.bob.client.post("/api/v1/auth/password", json={"current_password": "nope",
                                                             "new_password": "Brand-new-Passphrase-42"})
    assert r.status_code == 400


def test_idle_timeout(app, world):
    store = app.state.session_store
    digest = token_digest(world.bob.client.cookies[SESSION_COOKIE])
    store.r.delete(f"sess:{digest}")  # what the Redis TTL does after the idle period
    assert world.bob.client.get("/api/v1/auth/me").status_code == 401


def test_absolute_timeout(app, world, settings):
    store = app.state.session_store
    key = f"sess:{token_digest(world.bob.client.cookies[SESSION_COOKIE])}"
    data = json.loads(store.r.get(key))
    data["created"] -= settings.session_absolute_hours * 3600 + 1
    store.r.set(key, json.dumps(data))
    assert world.bob.client.get("/api/v1/auth/me").status_code == 401


def test_deactivated_user_loses_access(app, world):
    from app.models import User

    with app.state.sessionmaker() as s:
        s.get(User, world.bob.id).is_active = False
        s.commit()
    assert world.bob.client.get("/api/v1/auth/me").status_code == 401
