"""Insights panel (M11): plain rules over the numbers, each one explained. No AI model.

Each insight has a tone (good / neutral / warning / bad), a headline, the evidence behind it, the rule that produced it
and, where it helps, a link to the screen to act on. Insights only appear when the data supports them.
"""
from collections import Counter, defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import reports, starvation

REPEAT_CASES = 5        # a college with this many cases is a repeat-complaint college
CATEGORY_SHARE = 15     # % of all cases that makes a category a hotspot
RISING_FACTOR = 1.5     # last 30 days vs the 30 days before
GAP_POINTS = 15         # difference in beyond-timeline % between bureaus that is worth flagging


def build(db: Session, user: m.User, as_of: date | None = None) -> dict:
    as_of = as_of or date.today()
    rs = reports.load(db, user)
    out: list[dict] = []
    if not rs:
        return {"as_of": as_of.isoformat(), "insights": [], "note": "No cases are visible to this role."}
    verified = [r for r in rs if r["inst_id"]]
    opens = [r for r in rs if reports._is_open(r)]
    mm = reports.measures(rs, as_of)

    def add(id_, tone, title, detail, rule, link=None, evidence=None):
        out.append({"id": id_, "tone": tone, "title": title, "detail": detail, "rule": rule, "link": link, "evidence": evidence or {}})

    # 1. Repeat-complaint colleges
    by_inst = defaultdict(list)
    for r in verified:
        by_inst[r["inst_id"]].append(r)
    repeat = sorted(((len(g), g) for g in by_inst.values() if len(g) >= REPEAT_CASES), key=lambda x: -x[0])
    if repeat:
        n, g = repeat[0]
        top = Counter(r["category"] for r in g).most_common(1)[0]
        add("repeat", "warning", f"{g[0]['inst']} has {n} complaints",
            f"This is the most in your view. {top[1]} of them are about {top[0]}. {len(repeat)} college(s) have {REPEAT_CASES} or more complaints.",
            f"A college with {REPEAT_CASES}+ cases is a repeat-complaint college.", f"/institutions/{g[0]['inst_id']}",
            {"cases": n, "colleges_with_repeat": len(repeat)})

    # 2. Category hotspot and trend
    cats = Counter(r["category"] for r in rs)
    cat, cnt = cats.most_common(1)[0]
    share = round(100 * cnt / len(rs), 1)
    recent = Counter(r["category"] for r in rs if as_of - timedelta(days=30) < r["received"] <= as_of)
    before = Counter(r["category"] for r in rs if as_of - timedelta(days=60) < r["received"] <= as_of - timedelta(days=30))
    rising = [(c, recent[c], before[c]) for c in recent if recent[c] >= 3 and recent[c] >= RISING_FACTOR * max(before[c], 1)]
    if share >= CATEGORY_SHARE:
        add("category", "neutral", f"{cat} is the largest category ({share}% of cases)", f"{cnt} of {len(rs)} cases.",
            f"A category with {CATEGORY_SHARE}% or more of all cases is a hotspot.", f"/cases?category={cat}", {"cases": cnt, "share_pct": share})
    if rising:
        c, a, b = max(rising, key=lambda x: x[1])
        add("rising", "warning", f"{c} complaints are rising", f"{a} received in the last 30 days against {b} in the 30 days before.",
            f"A category with 3+ recent cases and {RISING_FACTOR}x the previous 30 days is rising.", f"/cases?category={c}", {"last_30_days": a, "previous_30_days": b})

    # 3. Bureau timeline gap
    per_bureau = {}
    for b in sorted({r["bureau"] for r in opens}):
        g = [r for r in opens if r["bureau"] == b]
        per_bureau[b] = (len(g), sum(1 for r in g if reports._overdue(r, as_of)))
    if len(per_bureau) >= 2:
        rates = {b: round(100 * o / n, 1) for b, (n, o) in per_bureau.items() if n}
        worst, best = max(rates, key=rates.get), min(rates, key=rates.get)
        if rates[worst] - rates[best] >= GAP_POINTS:
            add("bureau_gap", "warning", f"{worst} has more cases beyond timeline than {best}",
                f"{rates[worst]}% of {worst}'s open cases are past their expected date, against {rates[best]}% for {best}.",
                f"Flagged when two bureaus differ by {GAP_POINTS} percentage points or more.", "/cases?overdue=true", {"rates_pct": rates})
    if opens:
        late = sum(1 for r in opens if reports._overdue(r, as_of))
        tone = "bad" if late / len(opens) >= 0.5 else "warning" if late else "good"
        add("timeline", tone, f"{late} of {len(opens)} open cases are beyond their timeline" if late else "No open case is beyond its timeline",
            f"{round(100 * late / len(opens))}% of open cases.", "Open cases past the expected disposal date.", "/cases?overdue=true", {"beyond_timeline": late, "open": len(opens)})

    # 4. Stalled cases
    cfg = starvation.config(db)
    stalled = [r for r in opens if (as_of - (r["last"] or r["received"])).days >= cfg["STARVATION_DAYS"]]
    if stalled:
        worst = max(stalled, key=lambda r: (as_of - (r["last"] or r["received"])).days)
        add("stalled", "bad" if len(stalled) / len(opens) >= 0.4 else "warning", f"{len(stalled)} open cases have had no action for {cfg['STARVATION_DAYS']}+ days",
            f"The longest is {worst['no']} at {(as_of - (worst['last'] or worst['received'])).days} days.",
            f"Open cases with no action for {cfg['STARVATION_DAYS']} days are stalled (configurable).", "/alerts", {"stalled": len(stalled), "open": len(opens)})

    # 5. Waiting for officers (overlaps, conflicts)
    visible = {r["id"] for r in rs}
    waiting = [l for l in db.scalars(select(m.LinkSuggestion).where(m.LinkSuggestion.status == "SUGGESTED")) if l.case_a in visible or l.case_b in visible]
    if waiting:
        kinds = Counter(l.link_type for l in waiting)
        oldest = (as_of - min(l.created_at.date() for l in waiting)).days
        tone = "bad" if kinds["CONFLICT"] else "warning"
        add("waiting", tone, f"{len(waiting)} suggestions are waiting for an officer",
            ", ".join(f"{n} {k.replace('_', ' ').lower()}" for k, n in kinds.most_common()) + f". The oldest was raised " + ("today." if oldest == 0 else f"{oldest} day(s) ago."),
            "Suggestions stay open until an officer confirms or rejects them.", "/overlaps", dict(kinds))
    multi = [iid for iid, g in by_inst.items() if len({r["bureau"] for r in g if reports._is_open(r)}) >= 2]
    if multi:
        add("coordination", "neutral", f"{len(multi)} colleges have open cases in more than one bureau",
            "These are the colleges where RB and PGRC may need to coordinate.", "Open cases in two or more bureaus at one college.", "/overlaps", {"colleges": len(multi)})

    # 6. Disposal performance
    if mm["disposal_rate_pct"] is not None and mm["disposed"]:
        within = mm["disposed_within_expected_pct"]
        tone = "good" if (within or 0) >= 70 else "warning"
        add("disposal", tone, f"{mm['disposal_rate_pct']}% of cases are disposed", f"On average {mm['avg_days_to_dispose']} days to dispose; {within}% were disposed within the expected date.",
            "Disposal rate = disposed / cases with a verified college.", "/reports", {"disposal_rate_pct": mm["disposal_rate_pct"], "within_expected_pct": within})

    # 7. Region concentration
    regions = Counter(r["region"] for r in rs if r["region"])
    if len(regions) >= 2:
        reg, n = regions.most_common(1)[0]
        add("region", "neutral", f"{reg} region has the most complaints ({n})", f"{round(100 * n / sum(regions.values()))}% of cases with a known region.",
            "The region with the most cases.", f"/cases?region={reg}", dict(regions))

    # 8. Colleges not identified
    if mm["needs_review"]:
        add("needs_review", "warning", f"{mm['needs_review']} complaints name a college that could not be identified",
            "An officer has to pick the college before overlaps can be checked.", "Cases without a verified institution wait in Needs review.", "/needs-review", {"cases": mm["needs_review"]})

    order = {"bad": 0, "warning": 1, "neutral": 2, "good": 3}
    out.sort(key=lambda i: order[i["tone"]])
    return {"as_of": as_of.isoformat(), "insights": out, "note": "Every insight is a rule over live numbers; the rule is shown on each card."}
