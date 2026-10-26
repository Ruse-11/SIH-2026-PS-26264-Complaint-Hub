"""Duplicate / overlap matching (M6). The system only SUGGESTS; officers confirm or reject (M7).

All comparisons stay inside one institution. Three kinds of suggestion:
  A SAME_REPORTER  - same reporter, other portal, similar text            (similarity >= T_A)
  B CORROBORATION  - different reporters, same category, similar text     (similarity >= T_B)
  C CROSS_BUREAU   - open cases at the same institution in different bureaus (no text needed)
Every suggestion stores its reasons. A pair that already has a suggestion (any status, so also REJECTED)
is never suggested again.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import embeddings, similarity

OPEN_STATUSES = ("Pending", "Under Process", "Escalated")  # Disposed and Transferred cases are not open
OVERLAP_TITLE = "Potential Overlapping Cases – Coordination Required"


def threshold(db: Session, key: str, default: float) -> float:
    row = db.get(m.Threshold, key)
    return row.value if row else default


def _text(c: m.Case) -> str:
    return f"{c.title} {c.description}"


def _pair(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)  # a pair is stored once, smaller ID first


def _already_suggested(db: Session, a: str, b: str, link_type: str) -> bool:
    x, y = _pair(a, b)
    return db.scalar(select(m.LinkSuggestion.id).where(
        m.LinkSuggestion.case_a == x, m.LinkSuggestion.case_b == y, m.LinkSuggestion.link_type == link_type)) is not None


def _add(db: Session, a: m.Case, b: m.Case, link_type: str, score, reasons: dict) -> m.LinkSuggestion:
    x, y = _pair(a.hub_case_id, b.hub_case_id)
    s = m.LinkSuggestion(case_a=x, case_b=y, link_type=link_type, score=score, reasons=reasons, status="SUGGESTED")
    db.add(s)
    db.flush()
    return s


def suggest_lead(db: Session, cases: list[m.Case]) -> dict:
    """Which bureau should lead? Ordered rules, the rule that fired is returned. A suggestion only.
    1 category ownership table, 2 a bureau that already issued an ENFORCING action, 3 older open case, 4 refer."""
    bureaus = {c.assigned_bureau for c in cases}
    if len(bureaus) < 2:
        return {"bureau": None, "rule": "Only one bureau involved", "decided_by": "none"}
    owners = {db.get(m.CategoryOwnership, c.category).bureau for c in cases if db.get(m.CategoryOwnership, c.category)}
    if len(owners) == 1 and owners <= bureaus:
        return {"bureau": owners.pop(), "rule": "Rule 1: category ownership (assumed AICTE mandate)", "decided_by": "rules"}
    enforcing = set(db.scalars(select(m.CaseAction.bureau).where(
        m.CaseAction.case_id.in_([c.hub_case_id for c in cases]), m.CaseAction.stance == "ENFORCING")))
    if len(enforcing) == 1:
        return {"bureau": enforcing.pop(), "rule": "Rule 2: this bureau already issued an enforcing action", "decided_by": "rules"}
    # no enforcing action yet, or both bureaus enforced: tie-break on the older OPEN case
    open_cases = sorted((c for c in cases if c.status in OPEN_STATUSES), key=lambda c: c.received_at)
    if open_cases and (len(open_cases) == 1 or open_cases[0].received_at != open_cases[1].received_at):
        return {"bureau": open_cases[0].assigned_bureau, "rule": "Rule 3: the older open case leads", "decided_by": "rules"}
    return {"bureau": None, "rule": "Rule 4: no lead suggested; refer to the competent authority", "decided_by": "competent_authority"}


def detect_for_case(db: Session, case: m.Case, others: list[m.Case] | None = None, idf: dict | None = None) -> list[dict]:
    """Compare one case with the other cases of its institution. Saves new suggestions + alerts (caller commits)
    and returns the alert summaries for the intake receipt. `others` defaults to every other case there."""
    if not case.institution_id or case.status == "unverified_institution":
        return []  # nothing to compare until an officer picks the institution
    if others is None:
        others = list(db.scalars(select(m.Case).where(m.Case.institution_id == case.institution_id,
                                                       m.Case.hub_case_id != case.hub_case_id,
                                                       m.Case.status != "unverified_institution")))
    if idf is None:
        idf = similarity.build_idf([_text(c) for c in db.scalars(select(m.Case))])
    vectors = embeddings.embed_many([_text(case)] + [_text(o) for o in others])  # None -> TF-IDF only
    t_a, t_b = threshold(db, "T_A", 0.75), threshold(db, "T_B", 0.65)
    inst = db.get(m.Institution, case.institution_id)
    summaries: list[dict] = []

    # ---- A and B: text based, one pass over the other cases ----
    for o in others:
        if o.category != case.category and o.reporter_id != case.reporter_id:
            continue  # B needs the same category; A needs the same reporter
        score, shared = similarity.compare(_text(case), _text(o), idf, vectors)
        same_reporter = o.reporter_id == case.reporter_id
        if same_reporter and o.source_system != case.source_system and o.category == case.category and score >= t_a:
            kind = "SAME_REPORTER"
        elif not same_reporter and o.category == case.category and score >= t_b:
            kind = "CORROBORATION"
        else:
            continue
        if _already_suggested(db, case.hub_case_id, o.hub_case_id, kind):
            continue
        reasons = {"similarity": score, "method": "embeddings" if vectors else "tfidf", "shared_keywords": shared, "category": case.category,
                   "same_reporter": same_reporter, "portals": sorted({case.source_system, o.source_system}),
                   "institution": inst.official_name}
        s = _add(db, case, o, kind, score, reasons)
        if kind == "SAME_REPORTER":
            msg = f"Possible duplicate: the same reporter filed similar complaints on the {o.source_system} and {case.source_system} portals ({inst.official_name})."
            alert_type, severity = "DUPLICATE", "warning"
        else:
            msg = f"Possible corroboration: a different reporter describes a similar {case.category} problem at {inst.official_name}."
            alert_type, severity = "CORROBORATION", "info"
        db.add(m.Alert(type=alert_type, severity=severity, case_id=case.hub_case_id, institution_id=case.institution_id,
                       link_id=s.id, message=msg))
        summaries.append({"alert_type": alert_type, "severity": severity, "message": msg, "link_type": kind,
                          "institution": inst.official_name, "cases": [case.hub_case_id, o.hub_case_id],
                          "reasons": reasons, "suggested_lead": None, "dashboard_link": f"/overlaps?link={s.id}"})

    # ---- C: open cases in other bureaus at the same institution ----
    if case.status in OPEN_STATUSES:
        rivals = [o for o in others if o.status in OPEN_STATUSES and o.assigned_bureau != case.assigned_bureau
                  and not _already_suggested(db, case.hub_case_id, o.hub_case_id, "CROSS_BUREAU")]
        if rivals:
            involved = [case] + rivals
            lead = suggest_lead(db, involved)
            new_links = []
            for o in rivals:
                new_links.append(_add(db, case, o, "CROSS_BUREAU", None, {
                    "institution": inst.official_name,
                    "bureaus": sorted({case.assigned_bureau, o.assigned_bureau}),
                    "categories": sorted({case.category, o.category}),
                    "same_category": case.category == o.category,
                    "open_since": {c.hub_case_id: c.received_at.date().isoformat() for c in (case, o)},
                    "suggested_lead": lead}))
            bureaus = sorted({c.assigned_bureau for c in involved})
            msg = (f"{OVERLAP_TITLE}: {len(involved)} open cases at {inst.official_name} "
                   f"across {' and '.join(bureaus)}. Suggested lead: {lead['bureau'] or 'none'} ({lead['rule']}).")
            db.add(m.Alert(type="OVERLAP", severity="warning", case_id=case.hub_case_id, institution_id=case.institution_id,
                           link_id=new_links[0].id, message=msg))
            summaries.append({"alert_type": "OVERLAP", "severity": "warning", "message": msg, "link_type": "CROSS_BUREAU",
                              "institution": inst.official_name, "cases": [c.hub_case_id for c in involved],
                              "reasons": new_links[0].reasons, "suggested_lead": lead,
                              "dashboard_link": f"/overlaps?link={new_links[0].id}"})
    return summaries


def rebuild_all(db: Session) -> int:
    """Seed-time backfill: run detection for every case in date order, each against EARLIER cases only,
    exactly as if the complaints had arrived one by one. Returns the number of suggestions made."""
    cases = list(db.scalars(select(m.Case).where(m.Case.institution_id.is_not(None),
                                                 m.Case.status != "unverified_institution").order_by(m.Case.received_at, m.Case.hub_case_id)))
    idf = similarity.build_idf([_text(c) for c in db.scalars(select(m.Case))])
    embeddings.embed_many([_text(c) for c in cases])  # one batch up front; later calls hit the cache
    seen: dict[str, list[m.Case]] = {}
    for c in cases:
        detect_for_case(db, c, others=seen.get(c.institution_id, []), idf=idf)
        seen.setdefault(c.institution_id, []).append(c)
    return db.query(m.LinkSuggestion).count()


def _case_brief(c: m.Case) -> dict:
    return {"hub_case_id": c.hub_case_id, "source_case_no": c.source_case_no, "bureau": c.assigned_bureau, "status": c.status,
            "category": c.category, "title": c.title, "received_at": c.received_at.date().isoformat()}


def link_view(db: Session, link: m.LinkSuggestion) -> dict:
    a, b = db.get(m.Case, link.case_a), db.get(m.Case, link.case_b)
    inst = db.get(m.Institution, a.institution_id)
    reasons = link.reasons
    if link.link_type in ("CROSS_BUREAU", "CONFLICT", "DUPLICATE_ACTION"):
        reasons = {**(reasons or {}), "suggested_lead": suggest_lead(db, [a, b])}  # always from the latest actions
    return {"id": link.id, "link_type": link.link_type, "status": link.status, "score": link.score, "reasons": reasons,
            "institution": {"aicte_id": inst.aicte_id, "official_name": inst.official_name},
            "cases": [_case_brief(a), _case_brief(b)], "decided_by": link.decided_by,
            "decided_at": link.decided_at.isoformat() if link.decided_at else None,
            "created_at": link.created_at.isoformat(timespec="seconds")}


def list_links(db: Session, status=None, link_type=None, institution_id=None, case_id=None, limit=200, visible=None) -> list[dict]:
    """visible: set of case IDs the caller may see (None = all). A link is shown if it involves a visible case."""
    q = select(m.LinkSuggestion).order_by(m.LinkSuggestion.id.desc()).limit(limit)
    if status:
        q = q.where(m.LinkSuggestion.status == status)
    if link_type:
        q = q.where(m.LinkSuggestion.link_type == link_type)
    if visible is not None:
        q = q.where(m.LinkSuggestion.case_a.in_(visible) | m.LinkSuggestion.case_b.in_(visible))
    if case_id:
        q = q.where((m.LinkSuggestion.case_a == case_id) | (m.LinkSuggestion.case_b == case_id))
    if institution_id:
        ids = select(m.Case.hub_case_id).where(m.Case.institution_id == institution_id)
        q = q.where(m.LinkSuggestion.case_a.in_(ids))
    return [link_view(db, l) for l in db.scalars(q)]
