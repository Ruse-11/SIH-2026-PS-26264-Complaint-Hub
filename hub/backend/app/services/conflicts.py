"""Conflict and duplicate-action rules (M9). Rules only, no AI. The system suggests; officers confirm or reject.

Both rules compare cases at the SAME institution with the SAME category (our definition of "related"), where the
two actions were taken by DIFFERENT bureaus:
  CONFLICT          an ENFORCING action in one bureau and a CLOSING action in another within CONFLICT_WINDOW_DAYS
  DUPLICATE_ACTION  the same ENFORCING or REQUESTING action type in both bureaus within DUPLICATE_ACTION_DAYS
The stance of every action type (enforcing / requesting / closing / neutral) is a configurable table (assumption).
"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .matching import _add, _already_suggested, suggest_lead, threshold

RULE_TEXT = {
    "CONFLICT": "Conflict: one bureau took an enforcing action while another closed a related case.",
    "DUPLICATE_ACTION": "Duplicate action: two bureaus took the same kind of action on related cases.",
}


def _brief(a: m.CaseAction, case: m.Case) -> dict:
    return {"case": case.source_case_no, "hub_case_id": case.hub_case_id, "bureau": a.bureau,
            "action_type": a.action_type, "stance": a.stance, "date": a.at.date().isoformat()}


def check_pair(c1: m.Case, acts1, c2: m.Case, acts2, conflict_days: float, duplicate_days: float) -> list[tuple]:
    """Return [(link_type, reasons_without_lead)] for one pair of cases (0, 1 or 2 findings)."""
    found = []
    conflicts, duplicates = [], []
    for a in acts1:
        for b in acts2:
            if a.bureau == b.bureau:
                continue  # the rules are about two DIFFERENT bureaus
            gap = abs((a.at - b.at).days)
            enforcing, closing = (a, b) if a.stance == "ENFORCING" and b.stance == "CLOSING" else (b, a)
            if enforcing.stance == "ENFORCING" and closing.stance == "CLOSING" and gap <= conflict_days:
                conflicts.append({"gap_days": gap, "enforcing": _brief(enforcing, c1 if enforcing is a else c2),
                                  "closing": _brief(closing, c1 if closing is a else c2)})
            if a.stance in ("ENFORCING", "REQUESTING") and a.action_type == b.action_type and gap <= duplicate_days:
                duplicates.append({"gap_days": gap, "first": _brief(a, c1), "second": _brief(b, c2)})
    if conflicts:
        found.append(("CONFLICT", {"rule": RULE_TEXT["CONFLICT"], "window_days": conflict_days,
                                   "matches": sorted(conflicts, key=lambda x: x["gap_days"])[:3]}))
    if duplicates:
        found.append(("DUPLICATE_ACTION", {"rule": RULE_TEXT["DUPLICATE_ACTION"], "window_days": duplicate_days,
                                           "matches": sorted(duplicates, key=lambda x: x["gap_days"])[:3]}))
    return found


def _actions_by_case(db: Session, ids) -> dict:
    out: dict[str, list] = {}
    for a in db.scalars(select(m.CaseAction).where(m.CaseAction.case_id.in_(list(ids))).order_by(m.CaseAction.at)):
        out.setdefault(a.case_id, []).append(a)
    return out


def _raise(db: Session, c1: m.Case, c2: m.Case, link_type: str, reasons: dict, inst: m.Institution) -> dict:
    lead = suggest_lead(db, [c1, c2])
    reasons = {**reasons, "institution": inst.official_name, "category": c1.category,
               "bureaus": sorted({c1.assigned_bureau, c2.assigned_bureau}), "suggested_lead": lead}
    link = _add(db, c1, c2, link_type, None, reasons)
    if link_type == "CONFLICT":
        top = reasons["matches"][0]
        msg = (f"Conflicting actions at {inst.official_name}: {top['enforcing']['bureau']} took '{top['enforcing']['action_type']}' "
               f"while {top['closing']['bureau']} took '{top['closing']['action_type']}' ({c1.category}). "
               f"Suggested lead: {lead['bureau'] or 'none'} ({lead['rule']}). The competent authority decides if bureaus disagree.")
        alert_type, severity = "CONFLICT", "critical"
    else:
        top = reasons["matches"][0]
        msg = (f"Possible duplicate action at {inst.official_name}: {top['first']['bureau']} and {top['second']['bureau']} both took "
               f"'{top['first']['action_type']}' within {top['gap_days']} day(s) ({c1.category}). "
               f"Suggested lead: {lead['bureau'] or 'none'} ({lead['rule']}).")
        alert_type, severity = "DUPLICATE_ACTION", "warning"
    db.add(m.Alert(type=alert_type, severity=severity, case_id=c1.hub_case_id, institution_id=c1.institution_id,
                   link_id=link.id, message=msg))
    return {"alert_type": alert_type, "severity": severity, "message": msg, "link_type": link_type,
            "institution": inst.official_name, "cases": [c1.hub_case_id, c2.hub_case_id], "reasons": reasons,
            "suggested_lead": lead, "dashboard_link": f"/overlaps?link={link.id}"}


def detect_for_case(db: Session, case: m.Case) -> list[dict]:
    """Check one case (after a new action) against the other cases of its institution and category."""
    if not case.institution_id or case.status == "unverified_institution":
        return []
    others = list(db.scalars(select(m.Case).where(
        m.Case.institution_id == case.institution_id, m.Case.category == case.category,
        m.Case.hub_case_id != case.hub_case_id, m.Case.status != "unverified_institution")))
    return _detect(db, [(case, o) for o in others])


def _detect(db: Session, pairs) -> list[dict]:
    if not pairs:
        return []
    conflict_days = threshold(db, "CONFLICT_WINDOW_DAYS", 30)
    duplicate_days = threshold(db, "DUPLICATE_ACTION_DAYS", 10)
    acts = _actions_by_case(db, {c.hub_case_id for p in pairs for c in p})
    out = []
    for c1, c2 in pairs:
        for link_type, reasons in check_pair(c1, acts.get(c1.hub_case_id, []), c2, acts.get(c2.hub_case_id, []),
                                             conflict_days, duplicate_days):
            if _already_suggested(db, c1.hub_case_id, c2.hub_case_id, link_type):
                continue  # includes rejected pairs: never suggested again
            out.append(_raise(db, c1, c2, link_type, reasons, db.get(m.Institution, c1.institution_id)))
    return out


def rebuild_all(db: Session) -> int:
    """Seed-time backfill over every pair of cases at the same institution and category."""
    cases = list(db.scalars(select(m.Case).where(m.Case.institution_id.is_not(None),
                                                 m.Case.status != "unverified_institution").order_by(m.Case.hub_case_id)))
    groups: dict[tuple, list] = {}
    for c in cases:
        groups.setdefault((c.institution_id, c.category), []).append(c)
    pairs = [(a, b) for g in groups.values() for i, a in enumerate(g) for b in g[i + 1:]]
    return len(_detect(db, pairs))


LEAD_BUREAUS = ("RB", "PGRC")  # bureaus that can lead in this prototype's data


def decide_lead(db: Session, user: m.User, link_id: int, bureau: str, note: str | None) -> dict:
    """The competent authority records the final lead bureau for an overlap, conflict or duplicate action.
    The system's suggestion stays visible next to it; this is the human decision."""
    from fastapi import HTTPException  # local import keeps the service importable without FastAPI in unit use
    from . import auth, matching
    from .audit import log_event
    if not auth.permissions(user.role)["can_decide_lead"]:
        raise HTTPException(403, "Only the competent authority can decide the lead bureau")
    link = db.get(m.LinkSuggestion, link_id)
    if link is None or link.link_type not in ("CROSS_BUREAU", "CONFLICT", "DUPLICATE_ACTION"):
        raise HTTPException(404, f"No overlap, conflict or duplicate-action suggestion {link_id}")
    if bureau not in LEAD_BUREAUS:
        raise HTTPException(422, f"Lead bureau must be one of {', '.join(LEAD_BUREAUS)}")
    final = {"bureau": bureau, "decided_by": user.username, "decided_at": datetime.now().isoformat(timespec="seconds"),
             "note": (note or "").strip()[:500] or None}
    link.reasons = {**(link.reasons or {}), "final_lead": final}  # new dict so SQLAlchemy notices the JSON change
    log_event(db, actor=user.username, role=user.role, action="LEAD_BUREAU_DECIDED", entity_type="link_suggestion",
              entity_id=str(link.id), detail={"bureau": bureau, "note": final["note"],
                                              "suggested": (link.reasons.get("suggested_lead") or {}).get("bureau")})
    db.commit()
    return matching.link_view(db, link)
