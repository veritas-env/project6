"""Request dependencies: who is calling (A07), CSRF (A01), and what they may touch (A01).

Every route except the explicit public ones (see `PUBLIC_ROUTES` in tests) depends on
`current_user`, and admin routes on `platform_admin`. Tests enumerate the route
table to make sure nothing slips through."""

from __future__ import annotations

import hmac
import uuid

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.sessions import CSRF_HEADER, SESSION_COOKIE, SessionData, SessionStore
from ..models import User
from ..services import audit

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_store(request: Request) -> SessionStore:
    return request.app.state.session_store


def current_session(request: Request, store: SessionStore = Depends(get_store)) -> SessionData:
    sess = store.get(request.cookies.get(SESSION_COOKIE))
    if sess is None:
        raise HTTPException(401, "authentication_required")
    if request.method not in SAFE_METHODS:
        sent = request.headers.get(CSRF_HEADER, "")
        if not sent or not hmac.compare_digest(sent, sess.csrf):
            audit.record(request, "csrf.rejected", actor=sess.user_id, severity="medium")
            raise HTTPException(403, "csrf_failed")
    request.state.session = sess
    return sess


def current_user(
    request: Request,
    sess: SessionData = Depends(current_session),
    db: Session = Depends(get_db),
) -> User:
    user = db.get(User, uuid.UUID(sess.user_id))
    if user is None or not user.is_active:
        get_store(request).destroy_digest(sess.digest, sess.user_id)
        raise HTTPException(401, "authentication_required")
    return user


def platform_admin(request: Request, user: User = Depends(current_user)) -> User:
    if not user.is_platform_admin:
        audit.record(request, "authz.denied", actor=user.id, severity="medium", detail={"path": request.url.path, "need": "platform_admin"})
        raise HTTPException(404, "not_found")  # don't reveal that admin routes exist
    return user
