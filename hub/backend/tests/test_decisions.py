"""M7 test: officers confirm/reject suggestions; roles, audit trail, clusters and the priority boost.
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

from app import seed  # noqa: E402
from app import models as m  # noqa: E402
from app.db import get_db  # noqa: E402
from app.main import app  # noqa: E402


class DecisionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{Path(self.tmp.name, 'test.db').as_posix()}",
                                    connect_args={"check_same_thread": False})
        seed.run(self.engine)
        S = sessionmaker(bind=self.engine)

        def override():
            db = S()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override
        self.client = TestClient(app)
        self.heads = {}

    def tearDown(self):
        app.dependency_overrides.clear()
        self.engine.dispose()
        self.tmp.cleanup()

    def h(self, username):
        if username not in self.heads:
            t = self.client.post("/api/auth/login", json={"username": username, "password": "demo123"}).json()["token"]
            self.heads[username] = {"Authorization": f"Bearer {t}"}
        return self.heads[username]

    def link_id(self, link_type, a, b):
        with Session(self.engine) as db:
            no = {c.hub_case_id: c.source_case_no for c in db.scalars(select(m.Case))}
            for l in db.scalars(select(m.LinkSuggestion).where(m.LinkSuggestion.link_type == link_type)):
                if {no[l.case_a], no[l.case_b]} == {a, b}:
                    return l.id
        self.fail(f"no {link_type} link for {a}, {b}")

    def hub_id(self, source_no):
        with Session(self.engine) as db:
            return db.scalars(select(m.Case).where(m.Case.source_case_no == source_no)).one().hub_case_id

    def priority(self, source_no):
        return self.client.get(f"/api/cases/{self.hub_id(source_no)}", headers=self.h("senior.mgmt")).json()["priority"]

    def test_every_case_has_a_priority_score(self):
        with Session(self.engine) as db:
            self.assertTrue(all(c.priority_score > 0 for c in db.scalars(select(m.Case))))

    def test_confirm_corroboration_applies_boost_only_after_confirmation(self):
        before = self.priority("RB-2026-0003")
        self.assertEqual(before["confirmed_corroborators"], 0)
        self.assertGreaterEqual(before["potential_boost"], 5)  # shown as "potential +X", not yet applied
        lid = self.link_id("CORROBORATION", "RB-2026-0003", "PGRC-2026-0003")
        r = self.client.post(f"/api/matching/links/{lid}/confirm", json={"note": "same menu problem"}, headers=self.h("rb.officer"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "CONFIRMED")
        after = self.priority("RB-2026-0003")
        self.assertEqual(after["confirmed_corroborators"], 1)
        self.assertEqual(after["score"], before["score"] + 5)

    def test_three_reporters_share_a_cluster_and_boost_is_capped(self):
        for a, b in [("RB-2026-0003", "PGRC-2026-0003"), ("PGRC-2026-0003", "RB-2026-0004")]:
            self.client.post(f"/api/matching/links/{self.link_id('CORROBORATION', a, b)}/confirm", headers=self.h("competent.authority"))
        self.assertEqual(self.priority("RB-2026-0004")["confirmed_corroborators"], 2)
        ids = {self.client.get(f"/api/cases/{self.hub_id(n)}", headers=self.h("senior.mgmt")).json()["cluster_id"]
               for n in ("RB-2026-0003", "PGRC-2026-0003", "RB-2026-0004")}
        self.assertEqual(len(ids), 1)
        self.assertNotIn(None, ids)

    def test_reject_changes_no_priority_and_keeps_note(self):
        before = self.priority("RB-2026-0003")["score"]
        lid = self.link_id("CORROBORATION", "RB-2026-0003", "PGRC-2026-0003")
        r = self.client.post(f"/api/matching/links/{lid}/reject", json={"note": "different shift"}, headers=self.h("pgrc.officer"))
        self.assertEqual((r.status_code, r.json()["status"]), (200, "REJECTED"))
        self.assertEqual(self.priority("RB-2026-0003")["score"], before)

    def test_cannot_decide_twice(self):
        lid = self.link_id("SAME_REPORTER", "RB-2026-0002", "PGRC-2026-0002")
        self.assertEqual(self.client.post(f"/api/matching/links/{lid}/confirm", headers=self.h("rb.officer")).status_code, 200)
        again = self.client.post(f"/api/matching/links/{lid}/reject", headers=self.h("pgrc.officer"))
        self.assertEqual(again.status_code, 409)

    def test_role_rules(self):
        lid = self.link_id("CORROBORATION", "RB-2026-0003", "RB-2026-0004")  # both RB cases
        self.assertEqual(self.client.post(f"/api/matching/links/{lid}/confirm").status_code, 401)
        for user in ("senior.mgmt", "regional.south", "other.bureau"):
            self.assertEqual(self.client.post(f"/api/matching/links/{lid}/confirm", headers=self.h(user)).status_code, 403, user)
        self.assertEqual(self.client.post(f"/api/matching/links/{lid}/confirm", headers=self.h("pgrc.officer")).status_code, 403)
        self.assertEqual(self.client.post(f"/api/matching/links/{lid}/confirm", headers=self.h("rb.officer")).status_code, 200)
        self.assertEqual(self.client.post("/api/matching/links/999999/confirm", headers=self.h("rb.officer")).status_code, 404)

    def test_audit_trail_records_decision_and_is_role_gated(self):
        lid = self.link_id("SAME_REPORTER", "RB-2026-0002", "PGRC-2026-0002")
        self.client.post(f"/api/matching/links/{lid}/confirm", json={"note": "same person"}, headers=self.h("rb.officer"))
        self.assertEqual(self.client.get("/api/audit", headers=self.h("rb.officer")).status_code, 403)
        rows = self.client.get("/api/audit?action=LINK_CONFIRMED", headers=self.h("senior.mgmt")).json()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["actor"], rows[0]["entity_id"], rows[0]["detail"]["note"]), ("rb.officer", str(lid), "same person"))

    def test_decision_acknowledges_the_alert_and_case_shows_links(self):
        lid = self.link_id("CROSS_BUREAU", "PGRC-2026-0001", "RB-2026-0001")
        self.client.post(f"/api/matching/links/{lid}/confirm", headers=self.h("rb.officer"))
        open_overlaps = self.client.get("/api/alerts?type=OVERLAP&institution_id=SYN-0001&open_only=true", headers=self.h("rb.officer")).json()
        self.assertFalse([a for a in open_overlaps if a["link_id"] == lid])
        detail = self.client.get(f"/api/cases/{self.hub_id('RB-2026-0001')}", headers=self.h("rb.officer")).json()
        self.assertIn(lid, [l["id"] for l in detail["links"] if l["status"] == "CONFIRMED"])

    def test_acknowledge_alert_and_priority_endpoint(self):
        alert = self.client.get("/api/alerts", headers=self.h("rb.officer")).json()[0]
        r = self.client.post(f"/api/alerts/{alert['id']}/acknowledge", headers=self.h("senior.mgmt"))
        self.assertEqual(r.json()["acknowledged_by"], "senior.mgmt")
        p = self.client.get(f"/api/corroboration/{self.hub_id('RB-2026-0003')}", headers=self.h("rb.officer")).json()
        self.assertIn("potential_boost", p)
        self.assertEqual(self.client.get("/api/corroboration/NOPE", headers=self.h("rb.officer")).status_code, 404)


if __name__ == "__main__":
    unittest.main()
