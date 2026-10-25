"""M4 test: a portal submits a complaint and the hub stores reporter, case and first action.
Run from the project root:  python -m unittest discover -s hub/backend/tests -v
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # makes `import app` work from anywhere

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, func, select, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app import config, seed  # noqa: E402
from app import models as m  # noqa: E402
from app.db import get_db  # noqa: E402
from app.main import app  # noqa: E402

RB_KEY = {"X-API-Key": config.PORTAL_API_KEYS["RB"]}
PGRC_KEY = {"X-API-Key": config.PORTAL_API_KEYS["PGRC"]}


def complaint(**changes):
    body = {"source_case_no": "RB-2026-9001", "verified_institution_id": "SYN-0040",
            "resolution_method": "REPORTER_CONFIRMED", "finder_answers": None,
            "reporter": {"contact": "9000000001", "reporter_type": "student"},
            "category": "Fee/Refund", "title": "Deposit not refunded",
            "description": "I left the course in July and the deposit has not been returned.", "severity": 3}
    body.update(changes)
    return body


class IntakeTest(unittest.TestCase):
    def setUp(self):  # a fresh seeded database for every test, so tests never affect each other
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{Path(self.tmp.name, 'test.db').as_posix()}",
                                    connect_args={"check_same_thread": False})
        seed.run(self.engine)
        Session_ = sessionmaker(bind=self.engine, autoflush=False)  # same as the real app

        def override():
            db = Session_()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.engine.dispose()
        self.tmp.cleanup()

    def count(self, model):
        with Session(self.engine) as db:
            return db.scalar(select(func.count()).select_from(model))

    def post(self, body=None, headers=RB_KEY):
        return self.client.post("/api/intake", json=body or complaint(), headers=headers)

    def test_new_complaint_creates_reporter_case_and_first_action(self):
        r = self.post()
        self.assertEqual(r.status_code, 201)
        body = r.json()
        self.assertEqual(body["hub_case_id"], "HUB-0151")  # the seed loaded HUB-0001..0150
        self.assertEqual((body["status"], body["assigned_bureau"]), ("Pending", "RB"))
        self.assertEqual(body["institution"]["aicte_id"], "SYN-0040")
        self.assertTrue(body["reporter_is_new"])
        self.assertEqual(body["alerts_created"], [])  # filled by M6
        self.assertEqual((self.count(m.Case), self.count(m.Reporter)), (151, 81))
        with Session(self.engine) as db:
            case = db.get(m.Case, "HUB-0151")
            self.assertEqual(case.source_system, "RB")
            self.assertIsNotNone(case.expected_disposal_date)  # received date + the bureau's SLA days
            action = db.scalars(select(m.CaseAction).where(m.CaseAction.case_id == "HUB-0151")).one()
            self.assertEqual((action.seq, action.action_type, action.stance), (1, "Acknowledged", "NEUTRAL"))
            self.assertEqual(db.scalar(select(m.AuditLog.action).where(m.AuditLog.entity_id == "HUB-0151")),
                             "CASE_RECEIVED")

    def test_no_raw_contact_is_stored_anywhere(self):
        self.post()
        with self.engine.connect() as c:
            dump = " ".join(str(row) for t in ("reporter", "cases", "audit_log")
                            for row in c.execute(text(f"SELECT * FROM {t}")).fetchall())
        self.assertNotIn("9000000001", dump)

    def test_same_person_on_both_portals_is_one_reporter(self):
        self.post(complaint(source_case_no="RB-2026-9001"), RB_KEY)
        second = self.post(complaint(source_case_no="PGRC-2026-9001"), PGRC_KEY).json()
        self.assertFalse(second["reporter_is_new"])
        self.assertEqual(second["assigned_bureau"], "PGRC")
        self.assertEqual(self.count(m.Reporter), 81)
        with Session(self.engine) as db:
            ids = db.scalars(select(m.Case.reporter_id).where(m.Case.hub_case_id.in_(["HUB-0151", "HUB-0152"]))).all()
            self.assertEqual(len(set(ids)), 1)

    def test_existing_seed_reporter_is_recognised(self):
        r = self.post(complaint(reporter={"contact": "0000000003", "reporter_type": "parent"})).json()
        self.assertFalse(r["reporter_is_new"])  # REP-0003 from the dataset has phone 0000000003

    def test_resending_the_same_case_number_is_safe(self):
        first = self.post()
        again = self.post()
        self.assertEqual((first.status_code, again.status_code), (201, 200))
        self.assertTrue(again.json()["already_received"])
        self.assertEqual(again.json()["hub_case_id"], first.json()["hub_case_id"])
        self.assertEqual(self.count(m.Case), 151)

    def test_api_key_is_required_and_decides_the_portal(self):
        self.assertEqual(self.post(headers={}).status_code, 401)
        self.assertEqual(self.post(headers={"X-API-Key": "wrong"}).status_code, 401)
        self.assertEqual(self.count(m.Case), 150)

    def test_hub_does_not_guess_institutions(self):
        self.assertEqual(self.post(complaint(verified_institution_id="SYN-9999")).status_code, 422)
        parent = self.post(complaint(verified_institution_id="SYN-0001"))  # Southern Vale University has colleges
        self.assertEqual(parent.status_code, 422)
        self.assertIn("parent university", parent.json()["detail"])
        self.assertEqual(self.count(m.Case), 150)

    def test_unlisted_institution_goes_to_needs_review(self):
        body = complaint(verified_institution_id=None, resolution_method="UNLISTED",
                         finder_answers={"typed_name": "Unlisted Fictional College of Applied Studies"})
        r = self.post(body).json()
        self.assertEqual((r["status"], r["institution"], r["resolution_method"]),
                         ("unverified_institution", None, "UNLISTED"))

    def test_bad_input_is_rejected(self):
        for change in ({"category": "Parking"}, {"severity": 9}, {"title": ""}, {"description": "short"},
                       {"reporter": {"contact": "1"}}):
            with self.subTest(change=change):
                self.assertEqual(self.post(complaint(**change)).status_code, 422)
        self.assertEqual(self.count(m.Case), 150)

    def test_case_detail_needs_login_and_shows_history(self):
        hub_id = self.post().json()["hub_case_id"]
        self.assertEqual(self.client.get(f"/api/cases/{hub_id}").status_code, 401)
        token = self.client.post("/api/auth/login", json={"username": "rb.officer", "password": "demo123"}).json()["token"]
        r = self.client.get(f"/api/cases/{hub_id}", headers={"Authorization": "Bearer " + token}).json()
        self.assertEqual(r["institution"]["official_name"], "Norvella Institute of Applied Sciences")
        self.assertEqual([a["action_type"] for a in r["actions"]], ["Acknowledged"])
        self.assertNotIn("9000000001", str(r))
        self.assertEqual(self.client.get("/api/cases/HUB-9999", headers={"Authorization": "Bearer " + token}).status_code, 404)

    def test_bureau_action_sync_is_a_stub(self):
        self.assertEqual(self.client.post("/api/actions", json={}).status_code, 501)


if __name__ == "__main__":
    unittest.main()
