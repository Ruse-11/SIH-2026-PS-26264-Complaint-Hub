"""Stalled-case (starvation) and SLA alerts (M10). Rules only, based on dates; every number is a configurable threshold.

For every OPEN case (Pending, Under Process, Escalated) at a given "as of" date:
  deadline track  ESCALATION_SUGGESTED  overdue by ESCALATION_OVERDUE_DAYS or more (suggestion to escalate; an officer decides)
                  OVERDUE               past the expected disposal date
                  DUE_SOON              expected disposal date within SLA_DUE_SOON_DAYS
  activity track  STALLED               no action for STARVATION_DAYS or more
                  PENDING_REMINDER      still "Pending" (nobody started) after PENDING_REMINDER_DAYS
  escalation      ESCALATED             case is with the competent authority
A case has at most one alert per track, so a long-overdue case does not raise a pile of alerts.
The scan is safe to repeat: it creates missing alerts, refreshes the text, and clears alerts whose reason is gone.
"""
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import scope
from .matching import threshold
from .scope import OPEN_STATUSES

TIME_TYPES = ("ESCALATION_SUGGESTED", "OVERDUE", "DUE_SOON", "STALLED", "PENDING_REMINDER", "ESCALATED")
SEVERITY = {"ESCALATION_SUGGESTED": "warning", "OVERDUE": "warning", "DUE_SOON": "info", "STALLED": "warning",
            "PENDING_REMINDER": "info", "ESCALATED": "warning"}
DEFAULTS = {"STARVATION_DAYS": 30, "SLA_DUE_SOON_DAYS": 3, "PENDING_REMINDER_DAYS": 7, "ESCALATION_OVERDUE_DAYS": 30}


def config(db: Session) -> dict:
    return {k: int(threshold(db, k, v)) for k, v in DEFAULTS.items()}


def state(case: m.Case, as_of: date, cfg: dict) -> dict:
    """Date maths for one case plus which alert types apply."""
    is_open = case.status in OPEN_STATUSES
    last = (case.last_action_at or case.received_at).date()
    idle = (as_of - last).days
    to_due = (case.expected_disposal_date - as_of).days if case.expected_disposal_date else None
    over = -to_due if to_due is not None and to_due < 0 else 0
    types = []
    if is_open:
        if to_due is not None and to_due < 0:
            types.append("ESCALATION_SUGGESTED" if over >= cfg["ESCALATION_OVERDUE_DAYS"] and case.status != "Escalated" else "OVERDUE")
        elif to_due is not None and to_due <= cfg["SLA_DUE_SOON_DAYS"]:
            types.append("DUE_SOON")
        if idle >= cfg["STARVATION_DAYS"]:
            types.append("STALLED")
        elif case.status == "Pending" and (as_of - case.received_at.date()).days >= cfg["PENDING_REMINDER_DAYS"]:
            types.append("PENDING_REMINDER")
        if case.status == "Escalated":
            types.append("ESCALATED")
    return {"open": is_open, "idle_days": idle, "days_to_due": to_due, "days_overdue": over, "types": types}


def _message(kind: str, case: m.Case, inst_name: str, st: dict, cfg: dict) -> str:
    who = f"{case.source_case_no} ({case.assigned_bureau}) at {inst_name or 'unidentified college'}"
    due = case.expected_disposal_date.isoformat() if case.expected_disposal_date else "n/a"
    return {
        "ESCALATION_SUGGESTED": f"Consider escalating: {who} is {st['days_overdue']} days past its expected disposal date ({due}). Escalation is the officer's decision.",
        "OVERDUE": f"SLA overdue: {who} is {st['days_overdue']} day(s) past its expected disposal date ({due}).",
        "DUE_SOON": f"Due soon: {who} must be disposed by {due} ({st['days_to_due']} day(s) left).",
        "STALLED": f"Stalled: {who} has had no action for {st['idle_days']} days (limit {cfg['STARVATION_DAYS']}).",
        "PENDING_REMINDER": f"Reminder: {who} is still Pending, {st['idle_days']} day(s) since the last action.",
        "ESCALATED": f"Escalated: {who} is with the competent authority and awaits a decision.",
    }[kind]


def scan(db: Session, as_of: date | None = None, case_ids=None) -> dict:
    """Create / refresh / clear the time-based alerts. The caller commits. Returns {created, cleared, active}."""
    as_of = as_of or date.today()
    cfg = config(db)
    q = select(m.Case)
    if case_ids is not None:
        q = q.where(m.Case.hub_case_id.in_(list(case_ids)))
    cases = list(db.scalars(q))
    names = {i.aicte_id: i.official_name for i in db.scalars(select(m.Institution))}
    aq = select(m.Alert).where(m.Alert.type.in_(TIME_TYPES), m.Alert.case_id.is_not(None))
    if case_ids is not None:
        aq = aq.where(m.Alert.case_id.in_(list(case_ids)))
    existing = {(a.case_id, a.type): a for a in db.scalars(aq)}
    created = cleared = active = 0
    now = datetime.now()
    for c in cases:
        st = state(c, as_of, cfg)
        for kind in st["types"]:
            text = _message(kind, c, names.get(c.institution_id), st, cfg)
            a = existing.pop((c.hub_case_id, kind), None)
            if a is None:
                db.add(m.Alert(type=kind, severity=SEVERITY[kind], case_id=c.hub_case_id, institution_id=c.institution_id, message=text))
                created += 1
            elif a.acknowledged_by is None or a.acknowledged_by == "system":
                if a.acknowledged_by == "system":  # the problem came back after being cleared
                    a.acknowledged_by = a.acknowledged_at = None
                    a.created_at = now
                    created += 1
                a.message = text  # keep the day counts current
            active += 1
        for (cid, kind), a in list(existing.items()):  # alerts of this case whose reason is gone
            if cid == c.hub_case_id and a.acknowledged_by is None:
                a.acknowledged_by, a.acknowledged_at = "system", now
                cleared += 1
    db.flush()
    return {"as_of": as_of.isoformat(), "created": created, "cleared": cleared, "active": active}


def overview(db: Session, user: m.User, as_of: date | None = None, limit: int = 20) -> dict:
    """What is stalled or due, live from the cases the user may see (not read from the alert table)."""
    as_of = as_of or date.today()
    cfg = config(db)
    rows = db.execute(scope.scoped_case_query(user, m.Case, m.Institution.official_name)).all()
    buckets: dict[str, list] = {k: [] for k in ("stalled", "overdue", "due_soon", "pending_reminder", "escalation_suggested", "escalated")}
    for c, inst_name in rows:
        st = state(c, as_of, cfg)
        item = {"hub_case_id": c.hub_case_id, "source_case_no": c.source_case_no, "institution_id": c.institution_id,
                "institution_name": inst_name, "bureau": c.assigned_bureau, "category": c.category, "status": c.status,
                "title": c.title, "idle_days": st["idle_days"], "days_overdue": st["days_overdue"],
                "days_to_due": st["days_to_due"], "expected_disposal_date": c.expected_disposal_date.isoformat() if c.expected_disposal_date else None,
                "last_action_at": c.last_action_at.date().isoformat() if c.last_action_at else None, "priority_score": c.priority_score}
        for kind, bucket in (("STALLED", "stalled"), ("OVERDUE", "overdue"), ("DUE_SOON", "due_soon"), ("PENDING_REMINDER", "pending_reminder"),
                             ("ESCALATION_SUGGESTED", "escalation_suggested"), ("ESCALATED", "escalated")):
            if kind in st["types"]:
                buckets[bucket].append(item)
        if "ESCALATION_SUGGESTED" in st["types"]:  # also counts as overdue for the "beyond timeline" lists
            buckets["overdue"].append(item)
    sort_key = {"stalled": lambda i: -i["idle_days"], "overdue": lambda i: -i["days_overdue"], "escalation_suggested": lambda i: -i["days_overdue"],
                "due_soon": lambda i: i["days_to_due"], "pending_reminder": lambda i: -i["idle_days"], "escalated": lambda i: -i["idle_days"]}
    return {"as_of": as_of.isoformat(), "thresholds": cfg,
            "counts": {k: len(v) for k, v in buckets.items()},
            **{k: sorted(v, key=sort_key[k])[:limit] for k, v in buckets.items()}}
