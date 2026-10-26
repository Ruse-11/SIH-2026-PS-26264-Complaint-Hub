"""Case file (one case as a printable report). A standalone HTML page: opens in any browser, and
"Print / Save as PDF" in the page turns it into a PDF. Everything is HTML-escaped (complaint text is user input).

Sections: summary, institution, complaint as the reporter wrote it, action history, linked and suggested cases
(collaboration between bureaus), alerts, audit trail (senior management and competent authority only), notes.
"""
from datetime import date, datetime
from html import escape as esc

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import cases as case_service, dashboard

LINK_LABEL = {"CROSS_BUREAU": "Cross-bureau overlap", "SAME_REPORTER": "Same reporter, duplicate", "CORROBORATION": "Corroboration",
              "CONFLICT": "Conflicting actions", "DUPLICATE_ACTION": "Duplicate action", "RELATED": "Related cases (linked by an officer)"}
LINK_STATUS = {"SUGGESTED": "Suggested, awaiting an officer's decision", "CONFIRMED": "Confirmed by an officer", "REJECTED": "Rejected by an officer"}
AUDIT_ROLES = ("senior_management", "competent_authority")

CSS = """
body{font:14px/1.45 Segoe UI,Arial,sans-serif;color:#0f172a;max-width:900px;margin:24px auto;padding:0 16px}
h1{font-size:22px;margin:0}h2{font-size:15px;margin:22px 0 6px;border-bottom:2px solid #0f172a;padding-bottom:3px}
.sub{color:#64748b;font-size:12px}table{border-collapse:collapse;width:100%;font-size:13px}
th,td{border:1px solid #cbd5e1;padding:5px 7px;text-align:left;vertical-align:top}th{background:#f1f5f9}
.kv td:first-child{width:180px;background:#f8fafc;font-weight:600}.box{background:#f8fafc;border:1px solid #cbd5e1;padding:8px 10px;white-space:pre-wrap}
.pill{display:inline-block;border-radius:10px;padding:0 8px;background:#e2e8f0;font-size:12px}.note{color:#475569;font-size:12px}
.bar{display:flex;justify-content:space-between;align-items:flex-end}button{padding:6px 12px}
@media print{button{display:none}body{margin:0}h2{break-after:avoid}tr{break-inside:avoid}}
"""


def _d(x):
    if not x:
        return "–"
    return str(x)[:10]


def _dt(x):
    return str(x).replace("T", " ")[:16] if x else "–"


def _kv(rows):
    return "<table class='kv'>" + "".join(f"<tr><td>{esc(str(k))}</td><td>{v if isinstance(v, _Raw) else esc('–' if v in (None, '') else str(v))}</td></tr>"
                                         for k, v in rows) + "</table>"


class _Raw(str):
    """Already-safe HTML (built here from escaped pieces)."""


def _table(headers, rows):
    if not rows:
        return "<p class='note'>None.</p>"
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c if isinstance(c, _Raw) else esc('–' if c in (None, '') else str(c))}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><tr>{head}</tr>{body}</table>"


def _reason_text(reasons: dict | None) -> str:
    """Reasons stored with a suggestion, as short readable lines."""
    skip = {"institution", "portals", "category", "same_reporter", "method"}
    lines = []
    for k, v in (reasons or {}).items():
        if k in skip or v in (None, "", [], {}):
            continue
        label = k.replace("_", " ").capitalize()
        if k == "suggested_lead" and isinstance(v, dict):
            v = f"{v.get('bureau') or 'none'} ({v.get('rule')})"
        elif k == "final_lead" and isinstance(v, dict):
            v = f"{v.get('bureau')} decided by {v.get('decided_by')}"
        elif isinstance(v, list):
            v = ", ".join(str(x if not isinstance(x, dict) else "; ".join(f"{a}: {b}" for a, b in x.items())) for x in v)
        elif isinstance(v, dict):
            v = "; ".join(f"{a}: {b}" for a, b in v.items())
        lines.append(f"{label}: {v}")
    return "\n".join(lines)


def build(db: Session, user: m.User, hub_case_id: str) -> str:
    d = case_service.case_detail(db, hub_case_id)
    case = db.get(m.Case, hub_case_id)
    inst = db.get(m.Institution, case.institution_id) if case.institution_id else None
    parent = db.get(m.Institution, inst.parent_id) if inst and inst.parent_id else None
    now = datetime.now()
    p = d["priority"]
    overdue = dashboard.is_overdue(case.status, case.expected_disposal_date, date.today())

    # ---- summary ----
    summary = _kv([
        ("Case number", d["source_case_no"]), ("Hub case ID", d["hub_case_id"]), ("Status", case.status if case.status != "unverified_institution" else "Needs review (college not yet identified)"),
        ("Category", d["category"]), ("Bureau / officer", f"{d['assigned_bureau']} / {d['assigned_officer'] or 'unassigned'}"),
        ("Received", f"{_d(d['received_at'])} via the {d['source_system']} portal ({p['age_days']} days ago)"),
        ("Expected disposal", _d(d["expected_disposal_date"]) + (" (beyond the timeline)" if overdue else "")),
        ("Last action", f"{d['last_action'] or '–'} on {_d(d['last_action_at'])}"),
        ("Next action required", (f"{d['next_action']['text']} (due {_d(d['next_action']['due'])}, "
                                  f"{'set by the officer' if d['next_action']['source'] == 'officer' else 'suggested by rule'}"
                                  f"{', overdue' if d['next_action']['overdue'] else ''})") if d["next_action"]["text"] else "None (case closed)"),
        ("Priority score", f"{p['score']} = severity {d['severity']} x 10 ({p['parts']['severity']}) + confirmed independent reporters "
                           f"{p['confirmed_corroborators']} x 5 ({p['parts']['corroboration']}) + age {p['age_days']} days x 0.3 ({p['parts']['age']})"),
        ("Possible priority boost", f"+{p['potential_boost']} if an officer confirms the pending corroboration" if p["potential_boost"] else "none pending"),
    ])

    # ---- institution ----
    if inst:
        total = len(db.scalars(select(m.Case.hub_case_id).where(m.Case.institution_id == inst.aicte_id)).all())
        open_ = len(db.scalars(select(m.Case.hub_case_id).where(m.Case.institution_id == inst.aicte_id,
                                                              m.Case.status.in_(("Pending", "Under Process", "Escalated")))).all())
        inst_html = _kv([
            ("Institution", inst.official_name), ("AICTE ID", inst.aicte_id), ("Part of", parent.official_name if parent else None),
            ("Address", ", ".join(x for x in (inst.address_line, inst.area, inst.district, inst.state, inst.pincode) if x)),
            ("Region / type", f"{inst.region or '–'} / {inst.type or '–'}"), ("Programmes", (inst.programs or "").replace(";", ", ")),
            ("Complaints at this institution", f"{total} in total, {open_} still open (all bureaus)"),
        ])
    else:
        inst_html = "<p class='note'>The institution named in this complaint has not been identified yet. An officer must pick it in Needs review.</p>"

    # ---- complaint ----
    answers = d["finder_answers"]
    complaint = _kv([("Title", d["title"]), ("Reporter", f"{d['reporter_id']} ({d['reporter_type'] or 'unknown type'}; contact details are not stored, only a hash)"),
                     ("College identified by", d["resolution_method"]),
                     ("Finder answers", ", ".join(f"{k}: {v}" for k, v in answers.items()) if isinstance(answers, dict) and answers else None)])
    complaint += f"<p><b>Reporter-entered summary</b></p><div class='box'>{esc(d['description'] or '')}</div>"

    # ---- actions ----
    actions = _table(["#", "Date", "Action", "Type", "By", "Bureau", "Remarks", "Document"],
                     [(a["seq"], _dt(a["at"]), a["action_type"], a["stance"].lower(), a["actor"],
                       a["bureau"] + (f" → {a['to_bureau']}" if a["to_bureau"] else ""), a["remarks"], a["doc_ref"]) for a in d["actions"]])

    # ---- linked cases ----
    rows = []
    bureaus = {d["assigned_bureau"]}
    for l in d["links"]:
        other = next((c for c in l["cases"] if c["hub_case_id"] != hub_case_id), l["cases"][-1])
        bureaus.add(other["bureau"])
        r = l["reasons"] or {}
        lead = r.get("final_lead") or r.get("suggested_lead") or {}
        rows.append((LINK_LABEL.get(l["link_type"], l["link_type"]), LINK_STATUS.get(l["status"], l["status"]),
                     f"{other['source_case_no']} ({other['hub_case_id']}) · {other['bureau']} · {other['status']}", other["title"],
                     l["score"], _Raw(esc(_reason_text(r)).replace("\n", "<br>")),
                     (lead.get("bureau") or "none") if lead else None,
                     f"{l['decided_by']} on {_dt(l['decided_at'])}" if l["decided_by"] else "not decided yet"))
    links = _table(["Type", "Status", "Other case", "Other case title", "Similarity", "Why it was suggested", "Lead bureau", "Decision"], rows)
    collab = f"<p class='note'>Bureaus involved across this case and its linked cases: {esc(', '.join(sorted(b for b in bureaus if b)))}.</p>"

    # ---- alerts ----
    al = db.scalars(select(m.Alert).where(m.Alert.case_id == hub_case_id).order_by(m.Alert.created_at)).all()
    alerts = _table(["Raised", "Type", "Severity", "Message", "Acknowledged"],
                    [(_dt(a.created_at), a.type, a.severity, a.message, f"{a.acknowledged_by} on {_dt(a.acknowledged_at)}" if a.acknowledged_by else "no") for a in al])

    # ---- audit (restricted) ----
    if user.role in AUDIT_ROLES:
        link_ids = {str(l["id"]) for l in d["links"]}
        aud = [a for a in db.scalars(select(m.AuditLog).order_by(m.AuditLog.id)) if a.entity_id == hub_case_id or (a.entity_type == "link" and a.entity_id in link_ids)]
        audit_html = "<h2>Audit trail</h2>" + _table(["When", "Who", "Action", "On"], [(_dt(a.at), f"{a.actor} ({a.role})", a.action, f"{a.entity_type} {a.entity_id}") for a in aud])
    else:
        audit_html = "<h2>Audit trail</h2><p class='note'>Shown to senior management and the competent authority only.</p>"

    title = f"Case file {d['source_case_no']}"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{esc(title)}</title><style>{CSS}</style></head><body>
<div class="bar"><div><h1>{esc(title)}</h1><div class="sub">{esc(d['title'] or '')}</div></div>
<button onclick="window.print()">Print / Save as PDF</button></div>
<p class="sub">Generated {esc(now.strftime('%Y-%m-%d %H:%M'))} by {esc(user.display_name)} ({esc(user.role.replace('_', ' '))}). Synthetic prototype data.
Confidential: for officers handling this complaint.</p>
<h2>1. Summary</h2>{summary}
<h2>2. Institution</h2>{inst_html}
<h2>3. Complaint</h2>{complaint}
<h2>4. Action history ({len(d['actions'])})</h2>{actions}
<h2>5. Linked and suggested cases ({len(d['links'])})</h2>{collab}{links}
<h2>6. Alerts ({len(al)})</h2>{alerts}
{audit_html}
<h2>Notes</h2><p class="note">Links marked "suggested" are system suggestions only; an officer decides. The lead-bureau rule shown is a suggestion;
if bureaus disagree the competent authority decides. Time limits and category ownership are configurable assumptions.</p>
</body></html>"""
