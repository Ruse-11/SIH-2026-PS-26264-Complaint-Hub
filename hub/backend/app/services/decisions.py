"""Officer decisions on link suggestions (M7). The system suggests; a human confirms or rejects.

Who may decide: roles with can_decide_links. An RB or PGRC officer only for links that involve a case of their own
bureau; the competent authority for any link. Every decision is written to the audit trail.
"""
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import auth, cases as case_service, matching, priority
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


# ---- officer-made links (PS 3: "enable linking/mapping of related complaints") ----
MANUAL_TYPES = ("RELATED", "CORROBORATION", "SAME_REPORTER")  # the rule-based types (overlap, conflict, duplicate action) stay system-made


def linkable_cases(db: Session, user: m.User, case_id: str) -> list[dict]:
    """Other cases at the same institution that this officer could link to this case, with any existing links shown.
    The other case may belong to another bureau (that is the point), so only brief details are returned."""
    case = case_service.get_visible_case(db, user, case_id)
    if not case.institution_id:
        return []
    out = []
    for o in db.scalars(select(m.Case).where(m.Case.institution_id == case.institution_id, m.Case.hub_case_id != case_id)
                        .order_by(m.Case.received_at.desc())):
        x, y = sorted((case_id, o.hub_case_id))
        existing = [f"{l.link_type}:{l.status}" for l in db.scalars(select(m.LinkSuggestion).where(
            m.LinkSuggestion.case_a == x, m.LinkSuggestion.case_b == y))]
        out.append({**matching._case_brief(o), "existing_links": existing})
    return out


def create_manual_link(db: Session, user: m.User, case_id: str, other_id: str, link_type: str, note: str | None) -> dict:
    """An officer links two cases at the same institution. It is the officer's own decision, so it is created already
    CONFIRMED, through the same checks and effects as confirming a suggestion (audit, cluster, priority)."""
    perms = auth.permissions(user.role)
    if not perms["can_decide_links"]:
        raise HTTPException(403, f"{perms['label']} cannot link cases")
    if link_type not in MANUAL_TYPES:
        raise HTTPException(422, "Choose a link type: " + ", ".join(MANUAL_TYPES))
    note = (note or "").strip()
    if len(note) < 5:
        raise HTTPException(422, "Say why these cases are related (at least 5 characters). It is kept in the audit trail.")
    if case_id == other_id:
        raise HTTPException(422, "Choose a different case to link to")
    case = case_service.get_visible_case(db, user, case_id)
    other = db.get(m.Case, other_id)
    if other is None:
        raise HTTPException(404, f"No case {other_id}")
    if not case.institution_id or case.institution_id != other.institution_id:
        raise HTTPException(422, "Cases can only be linked when they concern the same institution")
    if matching._already_suggested(db, case_id, other_id, link_type):
        raise HTTPException(409, "These two cases already have a link of this type (see Linked and suggested cases)")
    inst = db.get(m.Institution, case.institution_id)
    x, y = matching._pair(case_id, other_id)
    link = m.LinkSuggestion(case_a=x, case_b=y, link_type=link_type, score=None, status="SUGGESTED", reasons={
        "manual": True, "created_by": user.username, "note": note, "institution": inst.official_name, "category": case.category,
        "same_reporter": case.reporter_id == other.reporter_id})
    db.add(link)
    db.flush()
    log_event(db, actor=user.username, role=user.role, action="LINK_CREATED_MANUALLY", entity_type="link_suggestion",
              entity_id=str(link.id), detail={"link_type": link_type, "cases": [x, y], "note": note})
    return decide(db, user, link.id, "CONFIRMED", note)
