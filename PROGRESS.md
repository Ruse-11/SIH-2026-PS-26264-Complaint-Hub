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
- **Next: M7** officer confirm/reject + audit + priority update, then M8 dashboard.

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
