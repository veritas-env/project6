"""Passwords, random tokens and signed values (A04, A07).

- Passwords: argon2id via argon2-cffi defaults (RFC 9106 low-memory profile).
- Tokens: `secrets`, 256 bits.
- Signed values: HMAC-SHA256 with the app secret, purpose-bound, with expiry.
No custom cryptography anywhere else in the app."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()
# Verified against when the account doesn't exist, so response time doesn't reveal it.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128
_COMMON = {
    line.strip().lower()
    for line in (Path(__file__).with_name("common_passwords.txt")).read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.startswith("#")
}


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def password_problems(password: str, email: str = "") -> list[str]:
    """Return human-readable reasons the password is rejected (empty = OK)."""
    problems = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > MAX_PASSWORD_LENGTH:
        problems.append(f"must be at most {MAX_PASSWORD_LENGTH} characters")
    if password.lower() in _COMMON:
        problems.append("is too common")
    local = email.split("@", 1)[0].lower()
    if len(local) >= 3 and local in password.lower():
        problems.append("must not contain your email name")
    if len(set(password)) < 5:
        problems.append("is too repetitive")
    return problems


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def token_digest(token: str) -> str:
    """Store and index tokens by digest so a data leak doesn't leak usable tokens."""
    return hashlib.sha256(token.encode()).hexdigest()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign(value: str, purpose: str, secret: str, ttl_seconds: int) -> str:
    """Return `value.expiry.mac`. The purpose is bound into the MAC."""
    if not secret:
        raise ValueError("secret key is not configured")
    expiry = str(int(time.time()) + ttl_seconds)
    mac = hmac.new(secret.encode(), f"{purpose}|{value}|{expiry}".encode(), hashlib.sha256).digest()
    return f"{_b64(value.encode())}.{expiry}.{_b64(mac)}"


def unsign(signed: str, purpose: str, secret: str) -> str | None:
    try:
        v64, expiry, mac64 = signed.split(".")
        value = _unb64(v64).decode()
        mac = _unb64(mac64)
    except (ValueError, UnicodeDecodeError):
        return None
    expected = hmac.new(secret.encode(), f"{purpose}|{value}|{expiry}".encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        return None
    if not expiry.isdigit() or int(expiry) < time.time():
        return None
    return value
