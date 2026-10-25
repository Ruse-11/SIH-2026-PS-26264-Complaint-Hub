"""Alerts (M6): list what the matching engine raised. Acknowledge comes with the officer actions in M7."""
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from .. import models as m


_RANK = case((m.Alert.severity == "critical", 0), (m.Alert.severity == "warning", 1), else_=2)  # critical first


def list_alerts(db: Session, type=None, institution_id=None, open_only=False, limit=500, visible=None) -> list[dict]:
    q = select(m.Alert).order_by(_RANK, m.Alert.id.desc()).limit(limit)
    if type:
        q = q.where(m.Alert.type == type)
    if institution_id:
        q = q.where(m.Alert.institution_id == institution_id)
    if visible is not None:
        # an alert is visible if its case, or either case of its link, is visible (the RB officer must see an
        # overlap raised by a new PGRC complaint)
        linked = select(m.LinkSuggestion.id).where(m.LinkSuggestion.case_a.in_(visible) | m.LinkSuggestion.case_b.in_(visible))
        q = q.where(m.Alert.case_id.in_(visible) | m.Alert.link_id.in_(linked))
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
