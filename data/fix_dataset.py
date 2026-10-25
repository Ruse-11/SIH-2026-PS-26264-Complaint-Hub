import csv, sys, re, zlib
from datetime import date, timedelta
from collections import defaultdict
SRC, DST = sys.argv[1], sys.argv[2]
CAP = date(2026, 10, 22)
def rd(n):
    with open(f"{SRC}/{n}", newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f); return r.fieldnames, list(r)
def wr(n, h, rows):
    with open(f"{DST}/{n}", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=h, lineterminator="\n"); w.writeheader(); w.writerows(rows)
d = lambda s: date.fromisoformat(s)
def conflicts(cases, acts):
    by = defaultdict(list)
    for a in acts: by[a['source_case_no']].append(a)
    n = 0
    cs = [c for c in cases if c['institution_id']]
    for i, x in enumerate(cs):
        for y in cs[i+1:]:
            if x['institution_id'] != y['institution_id'] or x['assigned_bureau'] == y['assigned_bureau']: continue
            for a in by[x['source_case_no']]:
                for b in by[y['source_case_no']]:
                    if abs((d(a['action_date'])-d(b['action_date'])).days) <= 30 and (
                       (a['action_type'] in ('Show-Cause Notice Issued','Inspection Ordered') and b['action_type'].startswith(('Closed','Disposed'))) or
                       (b['action_type'] in ('Show-Cause Notice Issued','Inspection Ordered') and a['action_type'].startswith(('Closed','Disposed')))):
                        n += 1
    return n
log = []
# ---- institutions: types from name, 6-decimal coords
h, inst = rd("institutions.csv")
for r in inst:
    for w in ("University","Pharmacy","Architecture","Management","Engineering"):
        if w in r['official_name'] and r['institution_type'] != w:
            log.append(f"{r['institution_id']} type {r['institution_type']} -> {w}"); r['institution_type'] = w
    for k in ('lat','lng'):
        v = r[k]; dec = v.split('.')[1] if '.' in v else ''
        if len(dec) != 6: r[k] = f"{float(v):.6f}"
wr("institutions.csv", h, inst)
# ---- aliases: strip dangling " of"
h, al = rd("institution_aliases.csv")
seen, out = set(), []
for r in al:
    if re.search(r"\sof$", r['alias'].strip()):
        old = r['alias']; r['alias'] = r['alias'].strip()[:-3]; log.append(f"alias '{old}' -> '{r['alias']}'")
    k = (r['alias'].lower(), r['institution_id'])
    if k in seen: log.append(f"dropped duplicate alias {k}"); continue
    seen.add(k); out.append(r)
wr("institution_aliases.csv", h, out)
# ---- name tests: parent names are AMBIGUOUS everywhere
h, tests = rd("institution_name_tests.csv")
kids = {"SYN-0009": "SYN-0010;SYN-0011;SYN-0012", "SYN-0013": "SYN-0014;SYN-0015;SYN-0016", "SYN-0001": "SYN-0002;SYN-0003;SYN-0004"}
for r in tests:
    if r['test_id'] in ('TEST-014','TEST-015'):
        r.update(expected_outcome="AMBIGUOUS", expected_institution_id=kids[r['expected_institution_id']], note="Parent university name matches multiple constituent colleges; never auto-pick")
    if r['test_id'] == 'TEST-044':
        r.update(typed_input="ZENVORA COLLEGE OF ARCHITECTURE", expected_institution_id="SYN-0004")
wr("institution_name_tests.csv", h, tests)
# ---- cases and actions
ch, cases = rd("cases.csv"); ah, acts = rd("actions.csv")
cb = {c['source_case_no']: c for c in cases}
before = conflicts(cases, acts)
# SYN-0040 -> spread over quiet colleges
quiet = ["SYN-0033","SYN-0034","SYN-0035","SYN-0036","SYN-0037","SYN-0038","SYN-0039"]
for c, q in zip([c for c in cases if c['institution_id']=="SYN-0040"], quiet):
    log.append(f"{c['source_case_no']} institution SYN-0040 -> {q}"); c['institution_id'] = q
# PGRC-2026-0004: nothing after the closing action
acts = [a for a in acts if not (a['source_case_no']=="PGRC-2026-0004" and a['action_seq']=="3")]
# RB-2026-0012 (S11): consistent bureaus/officers
for a in acts:
    if a['source_case_no']=="RB-2026-0012":
        if a['action_seq']=="1": a['bureau']="RB"
        if a['action_seq']=="3": a['bureau']="PGRC"; a['officer']="Officer PGRC-12"
cb["RB-2026-0012"]['assigned_officer'] = "Officer PGRC-12"
by = defaultdict(list)
for a in acts: by[a['source_case_no']].append(a)
n_doc = 0
def add(c, typ, bureau, days, remark):
    global n_doc
    L = sorted(by[c['source_case_no']], key=lambda x: int(x['action_seq']))
    last = d(L[-1]['action_date']); nd = min(last + timedelta(days=days), CAP)
    n_doc += 1
    a = dict(source_case_no=c['source_case_no'], action_seq=str(int(L[-1]['action_seq'])+1), action_date=nd.isoformat(),
             bureau=bureau, officer=f"Officer {bureau}-{(zlib.crc32(c['source_case_no'].encode())%12)+1:02d}", action_type=typ,
             remarks=remark, doc_ref="")
    by[c['source_case_no']].append(a); acts.append(a); log.append(f"{c['source_case_no']} +{typ} {a['action_date']}")
for c in cases:
    types = [a['action_type'] for a in by[c['source_case_no']]]
    other = "PGRC" if c['source_system']=="RB" else "RB"
    if c['status']=="Transferred" and "Transferred" not in types:
        add(c, "Transferred", c['source_system'], 3, f"Synthetic transfer from {c['source_system']} to {other}.")
        c['assigned_bureau'] = other; c['assigned_officer'] = f"Officer {other}-{(zlib.crc32(c['source_case_no'].encode())%12)+1:02d}"
    elif c['status']=="Escalated" and "Escalated to Competent Authority" not in types:
        add(c, "Escalated to Competent Authority", c['assigned_bureau'], 2, "Synthetic escalation to the competent authority.")
    elif c['status']=="Disposed" and not any(t.startswith(("Closed","Disposed")) for t in types):
        t = "Disposed - Action Taken" if zlib.crc32(c['source_case_no'].encode())%2 else "Disposed - Unsubstantiated"
        base = conflicts(cases, acts)
        add(c, t, c['assigned_bureau'], 3, "Synthetic final disposal of the complaint.")
        if conflicts(cases, acts) > base:  # would create an unplanned conflict: undo, keep S4 the only one
            bad = by[c['source_case_no']].pop(); acts.remove(bad); n_doc -= 1
            log.append(f"{c['source_case_no']} disposal action skipped (would create an unplanned conflict)")
# doc_ref for new rows
k = max(int(re.search(r"(\d+)", a['doc_ref']).group(1)) for a in acts if a['doc_ref'])
for a in acts:
    if not a['doc_ref']: k += 1; a['doc_ref'] = f"synthetic_action_{k:04d}.pdf"
# last_action_date = latest action
for c in cases:
    L = by[c['source_case_no']]
    if L: c['last_action_date'] = max(a['action_date'] for a in L)
acts.sort(key=lambda a: (a['source_case_no'], int(a['action_seq'])))
orig_order = [c['source_case_no'] for c in rd("actions.csv")[1]]
seen=[]; [seen.append(x) for x in orig_order if x not in seen]
pos = {x:i for i,x in enumerate(seen)}
acts.sort(key=lambda a: (pos[a['source_case_no']], int(a['action_seq'])))
wr("cases.csv", ch, cases); wr("actions.csv", ah, acts)
print("\n".join(log[-0:]) if "-v" in sys.argv else f"{len(log)} changes; actions now {len(acts)}")
print("planted-style conflicts (ENFORCING in one bureau vs closed in the other, same college, 30d): before", before, "after", conflicts(cases, acts))
