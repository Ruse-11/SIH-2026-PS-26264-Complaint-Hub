"""Officer decisions on link suggestions (M7). The system suggests; a human confirms or rejects.

Who may decide: roles with can_decide_links. An RB or PGRC officer only for links that involve a case of their own
bureau; the competent authority for any link. Every decision is written to the audit trail.
"""
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import auth, matching, priority
from .audit import log_event


def _cluster_on_confirm(db: Session, a: m.Case, b: m.Case, link: m.LinkSuggestion) -> int | None:
    """Confirmed corroboration puts the two cases (and anything already clustered with them) in one cluster."""
    if link.link_type != "CORROBORATION":
        return None
    ids = [x for x in (a.cluster_id, b.cluster_id) if x]
    keep = ids[0] if ids else None
    if keep is None:
        c = m.Cluster(institution_id=a.institution_id, category=a.category)
        db.add(c)
        db.flush()
        keep = c.id
    for other in set(ids) - {keep}:  # merge a second cluster into the first
        for case in db.scalars(select(m.Case).where(m.Case.cluster_id == other)):
            case.cluster_id = keep
    a.cluster_id = b.cluster_id = keep
    return keep


def decide(db: Session, user: m.User, link_id: int, decision: str, note: str | None) -> dict:
    """decision is 'CONFIRMED' or 'REJECTED'. Returns the updated link view."""
    perms = auth.permissions(user.role)
    if not perms["can_decide_links"]:
        raise HTTPException(403, f"{perms['label']} cannot confirm or reject links")
    link = db.get(m.LinkSuggestion, link_id)
    if link is None:
        raise HTTPException(404, f"No link suggestion {link_id}")
    if link.status != "SUGGESTED":
        raise HTTPException(409, f"This link was already {link.status.lower()} by {link.decided_by}")
    a, b = db.get(m.Case, link.case_a), db.get(m.Case, link.case_b)
    if user.role in ("rb_officer", "pgrc_officer") and user.bureau not in (a.assigned_bureau, b.assigned_bureau):
        raise HTTPException(403, "You can only decide links that involve a case of your own bureau")

    link.status, link.decided_by, link.decided_at = decision, user.username, datetime.now()
    link.note = (note or "").strip()[:500] or None
    cluster_id = _cluster_on_confirm(db, a, b, link) if decision == "CONFIRMED" else None
    for alert in db.scalars(select(m.Alert).where(m.Alert.link_id == link.id, m.Alert.acknowledged_by.is_(None))):
        alert.acknowledged_by, alert.acknowledged_at = user.username, datetime.now()  # the alert has been dealt with
    db.flush()  # the app's session does not autoflush: save the decision first so the priority recompute sees it
    before = {c.hub_case_id: c.priority_score for c in db.scalars(select(m.Case).where(m.Case.institution_id == a.institution_id))}
    priority.recompute_institution(db, a.institution_id)
    db.flush()
    changes = [{"hub_case_id": c.hub_case_id, "source_case_no": c.source_case_no, "before": before[c.hub_case_id],
                "after": c.priority_score}
               for c in db.scalars(select(m.Case).where(m.Case.institution_id == a.institution_id))
               if c.priority_score != before[c.hub_case_id]]
    log_event(db, actor=user.username, role=user.role, action=f"LINK_{decision}", entity_type="link_suggestion",
              entity_id=str(link.id), detail={"link_type": link.link_type, "cases": [a.hub_case_id, b.hub_case_id],
                                              "note": link.note, "cluster_id": cluster_id})
    db.commit()
    view = matching.link_view(db, link)
    view["priority_changes"] = changes  # shown to the officer as feedback ("priority 48 -> 53")
    view["cluster_id"] = cluster_id
    return view


def acknowledge_alert(db: Session, user: m.User, alert_id: int) -> dict:
    alert = db.get(m.Alert, alert_id)
    if alert is None:
        raise HTTPException(404, f"No alert {alert_id}")
    if alert.acknowledged_by is None:
        alert.acknowledged_by, alert.acknowledged_at = user.username, datetime.now()
        log_event(db, actor=user.username, role=user.role, action="ALERT_ACKNOWLEDGED", entity_type="alert",
                  entity_id=str(alert.id), detail={"type": alert.type})
        db.commit()
    return {"id": alert.id, "acknowledged_by": alert.acknowledged_by}
