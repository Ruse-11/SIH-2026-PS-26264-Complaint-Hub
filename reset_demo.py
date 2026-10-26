"""Resets the whole demo to a clean, current, seeded state with ONE command.   python reset_demo.py

What it does
  1. Rebuilds the hub database from data/*.csv (150 cases, 40 colleges, ...). Anything you filed while demoing disappears.
  2. Shifts every case date so the dataset's "today" (25 Oct 2026) becomes the real today. Deadlines and stalled cases
     then line up with the demo script: for example scenario S10 is due in 3 days again.
  3. Empties the two mock portals' own databases (their complaints and OTP codes) and restarts their case numbers
     at 1001, WITHOUT deleting the files, so the portals can stay running.
  4. Prints a short check, including that SYN-0040 (the clean demo college for the n8n replay) has no cases.

Options
  --no-shift           load the dataset exactly as written (25 Oct 2026 = today)
  --keep-portals       leave the portals' databases alone

The hub and portals may be running while you reset; refresh the browser afterwards.
Use it before every rehearsal, before recording the video, and to restore the demo in one command.
"""
import argparse
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "hub" / "backend"))

PORTAL_DBS = [ROOT / "portal_rb" / "rb.db", ROOT / "portal_pgrc" / "pgrc.db"]
DEMO_COLLEGE = "SYN-0040"


def clear_portal_db(path: Path) -> str:
    """Delete the portal's complaints and OTP codes but keep the file and tables (the portal may be running)."""
    if not path.exists():
        return f"{path.name}: not created yet (nothing to clear)"
    con = sqlite3.connect(path, timeout=10)
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        removed = 0
        for t in ("submissions", "otp"):
            if t in tables:
                removed += con.execute(f"DELETE FROM {t}").rowcount
        if "sqlite_sequence" in tables:
            con.execute("DELETE FROM sqlite_sequence WHERE name='submissions'")  # case numbers start again at 1001
        con.commit()
        return f"{path.name}: cleared {removed} rows, numbering restarts at 1001"
    finally:
        con.close()


def main():
    ap = argparse.ArgumentParser(description="Reset the demo to a clean seeded state.")
    ap.add_argument("--no-shift", action="store_true", help="do not move the dataset dates")
    ap.add_argument("--keep-portals", action="store_true", help="do not clear the portal databases")
    args = ap.parse_args()

    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    from app import config, models as m, seed
    from app.db import engine

    today = date.today()
    shift = 0 if args.no_shift else (today - seed.DATASET_TODAY).days
    print(f"Hub database: {config.DATABASE_URL}")
    print(f"Dates: dataset 'today' {seed.DATASET_TODAY} -> {today} (shift {shift:+d} days)")
    counts = seed.run(engine, shift_days=shift)
    print("Seeded:", json.dumps(counts))

    if not args.keep_portals:
        for p in PORTAL_DBS:
            print("Portal:", clear_portal_db(p))

    with Session(engine) as db:
        demo_cases = db.scalar(select(func.count()).select_from(m.Case).where(m.Case.institution_id == DEMO_COLLEGE))
        due_soon = db.scalar(select(func.count()).select_from(m.Alert).where(m.Alert.type == "DUE_SOON"))
        inst = db.get(m.Institution, DEMO_COLLEGE)
    print(f"Check: {DEMO_COLLEGE} ({inst.official_name if inst else 'MISSING'}) has {demo_cases} cases (should be 0); due-soon alerts: {due_soon}")
    ok = inst is not None and demo_cases == 0
    print("Ready. Refresh the dashboard and the portals." if ok else "WARNING: the demo college is not clean, check the dataset.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
