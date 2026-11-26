"""Sign-in, sign-out, password change (A07)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.security import hash_password, needs_rehash, password_problems, verify_password
from ..core.sessions import CSRF_COOKIE, SESSION_COOKIE, SessionData, SessionStore, hit_rate_limit
from ..models import User
from ..schemas import LoginIn, PasswordChangeIn, RegisterIn, SessionOut, UserOut
from ..services import audit
from .deps import current_session, current_user, get_store

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

GENERIC_LOGIN_ERROR = "invalid_credentials"


def _user_out(u: User) -> UserOut:
    return UserOut(id=u.id, email=u.email, display_name=u.display_name, is_platform_admin=u.is_platform_admin,
                   loyalty_points=u.loyalty_points)


def _set_cookies(request: Request, response: Response, token: str, csrf: str) -> None:
    settings = request.app.state.settings
    max_age = settings.session_absolute_hours * 3600
    # __Host- prefix: Secure, Path=/, no Domain. SameSite=Lax blocks cross-site sends.
    response.set_cookie(SESSION_COOKIE, token, max_age=max_age, path="/", secure=True, httponly=True, samesite="lax")
    response.set_cookie(CSRF_COOKIE, csrf, max_age=max_age, path="/", secure=True, httponly=False, samesite="lax")


def _clear_cookies(response: Response) -> None:
    for name in (SESSION_COOKIE, CSRF_COOKIE):
        response.delete_cookie(name, path="/", secure=True, samesite="lax")


@router.post("/login", response_model=SessionOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db),
          store: SessionStore = Depends(get_store)) -> SessionOut:
    settings = request.app.state.settings
    ip = audit.client_ip(request) or "unknown"
    if hit_rate_limit(store.r, f"login:ip:{ip}", settings.login_ip_limit, settings.login_ip_window_seconds):
        audit.record(request, "auth.login_rate_limited", severity="medium", detail={"email": body.email})
        raise HTTPException(429, "too_many_requests", headers={"Retry-After": str(settings.login_ip_window_seconds)})

    user = db.scalar(select(User).where(User.email == body.email).with_for_update())
    now = datetime.now(timezone.utc)

    if user is None or not user.is_active:
        verify_password(None, body.password)  # equalise timing
        audit.record(request, "auth.login_failed", severity="low", detail={"email": body.email, "reason": "unknown_or_inactive"})
        raise HTTPException(401, GENERIC_LOGIN_ERROR)

    if user.locked_until and user.locked_until > now:
        verify_password(None, body.password)
        audit.record(request, "auth.login_failed", actor=user.id, severity="medium", detail={"reason": "locked"})
        raise HTTPException(401, GENERIC_LOGIN_ERROR)

    if not verify_password(user.password_hash, body.password):
        user.failed_logins += 1
        locked = user.failed_logins >= settings.login_max_failures
        if locked:
            user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
            user.failed_logins = 0
        db.commit()
        audit.record(request, "auth.login_failed", actor=user.id, severity="low", detail={"reason": "bad_password"})
        if locked:
            audit.record(request, "account.locked", actor=user.id, severity="high",
                         detail={"minutes": settings.lockout_minutes})
        raise HTTPException(401, GENERIC_LOGIN_ERROR)

    user.failed_logins = 0
    user.locked_until = None
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    db.commit()

    # Always a brand-new session: an old cookie from before login is never reused.
    old = request.cookies.get(SESSION_COOKIE)
    if old:
        prev = store.get(old)
        if prev:
            store.destroy_digest(prev.digest, prev.user_id)
    token, sess = store.create(str(user.id))
    _set_cookies(request, response, token, sess.csrf)
    audit.record(request, "auth.login_succeeded", actor=user.id)
    return SessionOut(user=_user_out(user), csrf_token=sess.csrf)


@router.post("/register", response_model=SessionOut, status_code=201)
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db),
             store: SessionStore = Depends(get_store)) -> SessionOut:
    from ..core.security import hash_password, password_problems

    if db.scalar(select(User.id).where(User.email == body.email)) is not None:
        raise HTTPException(409, "email_taken")
    problems = password_problems(body.password, body.email)
    if problems:
        raise HTTPException(422, {"error": "weak_password", "problems": problems})
    user = User(email=body.email, display_name=body.display_name, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    token, sess = store.create(str(user.id))
    _set_cookies(request, response, token, sess.csrf)
    audit.record(request, "account.created", actor=user.id, detail={"via": "self_registration"})
    audit.record(request, "auth.login_succeeded", actor=user.id, detail={"via": "registration"})
    return SessionOut(user=_user_out(user), csrf_token=sess.csrf)


@router.post("/logout", status_code=204)
def logout(request: Request, sess: SessionData = Depends(current_session),
           store: SessionStore = Depends(get_store)) -> Response:
    store.destroy_digest(sess.digest, sess.user_id)
    response = Response(status_code=204)
    _clear_cookies(response)
    audit.record(request, "auth.logout", actor=sess.user_id)
    return response


@router.get("/me", response_model=SessionOut)
def me(sess: SessionData = Depends(current_session), user: User = Depends(current_user)) -> SessionOut:
    return SessionOut(user=_user_out(user), csrf_token=sess.csrf)


@router.post("/password", response_model=SessionOut)
def change_password(body: PasswordChangeIn, request: Request, response: Response,
                    user: User = Depends(current_user), db: Session = Depends(get_db),
                    store: SessionStore = Depends(get_store)) -> SessionOut:
    if not verify_password(user.password_hash, body.current_password):
        audit.record(request, "auth.password_change_failed", actor=user.id, severity="medium")
        raise HTTPException(400, "current_password_incorrect")
    problems = password_problems(body.new_password, user.email)
    if body.new_password == body.current_password:
        problems.append("must differ from the current password")
    if problems:
        raise HTTPException(422, {"error": "weak_password", "problems": problems})
    user.password_hash = hash_password(body.new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    db.commit()
    # Kill every session, including this one, then issue a fresh one.
    store.destroy_all(str(user.id))
    token, sess = store.create(str(user.id))
    _set_cookies(request, response, token, sess.csrf)
    audit.record(request, "auth.password_changed", actor=user.id, severity="medium")
    return SessionOut(user=_user_out(user), csrf_token=sess.csrf)
