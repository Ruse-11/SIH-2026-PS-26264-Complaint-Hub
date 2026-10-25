"""Loads data/*.csv into the hub database.

Run from hub/backend:   python -m app.seed
It DELETES and recreates every table, so running it twice gives the same clean result.
"""
import csv
import json
from datetime import date, datetime, time

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from . import config
from .db import Base, engine as default_engine
from . import models as m
from .services.auth import DEMO_PASSWORD, hash_password
from .services.institutions import normalize_name
from .services.reporters import make_fingerprint
from .services import conflicts, matching, priority, starvation

# ---- Config tables. These are ASSUMPTIONS about AICTE rules (labelled so in the PPT) and can be edited in the DB. ----
STANCES = {
    "Show-Cause Notice Issued": "ENFORCING", "Inspection Ordered": "ENFORCING", "Penalty Proposed": "ENFORCING",
    "Documents Sought": "REQUESTING", "Reply Sought from Institution": "REQUESTING",
    "Closed - No Action": "CLOSING", "Disposed - Unsubstantiated": "CLOSING", "Disposed - Action Taken": "CLOSING",
    "Acknowledged": "NEUTRAL", "Under Review": "NEUTRAL", "Transferred": "NEUTRAL",
    "Escalated to Competent Authority": "NEUTRAL",
}
CATEGORY_OWNER = {  # which bureau normally leads a category: regulatory -> RB, individual grievances -> PGRC
    "Approval/Affiliation": "RB", "Faculty Shortage/Qualification": "RB", "Infrastructure/Lab": "RB",
    "Admission Irregularity": "RB", "Placement Misrepresentation": "RB",
    "Misleading Advertisement/Accreditation Claim": "RB",
    "Fee/Refund": "PGRC", "Ragging/Harassment": "PGRC", "Exam/Result": "PGRC", "Hostel/Mess": "PGRC",
    "Scholarship": "PGRC",
}
SLA_DAYS = {"PGRC": 30, "RB": 45}  # default days to dispose, per bureau
THRESHOLDS = [  # key, value, description
    ("T_A", 0.20, "same-reporter duplicate: minimum text similarity (low, because reporter, institution and category already match)"),
    ("T_B", 0.35, "corroboration: minimum text similarity (TF-IDF baseline; raise after the M12 embeddings upgrade)"),
    ("CONFLICT_WINDOW_DAYS", 30, "enforcing vs closing action in different bureaus within N days = conflict"),
    ("DUPLICATE_ACTION_DAYS", 10, "same kind of action by two bureaus within N days = duplicate action"),
    ("STARVATION_DAYS", 30, "open case with no action for N days = stalled"),
    ("SLA_DUE_SOON_DAYS", 3, "open case due within N days = 'due soon' alert"),
    ("PENDING_REMINDER_DAYS", 7, "case still Pending (nobody started) after N days = reminder"),
    ("ESCALATION_OVERDUE_DAYS", 30, "open case overdue by N days or more = suggest escalating"),
    ("MAX_CORROBORATORS", 4, "cap on distinct reporters counted in the priority boost"),
]


def read_csv(name):
    """Read one CSV from data/ as a list of dicts (utf-8-sig drops a BOM if Excel added one)."""
    with open(config.DATA_DIR / name, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def at_time(day: str, hour: int) -> datetime:
    return datetime.combine(date.fromisoformat(day), time(hour, 0))


DEMO_USERS = [  # username, role, display name, bureau, region. One account per target user of the PS.
    ("rb.officer", "rb_officer", "Officer RB-01", "RB", None),
    ("pgrc.officer", "pgrc_officer", "Officer PGRC-01", "PGRC", None),
    ("other.bureau", "other_bureau", "Officer OB-01 (Other bureau)", "OTHER", None),
    ("regional.south", "regional_office", "Regional Office, South", None, "South"),
    ("senior.mgmt", "senior_management", "Senior Management", None, None),
    ("competent.authority", "competent_authority", "Competent Authority", None, None),
]


def load_users(db: Session):
    db.add_all(m.User(username=u, password_hash=hash_password(DEMO_PASSWORD), role=r, display_name=n,
                      bureau=b, region=g) for u, r, n, b, g in DEMO_USERS)
    return len(DEMO_USERS)


def load_config(db: Session):
    db.add_all(m.ActionTypeStance(action_type=a, stance=s) for a, s in STANCES.items())
    db.add_all(m.CategoryOwnership(category=c, bureau=b) for c, b in CATEGORY_OWNER.items())
    db.add_all(m.SlaPolicy(bureau=b, category=None, days=d) for b, d in SLA_DAYS.items())
    db.add_all(m.Threshold(key=k, value=v, description=d) for k, v, d in THRESHOLDS)


def load_institutions(db: Session):
    rows = read_csv("institutions.csv")
    for r in rows:  # parents first is not needed: SQLite checks foreign keys only if asked
        db.add(m.Institution(
            aicte_id=r["institution_id"], official_name=r["official_name"],
            name_normalized=normalize_name(r["official_name"]), parent_id=r["parent_id"] or None,
            address_line=r["address_line"], area=r["area"], district=r["district"], state=r["state"],
            pincode=r["pincode"] or None, region=r["region"], type=r["institution_type"],
            lat=float(r["lat"]), lng=float(r["lng"]), programs=r["programs"],
            established_year=int(r["established_year"]) if r["established_year"] else None))
    return len(rows)


def load_aliases(db: Session):
    seen = set()
    for r in read_csv("institution_aliases.csv"):
        key = (normalize_name(r["alias"]), r["institution_id"])
        if key in seen or not key[0]:  # two spellings that normalize the same are one alias
            continue
        seen.add(key)
        db.add(m.InstitutionAlias(alias=r["alias"], alias_normalized=key[0], institution_id=key[1],
                                  alias_type=r["alias_type"], source="curated"))
    return len(seen)


def load_reporters(db: Session):
    rows = read_csv("reporters.csv")
    for r in rows:  # only the hash is kept: name, email and phone are dropped on purpose
        db.add(m.Reporter(id=r["reporter_id"], fingerprint_hash=make_fingerprint(r["phone"]),
                          reporter_type=r["reporter_type"], validation_method="SEED",
                          validated_at=datetime(2026, 4, 1)))
    return len(rows)


def load_cases_and_actions(db: Session):
    actions_by_case = {}
    for a in read_csv("actions.csv"):
        actions_by_case.setdefault(a["source_case_no"], []).append(a)

    n_actions = 0
    for i, c in enumerate(read_csv("cases.csv"), start=1):
        hub_id = f"HUB-{i:04d}"
        acts = sorted(actions_by_case.get(c["source_case_no"], []), key=lambda a: int(a["action_seq"]))
        unverified = not c["institution_id"]  # S13 / S16: reporter could not pick a college
        db.add(m.Case(
            hub_case_id=hub_id, source_system=c["source_system"], source_case_no=c["source_case_no"],
            institution_id=c["institution_id"] or None,
            resolution_method="UNLISTED" if unverified else "REPORTER_CONFIRMED",
            finder_answers={"note": "institution not identified by reporter"} if unverified else None,
            reporter_id=c["reporter_id"], category=c["category"], title=c["title"], description=c["description"],
            received_at=at_time(c["received_date"], 9),
            status="unverified_institution" if unverified else c["status"],  # goes to the Needs Review queue
            assigned_bureau=c["assigned_bureau"], assigned_officer=c["assigned_officer"],
            severity=int(c["severity"]),
            expected_disposal_date=date.fromisoformat(c["expected_disposal_date"]),
            last_action_at=at_time(acts[-1]["action_date"], 11) if acts else None))
        for a in acts:
            moved = a["action_type"] == "Transferred"
            db.add(m.CaseAction(
                case_id=hub_id, seq=int(a["action_seq"]), action_type=a["action_type"],
                stance=STANCES[a["action_type"]], actor=a["officer"], bureau=a["bureau"], remarks=a["remarks"],
                doc_ref=a["doc_ref"], at=at_time(a["action_date"], 11),
                from_bureau=a["bureau"] if moved else None, to_bureau=c["assigned_bureau"] if moved else None))
            n_actions += 1
    return i, n_actions


def run(engine=None) -> dict:
    """Drop and rebuild all tables, load everything, return the row counts."""
    engine = engine or default_engine
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        load_config(db)
        load_users(db)
        counts = {"institutions": load_institutions(db), "aliases": load_aliases(db),
                  "reporters": load_reporters(db)}
        db.flush()  # institutions and reporters must exist before the cases that point to them
        counts["cases"], counts["actions"] = load_cases_and_actions(db)
        db.flush()
        counts["suggestions"] = matching.rebuild_all(db)  # M6: overlap suggestions for the loaded cases
        db.flush()
        counts["conflict_suggestions"] = conflicts.rebuild_all(db)  # M9: conflicts and duplicate actions
        db.flush()
        counts["time_alerts"] = starvation.scan(db)["active"]  # M10: stalled / SLA alerts as of today
        priority.recompute_all(db, now=datetime.now())  # M7: priority score for every case
        db.commit()
    return counts


def main():
    print(f"Seeding {config.DATABASE_URL}")
    print(json.dumps(run(), indent=2))


if __name__ == "__main__":
    main()
