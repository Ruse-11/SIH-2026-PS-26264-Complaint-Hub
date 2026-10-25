"""M6 test: A/B/C suggestions on the planted scenarios, plus live intake alerts.
Run from the project root:  python -m unittest discover -s hub/backend/tests -v
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app import config, seed  # noqa: E402
from app import models as m  # noqa: E402
from app.db import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import similarity  # noqa: E402

PORTAL = lambda p: {"X-API-Key": config.PORTAL_API_KEYS[p]}  # noqa: E731


def complaint(no, contact, category="Fee/Refund", title="Deposit not refunded",
              desc="I left the course in July and the deposit has not been returned.", inst="SYN-0040"):
    return {"source_case_no": no, "verified_institution_id": inst, "resolution_method": "REPORTER_CONFIRMED",
            "finder_answers": None, "reporter": {"contact": contact, "reporter_type": "student"},
            "category": category, "title": title, "description": desc, "severity": 3}


class MatchingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{Path(self.tmp.name, 'test.db').as_posix()}",
                                    connect_args={"check_same_thread": False})
        seed.run(self.engine)
        S = sessionmaker(bind=self.engine, autoflush=False)  # same as the real app

        def override():
            db = S()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override
        self.client = TestClient(app)
        token = self.client.post("/api/auth/login", json={"username": "rb.officer", "password": "demo123"}).json()["token"]
        self.auth = {"Authorization": f"Bearer {token}"}

    def tearDown(self):
        app.dependency_overrides.clear()
        self.engine.dispose()
        self.tmp.cleanup()

    def pairs(self, link_type):
        with Session(self.engine) as db:
            no = {c.hub_case_id: c.source_case_no for c in db.scalars(select(m.Case))}
            return {frozenset((no[l.case_a], no[l.case_b])) for l in db.scalars(
                select(m.LinkSuggestion).where(m.LinkSuggestion.link_type == link_type))}

    def test_similarity_ignores_wording_and_filler(self):
        same, _ = similarity.compare("Hostel meals differ from the menu", "The hostel food did not match the menu")
        other, _ = similarity.compare("Hostel meals differ from the menu", "Laboratory equipment is broken")
        self.assertGreater(same, other)

    def test_s1_cross_bureau_overlap(self):
        self.assertIn(frozenset(("PGRC-2026-0001", "RB-2026-0001")), self.pairs("CROSS_BUREAU"))

    def test_s2_same_reporter_duplicate(self):
        self.assertIn(frozenset(("RB-2026-0002", "PGRC-2026-0002")), self.pairs("SAME_REPORTER"))

    def test_s3_corroboration_three_reporters(self):
        found = self.pairs("CORROBORATION")
        for pair in [("RB-2026-0003", "PGRC-2026-0003"), ("RB-2026-0003", "RB-2026-0004"), ("PGRC-2026-0003", "RB-2026-0004")]:
            self.assertIn(frozenset(pair), found)

    def test_hard_negatives_are_not_linked(self):
        every = set().union(*(self.pairs(t) for t in ("SAME_REPORTER", "CORROBORATION", "CROSS_BUREAU")))
        for pair in [("RB-2026-0007", "PGRC-2026-0006"),   # S6 same college, unrelated issues (CROSS_BUREAU is allowed: see below)
                     ("RB-2026-0008", "PGRC-2026-0007"),   # S7 same reporter, two colleges
                     ("RB-2026-0009", "PGRC-2026-0008")]:  # S8 identical wording, two colleges
            if pair[0] != "RB-2026-0007":
                self.assertNotIn(frozenset(pair), every)
        self.assertNotIn(frozenset(("RB-2026-0007", "PGRC-2026-0006")), self.pairs("CORROBORATION"))
        self.assertNotIn(frozenset(("RB-2026-0007", "PGRC-2026-0006")), self.pairs("SAME_REPORTER"))

    def test_disposed_case_is_not_a_cross_bureau_overlap(self):
        # S4: PGRC-2026-0004 is Disposed, so the pair is a conflict (M9), not an open overlap
        self.assertNotIn(frozenset(("RB-2026-0005", "PGRC-2026-0004")), self.pairs("CROSS_BUREAU"))

    def test_every_suggestion_has_reasons_and_starts_suggested(self):
        with Session(self.engine) as db:
            for l in db.scalars(select(m.LinkSuggestion)):
                self.assertTrue(l.reasons)
                self.assertEqual(l.status, "SUGGESTED")

    def test_wow_moment_intake_raises_overlap_alert_with_lead(self):
        r1 = self.client.post("/api/intake", headers=PORTAL("RB"), json=complaint("RB-2026-9001", "9000000001",
                              category="Approval/Affiliation", title="Approval papers unclear", desc="The approval documents shown are not current."))
        self.assertEqual(r1.json()["alerts_created"], [])  # first case at SYN-0040: nothing to compare with
        r2 = self.client.post("/api/intake", headers=PORTAL("PGRC"), json=complaint("PGRC-2026-9001", "9000000002"))
        alerts = r2.json()["alerts_created"]
        overlap = [a for a in alerts if a["alert_type"] == "OVERLAP"]
        self.assertEqual(len(overlap), 1)
        self.assertIn("Potential Overlapping Cases – Coordination Required", overlap[0]["message"])
        self.assertEqual(sorted({c for c in overlap[0]["cases"]}), sorted(overlap[0]["cases"]))
        self.assertIn(overlap[0]["suggested_lead"]["bureau"], ("RB", "PGRC", None))
        self.assertTrue(overlap[0]["suggested_lead"]["rule"])
        # shown on the alerts API
        listed = self.client.get("/api/alerts?type=OVERLAP&institution_id=SYN-0040", headers=self.auth).json()
        self.assertEqual(len(listed), 1)

    def test_same_reporter_on_both_portals_raises_duplicate_alert(self):
        self.client.post("/api/intake", headers=PORTAL("RB"), json=complaint("RB-2026-9002", "9000000009"))
        r = self.client.post("/api/intake", headers=PORTAL("PGRC"), json=complaint(
            "PGRC-2026-9002", "9000000009", title="Deposit return delayed", desc="Still waiting for the deposit refund after leaving."))
        self.assertIn("DUPLICATE", [a["alert_type"] for a in r.json()["alerts_created"]])

    def test_rejected_pair_is_not_suggested_again(self):
        self.client.post("/api/intake", headers=PORTAL("RB"), json=complaint("RB-2026-9003", "9000000011"))
        self.client.post("/api/intake", headers=PORTAL("PGRC"), json=complaint("PGRC-2026-9003", "9000000012"))
        with Session(self.engine) as db:
            for l in db.scalars(select(m.LinkSuggestion)):
                l.status = "REJECTED"
            db.commit()
            case = db.scalars(select(m.Case).where(m.Case.source_case_no == "PGRC-2026-9003")).one()
            from app.services import matching
            self.assertEqual(matching.detect_for_case(db, case), [])

    def test_links_api_needs_login_and_filters(self):
        self.assertEqual(self.client.get("/api/matching/links").status_code, 401)
        rows = self.client.get("/api/matching/links?link_type=SAME_REPORTER", headers=self.auth).json()
        self.assertTrue(any({c["source_case_no"] for c in r["cases"]} == {"RB-2026-0002", "PGRC-2026-0002"} for r in rows))
        one = self.client.get(f"/api/matching/links/{rows[0]['id']}", headers=self.auth)
        self.assertEqual(one.status_code, 200)
        self.assertEqual(self.client.get("/api/matching/links/999999", headers=self.auth).status_code, 404)


if __name__ == "__main__":
    unittest.main()
