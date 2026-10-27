# Demo voice-over script (6 members, total 2:58, limit 3:00)

Record your voice while watching the matching clip. Speak at a calm pace, about 2 words per second. Clips are in `demo/output/`; `demo_full.mp4` is all six joined.

| # | Member | Clip | Length |
|---|--------|------|--------|
| 1 | Member 1 | 1_member1_architecture | 16 s |
| 2 | Member 2 | 2_member2_finder_and_map | 38 s |
| 3 | Member 3 | 3_member3_corroboration_live | 63 s |
| 4 | Member 4 | 4_member4_officer_actions | 23 s |
| 5 | Member 5 | 5_member5_dashboard_and_reports | 23 s |
| 6 | Member 6 | 6_member6_government_fit | 16 s |

## 1. Member 1: the problem and the architecture (16 s, about 36 words)
Architecture slide (0:00-0:10):
"Complaints about one college reach different AICTE bureaus separately, so nobody sees the full picture. We add one hub behind the existing portals. The portals stay untouched, and the hub does the analysis."
Portals on screen (0:10-0:15):
"Here are the two portals, the Regulation Bureau and the Public Grievance Cell, each with its own database."

## 2. Member 2: Institution Finder, map, verification (38 s, about 75 words)
"Every reporter starts by finding the college. If unsure, a few questions narrow it down, and if it is not listed, the reporter says so and an officer assigns it later. Our search forgives mistakes: 'kstora' and 'estora' both find Kestora, and typos in a full name still work. The reporter confirms the college on a card with its location from the registry, so it can be verified. Verification here is a mock OTP; in production it would be Aadhaar through DigiLocker."

## 3. Member 3: the complaint hub and live corroboration (63 s, about 115 words)
"Now a second, independent reporter files on the other portal about the same lab problem. Next, the hub: sign-in is role based, with one account per role. Here is our core idea, corroboration. Two different reporters, same college, same problem, and the hub suggests linking them, with the reasons shown. It only suggests. The officer reads the reasons, adds a note and confirms; that is the human in the loop. Only after confirmation does the priority rise, and the boost is capped so fake complaints cannot game it. The case file can be downloaded for the record. The other overlap types, cross-bureau, conflicting actions and same-reporter duplicates, are in the same screen."

## 4. Member 4: officer actions (23 s, about 45 words)
"Officers act inside the hub: enforcement actions, transfer, escalation, remarks and next action. Each action is checked against the other bureau's actions for conflicts. The history shows who did what and when, and the audit trail records every decision."

## 5. Member 5: dashboard, search, alerts, reports (23 s, about 45 words)
"Senior management sees live numbers: pending, disposed, transferred, escalated and overdue. Search works by college name, AICTE ID or case ID, with filters. Alerts show what needs a decision and what is running late. Reports export to CSV, and Insights uses plain rules."

## 6. Member 6: government fit and close (16 s, about 30 words)
"The hub reads from existing systems, so legacy portals keep their own pace and databases. It scales by moving to PostgreSQL and a queue. The system suggests, officers decide. Thank you."

## Recording the clips again
On your laptop (the real map needs internet, so the map tile will show properly there):
```
python reset_demo.py
python run_all.py          (leave running; open a second terminal)
pip install -r demo/requirements-demo.txt
python -m playwright install chromium
python demo/record_demo.py
```
Run `reset_demo.py` again before any re-run.
