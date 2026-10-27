# SIH 2026 · PS 26264 · Demo video: voice-over script (6 members, about 3 minutes)

Each member speaks for about 28 seconds (55 to 65 words) over a silent screen clip of the same length. Total about 3 minutes.
Read slowly and clearly. Record each part separately in a quiet room, then place it on its clip. Every sentence is something the prototype really does; if you change a line, keep it true.

| Order | Member | Topic | Clip file |
|---|---|---|---|
| 1 | Member 1 (opener) | Problem, idea, architecture | `1_member1_architecture` |
| 2 | Member 2 | Institution Finder, map, verification | `2_member2_finder_and_map` |
| 3 | Member 3 | Types of overlap, corroboration, conflict | `3_member3_overlap_detection` |
| 4 | Member 4 | What officers do | `4_member4_officer_actions` |
| 5 | Member 5 | Dashboard, search, alerts, reports | `5_member5_dashboard_and_reports` |
| 6 | Member 6 (closer) | Government fit, privacy, future, close | `6_member6_government_fit` |

Suggestion: the person who understands the matching rules best takes part 3. Swap members freely; keep the order of topics.

---

## Part 1 · Member 1: problem, idea, architecture
*Screen: architecture diagram, the RB portal, the PGRC portal.*

"We are Team ____, with our prototype for problem statement 26264. The Regulation Bureau and the Grievance Cell run separate portals, so complaints about the same college overlap, duplicate or conflict, and nobody sees it. Our answer is a hub behind both portals, which stay unchanged. It checks every complaint, compares it within that one institution, and gives officers a single view. Officers decide; the system only suggests."

## Part 2 · Member 2: Institution Finder, map, verification
*Screen: typing the college name, confirmation card with map, mobile verification, complaint, receipt.*

"Every complaint starts with our Institution Finder. The reporter types a name, even with a spelling mistake, and confirms the exact college: official name, AICTE ID, address and its location on a map. If unsure, simple questions narrow it down. The hub never guesses a college. Next comes mobile verification, a demo code here and Aadhaar or DigiLocker in production, then the receipt. The map can grow into 'colleges near me'."

## Part 3 · Member 3: overlaps, corroboration, conflict
*Screen: PGRC portal, then the hub Overlaps page and its filters.*

"A second reporter now files on the other portal. Instantly the hub raises: Potential Overlapping Cases, Coordination Required, with reasons and a suggested lead bureau. Matching runs only inside one institution. Other types: corroboration by independent reporters, capped, and counted only after an officer confirms; the same reporter filing twice; and conflicts, like a show-cause notice from one bureau and a closure from another."

## Part 4 · Member 4: what officers do
*Screen: confirm the link with a note, log a show-cause action with a next step, action history, audit trail.*

"The officer reads the reasons, adds a note and confirms the link; a rejected pair never returns. Then they log an action: update, ask the institution, enforce, close, transfer or escalate. The hub checks it against what the other bureau has done, and the officer records the next action required. Every action is in the case history, and every decision is in the audit trail."

## Part 5 · Member 5: dashboard, search, alerts, reports
*Screen: dashboard, Cases search, Alerts, Reports, Insights.*

"For management, the dashboard shows live numbers: cases by status, bureau workload and institution-wise status, refreshed every minute. Search by name, AICTE ID or case ID, and filter by bureau, region, status and date. Alerts show what needs a decision and the stalled or overdue cases. Reports export to CSV, and Insights gives plain findings, each with its rule."

## Part 6 · Member 6: government fit, privacy, future, close
*Screen: "Built for government servers" slide, the sign-in page with all roles, the dashboard.*

"Built for government servers: matching is per institution, SQLite today and PostgreSQL to scale, text similarity runs locally with no paid cloud. Existing portals stay unchanged, send one call with an API key, and retry if the hub is down. Bureau rules are editable tables, reporter phones are only hashed. Future scope: Aadhaar, DigiLocker, single sign-on, SMS. One hub, one view, and officers decide. Thank you."

---

## Optional (10 seconds, only if the total stays under 3 minutes)
The n8n teammate's Telegram clip can follow Part 3, labelled "Demo replay: production portals call the hub directly".

## Recording tips
1. Play your clip muted and read your part once while watching.
2. Record in a quiet room with the mic close; do not read faster than normal.
3. Keep each member's audio as a separate file, place it on its clip in any editor (Clipchamp, CapCut), then join the six clips in order.
4. Note for the editor: the map pane is blank in clips recorded without internet. Re-run `python demo/record_demo.py` on a machine with internet to get the real map.
