"""A02 Security Misconfiguration: safe defaults in the app itself. Response headers set
by Nginx are checked against a deployed instance in security/acceptance/."""

from __future__ import annotations

import fakeredis
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app
from tests.conftest import make_client


def test_production_refuses_missing_or_short_secret():
    with pytest.raises(ValidationError):
        Settings(env="production", secret_key="short", database_url="postgresql+psycopg://u:p@db/x")


def test_production_refuses_default_db_credentials():
    with pytest.raises(ValidationError):
        Settings(env="production", secret_key="x" * 40)


def test_production_hides_api_docs(settings):
    prod = settings.model_copy(update={"env": "production"})
    c = make_client(create_app(prod, fakeredis.FakeRedis()))
    for path in ("/api/docs", "/api/openapi.json", "/docs", "/redoc", "/openapi.json"):
        assert c.get(path).status_code == 404, path


@pytest.mark.parametrize("path", ["/.git/config", "/.env", "/api/.env", "/server-status", "/api/v1/../../etc/passwd"])
def test_sensitive_paths_not_served(app, path):
    r = make_client(app).get(path)
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")


def test_no_cors_for_foreign_origins(app, world):
    r = world.alice.client.get("/api/v1/auth/me", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers
    pre = make_client(app).options("/api/v1/auth/me", headers={
        "Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in pre.headers
    assert "access-control-allow-credentials" not in pre.headers


def test_api_responses_not_cached(app, world):
    r = world.alice.client.get("/api/v1/auth/me")
    assert r.headers["cache-control"] == "no-store"


def test_errors_are_generic_json(app):
    c = make_client(app)
    r = c.get("/api/v1/does-not-exist")
    assert r.status_code == 404 and r.json()["error"] == "not_found"
    r = c.delete("/api/health")
    assert r.status_code == 405 and r.json()["error"] == "method_not_allowed"
    assert "fastapi" not in r.text.lower() and "starlette" not in r.text.lower()


def test_request_id_is_always_server_generated(app):
    r = make_client(app).get("/api/health", headers={"X-Request-ID": "injected\r\nX-Evil: 1"})
    assert r.headers["x-request-id"] != "injected" and len(r.headers["x-request-id"]) == 32
    assert "x-evil" not in r.headers
