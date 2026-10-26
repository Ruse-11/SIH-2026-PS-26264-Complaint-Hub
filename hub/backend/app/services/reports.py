"""Reports and analytics (M11). Every report is a plain table: {columns, rows}, so the screen and the CSV export
share one code path. All reports respect the viewer's scope (an RB officer's bureau report only covers RB cases).

Definitions (shown on the report page, so judges can see how numbers are made):
  open            Pending, Under Process or Escalated
  beyond timeline open and past its expected disposal date
  disposed on     date of the closing action (or the last action if the dataset has none)
  disposal rate   disposed / all cases that arrived with a verified college
  ageing          days from receipt to the report date, for open cases only
  quarters        Indian financial-year quarters (Apr-Jun = Q1). An assumption, easy to change.
"""
import csv
import io
from collections import Counter, defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import matching, scope
from .scope import OPEN_STATUSES

STATUSES = ["Pending", "Under Process", "Disposed", "Transferred", "Escalated", "unverified_institution"]
AGE_BUCKETS = [("0-7 days", 0, 7), ("8-15 days", 8, 15), ("16-30 days", 16, 30), ("Over 30 days", 31, 10**6)]

CATALOGUE = [
    {"key": "bureau", "title": "Bureau-wise report", "description": "Cases, status mix, beyond-timeline and disposal rate for each bureau or cell."},
    {"key": "region", "title": "Region-wise report", "description": "The same measures for each region (by the college's region)."},
    {"key": "status", "title": "Status-wise report", "description": "How many cases are in each status."},
    {"key": "institution", "title": "Institution-wise report", "description": "Every college with its complaint counts, repeat complaints and open cases."},
    {"key": "institution_history", "title": "Institution complaint history", "description": "Chronological complaints for one college (a university includes its colleges). Needs institution_id.", "needs": "institution_id"},
    {"key": "ageing", "title": "Pending case ageing", "description": "Open cases by age: 0-7, 8-15, 16-30 and over 30 days."},
    {"key": "disposal", "title": "Disposal rate", "description": "Disposal rate, average days to dispose and share disposed within the expected date, by bureau and by category."},
    {"key": "overlaps", "title": "Overlapping and duplicate cases", "description": "Every overlap, duplicate, corroboration and conflict suggestion with its status."},
    {"key": "monthly", "title": "Monthly performance", "description": "Received, disposed, escalated, transferred and open cases for each month."},
    {"key": "quarterly", "title": "Quarterly performance", "description": "The same for each financial-year quarter (Apr-Jun is Q1)."},
]
TITLES = {c["key"]: c for c in CATALOGUE}


def _d(x):
    return x.date() if hasattr(x, "date") else x


def load(db: Session, user: m.User) -> list[dict]:
    """One small dict per case the user may see, with the disposal date worked out."""
    rows = db.execute(scope.scoped_case_query(user, m.Case, m.Institution.official_name, m.Institution.region)).all()
    ids = [r[0].hub_case_id for r in rows]
    closing: dict[str, date] = {}
    for a in db.scalars(select(m.CaseAction).where(m.CaseAction.case_id.in_(ids), m.CaseAction.stance == "CLOSING")):
        closing[a.case_id] = max(closing.get(a.case_id, a.at.date()), a.at.date())
    out = []
    for c, inst_name, region in rows:
        disposed = None
        if c.status == "Disposed":
            disposed = closing.get(c.hub_case_id) or _d(c.last_action_at or c.received_at)
        out.append({"id": c.hub_case_id, "no": c.source_case_no, "inst_id": c.institution_id, "inst": inst_name, "region": region,
                    "bureau": c.assigned_bureau, "category": c.category, "status": c.status, "title": c.title,
                    "officer": c.assigned_officer, "received": _d(c.received_at), "expected": c.expected_disposal_date,
                    "disposed": disposed, "last": _d(c.last_action_at) if c.last_action_at else None, "cluster": c.cluster_id})
    return out


def _is_open(r):
    return r["status"] in OPEN_STATUSES


def _overdue(r, as_of):
    return _is_open(r) and r["expected"] is not None and r["expected"] < as_of


def _pct(a, b):
    return round(100 * a / b, 1) if b else None


def measures(rs: list[dict], as_of: date) -> dict:
    """The standard set of numbers for a group of cases."""
    verified = [r for r in rs if r["status"] != "unverified_institution"]
    disposed = [r for r in rs if r["disposed"]]
    days = [(r["disposed"] - r["received"]).days for r in disposed]
    in_sla = [r for r in disposed if r["expected"] and r["disposed"] <= r["expected"]]
    opens = [r for r in rs if _is_open(r)]
    counts = Counter(r["status"] for r in rs)
    return {"total": len(rs), "pending": counts["Pending"], "under_process": counts["Under Process"], "disposed": counts["Disposed"],
            "transferred": counts["Transferred"], "escalated": counts["Escalated"], "needs_review": counts["unverified_institution"],
            "open": len(opens), "beyond_timeline": sum(1 for r in rs if _overdue(r, as_of)),
            "disposal_rate_pct": _pct(len(disposed), len(verified)),
            "avg_days_to_dispose": round(sum(days) / len(days), 1) if days else None,
            "disposed_within_expected_pct": _pct(len(in_sla), len(disposed)),
            "avg_open_age_days": round(sum((as_of - r["received"]).days for r in opens) / len(opens), 1) if opens else None}


MEASURE_COLUMNS = [("total", "Total"), ("pending", "Pending"), ("under_process", "Under process"), ("disposed", "Disposed"),
                   ("transferred", "Transferred"), ("escalated", "Escalated"), ("open", "Open"), ("beyond_timeline", "Beyond timeline"),
                   ("disposal_rate_pct", "Disposal rate %"), ("avg_days_to_dispose", "Avg days to dispose"), ("avg_open_age_days", "Avg age of open cases (days)")]


def _group(rs, key, label, as_of, none_label="(not identified)"):
    groups = defaultdict(list)
    for r in rs:
        groups[r[key] or none_label].append(r)
    return [{label: name, **measures(g, as_of)} for name, g in sorted(groups.items(), key=lambda x: (-len(x[1]), x[0]))]


def _report(key, columns, rows, as_of, note=None):
    return {"key": key, "title": TITLES[key]["title"], "description": TITLES[key]["description"], "as_of": as_of.isoformat(),
            "columns": [{"key": k, "label": l} for k, l in columns], "rows": rows, "note": note}


def bureau(rs, as_of):
    return _report("bureau", [("bureau", "Bureau / cell")] + MEASURE_COLUMNS, _group(rs, "bureau", "bureau", as_of), as_of,
                   "A transferred case counts under the bureau it was transferred to.")


def region(rs, as_of):
    return _report("region", [("region", "Region")] + MEASURE_COLUMNS, _group(rs, "region", "region", as_of), as_of,
                   "Cases whose college is not yet identified have no region.")


def status(rs, as_of):
    c = Counter(r["status"] for r in rs)
    rows = [{"status": "Needs review (college not identified)" if s == "unverified_institution" else s, "cases": c[s],
             "share_pct": _pct(c[s], len(rs))} for s in STATUSES]
    return _report("status", [("status", "Status"), ("cases", "Cases"), ("share_pct", "Share %")], rows, as_of)


def institution(rs, as_of):
    groups = defaultdict(list)
    for r in rs:
        if r["inst_id"]:
            groups[r["inst_id"]].append(r)
    rows = []
    for iid, g in groups.items():
        top = Counter(r["category"] for r in g).most_common(1)[0]
        mm = measures(g, as_of)
        rows.append({"institution_id": iid, "institution": g[0]["inst"], "total": mm["total"], "open": mm["open"], "disposed": mm["disposed"],
                     "beyond_timeline": mm["beyond_timeline"], "top_category": f"{top[0]} ({top[1]})",
                     "bureaus": ", ".join(sorted({r["bureau"] for r in g})), "last_received": max(r["received"] for r in g).isoformat(),
                     "repeat_complaints": "yes" if mm["total"] >= 5 else ""})
    rows.sort(key=lambda r: (-r["total"], r["institution_id"]))
    return _report("institution", [("institution_id", "AICTE ID"), ("institution", "Institution"), ("total", "Cases"), ("open", "Open"),
                                   ("disposed", "Disposed"), ("beyond_timeline", "Beyond timeline"), ("top_category", "Most common category"),
                                   ("bureaus", "Bureaus involved"), ("last_received", "Last complaint"), ("repeat_complaints", "Repeat (5+ cases)")], rows, as_of)


def institution_history(db: Session, rs, as_of, institution_id):
    inst = db.get(m.Institution, institution_id) if institution_id else None
    ids = {institution_id} | set(db.scalars(select(m.Institution.aicte_id).where(m.Institution.parent_id == institution_id))) if inst else set()
    last_action = {}
    for a in db.scalars(select(m.CaseAction).order_by(m.CaseAction.at)):
        last_action[a.case_id] = a.action_type
    rows = [{"received": r["received"].isoformat(), "case_no": r["no"], "hub_case_id": r["id"], "institution": r["inst"], "bureau": r["bureau"],
             "category": r["category"], "title": r["title"], "status": r["status"], "officer": r["officer"],
             "last_action": last_action.get(r["id"], ""), "last_action_date": r["last"].isoformat() if r["last"] else "",
             "expected_disposal": r["expected"].isoformat() if r["expected"] else "", "disposed_on": r["disposed"].isoformat() if r["disposed"] else ""}
            for r in sorted(rs, key=lambda r: (r["received"], r["id"])) if r["inst_id"] in ids]
    rep = _report("institution_history", [("received", "Received"), ("case_no", "Case"), ("hub_case_id", "Hub ID"), ("institution", "Institution"),
                                          ("bureau", "Bureau"), ("category", "Category"), ("title", "Title"), ("status", "Status"), ("officer", "Officer"),
                                          ("last_action", "Last action"), ("last_action_date", "Date of last action"),
                                          ("expected_disposal", "Expected disposal"), ("disposed_on", "Disposed on")], rows, as_of)
    rep["title"] = "Complaint history: " + (inst.official_name if inst else "choose an institution")
    return rep


def ageing(rs, as_of):
    def row(label, g):
        ages = [(as_of - r["received"]).days for r in g]
        out = {"group": label, "open_cases": len(g)}
        for name, lo, hi in AGE_BUCKETS:
            out[name] = sum(1 for a in ages if lo <= a <= hi)
        out["average_age_days"] = round(sum(ages) / len(ages), 1) if ages else None
        out["oldest_days"] = max(ages) if ages else None
        return out
    opens = [r for r in rs if _is_open(r)]
    by_bureau = defaultdict(list)
    for r in opens:
        by_bureau[r["bureau"]].append(r)
    rows = [row("All bureaus", opens)] + [row(b, g) for b, g in sorted(by_bureau.items())]
    return _report("ageing", [("group", "Bureau"), ("open_cases", "Open cases")] + [(n, n) for n, _, _ in AGE_BUCKETS] +
                   [("average_age_days", "Average age (days)"), ("oldest_days", "Oldest (days)")], rows, as_of,
                   "Age = days from receipt to the report date, open cases only.")


def disposal(rs, as_of):
    cols = [("group_type", "Group by"), ("group", "Group"), ("total", "Cases"), ("disposed", "Disposed"), ("disposal_rate_pct", "Disposal rate %"),
            ("avg_days_to_dispose", "Avg days to dispose"), ("disposed_within_expected_pct", "Disposed within expected date %")]
    rows = []
    for gtype, key in (("Bureau", "bureau"), ("Category", "category")):
        for g in _group(rs, key, "group", as_of):
            rows.append({"group_type": gtype, **{k: g[k] for k in ("group", "total", "disposed", "disposal_rate_pct", "avg_days_to_dispose", "disposed_within_expected_pct")}})
    all_m = measures(rs, as_of)
    rows.insert(0, {"group_type": "All", "group": "All cases", **{k: all_m[k] for k in ("total", "disposed", "disposal_rate_pct", "avg_days_to_dispose", "disposed_within_expected_pct")}})
    return _report("disposal", cols, rows, as_of, "Disposal rate = disposed cases / cases with a verified college.")


def overlaps(db: Session, user: m.User, as_of):
    visible = scope.visible_case_ids(db, user)
    rows = []
    for l in matching.list_links(db, limit=5000, visible=visible):
        a, b = l["cases"]
        r = l["reasons"] or {}
        lead = r.get("final_lead") or {}
        sug = r.get("suggested_lead") or {}
        rows.append({"suggestion": l["id"], "type": l["link_type"], "status": l["status"], "institution": l["institution"]["official_name"],
                     "case_a": a["source_case_no"], "bureau_a": a["bureau"], "case_b": b["source_case_no"], "bureau_b": b["bureau"],
                     "similarity": l["score"] if l["score"] is not None else "", "suggested_lead": sug.get("bureau") or "",
                     "final_lead": lead.get("bureau", ""), "decided_by": l["decided_by"] or "", "created": l["created_at"][:10]})
    rows.sort(key=lambda r: (r["status"] != "SUGGESTED", r["type"], -r["suggestion"]))
    return _report("overlaps", [("suggestion", "#"), ("type", "Type"), ("status", "Status"), ("institution", "Institution"), ("case_a", "Case A"),
                                ("bureau_a", "Bureau A"), ("case_b", "Case B"), ("bureau_b", "Bureau B"), ("similarity", "Text similarity"),
                                ("suggested_lead", "Suggested lead"), ("final_lead", "Final lead (competent authority)"),
                                ("decided_by", "Decided by"), ("created", "Created")], rows, as_of)


def _fy_quarter(d: date) -> tuple[str, date, date]:
    """Indian financial year quarter: Apr-Jun is Q1."""
    fy = d.year if d.month >= 4 else d.year - 1
    q = ((d.month - 4) % 12) // 3 + 1
    start_month = 4 + 3 * (q - 1)
    sy, sm = (fy, start_month) if start_month <= 12 else (fy + 1, start_month - 12)
    start = date(sy, sm, 1)
    em, ey = sm + 3, sy
    if em > 12:
        em, ey = em - 12, ey + 1
    end = date(ey, em, 1) - timedelta(days=1)
    return f"FY{fy}-{str(fy + 1)[2:]} Q{q}", start, end


def _periods(rs, as_of, quarterly):
    if not rs:
        return []
    d, seen, out = min(r["received"] for r in rs), set(), []
    while d <= as_of:
        if quarterly:
            label, start, end = _fy_quarter(d)
        else:
            start = d.replace(day=1)
            nxt = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
            label, end = start.strftime("%Y-%m"), nxt - timedelta(days=1)
        if label not in seen:
            seen.add(label)
            out.append((label, start, end))
        d = end + timedelta(days=1)
    return out


def performance(db: Session, rs, as_of, quarterly):
    ids = {r["id"] for r in rs}
    acts = [(a.case_id, a.action_type, a.at.date()) for a in db.scalars(
        select(m.CaseAction).where(m.CaseAction.action_type.in_(["Escalated to Competent Authority", "Transferred"]), m.CaseAction.case_id.in_(list(ids))))]

    def open_on(r, day):
        # Transferred cases count as handed over (not open), like everywhere else in the hub
        return r["received"] <= day and (r["disposed"] is None or r["disposed"] > day) and r["status"] in OPEN_STATUSES + ("Disposed",)
    rows = []
    for label, start, end in _periods(rs, as_of, quarterly):
        end = min(end, as_of)
        received = [r for r in rs if start <= r["received"] <= end]
        disposed = [r for r in rs if r["disposed"] and start <= r["disposed"] <= end]
        opening = sum(1 for r in rs if open_on(r, start - timedelta(days=1)))
        handled = opening + len(received)
        days = [(r["disposed"] - r["received"]).days for r in disposed]
        rows.append({"period": label, "received": len(received), "disposed": len(disposed),
                     "disposal_rate_pct": _pct(len(disposed), handled), "avg_days_to_dispose": round(sum(days) / len(days), 1) if days else None,
                     "escalated": sum(1 for _, t, d in acts if t.startswith("Escalated") and start <= d <= end),
                     "transferred": sum(1 for _, t, d in acts if t == "Transferred" and start <= d <= end),
                     "open_at_end": sum(1 for r in rs if open_on(r, end))})
    key = "quarterly" if quarterly else "monthly"
    return _report(key, [("period", "Period"), ("received", "Received"), ("disposed", "Disposed"), ("disposal_rate_pct", "Disposal rate %"),
                         ("avg_days_to_dispose", "Avg days to dispose"), ("escalated", "Escalated"), ("transferred", "Transferred"),
                         ("open_at_end", "Open at period end")], rows, as_of,
                   "Disposal rate = disposed in the period / (cases open at the start + received in the period)."
                   + (" Quarters follow the Indian financial year (Apr-Jun = Q1), an assumption." if quarterly else ""))


def build(db: Session, user: m.User, key: str, as_of: date | None = None, institution_id: str | None = None) -> dict | None:
    as_of = as_of or date.today()
    if key not in TITLES:
        return None
    if key == "overlaps":
        return overlaps(db, user, as_of)
    rs = load(db, user)
    if key in ("monthly", "quarterly"):
        return performance(db, rs, as_of, key == "quarterly")
    if key == "institution_history":
        return institution_history(db, rs, as_of, institution_id)
    return {"bureau": bureau, "region": region, "status": status, "institution": institution, "ageing": ageing, "disposal": disposal}[key](rs, as_of)


# ---- CSV ----
def _safe(v):
    """Stop spreadsheet formula injection: a cell starting with = + - @ would run as a formula in Excel."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v  # real numbers (even negative ones) are safe
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def to_csv(report: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([_safe(c["label"]) for c in report["columns"]])
    for r in report["rows"]:
        w.writerow([_safe(r.get(c["key"])) for c in report["columns"]])
    return buf.getvalue()
