# PROGRESS.md

## Done
- Dataset validated and fixed (data/validate_dataset.py reports 0 errors; originals in data/backup_before_fix/).
- **M0** scaffold: folder structure, pinned requirements, hub backend that starts (health + 501 stubs for all 19 features), two placeholder portals, React dashboard shell with "Coming soon" pages, run_all.py, FEATURES.md.

- **M1** 14 tables, CSV loader (`python -m app.seed` from hub/backend): 40 institutions, 212 aliases, 80 reporters, 150 cases, 350 actions, config tables. 3 cases without an institution get status `unverified_institution`.

## Next
- **M2** registry API + resolver (tested against data/institution_name_tests.csv), then M4 intake, M6 overlap detection, M7 confirm/reject, M8 dashboard.

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
