"""
validate_dataset.py - checks the synthetic CSVs in data/ against CLAUDE.md section 13.

Standard library only. It never changes a CSV; it only reads and reports.
Run from the project root:   python data/validate_dataset.py
Exit code: 0 = no ERRORs, 1 = at least one ERROR (WARNs do not fail).
"""
import csv
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

DATA = Path(__file__).resolve().parent

# ---------- spec values (CLAUDE.md sections 7, 9, 13) ----------
DATE_MIN, DATE_MAX = date(2026, 4, 1), date(2026, 10, 22)
# "today" for stalled / due-soon / overdue checks. Default = real today; override with
#   python data/validate_dataset.py 2026-10-27
REF_DATE = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()

EXPECTED_ROWS = {  # file: (target, tolerance) ; tolerance None = "at least"
    "institutions.csv": (40, 0),
    "institution_aliases.csv": (160, 0.15),
    "institution_name_tests.csv": (45, None),
    "reporters.csv": (80, 0),
    "cases.csv": (150, 0),
    "actions.csv": (300, 0.20),
}

EXPECTED_COLUMNS = {
    "institutions.csv": ["institution_id", "official_name", "institution_type", "parent_id", "address_line",
                         "area", "district", "state", "pincode", "region", "lat", "lng", "programs",
                         "established_year"],
    "institution_aliases.csv": ["alias", "institution_id", "alias_type"],
    "institution_name_tests.csv": ["test_id", "typed_input", "expected_outcome", "expected_institution_id", "note"],
    "reporters.csv": ["reporter_id", "display_name", "reporter_type", "email", "phone"],
    "cases.csv": ["source_case_no", "source_system", "institution_id", "reporter_id", "category", "title",
                  "description", "severity", "received_date", "status", "assigned_bureau", "assigned_officer",
                  "last_action_date", "expected_disposal_date", "scenario_tag"],
    "actions.csv": ["source_case_no", "action_seq", "action_date", "bureau", "officer", "action_type",
                    "remarks", "doc_ref"],
}

CATEGORIES = {"Fee/Refund", "Faculty Shortage/Qualification", "Infrastructure/Lab", "Admission Irregularity",
              "Approval/Affiliation", "Ragging/Harassment", "Placement Misrepresentation", "Exam/Result",
              "Hostel/Mess", "Scholarship", "Misleading Advertisement/Accreditation Claim"}
STATUSES = {"Pending", "Under Process", "Disposed", "Transferred", "Escalated"}
SYSTEMS = {"RB", "PGRC"}
STANCE = {
    "Show-Cause Notice Issued": "ENFORCING", "Inspection Ordered": "ENFORCING", "Penalty Proposed": "ENFORCING",
    "Documents Sought": "REQUESTING", "Reply Sought from Institution": "REQUESTING",
    "Closed - No Action": "CLOSING", "Disposed - Unsubstantiated": "CLOSING", "Disposed - Action Taken": "CLOSING",
    "Acknowledged": "NEUTRAL", "Under Review": "NEUTRAL", "Transferred": "NEUTRAL",
    "Escalated to Competent Authority": "NEUTRAL",
}
INSTITUTION_TYPES = {"University", "Engineering", "Pharmacy", "Architecture", "Management", "Diploma",
                     "Applied Sciences"}
# keyword in the official name -> the type it implies (used for a consistency warning)
NAME_TYPE_HINTS = {"University": "University", "Pharmacy": "Pharmacy", "Architecture": "Architecture",
                   "Management": "Management", "Engineering": "Engineering"}
REPORTER_TYPES = {"student", "parent", "alumni", "faculty", "other"}
NAME_TEST_OUTCOMES = {"RESOLVED", "AMBIGUOUS", "NOT_LISTED"}
INDIA_LAT, INDIA_LNG = (6.5, 37.6), (68.0, 97.5)
SCENARIOS = [f"S{i}" for i in range(1, 17)]

# words that often appear in REAL Indian institution names; a hit is only "please check by hand"
REAL_NAME_HINTS = ["iit", "nit", "iiit", "bits", "vit", "srm", "amity", "manipal", "anna", "guindy", "jntu",
                   "osmania", "jadavpur", "delhi technological", "thapar", "pes", "rvce", "psg", "sastra",
                   "kalinga", "lovely", "chandigarh", "symbiosis", "christ", "nirma", "vellore", "pune university",
                   "mumbai university", "indian institute", "national institute", "government college", "aicte"]

problems = []  # (level, file, row, message, fix)


def report(level, file, row, msg, fix=""):
    problems.append((level, file, str(row), msg, fix))


def load(name):
    """Return (header, rows). Row numbers used in messages = line number in the file (header = line 1)."""
    path = DATA / name
    if not path.exists():
        report("ERROR", name, "-", "file is missing", "add the file to data/")
        return [], []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        return reader.fieldnames or [], rows


def parse_date(text):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text or ""):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def section(title):
    print("\n" + "=" * 70 + "\n" + title + "\n" + "=" * 70)


# ---------------------------------------------------------------- load
files = {name: load(name) for name in EXPECTED_COLUMNS}
inst_rows = files["institutions.csv"][1]
alias_rows = files["institution_aliases.csv"][1]
test_rows = files["institution_name_tests.csv"][1]
rep_rows = files["reporters.csv"][1]
case_rows = files["cases.csv"][1]
act_rows = files["actions.csv"][1]

print(f"Reference date for stalled/overdue checks: {REF_DATE}")

# ---------------------------------------------------------------- 1. counts
section("1. File and row counts vs spec")
for name, (target, tol) in EXPECTED_ROWS.items():
    n = len(files[name][1])
    if tol is None:
        ok = n >= target
        want = f">= {target}"
    else:
        ok = abs(n - target) <= target * tol
        want = f"{target}" if tol == 0 else f"~{target} (+/-{int(tol * 100)}%)"
    print(f"  {'OK  ' if ok else 'WARN'} {name:30s} rows={n:4d}  spec {want}")
    if not ok:
        level = "ERROR" if tol == 0 else "WARN"
        report(level, name, "-", f"{n} rows, spec says {want}",
               "fine if intentional; otherwise trim/add rows")

# ---------------------------------------------------------------- 2. columns
section("2. Column names per file")
for name, expected in EXPECTED_COLUMNS.items():
    header = files[name][0]
    missing = [c for c in expected if c not in header]
    extra = [c for c in header if c not in expected]
    print(f"  {name}: {', '.join(header)}")
    if missing:
        print(f"    MISSING: {missing}")
        report("ERROR", name, 1, f"missing columns {missing}", "add the columns")
    if extra:
        print(f"    EXTRA:   {extra}")
        report("WARN", name, 1, f"extra columns {extra}", "ok if used; seed loader will ignore them")
print("  Note: CLAUDE.md section 9 calls the institution key aicte_id and uses received_at; the CSVs use\n"
      "  institution_id and received_date. The M1 seed loader maps these names; no CSV change needed.")

# ---------------------------------------------------------------- 3. integrity
section("3. Integrity (unique IDs and references)")


def check_unique(name, rows, key):
    seen = {}
    for i, r in enumerate(rows, start=2):
        k = r.get(key, "").strip()
        if not k:
            report("ERROR", name, i, f"empty {key}", f"fill {key}")
        elif k in seen:
            report("ERROR", name, i, f"duplicate {key} {k} (first at row {seen[k]})", "make IDs unique")
        else:
            seen[k] = i
    return set(seen)


inst_ids = check_unique("institutions.csv", inst_rows, "institution_id")
rep_ids = check_unique("reporters.csv", rep_rows, "reporter_id")
case_ids = check_unique("cases.csv", case_rows, "source_case_no")
check_unique("institution_name_tests.csv", test_rows, "test_id")
inst_by_id = {r["institution_id"]: r for r in inst_rows}
case_by_id = {r["source_case_no"]: r for r in case_rows}

for i, r in enumerate(inst_rows, start=2):
    p = r["parent_id"].strip()
    if p and p not in inst_ids:
        report("ERROR", "institutions.csv", i, f"parent_id {p} does not exist", "fix parent_id")
    if p == r["institution_id"]:
        report("ERROR", "institutions.csv", i, "institution is its own parent", "clear parent_id")
    if not r["pincode"].strip():
        report("WARN", "institutions.csv", i, f"{r['institution_id']} has empty pincode",
               "optional; add a 6-digit pincode if the confirm card should show it")
parents = Counter(r["parent_id"] for r in inst_rows if r["parent_id"].strip())
print(f"  parent groups: {len(parents)} (spec 4) -> {dict(parents)}")
if len(parents) != 4:
    report("WARN", "institutions.csv", "-", f"{len(parents)} parent groups, spec says 4", "")

for i, r in enumerate(alias_rows, start=2):
    if r["institution_id"] not in inst_ids:
        report("ERROR", "institution_aliases.csv", i, f"institution_id {r['institution_id']} not found", "fix ID")
for i, r in enumerate(case_rows, start=2):
    iid = r["institution_id"].strip()
    if iid and iid not in inst_ids:
        report("ERROR", "cases.csv", i, f"institution_id {iid} not found", "fix ID")
    if not iid and r["scenario_tag"] not in ("S13", "S16"):
        report("WARN", "cases.csv", i, f"{r['source_case_no']} has no institution_id but is not S13/S16",
               "add the ID or tag it")
    if r["reporter_id"] not in rep_ids:
        report("ERROR", "cases.csv", i, f"reporter_id {r['reporter_id']} not found", "fix ID")

actions_by_case = defaultdict(list)
for i, r in enumerate(act_rows, start=2):
    if r["source_case_no"] not in case_ids:
        report("ERROR", "actions.csv", i, f"source_case_no {r['source_case_no']} not in cases.csv", "fix case no")
    else:
        actions_by_case[r["source_case_no"]].append((i, r))

for cno, acts in actions_by_case.items():
    seqs = sorted(int(a["action_seq"]) for _, a in acts if a["action_seq"].isdigit())
    if seqs != list(range(1, len(acts) + 1)):
        report("ERROR", "actions.csv", acts[0][0], f"{cno} action_seq is {seqs}, expected 1..{len(acts)}",
               "renumber action_seq")
no_actions = sorted(case_ids - set(actions_by_case))
print(f"  unique IDs checked; cases without any action: {len(no_actions)}")
for c in no_actions:
    report("WARN", "cases.csv", "-", f"{c} has no actions", "add at least an Acknowledged action")

# ---------------------------------------------------------------- 4. allowed values
section("4. Allowed values")


def check_allowed(name, rows, col, allowed, level="ERROR"):
    bad = Counter()
    for i, r in enumerate(rows, start=2):
        v = r.get(col, "").strip()
        if v not in allowed:
            bad[v] += 1
            report(level, name, i, f"{col}='{v}' not allowed", f"use one of {sorted(allowed)}")
    print(f"  {name}.{col}: {'OK' if not bad else 'BAD ' + str(dict(bad))}")


check_allowed("cases.csv", case_rows, "category", CATEGORIES)
check_allowed("cases.csv", case_rows, "status", STATUSES)
check_allowed("cases.csv", case_rows, "severity", {"1", "2", "3", "4", "5"})
check_allowed("cases.csv", case_rows, "source_system", SYSTEMS)
check_allowed("cases.csv", case_rows, "assigned_bureau", SYSTEMS, level="WARN")
check_allowed("actions.csv", act_rows, "action_type", set(STANCE))
check_allowed("actions.csv", act_rows, "bureau", SYSTEMS, level="WARN")
check_allowed("institutions.csv", inst_rows, "institution_type", INSTITUTION_TYPES)
check_allowed("reporters.csv", rep_rows, "reporter_type", REPORTER_TYPES)
check_allowed("institution_name_tests.csv", test_rows, "expected_outcome", NAME_TEST_OUTCOMES)

used_types = Counter(r["action_type"] for r in act_rows)
unused = [t for t in STANCE if t not in used_types]
print(f"  action types never used: {unused}")
if any(t in unused for t in ("Disposed - Unsubstantiated", "Disposed - Action Taken")):
    report("WARN", "actions.csv", "-", f"{sum(1 for r in case_rows if r['status'] == 'Disposed')} cases are "
           f"Disposed but 'Disposed - ...' action types are never used",
           "give each Disposed case a final CLOSING action (Disposed - Action Taken / Unsubstantiated)")

# institution type vs the word in its name (the Finder's guided 'type' question depends on this)
mismatch = 0
for i, r in enumerate(inst_rows, start=2):
    for word, implied in NAME_TYPE_HINTS.items():
        if word in r["official_name"] and r["institution_type"] != implied:
            mismatch += 1
            report("WARN", "institutions.csv", i,
                   f"{r['institution_id']} '{r['official_name']}' has type {r['institution_type']}",
                   "set institution_type to match the word in the name")
print(f"  institution_type contradicting the name: {mismatch} rows")

# ---------------------------------------------------------------- 5. dates
section("5. Dates (YYYY-MM-DD, 2026-04-01..2026-10-22, order)")
date_errors = 0
for i, r in enumerate(case_rows, start=2):
    rec, last, exp = (parse_date(r["received_date"]), parse_date(r["last_action_date"]),
                      parse_date(r["expected_disposal_date"]))
    for col, d in (("received_date", rec), ("last_action_date", last)):
        if d is None:
            date_errors += 1
            report("ERROR", "cases.csv", i, f"{col}='{r[col]}' is not YYYY-MM-DD", "fix format")
        elif not DATE_MIN <= d <= DATE_MAX:
            date_errors += 1
            report("ERROR", "cases.csv", i, f"{col} {d} outside {DATE_MIN}..{DATE_MAX}", "move into range")
    if exp is None:
        date_errors += 1
        report("ERROR", "cases.csv", i, f"expected_disposal_date='{r['expected_disposal_date']}' invalid", "fix")
    if rec and last and last < rec:
        date_errors += 1
        report("ERROR", "cases.csv", i, f"last_action_date {last} before received_date {rec}", "fix order")
    if rec and exp and exp < rec:
        date_errors += 1
        report("ERROR", "cases.csv", i, f"expected_disposal_date {exp} before received_date {rec}", "fix order")
    # last_action_date should equal the latest action in actions.csv
    acts = actions_by_case.get(r["source_case_no"], [])
    act_dates = [parse_date(a["action_date"]) for _, a in acts if parse_date(a["action_date"])]
    if last and act_dates and max(act_dates) != last:
        date_errors += 1
        report("WARN", "cases.csv", i, f"{r['source_case_no']} last_action_date {last} but latest action is "
               f"{max(act_dates)}", "set last_action_date = latest action_date (or let the loader derive it)")

for i, r in enumerate(act_rows, start=2):
    d = parse_date(r["action_date"])
    c = case_by_id.get(r["source_case_no"])
    if d is None:
        date_errors += 1
        report("ERROR", "actions.csv", i, f"action_date='{r['action_date']}' invalid", "fix format")
        continue
    if not DATE_MIN <= d <= DATE_MAX:
        date_errors += 1
        report("ERROR", "actions.csv", i, f"action_date {d} outside range", "move into range")
    if c and parse_date(c["received_date"]) and d < parse_date(c["received_date"]):
        date_errors += 1
        report("ERROR", "actions.csv", i, f"action {d} before case received {c['received_date']}", "fix order")
for cno, acts in actions_by_case.items():
    ordered = sorted(acts, key=lambda x: int(x[1]["action_seq"]) if x[1]["action_seq"].isdigit() else 0)
    ds = [parse_date(a["action_date"]) for _, a in ordered]
    if all(ds) and ds != sorted(ds):
        date_errors += 1
        report("ERROR", "actions.csv", ordered[0][0], f"{cno} action dates go backwards by seq", "fix dates")
print(f"  date issues found: {date_errors}")

# ---------------------------------------------------------------- 5b. status vs actions
section("5b. Status vs action history (consistency)")
cons = 0
for i, r in enumerate(case_rows, start=2):
    acts = [a for _, a in sorted(actions_by_case.get(r["source_case_no"], []),
                                 key=lambda x: int(x[1]["action_seq"]) if x[1]["action_seq"].isdigit() else 0)]
    types = [a["action_type"] for a in acts]
    if r["status"] == "Transferred" and "Transferred" not in types:
        cons += 1
        report("WARN", "cases.csv", i, f"{r['source_case_no']} is Transferred but has no Transferred action",
               "add a Transferred action")
    if r["status"] == "Escalated" and "Escalated to Competent Authority" not in types:
        cons += 1
        report("WARN", "cases.csv", i, f"{r['source_case_no']} is Escalated but has no escalation action",
               "add an Escalated to Competent Authority action")
    if types and STANCE.get(types[-1]) == "CLOSING" and r["status"] != "Disposed":
        cons += 1
        report("WARN", "cases.csv", i, f"{r['source_case_no']} last action is CLOSING but status {r['status']}",
               "set status Disposed")
    if r["status"] != "Disposed" and any(STANCE.get(t) == "CLOSING" for t in types[:-1]):
        cons += 1
        report("WARN", "actions.csv", "-", f"{r['source_case_no']} has actions after a CLOSING action",
               "make the CLOSING action the last one")
    if r["status"] == "Disposed" and any(STANCE.get(t) == "CLOSING" for t in types[:-1]):
        cons += 1
        report("WARN", "actions.csv", "-", f"{r['source_case_no']} has an action after it was closed "
               f"({types})", "make the CLOSING action the last one")
    # action bureau should be the case's source bureau before a transfer, the assigned bureau after
    transferred = False
    for a in acts:
        expected = r["assigned_bureau"] if transferred else r["source_system"]
        if a["bureau"] != expected and a["action_type"] != "Transferred":
            cons += 1
            report("WARN", "actions.csv", "-", f"{r['source_case_no']} seq {a['action_seq']} "
                   f"({a['action_type']}) logged by {a['bureau']}, expected {expected}", f"set bureau {expected}")
        if a["action_type"] == "Transferred":
            transferred = True
    # officer prefix should match the bureau of the action
    for a in acts:
        m = re.match(r"Officer (\w+)-", a["officer"])
        if m and m.group(1) != a["bureau"]:
            cons += 1
            report("WARN", "actions.csv", "-", f"{r['source_case_no']} seq {a['action_seq']}: {a['officer']} "
                   f"acting for {a['bureau']}", "use an officer of that bureau")
print(f"  consistency issues found: {cons}")

# ---------------------------------------------------------------- 6. coordinates
section("6. Coordinates")
coord_seen = {}
coord_issues = 0
for i, r in enumerate(inst_rows, start=2):
    try:
        lat, lng = float(r["lat"]), float(r["lng"])
    except ValueError:
        coord_issues += 1
        report("ERROR", "institutions.csv", i, f"lat/lng not numeric ({r['lat']},{r['lng']})", "fix")
        continue
    if not (INDIA_LAT[0] <= lat <= INDIA_LAT[1] and INDIA_LNG[0] <= lng <= INDIA_LNG[1]):
        coord_issues += 1
        report("ERROR", "institutions.csv", i, f"({lat},{lng}) outside India", "fix")
    for col in ("lat", "lng"):
        dec = r[col].split(".")[1] if "." in r[col] else ""
        if len(dec) != 6:
            coord_issues += 1
            report("WARN", "institutions.csv", i, f"{col}={r[col]} has {len(dec)} decimals, expected 6",
                   "pad to 6 decimals (Excel drops trailing zeros; save lat/lng as text)")
    key = (round(lat, 6), round(lng, 6))
    if key in coord_seen:
        coord_issues += 1
        report("ERROR", "institutions.csv", i, f"same coordinates as row {coord_seen[key]}", "move the pin")
    coord_seen[key] = i
print(f"  coordinate issues: {coord_issues}")

# ---------------------------------------------------------------- 7. SYN-0040
section("7. Demo college SYN-0040")
n40 = sum(1 for r in case_rows if r["institution_id"] == "SYN-0040")
print(f"  exists: {'SYN-0040' in inst_ids}, cases: {n40}")
if "SYN-0040" not in inst_ids:
    report("ERROR", "institutions.csv", "-", "SYN-0040 missing", "add the clean demo college")
if n40:
    report("ERROR", "cases.csv", "-", f"SYN-0040 has {n40} cases, must have 0", "move those cases elsewhere")

# ---------------------------------------------------------------- 8. scenarios
section("8. Scenarios S1-S16")
md_text = (DATA / "scenarios.md").read_text(encoding="utf-8") if (DATA / "scenarios.md").exists() else ""
md_tags = set(re.findall(r"^#+\s*(S\d+)\b", md_text, flags=re.M))
by_tag = defaultdict(list)
for r in case_rows:
    if r["scenario_tag"].strip():
        by_tag[r["scenario_tag"].strip()].append(r)

# case numbers listed under each heading in scenarios.md must match the tagged cases
md_cases = {}
for block in re.split(r"^###\s+", md_text, flags=re.M)[1:]:
    tag = block.split(":")[0].strip()
    m = re.search(r"\*\*Case numbers:\*\*\s*(.+)", block)
    md_cases[tag] = {c.strip() for c in m.group(1).split(",")} if m else set()


def acts_of(c):
    return [a for _, a in actions_by_case.get(c["source_case_no"], [])]


def is_open(c):
    return c["status"] != "Disposed"


def check_s1(cs):
    return (len({c["institution_id"] for c in cs}) == 1 and {c["source_system"] for c in cs} == SYSTEMS
            and all(is_open(c) for c in cs)), "same institution, RB and PGRC, both open"


def check_s2(cs):
    return (len({c["reporter_id"] for c in cs}) == 1 and {c["source_system"] for c in cs} == SYSTEMS
            and len({c["institution_id"] for c in cs}) == 1), "same reporter, same institution, both portals"


def check_s3(cs):
    return (len({c["reporter_id"] for c in cs}) >= 3 and len({c["institution_id"] for c in cs}) == 1
            and len({c["category"] for c in cs}) == 1), ">=3 different reporters, same institution and category"


def check_s4(cs):
    enf = [c for c in cs if any(STANCE.get(a["action_type"]) == "ENFORCING" for a in acts_of(c))]
    clo = [c for c in cs if any(STANCE.get(a["action_type"]) == "CLOSING" for a in acts_of(c))]
    ok = any(e["assigned_bureau"] != k["assigned_bureau"] and e["institution_id"] == k["institution_id"]
             for e in enf for k in clo)
    return ok, "ENFORCING action in one bureau, CLOSING in another, same institution"


def check_s5(cs):
    ds = [(c["assigned_bureau"], parse_date(a["action_date"])) for c in cs for a in acts_of(c)
          if a["action_type"] == "Documents Sought"]
    ok = any(b1 != b2 and abs((d1 - d2).days) <= 10 for b1, d1 in ds for b2, d2 in ds)
    return ok, "Documents Sought by both bureaus within 10 days"


def check_s6(cs):
    return (len({c["institution_id"] for c in cs}) == 1 and len({c["category"] for c in cs}) == len(cs)), \
        "same institution, different categories (must NOT be linked as duplicate)"


def check_s7(cs):
    return (len({c["reporter_id"] for c in cs}) == 1 and len({c["institution_id"] for c in cs}) == len(cs)), \
        "same reporter, different institutions (must NOT be linked)"


def check_s8(cs):
    return (len({c["description"] for c in cs}) == 1 and len({c["institution_id"] for c in cs}) == len(cs)), \
        "identical description, different institutions (must NOT be linked)"


def check_s9(cs):
    ok = False
    for c in cs:
        ds = [parse_date(a["action_date"]) for a in acts_of(c)] or [parse_date(c["last_action_date"])]
        if c["status"] == "Pending" and (REF_DATE - max(ds)).days >= 45:
            ok = True
    return ok, f"Pending and no action for 45+ days before {REF_DATE}"


def check_s10(cs):
    soon = any(is_open(c) and 0 <= (parse_date(c["expected_disposal_date"]) - REF_DATE).days <= 3 for c in cs)
    late = any(is_open(c) and parse_date(c["expected_disposal_date"]) < REF_DATE for c in cs)
    return soon and late, f"one open case due within 3 days of {REF_DATE}, one overdue"


def check_s11(cs):
    return any(c["status"] == "Transferred" and "Transferred" in [a["action_type"] for a in acts_of(c)]
               for c in cs), "status Transferred with a Transferred action"


def check_s12(cs):
    return any(c["status"] == "Escalated" and "Escalated to Competent Authority" in
               [a["action_type"] for a in acts_of(c)] for c in cs), "status Escalated with escalation action"


def check_s13(cs):
    return all(not c["institution_id"].strip() for c in cs), "no institution_id (unlisted)"


def check_s14(cs):
    return len({c["institution_id"] for c in cs}) == 1 and len({c["category"] for c in cs}) == 1, \
        "same institution and category, different wording"


def check_s15(cs):
    inst = Counter(c["institution_id"] for c in cs).most_common(1)
    months = {c["received_date"][:7] for c in cs}
    return bool(inst) and inst[0][1] >= 8 and len(months) >= 3, ">=8 cases at one institution over 3+ months"


def check_s16(cs):
    return all(not c["institution_id"].strip() for c in cs), "no institution_id (ambiguous parent)"


CHECKS = {f"S{i}": globals()[f"check_s{i}"] for i in range(1, 17)}
for tag in SCENARIOS:
    cs = by_tag.get(tag, [])
    in_md = tag in md_tags
    if not cs:
        print(f"  FAIL {tag}: no cases tagged")
        report("ERROR", "cases.csv", "-", f"no case tagged {tag}", "tag the planted cases")
        continue
    if not in_md:
        report("ERROR", "scenarios.md", "-", f"{tag} not described", "add a section")
    listed = md_cases.get(tag, set())
    tagged = {c["source_case_no"] for c in cs}
    if in_md and listed != tagged:
        report("WARN", "scenarios.md", "-", f"{tag} lists {sorted(listed)} but cases.csv tags {sorted(tagged)}",
               "make them match")
    ok, rule = CHECKS[tag](cs)
    print(f"  {'PASS' if ok else 'FAIL'} {tag} ({len(cs)} cases, in md: {in_md}): {rule}")
    if not ok:
        fix = ("dates are relative: set the due date to demo day + 2, or let reset_demo.py shift it"
               if tag == "S10" else "adjust the planted rows")
        report("ERROR", "cases.csv/actions.csv", "-", f"{tag} does not satisfy: {rule}", fix)

# S15 spec: one repeat college with 8+ cases (overall, not only tagged)
top_inst = Counter(r["institution_id"] for r in case_rows if r["institution_id"]).most_common(3)
print(f"  institutions with most cases: {top_inst}")

# ---------------------------------------------------------------- 8b. name tests and aliases
section("8b. Name tests and aliases (resolver inputs)")
norm = lambda s: re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()
outcome_by_input = defaultdict(set)
for i, r in enumerate(test_rows, start=2):
    outcome_by_input[norm(r["typed_input"])].add((r["expected_outcome"], r["test_id"]))
    ids = [x for x in r["expected_institution_id"].split(";") if x.strip()]
    for x in ids:
        if x not in inst_ids:
            report("ERROR", "institution_name_tests.csv", i, f"expected id {x} not found", "fix ID")
    if r["expected_outcome"] == "RESOLVED" and len(ids) != 1:
        report("ERROR", "institution_name_tests.csv", i, "RESOLVED must have exactly one id", "fix")
    if r["expected_outcome"] == "NOT_LISTED" and ids:
        report("ERROR", "institution_name_tests.csv", i, "NOT_LISTED must have no id", "clear id")
    if r["expected_outcome"] == "AMBIGUOUS" and len(ids) < 2:
        report("ERROR", "institution_name_tests.csv", i, "AMBIGUOUS needs 2+ ids", "fix")
for text, outs in outcome_by_input.items():
    if len({o for o, _ in outs}) > 1:
        report("ERROR", "institution_name_tests.csv", "-",
               f"'{text}' expects different outcomes: {sorted(outs)}",
               "decide: the parent university itself is a registry row, so either RESOLVED to the parent "
               "or AMBIGUOUS across parent + children; use one rule everywhere")

alias_map = defaultdict(set)
for i, r in enumerate(alias_rows, start=2):
    alias_map[norm(r["alias"])].add(r["institution_id"])
    if re.search(r"\b(of|and|the|for)$", r["alias"].strip(), flags=re.I):
        report("WARN", "institution_aliases.csv", i, f"alias '{r['alias']}' ends mid-phrase",
               "use a real short name (e.g. drop 'of')")
official = {norm(r["official_name"]): r["institution_id"] for r in inst_rows}
for a, ids in alias_map.items():
    if a in official and official[a] not in ids:
        report("WARN", "institution_aliases.csv", "-",
               f"alias '{a}' is the official name of {official[a]} but points to {sorted(ids)}",
               "remove it, or include the parent itself so the resolver shows parent + children")
    if len(ids) > 1:
        groups = {inst_by_id[x]["parent_id"] or x for x in ids if x in inst_by_id}
        if len(groups) > 1:
            report("WARN", "institution_aliases.csv", "-", f"alias '{a}' maps to unrelated {sorted(ids)}",
                   "ok only if meant to be ambiguous")
print(f"  aliases: {len(alias_rows)}, distinct: {len(alias_map)}, "
      f"types: {dict(Counter(r['alias_type'] for r in alias_rows))}")

# ---------------------------------------------------------------- 9. privacy
section("9. Privacy")
priv = 0
for i, r in enumerate(rep_rows, start=2):
    if not r["email"].lower().endswith("@example.com"):
        priv += 1
        report("ERROR", "reporters.csv", i, f"email {r['email']} not @example.com", "use @example.com")
    if not re.fullmatch(r"0{4,}\d{1,6}", r["phone"]) or len(r["phone"]) != 10:
        priv += 1
        report("ERROR", "reporters.csv", i, f"phone {r['phone']} is not placeholder style", "use 00000000NN")
text_fields = ([("institutions.csv", i, r["official_name"]) for i, r in enumerate(inst_rows, start=2)]
               + [("institution_aliases.csv", i, r["alias"]) for i, r in enumerate(alias_rows, start=2)]
               + [("institution_name_tests.csv", i, r["typed_input"]) for i, r in enumerate(test_rows, start=2)]
               + [("cases.csv", i, r["title"] + " " + r["description"]) for i, r in enumerate(case_rows, start=2)])
suspicious = []
for f, i, t in text_fields:
    low = " " + t.lower() + " "
    for w in REAL_NAME_HINTS:
        if re.search(r"\b" + re.escape(w) + r"\b", low):
            suspicious.append((f, i, w, t[:60]))
for f, i, w, t in suspicious:
    report("CHECK", f, i, f"contains '{w}' (looks like a real name?): {t}", "confirm it is fictional")
print(f"  privacy errors: {priv}; suspicious real-name hits: {len(suspicious)}")
print("  institution names (check by eye that none is a real college):")
for r in inst_rows:
    print(f"    {r['institution_id']}  {r['official_name']}  ({r['district']}, {r['state']})")

# ---------------------------------------------------------------- 10. problems table
section("10. Problems table")
order = {"ERROR": 0, "WARN": 1, "CHECK": 2}
problems.sort(key=lambda p: (order[p[0]], p[1]))
if not problems:
    print("  No problems found.")
else:
    print(f"  {'LEVEL':6} | {'FILE':26} | {'ROWS':14} | PROBLEM -> SUGGESTED FIX")
    print("  " + "-" * 100)
    # the same problem on many rows is printed once, with the row list
    groups = defaultdict(list)
    for level, f, row, msg, fix in problems:
        groups[(level, f, fix)].append((row, msg))
    for (level, f, fix), items in groups.items():
        if len(items) > 3:
            rows = ",".join(r for r, _ in items[:8] if r != "-") + ("..." if len(items) > 8 else "")
            msg = f"{len(items)}x, e.g. {items[0][1]}"
            print(f"  {level:6} | {f:26} | {rows or '-':14} | {msg}" + (f" -> {fix}" if fix else ""))
        else:
            for row, msg in items:
                print(f"  {level:6} | {f:26} | {row:14} | {msg}" + (f" -> {fix}" if fix else ""))
counts = Counter(p[0] for p in problems)
print(f"\nSUMMARY: {counts.get('ERROR', 0)} errors, {counts.get('WARN', 0)} warnings, "
      f"{counts.get('CHECK', 0)} to check by hand")
sys.exit(1 if counts.get("ERROR") else 0)
