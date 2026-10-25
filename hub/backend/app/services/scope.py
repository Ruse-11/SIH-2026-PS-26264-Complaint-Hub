"""Who sees which cases (CLAUDE.md section 12). One place, used by every list, KPI and detail screen.

RB / PGRC / other bureau officers: cases assigned to their bureau. Regional office: cases at colleges in their region.
Senior management and competent authority: everything.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .auth import permissions

OPEN_STATUSES = ("Pending", "Under Process", "Escalated")


def scope_kind(user: m.User) -> str:
    return permissions(user.role)["view_scope"]


def scoped_case_query(user: m.User, *columns):
    """SELECT over cases (+ institution, outer join because unverified cases have none) limited to what `user` may see."""
    q = select(*(columns or (m.Case,))).select_from(m.Case).outerjoin(
        m.Institution, m.Institution.aicte_id == m.Case.institution_id)
    kind = scope_kind(user)
    if kind in ("bureau", "assigned"):
        q = q.where(m.Case.assigned_bureau == user.bureau)
    elif kind == "region":
        q = q.where(m.Institution.region == user.region)
    return q


def can_see_case(db: Session, user: m.User, case: m.Case) -> bool:
    kind = scope_kind(user)
    if kind == "all":
        return True
    if kind in ("bureau", "assigned"):
        return case.assigned_bureau == user.bureau
    inst = db.get(m.Institution, case.institution_id) if case.institution_id else None
    return bool(inst and inst.region == user.region)


def visible_case_ids(db: Session, user: m.User) -> set | None:
    """Set of case IDs the user may see, or None when they may see all (callers skip filtering)."""
    if scope_kind(user) == "all":
        return None
    return set(db.scalars(scoped_case_query(user, m.Case.hub_case_id)))
