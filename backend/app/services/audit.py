"""Security event recording and alerting (A09).

Events are written in their OWN transaction, so they survive even when the request
that produced them fails and rolls back. Alert rules run right after the event is
stored, in the same short transaction.

Rules:
  immediate   one event raises one alert           (see IMMEDIATE)
  threshold   N events of a type per key in a window (see THRESHOLDS), one alert
              per key per window (deduplicated by dedupe_key)
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from ..core.config import Settings
from ..core.logging import request_id_var
from ..models import Alert, SecurityEvent

log = logging.getLogger("security")

# event type -> (severity, summary)
IMMEDIATE: dict[str, tuple[str, str]] = {
    "booking.points_awarded": ("info", "Loyalty points awarded"),
    "account.locked": ("high", "Account locked after repeated failed sign-ins"),
    "membership.role_elevated": ("high", "User granted an elevated role"),
    "auth.password_changed": ("medium", "Password changed"),
    "file.rejected": ("low", "Upload rejected by content checks"),
}


@dataclass(frozen=True)
class Threshold:
    rule: str
    event_type: str
    key: str  # "ip" or "actor"
    setting: str  # Settings attribute holding the count
    severity: str
    summary: str


THRESHOLDS = [
    Threshold("login.failed.burst", "auth.login_failed", "ip", "alert_failed_login_threshold", "high",
              "Burst of failed sign-ins from one address"),
    Threshold("authz.denied.burst", "authz.denied", "actor", "alert_authz_denied_threshold", "high",
              "Burst of access-denied responses for one user"),
]


def client_ip(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    return request.client.host


def record(
    request: Request,
    type_: str,
    *,
    actor: uuid.UUID | str | None = None,
    severity: str = "info",
    detail: dict[str, Any] | None = None,
) -> int:
    maker: sessionmaker[Session] = request.app.state.sessionmaker
    settings: Settings = request.app.state.settings
    ip = client_ip(request)
    with maker() as s:
        ev = SecurityEvent(
            type=type_,
            severity=severity,
            actor_user_id=uuid.UUID(str(actor)) if actor else None,
            ip=ip,
            request_id=request_id_var.get(),
            detail=detail or {},
        )
        s.add(ev)
        s.flush()
        _evaluate(s, ev, settings)
        s.commit()
        event_id = ev.id
    log.info("security_event", extra={"fields": {"event": type_, "severity": severity, "actor": str(actor) if actor else None, "ip": ip, "detail": detail or {}}})
    return event_id


def _raise_alert(s: Session, rule: str, severity: str, summary: str, event_id: int, dedupe_key: str | None) -> None:
    stmt = insert(Alert).values(rule=rule, severity=severity, summary=summary, event_id=event_id, dedupe_key=dedupe_key)
    if dedupe_key:
        stmt = stmt.on_conflict_do_nothing(index_elements=["dedupe_key"])
    s.execute(stmt)


def _evaluate(s: Session, ev: SecurityEvent, settings: Settings) -> None:
    if ev.type in IMMEDIATE:
        sev, summary = IMMEDIATE[ev.type]
        _raise_alert(s, ev.type, sev, summary, ev.id, None)

    window = timedelta(minutes=settings.alert_window_minutes)
    now = datetime.now(timezone.utc)
    for t in THRESHOLDS:
        if ev.type != t.event_type:
            continue
        key_value = ev.ip if t.key == "ip" else (str(ev.actor_user_id) if ev.actor_user_id else None)
        if not key_value:
            continue
        col = SecurityEvent.ip if t.key == "ip" else SecurityEvent.actor_user_id
        count = s.scalar(
            select(func.count()).select_from(SecurityEvent).where(
                SecurityEvent.type == t.event_type,
                col == (key_value if t.key == "ip" else ev.actor_user_id),
                SecurityEvent.at >= now - window,
            )
        )
        if count >= getattr(settings, t.setting):
            bucket = int(now.timestamp() // window.total_seconds())
            _raise_alert(s, t.rule, t.severity, f"{t.summary} ({count} in {settings.alert_window_minutes} min)",
                         ev.id, f"{t.rule}:{key_value}:{bucket}")
