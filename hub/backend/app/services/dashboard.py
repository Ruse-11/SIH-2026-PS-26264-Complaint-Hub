"""Dashboard KPIs (M8). Computed live from the database on every call, so the numbers are always current.
(For a very large database the same counts would be SQL GROUP BY queries; at prototype size Python is simpler.)"""
from collections import Counter, defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import scope
from .scope import OPEN_STATUSES

STATUS_KEYS = {"Pending": "pending", "Under Process": "under_process", "Disposed": "disposed",
               "Transferred": "transferred", "Escalated": "escalated", "unverified_institution": "unverified"}


def is_overdue(status, expected, as_of: date) -> bool:
    return status in OPEN_STATUSES and expected is not None and expected < as_of


def _status_counts(statuses) -> dict:
    c = Counter(statuses)
    return {key: c.get(name, 0) for name, key in STATUS_KEYS.items()}


def kpis(db: Session, user: m.User, as_of: date | None = None) -> dict:
    as_of = as_of or date.today()
    rows = db.execute(scope.scoped_case_query(
        user, m.Case.hub_case_id, m.Case.status, m.Case.assigned_bureau, m.Case.institution_id, m.Case.category,
        m.Case.expected_disposal_date, m.Institution.region, m.Institution.official_name)).all()
    overdue = [r for r in rows if is_overdue(r.status, r.expected_disposal_date, as_of)]
    totals = {"total": len(rows), **_status_counts(r.status for r in rows),
              "open": sum(1 for r in rows if r.status in OPEN_STATUSES), "overdue": len(overdue)}

    def group(key, label=None):
        buckets = defaultdict(list)
        for r in rows:
            buckets[getattr(r, key) or "(none)"].append(r)
        out = []
        for k, rs in buckets.items():
            item = {key: k, "total": len(rs), "open": sum(1 for r in rs if r.status in OPEN_STATUSES),
                    "overdue": sum(1 for r in rs if is_overdue(r.status, r.expected_disposal_date, as_of)),
                    "by_status": _status_counts(r.status for r in rs)}
            if label:
                item["name"] = getattr(rs[0], label)
            out.append(item)
        return out

    by_inst = sorted((i for i in group("institution_id", "official_name") if i["institution_id"] != "(none)"),
                     key=lambda i: (-i["open"], -i["total"], i["institution_id"]))
    ids = {r.hub_case_id for r in rows}
    links = db.scalars(select(m.LinkSuggestion).where(m.LinkSuggestion.status == "SUGGESTED")).all()
    visible_links = [l for l in links if l.case_a in ids or l.case_b in ids]
    link_cases = {l.id: (l.case_a, l.case_b) for l in db.scalars(select(m.LinkSuggestion))}
    alerts = [a for a in db.scalars(select(m.Alert).where(m.Alert.acknowledged_by.is_(None)))
              if a.case_id in ids or any(c in ids for c in link_cases.get(a.link_id, ()))]
    return {
        "as_of": as_of.isoformat(), "scope": scope.scope_kind(user), "totals": totals,
        "by_bureau": sorted(group("assigned_bureau"), key=lambda i: -i["open"]),
        "by_institution": by_inst[:15], "by_category": sorted(group("category"), key=lambda i: -i["total"]),
        "by_region": sorted(group("region"), key=lambda i: -i["total"]),
        "suggestions_waiting": {"total": len(visible_links),
                                "cross_bureau": sum(1 for l in visible_links if l.link_type == "CROSS_BUREAU"),
                                "same_reporter": sum(1 for l in visible_links if l.link_type == "SAME_REPORTER"),
                                "corroboration": sum(1 for l in visible_links if l.link_type == "CORROBORATION"),
                                "conflict": sum(1 for l in visible_links if l.link_type == "CONFLICT"),
                                "duplicate_action": sum(1 for l in visible_links if l.link_type == "DUPLICATE_ACTION")},
        "open_alerts": len(alerts),
    }
