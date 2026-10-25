"""Cases, actions and case history (M4: one case with its history; list, search and filters come in M8)."""
from datetime import date, datetime, time

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import models as m
from . import dashboard, matching, priority, scope
from .audit import log_event
from .institutions import normalize_name


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
        "last_action": actions[-1].action_type if actions else None, "cluster_id": case.cluster_id,
        "priority": priority.breakdown(db, case),
        "links": matching.list_links(db, case_id=hub_case_id),
        "actions": [{"seq": a.seq, "action_type": a.action_type, "stance": a.stance, "actor": a.actor,
                     "bureau": a.bureau, "remarks": a.remarks, "doc_ref": a.doc_ref, "at": iso(a.at),
                     "from_bureau": a.from_bureau, "to_bureau": a.to_bureau} for a in actions],
    }


def _institution_ids_for_name(db: Session, q: str) -> set:
    """Institutions whose name or alias contains the typed text (so 'CEG' finds the right college too)."""
    n = normalize_name(q)
    if not n:
        return set()
    like = f"%{n}%"
    ids = set(db.scalars(select(m.Institution.aicte_id).where(m.Institution.name_normalized.like(like))))
    ids |= set(db.scalars(select(m.InstitutionAlias.institution_id).where(m.InstitutionAlias.alias_normalized.like(like))))
    return _with_children(db, ids)


def _with_children(db: Session, ids: set) -> set:
    """A university stands for its constituent colleges too: searching it also finds their cases."""
    if not ids:
        return ids
    return ids | set(db.scalars(select(m.Institution.aicte_id).where(m.Institution.parent_id.in_(list(ids)))))


def list_cases(db: Session, user: m.User, q=None, bureau=None, region=None, category=None, status=None,
               institution_id=None, date_from: date | None = None, date_to: date | None = None, overdue=False,
               sort="priority", page=1, page_size=25, as_of: date | None = None) -> dict:
    """Case list with search (institution name, AICTE ID, case ID) and filters, limited to the user's scope."""
    as_of = as_of or date.today()
    stmt = scope.scoped_case_query(user, m.Case, m.Institution.official_name, m.Institution.region)
    if q and q.strip():
        t = q.strip()
        conds = [m.Case.hub_case_id.ilike(f"%{t}%"), m.Case.source_case_no.ilike(f"%{t}%"),
                 m.Case.institution_id.ilike(f"%{t}%"), m.Case.title.ilike(f"%{t}%")]
        ids = _institution_ids_for_name(db, t)
        if ids:
            conds.append(m.Case.institution_id.in_(ids))
        stmt = stmt.where(or_(*conds))
    if institution_id:
        stmt = stmt.where(m.Case.institution_id.in_(_with_children(db, {institution_id})))  # a university includes its colleges
    for column, value in ((m.Case.assigned_bureau, bureau), (m.Institution.region, region), (m.Case.category, category),
                          (m.Case.status, status)):
        if value:
            stmt = stmt.where(column == value)
    if date_from:
        stmt = stmt.where(m.Case.received_at >= datetime.combine(date_from, time.min))
    if date_to:
        stmt = stmt.where(m.Case.received_at <= datetime.combine(date_to, time.max))
    if overdue:
        stmt = stmt.where(m.Case.status.in_(scope.OPEN_STATUSES), m.Case.expected_disposal_date < as_of)
    order = {"priority": m.Case.priority_score.desc(), "received": m.Case.received_at.desc(),
             "last_action": m.Case.last_action_at.desc(), "oldest": m.Case.received_at.asc()}.get(sort, m.Case.priority_score.desc())
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    page_size = min(max(page_size, 1), 100)
    rows = db.execute(stmt.order_by(order, m.Case.hub_case_id).limit(page_size).offset((max(page, 1) - 1) * page_size)).all()
    ids = [r[0].hub_case_id for r in rows]
    last = {}  # latest action per case on this page
    for a in db.scalars(select(m.CaseAction).where(m.CaseAction.case_id.in_(ids)).order_by(m.CaseAction.at, m.CaseAction.seq)):
        last[a.case_id] = a
    open_links = {}
    for l in db.scalars(select(m.LinkSuggestion).where(m.LinkSuggestion.status == "SUGGESTED",
                                                       (m.LinkSuggestion.case_a.in_(ids)) | (m.LinkSuggestion.case_b.in_(ids)))):
        for cid in (l.case_a, l.case_b):
            open_links[cid] = open_links.get(cid, 0) + 1
    items = []
    for c, inst_name, inst_region in rows:
        a = last.get(c.hub_case_id)
        items.append({
            "hub_case_id": c.hub_case_id, "source_case_no": c.source_case_no, "institution_id": c.institution_id,
            "institution_name": inst_name, "region": inst_region, "category": c.category, "title": c.title,
            "status": c.status, "assigned_bureau": c.assigned_bureau, "assigned_officer": c.assigned_officer,
            "received_at": c.received_at.date().isoformat(), "last_action": a.action_type if a else None,
            "last_action_at": c.last_action_at.date().isoformat() if c.last_action_at else None,
            "expected_disposal_date": c.expected_disposal_date.isoformat() if c.expected_disposal_date else None,
            "overdue": dashboard.is_overdue(c.status, c.expected_disposal_date, as_of),
            "priority_score": c.priority_score, "cluster_id": c.cluster_id, "suggestions_waiting": open_links.get(c.hub_case_id, 0)})
    return {"total": total, "page": page, "page_size": page_size, "items": items}


def filter_options(db: Session, user: m.User) -> dict:
    """Values for the filter dropdowns (only what the user can see)."""
    rows = db.execute(scope.scoped_case_query(user, m.Case.assigned_bureau, m.Institution.region, m.Case.category, m.Case.status)).all()
    pick = lambda i: sorted({r[i] for r in rows if r[i]})  # noqa: E731
    return {"bureaus": pick(0), "regions": pick(1), "categories": pick(2), "statuses": pick(3),
            "sorts": ["priority", "received", "oldest", "last_action"]}


def get_visible_case(db: Session, user: m.User, hub_case_id: str) -> m.Case:
    case = db.get(m.Case, hub_case_id)
    if case is None:
        raise HTTPException(404, f"No case {hub_case_id}")
    if not scope.can_see_case(db, user, case):
        raise HTTPException(403, "This case is outside your view")  # e.g. an RB officer opening a PGRC-only case
    return case


def needs_review(db: Session, user: m.User) -> list[dict]:
    """Cases whose college the reporter could not identify, waiting for an officer to pick one."""
    rows = db.scalars(scope.scoped_case_query(user, m.Case).where(m.Case.status == "unverified_institution")
                      .order_by(m.Case.received_at)).all()
    return [{"hub_case_id": c.hub_case_id, "source_case_no": c.source_case_no, "assigned_bureau": c.assigned_bureau,
             "category": c.category, "title": c.title, "description": c.description,
             "received_at": c.received_at.date().isoformat(), "typed_details": c.finder_answers} for c in rows]


def assign_institution(db: Session, user: m.User, hub_case_id: str, institution_id: str) -> dict:
    """An officer picks the college for an unverified case. The typed name is saved as a learned alias."""
    if user.role not in ("rb_officer", "pgrc_officer", "competent_authority"):
        raise HTTPException(403, "Only bureau officers and the competent authority can assign a college")
    case = get_visible_case(db, user, hub_case_id)
    if case.status != "unverified_institution":
        raise HTTPException(409, "This case already has a verified institution")
    inst = db.get(m.Institution, institution_id)
    if inst is None:
        raise HTTPException(422, f"Unknown institution ID {institution_id}")
    if db.scalar(select(func.count()).select_from(m.Institution).where(m.Institution.parent_id == institution_id)):
        raise HTTPException(422, f"{institution_id} is a parent university. Choose one of its constituent colleges.")
    case.institution_id, case.status, case.resolution_method = institution_id, "Pending", "OFFICER_ASSIGNED"
    typed = ((case.finder_answers or {}).get("typed_name") or "").strip()
    learned = None
    if typed and normalize_name(typed):
        n = normalize_name(typed)
        taken = db.scalar(select(m.InstitutionAlias.id).where(m.InstitutionAlias.alias_normalized == n,
                                                              m.InstitutionAlias.institution_id == institution_id))
        if taken is None:
            db.add(m.InstitutionAlias(alias=typed, alias_normalized=n, institution_id=institution_id,
                                      alias_type="LEARNED", source="learned"))
            learned = typed
    log_event(db, actor=user.username, role=user.role, action="INSTITUTION_ASSIGNED", entity_type="case",
              entity_id=hub_case_id, detail={"institution_id": institution_id, "learned_alias": learned})
    db.flush()
    alerts = matching.detect_for_case(db, case)  # now that the college is known, look for overlaps
    priority.recompute_case(db, case)
    db.commit()
    return {"hub_case_id": hub_case_id, "institution_id": institution_id, "status": case.status,
            "learned_alias": learned, "alerts_created": alerts}
