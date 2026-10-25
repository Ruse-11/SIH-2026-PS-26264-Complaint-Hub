"""Audit trail. Every decision or intake writes one row (who, what, which record). Viewing screens come in M7."""
from sqlalchemy.orm import Session

from .. import models as m


def log_event(db: Session, actor: str, action: str, entity_type=None, entity_id=None, detail=None, role=None):
    """Add an audit row to the current transaction (the caller commits)."""
    db.add(m.AuditLog(actor=actor, role=role, action=action, entity_type=entity_type,
                      entity_id=entity_id, detail=detail))
