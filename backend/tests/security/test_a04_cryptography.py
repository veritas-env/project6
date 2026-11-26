"""A04 Cryptographic Failures: password storage, token randomness, signed values."""

from __future__ import annotations

import time

from app.core import security
from app.core.sessions import SESSION_COOKIE
from app.models import User


def test_passwords_stored_as_argon2id(app, world):
    with app.state.sessionmaker() as s:
        h = s.get(User, world.bob.id).password_hash
    assert h.startswith("$argon2id$")
    assert world.bob.password not in h


def test_same_password_hashes_differently():
    assert security.hash_password("Same-password-123") != security.hash_password("Same-password-123")


def test_tokens_are_long_and_unique():
    tokens = {security.new_token() for _ in range(2000)}
    assert len(tokens) == 2000
    assert all(len(t) >= 43 for t in tokens)  # 32 bytes base64url


def test_session_tokens_not_stored_in_plaintext(app, world):
    token = world.bob.client.cookies[SESSION_COOKIE]
    r = app.state.redis
    keys = [k.decode() for k in r.keys("*")]
    assert not any(token in k for k in keys)
    for k in keys:
        if r.type(k) == b"string":
            assert token.encode() not in r.get(k)


def test_signed_values_roundtrip_and_reject_tampering():
    key = "k" * 40
    s = security.sign("doc-123", "share", key, 60)
    assert security.unsign(s, "share", key) == "doc-123"
    v, exp, mac = s.split(".")
    assert security.unsign(f"{v}.{int(exp) + 1000}.{mac}", "share", key) is None   # extended expiry
    assert security.unsign(s, "reset", key) is None                                 # other purpose
    assert security.unsign(s, "share", "j" * 40) is None                            # other key
    assert security.unsign(s.replace(v, security._b64(b"doc-999")), "share", key) is None
    assert security.unsign("garbage", "share", key) is None


def test_signed_values_expire():
    key = "k" * 40
    s = security.sign("x", "p", key, -1)
    assert security.unsign(s, "p", key) is None


def test_sign_refuses_empty_key():
    import pytest
    with pytest.raises(ValueError):
        security.sign("x", "p", "", 10)


def test_password_check_timing_does_not_reveal_unknown_users():
    known = security.hash_password("Some-password-123")
    t0 = time.perf_counter(); security.verify_password(known, "wrong-guess-123"); t1 = time.perf_counter()
    security.verify_password(None, "wrong-guess-123"); t2 = time.perf_counter()
    a, b = t1 - t0, t2 - t1
    assert 0.3 < a / b < 3.0
