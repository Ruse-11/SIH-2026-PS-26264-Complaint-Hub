"""Complaint intake (M4): the portals call this; the hub validates, stores and acknowledges.

The hub NEVER guesses an institution. It only checks that the confirmed ID exists in the registry.
A complaint without an institution is stored as 'unverified_institution' for the Needs Review queue.
"""
import hmac
from datetime import date, datetime, timedelta

from fastapi import Header, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import config
from .. import models as m
from .audit import log_event
from . import matching, priority
from .reporters import make_fingerprint

FIRST_ACTION = "Acknowledged"


def portal_from_api_key(x_api_key: str | None = Header(default=None)) -> str:
    """FastAPI dependency: which portal is calling? One secret key per portal. Returns 'RB' or 'PGRC'."""
    for portal, key in config.PORTAL_API_KEYS.items():
        if x_api_key and hmac.compare_digest(x_api_key, key):  # constant-time compare
            return portal
    raise HTTPException(status_code=401, detail="Missing or wrong X-API-Key")


def _next_number(db: Session, column, prefix: str) -> int:
    """Highest existing number in an ID like HUB-0150 / REP-0080, plus one."""
    last = db.scalar(select(func.max(column)).where(column.like(prefix + "%")))
    return int(last.split("-")[1]) + 1 if last else 1


def _receipt(db: Session, case: m.Case, already_received=False, reporter_is_new=False, alerts=None) -> dict:
    inst = db.get(m.Institution, case.institution_id) if case.institution_id else None
    return {
        "hub_case_id": case.hub_case_id, "source_case_no": case.source_case_no, "status": case.status,
        "assigned_bureau": case.assigned_bureau, "resolution_method": case.resolution_method,
        "institution": {"aicte_id": inst.aicte_id, "official_name": inst.official_name} if inst else None,
        "received_at": case.received_at.isoformat(timespec="seconds"),
        "expected_disposal_date": case.expected_disposal_date.isoformat() if case.expected_disposal_date else None,
        "already_received": already_received, "reporter_is_new": reporter_is_new,
        "alerts_created": alerts or [],  # overlap / duplicate / corroboration suggestions made by this complaint
    }


def receive_complaint(db: Session, portal: str, data) -> tuple[dict, bool]:
    """Store one complaint. Returns (receipt, created). Sending the same portal case number again is safe:
    the portals retry after a failure (outbox), so the second call returns the first case unchanged."""
    existing = db.scalars(select(m.Case).where(m.Case.source_system == portal,
                                               m.Case.source_case_no == data.source_case_no)).first()
    if existing:
        return _receipt(db, existing, already_received=True), False

    # 1. Institution: must exist, and must be a college (a parent university is not one).
    institution_id = data.verified_institution_id
    if institution_id:
        inst = db.get(m.Institution, institution_id)
        if inst is None:
            raise HTTPException(422, f"Unknown institution ID {institution_id}. The hub does not guess institutions.")
        has_children = db.scalar(select(func.count()).select_from(m.Institution)
                                 .where(m.Institution.parent_id == institution_id))
        if has_children:
            raise HTTPException(422, f"{institution_id} is a parent university. Choose one of its constituent colleges.")
        resolution = data.resolution_method if data.resolution_method != "UNLISTED" else "REPORTER_CONFIRMED"
        status = "Pending"
    else:
        resolution, status = "UNLISTED", "unverified_institution"  # an officer picks the college later

    # 2. Category must be one the hub knows.
    if db.get(m.CategoryOwnership, data.category) is None:
        raise HTTPException(422, f"Unknown category '{data.category}'.")

    # 3. Reporter: hash the verified contact, keep only the hash. Same person on both portals -> same reporter.
    fingerprint = make_fingerprint(data.reporter.contact)
    reporter = db.scalars(select(m.Reporter).where(m.Reporter.fingerprint_hash == fingerprint)).first()
    reporter_is_new = reporter is None
    if reporter_is_new:
        reporter = m.Reporter(id=f"REP-{_next_number(db, m.Reporter.id, 'REP-'):04d}", fingerprint_hash=fingerprint,
                              reporter_type=data.reporter.reporter_type,
                              validation_method=data.reporter.validation_method, validated_at=datetime.now())
        db.add(reporter)

    # 4. The case, due date from the bureau's SLA, and the first history entry.
    now = datetime.now()
    sla_days = db.scalar(select(m.SlaPolicy.days).where(m.SlaPolicy.bureau == portal, m.SlaPolicy.category.is_(None)))
    case = m.Case(
        hub_case_id=f"HUB-{_next_number(db, m.Case.hub_case_id, 'HUB-'):04d}", source_system=portal,
        source_case_no=data.source_case_no, institution_id=institution_id, resolution_method=resolution,
        finder_answers=data.finder_answers, reporter_id=reporter.id, category=data.category, title=data.title,
        description=data.description, received_at=now, status=status, assigned_bureau=portal,
        assigned_officer=None, severity=data.severity, last_action_at=now,
        expected_disposal_date=date.today() + timedelta(days=sla_days) if sla_days else None)
    db.add(case)
    db.flush()  # the case row must exist before the action that points to it
    db.add(m.CaseAction(case_id=case.hub_case_id, seq=1, action_type=FIRST_ACTION, stance="NEUTRAL",
                        actor=f"System ({portal} portal intake)", bureau=portal, at=now,
                        remarks=f"Complaint received through the {portal} portal."))
    log_event(db, actor=f"portal:{portal}", action="CASE_RECEIVED", entity_type="case", entity_id=case.hub_case_id,
              detail={"source_case_no": data.source_case_no, "institution_id": institution_id,
                      "resolution_method": resolution})
    priority.recompute_case(db, case)
    alerts = matching.detect_for_case(db, case)  # M6: suggestions + alerts, officers decide later
    db.commit()
    return _receipt(db, case, reporter_is_new=reporter_is_new, alerts=alerts), True
