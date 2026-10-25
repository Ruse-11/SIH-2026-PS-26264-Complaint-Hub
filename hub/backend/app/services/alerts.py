"""Alerts (M6): list what the matching engine raised. Acknowledge comes with the officer actions in M7."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m


def list_alerts(db: Session, type=None, institution_id=None, open_only=False, limit=200) -> list[dict]:
    q = select(m.Alert).order_by(m.Alert.id.desc()).limit(limit)
    if type:
        q = q.where(m.Alert.type == type)
    if institution_id:
        q = q.where(m.Alert.institution_id == institution_id)
    if open_only:
        q = q.where(m.Alert.acknowledged_by.is_(None))
    out = []
    for a in db.scalars(q):
        inst = db.get(m.Institution, a.institution_id) if a.institution_id else None
        case = db.get(m.Case, a.case_id) if a.case_id else None
        out.append({"id": a.id, "type": a.type, "severity": a.severity, "message": a.message, "case_id": a.case_id,
                    "source_case_no": case.source_case_no if case else None, "link_id": a.link_id,
                    "institution": {"aicte_id": inst.aicte_id, "official_name": inst.official_name} if inst else None,
                    "created_at": a.created_at.isoformat(timespec="seconds"), "acknowledged_by": a.acknowledged_by})
    return out
