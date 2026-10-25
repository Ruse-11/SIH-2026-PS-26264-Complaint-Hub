"""Priority score (M7).  priority = severity*10 + min(corroborators,4)*5 + min(age_days,60)*0.3

Corroborators are DISTINCT reporters, other than the case's own, whose cases are linked to it by a CONFIRMED
corroboration link (directly or through a chain). A suggested link only shows "potential +X"; the boost is applied
after an officer confirms. The cap of 4 stops coordinated fake complaints from inflating priority.
"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .matching import threshold


def _components(links) -> dict:
    """Group case IDs that are connected by the given links (union-find). Returns case_id -> set of case IDs."""
    parent: dict[str, str] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for l in links:
        parent[find(l.case_a)] = find(l.case_b)
    groups: dict[str, set] = {}
    for x in list(parent):
        groups.setdefault(find(x), set()).add(x)
    return {c: g for g in groups.values() for c in g}


def _corroborators(db: Session, institution_id: str, statuses: tuple) -> dict:
    """case_id -> number of distinct OTHER reporters connected through corroboration links with these statuses."""
    ids = select(m.Case.hub_case_id).where(m.Case.institution_id == institution_id)
    links = db.scalars(select(m.LinkSuggestion).where(
        m.LinkSuggestion.link_type == "CORROBORATION", m.LinkSuggestion.status.in_(statuses),
        m.LinkSuggestion.case_a.in_(ids))).all()
    comp = _components(links)
    reporter = {c.hub_case_id: c.reporter_id for c in db.scalars(select(m.Case).where(m.Case.hub_case_id.in_(list(comp))))}
    return {cid: len({reporter[o] for o in group if o in reporter} - {reporter.get(cid)})
            for cid, group in comp.items()}


def breakdown(db: Session, case: m.Case, now: datetime | None = None, confirmed=None, with_suggested=None) -> dict:
    now = now or datetime.now()
    cap = int(threshold(db, "MAX_CORROBORATORS", 4))
    if case.institution_id:
        confirmed = confirmed if confirmed is not None else _corroborators(db, case.institution_id, ("CONFIRMED",))
        with_suggested = with_suggested if with_suggested is not None else _corroborators(db, case.institution_id, ("CONFIRMED", "SUGGESTED"))
    n_conf = (confirmed or {}).get(case.hub_case_id, 0)
    n_pot = (with_suggested or {}).get(case.hub_case_id, 0)
    age_days = max((now - case.received_at).days, 0)
    parts = {"severity": case.severity * 10, "corroboration": min(n_conf, cap) * 5, "age": round(min(age_days, 60) * 0.3, 1)}
    return {"score": round(sum(parts.values()), 1), "parts": parts, "age_days": age_days,
            "confirmed_corroborators": n_conf, "potential_boost": (min(n_pot, cap) - min(n_conf, cap)) * 5,
            "note": "Boost is applied only after an officer confirms the link."}


def recompute_institution(db: Session, institution_id: str, now: datetime | None = None) -> None:
    """Refresh priority_score for every case at one institution (the caller commits)."""
    confirmed = _corroborators(db, institution_id, ("CONFIRMED",))
    for c in db.scalars(select(m.Case).where(m.Case.institution_id == institution_id)):
        c.priority_score = breakdown(db, c, now, confirmed, {})["score"]


def recompute_case(db: Session, case: m.Case, now: datetime | None = None) -> None:
    if case.institution_id:
        recompute_institution(db, case.institution_id, now)
    else:
        case.priority_score = breakdown(db, case, now)["score"]  # unverified institution: severity + age only


def recompute_all(db: Session, now: datetime | None = None) -> int:
    inst_ids = db.scalars(select(m.Case.institution_id).where(m.Case.institution_id.is_not(None)).distinct()).all()
    for i in inst_ids:
        recompute_institution(db, i, now)
    for c in db.scalars(select(m.Case).where(m.Case.institution_id.is_(None))):
        recompute_case(db, c, now)
    return db.query(m.Case).count()
