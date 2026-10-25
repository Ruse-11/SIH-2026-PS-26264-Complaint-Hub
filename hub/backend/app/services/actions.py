"""Officers log actions on a case in the hub (M9). In production the bureau systems would call POST /api/actions.
Logging an action updates the case status and last action, writes the audit trail and re-checks for conflicts."""
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from . import cases as case_service, conflicts, priority
from .audit import log_event
from .auth import permissions

TRANSFER, ESCALATE = "Transferred", "Escalated to Competent Authority"
BUREAUS = ("RB", "PGRC")


def allowed_action_types(db: Session, user: m.User) -> list[dict]:
    """The action types this role may log (shown in the form; also enforced when saving)."""
    perms = permissions(user.role)
    rows = db.scalars(select(m.ActionTypeStance).order_by(m.ActionTypeStance.stance, m.ActionTypeStance.action_type)).all()
    out = []
    for r in rows:
        if r.action_type == "Acknowledged":
            continue  # written by the system when the complaint arrives
        if perms["can_log_actions"]:
            ok = (r.action_type != TRANSFER or perms["can_transfer"]) and (r.action_type != ESCALATE or perms["can_escalate"])
        else:
            ok = perms["can_escalate"] and r.action_type == ESCALATE
        if ok:
            out.append({"action_type": r.action_type, "stance": r.stance})
    return out


def log_action(db: Session, user: m.User, hub_case_id: str, action_type: str, remarks: str | None,
               doc_ref: str | None, to_bureau: str | None) -> dict:
    case = case_service.get_visible_case(db, user, hub_case_id)
    allowed = {a["action_type"] for a in allowed_action_types(db, user)}
    if action_type not in allowed:
        raise HTTPException(403, f"{permissions(user.role)['label']} cannot log '{action_type}'")
    if case.status in ("Disposed", "unverified_institution"):
        raise HTTPException(409, "This case is " + ("disposed" if case.status == "Disposed" else "waiting for a college to be assigned")
                            + ", so no further action can be logged")
    stance = db.get(m.ActionTypeStance, action_type).stance
    bureau = user.bureau if user.bureau in BUREAUS else case.assigned_bureau
    from_b = None
    if action_type == TRANSFER:
        if to_bureau not in BUREAUS or to_bureau == case.assigned_bureau:
            raise HTTPException(422, "Choose the other bureau to transfer to")
        from_b = case.assigned_bureau
        case.assigned_bureau = to_bureau
    now = datetime.now()
    seq = (db.scalar(select(func.max(m.CaseAction.seq)).where(m.CaseAction.case_id == hub_case_id)) or 0) + 1
    db.add(m.CaseAction(case_id=hub_case_id, seq=seq, action_type=action_type, stance=stance, actor=user.display_name,
                        bureau=bureau, remarks=(remarks or "").strip()[:500] or None,
                        doc_ref=(doc_ref or "").strip()[:200] or None, at=now, from_bureau=from_b,
                        to_bureau=to_bureau if action_type == TRANSFER else None))
    if action_type == TRANSFER:
        case.status = "Transferred"
    elif action_type == ESCALATE:
        case.status = "Escalated"
    elif stance == "CLOSING":
        case.status = "Disposed"
    elif case.status == "Pending":
        case.status = "Under Process"
    case.last_action_at = now
    log_event(db, actor=user.username, role=user.role, action="ACTION_LOGGED", entity_type="case", entity_id=hub_case_id,
              detail={"action_type": action_type, "stance": stance, "seq": seq, "to_bureau": to_bureau})
    db.flush()  # the session does not autoflush: save the action before the conflict check reads it
    alerts = conflicts.detect_for_case(db, case)
    priority.recompute_case(db, case)
    db.commit()
    return {"hub_case_id": hub_case_id, "seq": seq, "action_type": action_type, "stance": stance, "status": case.status,
            "assigned_bureau": case.assigned_bureau, "alerts_created": alerts}
