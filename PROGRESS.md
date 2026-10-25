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
- **Next: M9** conflict rules (enforcing vs closing, duplicate action) and the lead-bureau suggestion on the overlap and conflict alerts.

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
