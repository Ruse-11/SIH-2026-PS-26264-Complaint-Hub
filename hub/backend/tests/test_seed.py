"""M1 test: the CSV loader fills a throw-away database correctly.
Run from the project root:  python -m unittest discover -s hub/backend/tests -v
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # makes `import app` work from anywhere

from sqlalchemy import create_engine, func, select, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import models as m  # noqa: E402
from app import seed  # noqa: E402
from app.services.institutions import normalize_name  # noqa: E402
from app.services.reporters import make_fingerprint  # noqa: E402


class SeedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()  # a temp database, so hub.db is never touched
        cls.engine = create_engine(f"sqlite:///{Path(cls.tmp.name, 'test.db').as_posix()}")
        cls.counts = seed.run(cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        cls.tmp.cleanup()

    def count(self, model, *where):
        with Session(self.engine) as db:
            return db.scalar(select(func.count()).select_from(model).where(*where))

    def test_row_counts(self):
        self.assertEqual(self.counts["institutions"], 40)
        self.assertEqual(self.counts["reporters"], 80)
        self.assertEqual(self.counts["cases"], 150)
        self.assertEqual(self.counts["actions"], 350)
        self.assertGreaterEqual(self.counts["aliases"], 150)

    def test_demo_college_is_clean(self):
        self.assertEqual(self.count(m.Case, m.Case.institution_id == "SYN-0040"), 0)

    def test_unverified_cases_go_to_needs_review(self):
        self.assertEqual(self.count(m.Case, m.Case.institution_id.is_(None)), 3)
        self.assertEqual(self.count(m.Case, m.Case.status == "unverified_institution"), 3)

    def test_no_broken_references(self):
        with self.engine.connect() as c:
            self.assertEqual(c.execute(text("PRAGMA foreign_key_check")).fetchall(), [])

    def test_stance_filled_for_every_action(self):
        self.assertEqual(self.count(m.CaseAction, m.CaseAction.stance.is_(None)), 0)
        self.assertEqual(self.count(m.CaseAction, m.CaseAction.action_type == "Show-Cause Notice Issued",
                                    m.CaseAction.stance == "ENFORCING"), 1)

    def test_no_personal_data_in_reporter_table(self):
        with Session(self.engine) as db:
            r = db.get(m.Reporter, "REP-0001")
            self.assertEqual(len(r.fingerprint_hash), 64)  # a sha256 hex digest
            self.assertNotIn("0000000001", r.fingerprint_hash)
        self.assertFalse(hasattr(m.Reporter, "email") or hasattr(m.Reporter, "phone"))

    def test_transfer_has_from_and_to_bureau(self):
        with Session(self.engine) as db:
            t = db.scalars(select(m.CaseAction).where(m.CaseAction.action_type == "Transferred")).first()
            self.assertEqual({t.from_bureau, t.to_bureau}, {"RB", "PGRC"})

    def test_config_tables(self):
        self.assertEqual(self.count(m.ActionTypeStance), 12)
        self.assertEqual(self.count(m.CategoryOwnership), 11)
        self.assertEqual(self.count(m.Threshold), 9)  # M10 added SLA_DUE_SOON_DAYS, PENDING_REMINDER_DAYS, ESCALATION_OVERDUE_DAYS

    def test_seed_twice_gives_same_result(self):
        self.assertEqual(seed.run(self.engine), self.counts)

    def test_normalize_name(self):
        self.assertEqual(normalize_name("Orbelis Clg. of Technology"), "orbelis college technology")
        self.assertEqual(normalize_name("QUORALIS Institute of Engg"), "quoralis institute engineering")

    def test_fingerprint_same_for_same_phone(self):
        self.assertEqual(make_fingerprint("+91 98765-43210"), make_fingerprint("919876543210"))
        self.assertNotEqual(make_fingerprint("0000000001"), make_fingerprint("0000000002"))


if __name__ == "__main__":
    unittest.main()
