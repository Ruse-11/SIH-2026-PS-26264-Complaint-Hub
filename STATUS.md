# Complaint Monitoring Hub: what is built, what is left, what we can add
Status as of 26 Oct 2026 (after M13, all planned modules built). Source of truth for the plan: CLAUDE.md. Per-feature file map: FEATURES.md.
Test status: 127 automated tests pass. Code is on GitHub `main`.

## 1. Built and working (DONE)

### Reporter side (mock portals, not the real AICTE portals)
- RB portal (:8001) and PGRC portal (:8002), each with its own database and its own case numbers.
- Institution Finder on both: type a name, live suggestions, confirm card with address and map pin, guided questions (state, district, type, area, programs), "my institution isn't listed".
- Mock OTP, signed 30-minute token carrying the confirmed institution ID, complaint form, receipt.
- If the hub is down, the complaint waits (sync pending) and is re-sent automatically.
- The receipt shows the alerts raised (`alerts_created`).

### Hub: intake and data
- `POST /api/intake` with an API key per portal. Validates the institution ID. The hub never guesses a college.
- Reporter contact is stored only as a hash.
- Unlisted-college complaints go to the Needs Review queue, where an officer picks the college. The typed name becomes a learned alias.
- Synthetic dataset loader: 40 institutions, 212 aliases, 80 reporters, 150 cases, 350 actions.
- Institution registry with search, name resolver (passes all 45 name tests), profile and complaint history.

### Detection (the novelty)
- A: same reporter on both portals (duplicate suggestion).
- B: different reporters, same category, similar text (corroboration, "N independent reporters").
- C: open cases in two or more bureaus at one college ("Potential Overlapping Cases – Coordination Required").
- Conflict: an enforcing action in one bureau against a closing action in another (30 days). Duplicate action: both bureaus took the same enforcing or requesting action (10 days).
- Lead-bureau suggestion by ordered rules, with the rule shown. The competent authority makes the final decision.
- Every suggestion stores its reasons. Rejected pairs are never re-suggested.
- Text similarity: TF-IDF plus keyword overlap, with optional local embeddings (off by default; works on your laptop).

### Officer workflow
- Confirm or reject every suggestion, with an optional note and an instant on-screen confirmation.
- Priority score with corroboration boost applied only after an officer confirms. Distinct reporters only, capped.
- Log actions on a case: acknowledge, review, show-cause, close and so on, plus transfer and escalate. A remark and a document reference can be added.
- Chronological case history with officer, bureau, timestamp, remarks.
- Alerts: overlap, duplicate, corroboration, conflict, duplicate action, due soon, overdue, escalation suggested, stalled, pending reminder, escalated. Repeat-safe scan on start, every 30 minutes and after each action.
- Audit trail of every decision, assignment and export, with an Audit trail screen for senior management and the competent authority.

### Dashboard and search
- KPIs: total, pending, under process, disposed, transferred, escalated, pending beyond timeline.
- Institution-wise status, bureau-wise workload, category chart, waiting-for-decision panel, stalled and deadline watch.
- Cases page: search by institution name, AICTE ID, case ID (with college suggestions as you type). Filters by bureau, region, category, status, dates, beyond timeline. Sort and paging.
- Download case file (CSV of the filtered list, audited).
- Institution profile, overlaps page, alerts page with a filter for every type, Needs Review page.

### Reports and insights
- Reports: bureau, region, status, institution history, ageing (0-7, 8-15, 16-30, over 30 days), disposal rate, overlaps, monthly, quarterly. CSV export is audited and formula-safe.
- Insights panel: plain rules over live numbers, each card shows the rule that fired and a link.

### Roles (seeded accounts, password `demo123`)
`rb.officer`, `pgrc.officer`, `other.bureau`, `regional.south`, `senior.mgmt`, `competent.authority`. Each sees only its scope. Senior management is read-only. A banner on the dashboard says what each role can do.

## 2. Not built yet (planned)

| Item | Why it matters | Effort |
|---|---|---|
| ~~M13: `reset_demo.py` and n8n replay support~~ | **DONE 26 Oct.** `python reset_demo.py` resets and re-dates the demo; `n8n/README.md` and `n8n/replay_check.py` support the teammate's workflow. | Done |
| Explicit "next action" field on a case | PS "should" item. Expected disposal date and last action are shown, but there is no editable next-action field. | Small |
| Supporting-document reference on the case page | A document reference can be typed when logging an action. There is no list or upload. | Small |
| Real-time push to the browser | The screens refresh on load or action, not live. The backend recomputes on every request. | Medium, can be skipped |
| Frontend automated tests | Backend is tested (127). The React screens were checked by browser scripts, not kept as tests. | Medium |

## 3. Future scope (stub files exist, return "planned")
Case graph view, Attention Index, email/SMS notifications, document storage, local-LLM summaries, real Aadhaar/DigiLocker/OTP, real SSO, PostgreSQL migration, integration with the real AICTE portal, multilingual matching, "colleges near me" and pin drop.

## 4. Known limits (say these honestly to judges)
- All data is synthetic. The bureau rules (category ownership, action stances, SLA days, thresholds) are assumptions about AICTE mandates, stored in editable tables.
- "Related category" for conflicts means the same category.
- Thresholds T_A 0.20 and T_B 0.35 were tuned on the synthetic data with TF-IDF. With embeddings on they may need re-tuning.
- Quarters follow the Indian financial year (assumption).
- SQLite and one server; development secrets in config. Production would use PostgreSQL, real secrets, HTTPS, a queue.
- Officers log actions in the hub UI for the prototype. Production would have bureau systems call an API (stubbed).
- A reporter-confirmed college is not guaranteed true; officers see how each college was resolved.
- The type column in `institutions.csv` has some odd values (question to the dataset teammate, still open).
- The suggestion dropdown works with the mouse, not arrow keys.

## 5. What we can build further (ideas, best value first, none is in the PS "must")
1. **Demo polish:** `reset_demo.py`, a "demo mode" banner, and a one-page script for the 3-minute demo (reporter files on RB, then PGRC, overlap alert, officer confirms).
2. **Why-this-match panel:** show the two complaint texts side by side with shared words highlighted on the overlap card, so a judge sees why it matched.
3. **Threshold tuning screen** (senior management): edit T_A, T_B, SLA days, stalled days in the browser, with a "what would change" preview.
4. **Case graph view:** colleges, cases, links as a small network picture. Strong visual for the PPT.
5. **Institution Attention Index:** one score per college combining repeat complaints, overdue cases, conflicts. A ranked "colleges to look at" list.
6. **Document references list** per case, with upload for the prototype.
7. **Notifications:** an in-app bell with unread alerts per role. Email/SMS stays future scope.
8. **Accessibility and mobile:** keyboard navigation in suggestions, larger tap targets, Hindi labels on the portal forms.
9. **Evaluation page:** run the planted scenarios S1-S16 and show a pass table (hits, false links avoided). Good evidence for "how do you avoid false links?"
10. **Production-readiness slide with code backing:** PostgreSQL via config, an indexed institution column, a job queue note.

## 6. Suggested plan for the remaining days
- **Now:** run `python reset_demo.py`, rehearse the demo, record the fallback demo video.
- **Then:** pick one or two from section 5 (my pick: "why this match" panel, then the evaluation page).
- **Feature freeze:** evening of 26 Oct, as planned. 27 Oct is for the video, PPT and a full test run. 28 Oct is buffer only.
