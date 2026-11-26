"""A09 Security Logging & Alerting Failures: every security-relevant action produces an
event, alertable events produce alerts, and the log can't be rewritten."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.conftest import alerts, events, make_client


def _login(app, email, pw):
    return make_client(app).post("/api/v1/auth/login", json={"email": email, "password": pw})


def test_login_success_and_failure_are_logged(app, world):
    before = len(events(app, "auth.login_succeeded"))
    _login(app, world.bob.email, world.bob.password)
    _login(app, world.bob.email, "Wrong-password-123")
    _login(app, "ghost@lab.test", "Wrong-password-123")
    assert len(events(app, "auth.login_succeeded")) == before + 1
    failed = events(app, "auth.login_failed")
    assert {e.detail.get("reason") for e in failed} >= {"bad_password", "unknown_or_inactive"}
    assert all(e.ip and e.request_id for e in failed)


def test_logout_is_logged(app, world):
    world.bob.client.post("/api/v1/auth/logout")
    assert events(app, "auth.logout")[-1].actor_user_id == world.bob.id


def test_authorization_denials_are_logged(app, world):
    world.mallory.client.get(f"/api/v1/bookings/{world.ids['booking_a']}")  # not owner
    world.bob.client.get("/api/v1/admin/alerts")  # not admin
    reasons = [(e.actor_user_id, e.detail.get("reason") or e.detail.get("need")) for e in events(app, "authz.denied")]
    assert (world.mallory.id, "not_owner") in reasons
    assert (world.bob.id, "platform_admin") in reasons


def test_csrf_rejection_is_logged(app, world):
    c = make_client(app)
    c.cookies = world.alice.client.cookies
    c.post("/api/v1/bookings", json={"flight_id": str(world.ids["flight2"]), "contact_email": "x@lab.test"})
    assert events(app, "csrf.rejected")[-1].actor_user_id == world.alice.id


def test_lockout_raises_alert(app, world, settings):
    for _ in range(settings.login_max_failures):
        _login(app, world.mallory.email, "Wrong-password-123")
    assert len(events(app, "account.locked")) == 1
    assert len(alerts(app, "account.locked")) == 1

def test_password_change_is_logged_and_alerted(app, world):
    world.bob.client.post("/api/v1/auth/password", json={"current_password": world.bob.password,
                                                         "new_password": "Brand-new-Passphrase-42"})
    assert len(events(app, "auth.password_changed")) == 1
    assert len(alerts(app, "auth.password_changed")) == 1


def test_failed_login_burst_alerts_once_per_window(app, world, settings):
    c = make_client(app)
    for i in range(settings.alert_failed_login_threshold + 5):
        c.post("/api/v1/auth/login", json={"email": f"user{i}@lab.test", "password": "Wrong-password-123"})
    assert len(alerts(app, "login.failed.burst")) == 1


def test_authz_denied_burst_alerts(app, world, settings):
    for _ in range(settings.alert_authz_denied_threshold):
        world.mallory.client.get(f"/api/v1/bookings/{world.ids['booking_a']}")
    assert len(alerts(app, "authz.denied.burst")) == 1


def test_alerts_visible_and_acknowledgeable_by_platform_admin(app, world, settings):
    for _ in range(settings.login_max_failures):
        _login(app, world.mallory.email, "Wrong-password-123")
    root = world.root.client
    open_alerts = root.get("/api/v1/admin/alerts", params={"status": "open"}).json()
    assert any(a["rule"] == "account.locked" for a in open_alerts)
    aid = open_alerts[0]["id"]
    assert root.post(f"/api/v1/admin/alerts/{aid}/ack").json()["status"] == "acknowledged"
    assert root.get("/api/v1/admin/security-events", params={"type": "account.locked"}).json()


@pytest.mark.parametrize("sql", ["UPDATE security_events SET type = 'x'", "DELETE FROM security_events"])
def test_security_events_are_append_only(app, world, sql):
    with app.state.engine.connect() as conn:
        with pytest.raises(Exception, match="append-only"):
            conn.execute(text(sql))


def test_events_survive_a_failed_request(app, world):
    """The event is written in its own transaction, so a rollback can't erase it."""
    before = len(events(app, "authz.denied"))
    world.mallory.client.get(f"/api/v1/bookings/{world.ids['booking_a']}")
    assert len(events(app, "authz.denied")) == before + 1


def test_log_injection_is_neutralised(app, world, capsys):
    import json
    import logging

    from app.core.logging import JsonFormatter

    rec = logging.LogRecord("security", logging.INFO, __file__, 1, "security_event", None, None)
    rec.fields = {"email": "x@lab.test\n{\"level\":\"info\",\"msg\":\"forged\"}"}
    line = JsonFormatter().format(rec)
    assert "\n" not in line
    assert json.loads(line)["email"].startswith("x@lab.test\n")
