"""M13 test: reset_demo.py (date shift, portal clean-up, demo college check).
Run from the project root:  python -m unittest discover -s hub/backend/tests -v
"""
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "hub" / "backend"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import models as m, seed  # noqa: E402
import reset_demo  # noqa: E402


class ResetDemoTest(unittest.TestCase):
    def make_db(self, shift):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        engine = create_engine(f"sqlite:///{Path(tmp.name, 'h.db').as_posix()}")
        self.addCleanup(engine.dispose)
        seed.run(engine, shift_days=shift)
        return engine

    def test_shift_moves_every_date_by_the_same_days(self):
        a, b = self.make_db(0), self.make_db(5)
        with Session(a) as da, Session(b) as db:
            ca = {c.hub_case_id: c for c in da.scalars(select(m.Case))}
            cb = {c.hub_case_id: c for c in db.scalars(select(m.Case))}
            self.assertEqual(set(ca), set(cb))
            for k in ca:
                self.assertEqual(cb[k].received_at - ca[k].received_at, timedelta(days=5))
                self.assertEqual(cb[k].expected_disposal_date - ca[k].expected_disposal_date, timedelta(days=5))
                self.assertEqual((cb[k].last_action_at - ca[k].last_action_at) if ca[k].last_action_at else None,
                                 timedelta(days=5) if ca[k].last_action_at else None)
            first_a = da.scalars(select(m.CaseAction).order_by(m.CaseAction.id)).first()
            first_b = db.scalars(select(m.CaseAction).order_by(m.CaseAction.id)).first()
            self.assertEqual(first_b.at - first_a.at, timedelta(days=5))

    def test_demo_stays_current_whatever_day_it_is(self):
        shift = (date.today() - seed.DATASET_TODAY).days
        engine = self.make_db(shift)
        with Session(engine) as db:
            s10 = db.scalars(select(m.Case).where(m.Case.source_case_no == "PGRC-2026-0009")).one()
            self.assertEqual(s10.expected_disposal_date, date.today() + timedelta(days=1))  # S10: due very soon
            types = {a.type for a in db.scalars(select(m.Alert).where(m.Alert.case_id == s10.hub_case_id))}
            self.assertIn("DUE_SOON", types)
            overdue = db.scalars(select(m.Case).where(m.Case.source_case_no == "RB-2026-0011")).one()
            self.assertIn("OVERDUE", {a.type for a in db.scalars(select(m.Alert).where(m.Alert.case_id == overdue.hub_case_id))})

    def test_portal_databases_are_cleared_not_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "rb.db")
            con = sqlite3.connect(path)
            con.executescript("""CREATE TABLE otp (contact TEXT PRIMARY KEY, code_hash TEXT);
                CREATE TABLE submissions (id INTEGER PRIMARY KEY AUTOINCREMENT, portal_case_no TEXT);""")
            con.execute("INSERT INTO otp VALUES ('x','y')")
            con.executemany("INSERT INTO submissions (portal_case_no) VALUES (?)", [("RB-2026-1001",), ("RB-2026-1002",)])
            con.commit()
            con.close()
            msg = reset_demo.clear_portal_db(path)
            self.assertIn("cleared 3 rows", msg)
            self.assertTrue(path.exists())
            con = sqlite3.connect(path)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM submissions").fetchone()[0], 0)
            con.execute("INSERT INTO submissions (portal_case_no) VALUES ('new')")
            self.assertEqual(con.execute("SELECT id FROM submissions").fetchone()[0], 1)  # numbering starts again
            con.close()
            self.assertIn("not created yet", reset_demo.clear_portal_db(Path(tmp, "missing.db")))

    def test_command_runs_and_confirms_the_demo_college_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, HUB_DATABASE_URL=f"sqlite:///{Path(tmp, 'h.db').as_posix()}")
            r = subprocess.run([sys.executable, str(ROOT / "reset_demo.py"), "--keep-portals"], capture_output=True, text=True, env=env, timeout=180)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("SYN-0040", r.stdout)
            self.assertIn("has 0 cases", r.stdout)
            self.assertIn("Ready.", r.stdout)


if __name__ == "__main__":
    unittest.main()
