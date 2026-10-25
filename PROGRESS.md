# PROGRESS.md

## Done
- Dataset validated and fixed (data/validate_dataset.py reports 0 errors; originals in data/backup_before_fix/).
- **M0** scaffold: folder structure, pinned requirements, hub backend that starts (health + 501 stubs for all 19 features), two placeholder portals, React dashboard shell with "Coming soon" pages, run_all.py, FEATURES.md.

## Next
- **M1** models + CSV seed loader (map CSV columns: institution_id, received_date, source_case_no).
- Then M2 registry + resolver, M4 intake, M6 overlap detection, M7 confirm/reject, M8 dashboard.

## Run (Windows, from the project folder)
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cd hub\frontend && npm install && cd ..\..
python run_all.py
```
