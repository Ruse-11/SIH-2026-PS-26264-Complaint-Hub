"""Cases, actions and case history (M4: one case with its history; list, search and filters come in M8)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m


def case_detail(db: Session, hub_case_id: str):
    case = db.get(m.Case, hub_case_id)
    if case is None:
        return None
    inst = db.get(m.Institution, case.institution_id) if case.institution_id else None
    reporter = db.get(m.Reporter, case.reporter_id) if case.reporter_id else None
    actions = db.scalars(select(m.CaseAction).where(m.CaseAction.case_id == hub_case_id)
                         .order_by(m.CaseAction.at, m.CaseAction.seq)).all()
    iso = lambda d: d.isoformat() if d else None  # noqa: E731
    return {
        "hub_case_id": case.hub_case_id, "source_system": case.source_system, "source_case_no": case.source_case_no,
        "institution": {"aicte_id": inst.aicte_id, "official_name": inst.official_name, "district": inst.district,
                        "state": inst.state, "region": inst.region} if inst else None,
        "resolution_method": case.resolution_method, "finder_answers": case.finder_answers,
        "reporter_id": case.reporter_id, "reporter_type": reporter.reporter_type if reporter else None,
        "category": case.category, "title": case.title, "description": case.description,
        "received_at": iso(case.received_at), "status": case.status, "assigned_bureau": case.assigned_bureau,
        "assigned_officer": case.assigned_officer, "severity": case.severity, "priority_score": case.priority_score,
        "expected_disposal_date": iso(case.expected_disposal_date), "last_action_at": iso(case.last_action_at),
        "last_action": actions[-1].action_type if actions else None,
        "actions": [{"seq": a.seq, "action_type": a.action_type, "stance": a.stance, "actor": a.actor,
                     "bureau": a.bureau, "remarks": a.remarks, "doc_ref": a.doc_ref, "at": iso(a.at),
                     "from_bureau": a.from_bureau, "to_bureau": a.to_bureau} for a in actions],
    }
