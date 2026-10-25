# PROGRESS.md

## Done
- Dataset validated and fixed (data/validate_dataset.py reports 0 errors; originals in data/backup_before_fix/).
- **M0** scaffold: folder structure, pinned requirements, hub backend that starts (health + 501 stubs for all 19 features), two placeholder portals, React dashboard shell with "Coming soon" pages, run_all.py, FEATURES.md.

- **M1** 14 tables, CSV loader (`python -m app.seed` from hub/backend): 40 institutions, 212 aliases, 80 reporters, 150 cases, 350 actions, config tables. 3 cases without an institution get status `unverified_institution`.
- **M2** `GET /api/institutions/search?q=` (resolver), `/filters` (guided questions), `/{id}` (profile). Passes all 45 name tests.
- **M3** login: `POST /api/auth/login`, `GET /api/auth/me`, 6 demo accounts (password demo123), role rules, login page with one-click role buttons, header shows role and what it can see.
- **M4** `POST /api/intake` (X-API-Key per portal): validates the institution ID (never guesses; parent universities rejected), hashes the reporter contact, creates case HUB-nnnn + first action "Acknowledged" + audit row; resending a case number is safe. `GET /api/cases/{id}` shows a case with its history.
- **M5** RB portal http://localhost:8001 and PGRC portal http://localhost:8002: Institution Finder -> mock OTP -> complaint form -> receipt. Portal case numbers start at 1001 (RB-2026-1001). If the hub is down the complaint waits (sync pending) and is re-sent every 10 s.
- **M5 fix** Portal: removed the red error that showed on the "Verify your phone" step. Guided questions: every dropdown now lists all its choices, so you can change State directly; answers that no longer fit are cleared automatically.

## Next
- **M6 DONE** Overlap detection A/B/C (TF-IDF baseline), suggestions with reasons, alerts, `alerts_created` in the receipt, `GET /api/matching/links`, `GET /api/alerts`. Dataset is backfilled at seed time. T_A=0.20 and T_B=0.35 are tuned placeholders for the TF-IDF baseline.
- **M7 DONE** `POST /api/matching/links/{id}/confirm|reject` (note optional), `POST /api/alerts/{id}/acknowledge`, `GET /api/audit` (senior mgmt + competent authority), `GET /api/corroboration/{case_id}` (priority breakdown). Priority = severity x10 + confirmed corroborators (max 4) x5 + age (max 60 days) x0.3; the boost applies only after confirmation.
- **M8 DONE** Dashboard screens: KPI tiles, waiting-for-decision panel, bureau workload, institution-wise status, category chart, cases list (search by institution name, AICTE ID, case ID; filters bureau, region, category, status, dates, beyond timeline, sort, paging), case detail (priority breakdown, action history, Confirm/Reject), institution profile with chronological history, overlaps (grouped by college), alerts (acknowledge), Needs Review (assign a college, learned alias). Role scoping everywhere: officers see their bureau, regional office its region, senior management and competent authority everything. APIs: `GET /api/dashboard/kpis`, `GET /api/cases` (+ `/filters`, `/needs-review`, `POST /{id}/assign-institution`), `GET /api/search`, `GET /api/institutions/{id}/history`.
- **M8 follow-up** Search boxes (header and Cases page) suggest colleges while you type; Confirm or Reject shows a message with the priority change; fixed a bug where a second confirm in the same cluster did not update priority (tests now use the same no-autoflush session as the real app).
- **M9 DONE** Conflict rule (ENFORCING in one bureau vs CLOSING in another, same college and category, within 30 days) and duplicate-action rule (same enforcing or requesting action in both bureaus within 10 days), both as suggestions with reasons and a critical or warning alert. The seed finds exactly S4 and S5. Officers can now log actions on a case (`POST /api/cases/{id}/actions`, `GET /api/cases/action-types`): closing disposes, transfer moves the case, escalate sets Escalated, and every logged action re-checks conflicts. Lead bureau: ordered rules shown with the rule that fired and always recomputed from the latest actions; the competent authority records the final lead (`POST /api/conflicts/{link_id}/lead`), kept next to the suggestion and audited. Also fixed: a slow old answer could overwrite a newer one on screens with filters.
- **M10 DONE** Stalled and SLA alerts. Per open case, at most one alert per track: deadline (DUE_SOON within 3 days, OVERDUE, ESCALATION_SUGGESTED when 30+ days late) and activity (STALLED after 30 days without action, PENDING_REMINDER after 7 days still Pending); ESCALATED for cases with the competent authority. All limits are rows in the thresholds table. The scan runs when the hub starts, every 30 minutes, after seeding and after each logged action; it is repeat-safe, refreshes day counts, clears alerts whose reason is gone, and never re-raises one an officer acknowledged. `GET /api/starvation` (live lists, worst first, as_of date for demos), `POST /api/starvation/scan`. Dashboard has a "Stalled and deadline watch" panel; Alerts page filters by every type. Alerts list is critical first.
- **Next: M11** reports, CSV export, ageing analysis, disposal rate, monthly/quarterly reports, Insights panel, role view polish.

## Run (Windows, from the project folder)
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cd hub\frontend && npm install && cd ..\..
cd hub\backend
python -m app.seed
cd ..\..
python run_all.py
```
