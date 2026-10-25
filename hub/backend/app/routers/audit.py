"""Audit trail API (M7). Senior management and the competent authority can read it."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..db import get_db
from ..services import auth

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
def audit(entity_id: str | None = None, action: str | None = None, actor: str | None = None, limit: int = 100,
          db: Session = Depends(get_db), _user=Depends(auth.require_roles("senior_management", "competent_authority"))):
    """Newest first. Filters: entity_id (a case or link ID), action (e.g. LINK_CONFIRMED), actor."""
    q = select(m.AuditLog).order_by(m.AuditLog.id.desc()).limit(min(max(limit, 1), 500))
    if entity_id:
        q = q.where(m.AuditLog.entity_id == entity_id)
    if action:
        q = q.where(m.AuditLog.action == action)
    if actor:
        q = q.where(m.AuditLog.actor == actor)
    return [{"id": r.id, "at": r.at.isoformat(timespec="seconds"), "actor": r.actor, "role": r.role, "action": r.action,
             "entity_type": r.entity_type, "entity_id": r.entity_id, "detail": r.detail} for r in db.scalars(q)]
