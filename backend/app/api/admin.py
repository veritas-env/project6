"""Platform-admin views of security events and alerts (A09)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..models import Alert, SecurityEvent, User
from ..schemas import AlertOut, EventOut
from .deps import platform_admin

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/security-events", response_model=list[EventOut])
def events(
    _: User = Depends(platform_admin),
    db: Session = Depends(get_db),
    type: str | None = Query(default=None, max_length=64, pattern=r"^[a-z0-9_.]+$"),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[EventOut]:
    stmt = select(SecurityEvent).order_by(SecurityEvent.id.desc()).limit(limit)
    if type:
        stmt = stmt.where(SecurityEvent.type == type)
    return [EventOut.model_validate(e, from_attributes=True) for e in db.scalars(stmt)]


@router.get("/alerts", response_model=list[AlertOut])
def alerts(
    _: User = Depends(platform_admin),
    db: Session = Depends(get_db),
    status: str | None = Query(default=None, pattern=r"^(open|acknowledged)$"),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AlertOut]:
    stmt = select(Alert).order_by(Alert.id.desc()).limit(limit)
    if status:
        stmt = stmt.where(Alert.status == status)
    return [AlertOut.model_validate(a, from_attributes=True) for a in db.scalars(stmt)]


@router.post("/alerts/{alert_id}/ack", response_model=AlertOut)
def ack(alert_id: int, user: User = Depends(platform_admin), db: Session = Depends(get_db)) -> AlertOut:
    a = db.scalar(select(Alert).where(Alert.id == alert_id).with_for_update())
    if a is None:
        raise HTTPException(404, "not_found")
    if a.status != "acknowledged":
        a.status, a.acknowledged_by, a.acknowledged_at = "acknowledged", user.id, datetime.now(timezone.utc)
        db.commit()
    return AlertOut.model_validate(a, from_attributes=True)
