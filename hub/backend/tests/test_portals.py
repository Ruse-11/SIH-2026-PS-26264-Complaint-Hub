"""M5 test: both mock portals end to end against the real hub app (no network, no browser).
Run from the project root:  python -m unittest discover -s hub/backend/tests -v
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "hub" / "backend"))  # makes `import app` work from anywhere
sys.path.insert(0, str(ROOT / "shared"))  # makes `import portal_core` work

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app import models as m  # noqa: E402
from app import seed  # noqa: E402
from app.db import get_db  # noqa: E402
from app.main import app as hub_app  # noqa: E402
from portal_core import Portal  # noqa: E402


class DownHub:
    """Stands in for a hub that is switched off."""
    def post(self, *a, **k):
        raise httpx.ConnectError("hub is down")

    def get(self, *a, **k):
        raise httpx.ConnectError("hub is down")


class PortalTest(unittest.TestCase):
    def setUp(self):  # fresh seeded hub + fresh portal databases for every test
        self.tmp = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp.name)
        self.engine = create_engine(f"sqlite:///{(tmp / 'hub.db').as_posix()}", connect_args={"check_same_thread": False})
        seed.run(self.engine)
        Session_ = sessionmaker(bind=self.engine)

        def override():
            db = Session_()
            try:
                yield db
            finally:
                db.close()

        hub_app.dependency_overrides[get_db] = override
        self.hub = TestClient(hub_app)
        self.rb = Portal("RB", "Regulation Bureau", ROOT / "portal_rb", ROOT / "shared", "dev-rb-key",
                         db_path=tmp / "rb.db", hub_client=self.hub)
        self.pgrc = Portal("PGRC", "Public Grievance Redressal Cell", ROOT / "portal_pgrc", ROOT / "shared",
                           "dev-pgrc-key", db_path=tmp / "pgrc.db", hub_client=self.hub)
        self.rb_web, self.pgrc_web = TestClient(self.rb.build_app()), TestClient(self.pgrc.build_app())

    def tearDown(self):
        hub_app.dependency_overrides.clear()
        self.engine.dispose()
        self.tmp.cleanup()

    # --- helpers that walk the same steps as the page ---
    def verify_phone(self, web, contact="9876543210"):
        otp = web.post("/otp/request", json={"contact": contact}).json()
        r = web.post("/otp/verify", json={"contact": contact, "code": otp["demo_otp"]})
        self.assertEqual(r.status_code, 200)
        return r.json()["verification_token"]

    def confirm(self, web, iid="SYN-0040", method="REPORTER_CONFIRMED", answers=None):
        r = web.post("/institution/confirm", json={"institution_id": iid, "resolution_method": method, "finder_answers": answers})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["institution_token"]

    def submit(self, web, inst_token, verif_token, **changes):
        body = {"institution_token": inst_token, "verification_token": verif_token, "reporter_type": "student",
                "category": "Fee/Refund", "title": "Deposit not refunded",
                "description": "I left the course in July and my deposit has not been returned.", "severity": 3}
        body.update(changes)
        return web.post("/submit", json=body)

    def hub_cases(self):
        with Session(self.engine) as db:
            return db.scalars(select(m.Case).where(m.Case.source_case_no.like("%-2026-1%"))).all()

    # --- tests ---
    def test_pages_and_config(self):
        for web, code in ((self.rb_web, "RB"), (self.pgrc_web, "PGRC")):
            self.assertEqual(web.get("/health").status_code, 200)
            self.assertEqual(web.get("/config").json()["portal_code"], code)
            page = web.get("/")
            self.assertEqual(page.status_code, 200)
            self.assertIn("/shared/institution-finder.js", page.text)
            self.assertEqual(web.get("/shared/institution-finder.js").status_code, 200)

    def test_full_journey_reaches_the_hub(self):
        receipt = self.submit(self.rb_web, self.confirm(self.rb_web), self.verify_phone(self.rb_web)).json()
        self.assertEqual(receipt["portal_case_no"], "RB-2026-1001")
        self.assertEqual((receipt["sync_status"], receipt["hub_case_id"]), ("synced", "HUB-0151"))
        self.assertEqual(receipt["institution"]["aicte_id"], "SYN-0040")
        case = self.hub_cases()[0]
        self.assertEqual((case.source_system, case.source_case_no, case.institution_id, case.status),
                         ("RB", "RB-2026-1001", "SYN-0040", "Pending"))

    def test_same_phone_on_both_portals_is_one_reporter(self):  # the S2 pattern, now through the real portals
        self.submit(self.rb_web, self.confirm(self.rb_web), self.verify_phone(self.rb_web))
        self.submit(self.pgrc_web, self.confirm(self.pgrc_web), self.verify_phone(self.pgrc_web))
        by_portal = {c.source_system: c for c in self.hub_cases()}
        self.assertEqual(set(by_portal), {"RB", "PGRC"})
        self.assertEqual(by_portal["RB"].reporter_id, by_portal["PGRC"].reporter_id)
        self.assertEqual(by_portal["RB"].source_case_no, "RB-2026-1001")
        self.assertEqual(by_portal["PGRC"].source_case_no, "PGRC-2026-1001")

    def test_unlisted_institution_is_pending_verification(self):
        r = self.rb_web.post("/institution/confirm", json={"institution_id": None, "resolution_method": "UNLISTED",
                             "finder_answers": {"typed_name": "Unlisted Fictional College of Applied Studies"}})
        self.assertTrue(r.json()["pending_verification"])
        receipt = self.submit(self.rb_web, r.json()["institution_token"], self.verify_phone(self.rb_web)).json()
        self.assertTrue(receipt["pending_verification"])
        self.assertEqual(self.hub_cases()[0].status, "unverified_institution")
        self.assertEqual(self.rb_web.post("/institution/confirm", json={"institution_id": None, "finder_answers": {}}).status_code, 422)

    def test_guided_answers_travel_to_the_hub(self):
        answers = {"state": "Tamil Nadu", "district": "Chennai"}
        self.submit(self.rb_web, self.confirm(self.rb_web, "SYN-0002", "GUIDED", answers), self.verify_phone(self.rb_web))
        case = self.hub_cases()[0]
        self.assertEqual((case.resolution_method, case.finder_answers), ("GUIDED", answers))

    def test_cannot_submit_without_valid_tokens(self):
        inst, verif = self.confirm(self.rb_web), self.verify_phone(self.rb_web)
        self.assertEqual(self.submit(self.rb_web, "junk", verif).status_code, 401)
        self.assertEqual(self.submit(self.rb_web, inst, "junk").status_code, 401)
        self.assertEqual(self.submit(self.rb_web, inst, inst).status_code, 401)  # wrong kind of token
        self.assertEqual(self.submit(self.rb_web, inst[:-3] + "abc", verif).status_code, 401)  # tampered
        self.assertEqual(self.submit(self.pgrc_web, inst, verif).status_code, 401)  # token from the other portal
        expired = self.rb.sign({"kind": "inst", "iid": "SYN-0040", "method": "REPORTER_CONFIRMED"}, minutes=-1)
        self.assertEqual(self.submit(self.rb_web, expired, verif).status_code, 401)
        self.assertEqual(self.hub_cases(), [])

    def test_otp_rules(self):
        contact = "9876543210"
        self.assertEqual(self.rb_web.post("/otp/request", json={"contact": "abc"}).status_code, 422)
        code = self.rb_web.post("/otp/request", json={"contact": contact}).json()["demo_otp"]
        wrong = "000000" if code != "000000" else "111111"
        self.assertEqual(self.rb_web.post("/otp/verify", json={"contact": contact, "code": wrong}).status_code, 400)
        self.assertEqual(self.rb_web.post("/otp/verify", json={"contact": contact, "code": code}).status_code, 200)
        self.assertEqual(self.rb_web.post("/otp/verify", json={"contact": contact, "code": code}).status_code, 400)  # used once
        code = self.rb_web.post("/otp/request", json={"contact": contact}).json()["demo_otp"]
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(5):
            self.rb_web.post("/otp/verify", json={"contact": contact, "code": wrong})
        self.assertEqual(self.rb_web.post("/otp/verify", json={"contact": contact, "code": code}).status_code, 429)  # locked

    def test_parent_and_unknown_institutions_are_refused(self):
        for iid in ("SYN-0001", "SYN-9999"):
            r = self.rb_web.post("/institution/confirm", json={"institution_id": iid})
            self.assertEqual(r.status_code, 422, iid)

    def test_outbox_keeps_complaint_when_hub_is_down_then_sends_it(self):
        self.rb.hub = DownHub()
        inst, verif = self.confirm_offline_token(), self.verify_phone(self.rb_web)
        receipt = self.submit(self.rb_web, inst, verif).json()
        self.assertEqual((receipt["sync_status"], receipt["hub_case_id"]), ("pending", None))
        self.assertEqual(self.hub_cases(), [])
        self.assertEqual(self.rb.sync_pending(), 1)  # still down: stays pending
        self.assertEqual(self.rb_web.get("/submission/RB-2026-1001").json()["sync_status"], "pending")
        self.rb.hub = self.hub  # the hub comes back
        self.assertEqual(self.rb.sync_pending(), 1)
        self.assertEqual(self.rb_web.get("/submission/RB-2026-1001").json()["sync_status"], "synced")
        self.assertEqual(len(self.hub_cases()), 1)
        self.assertEqual(self.rb.sync_pending(), 0)  # nothing left, nothing duplicated
        self.assertEqual(len(self.hub_cases()), 1)

    def confirm_offline_token(self):
        # the institution is confirmed while the hub is up, then the hub goes down before submit
        hub, self.rb.hub = self.rb.hub, self.hub
        token = self.confirm(self.rb_web)
        self.rb.hub = hub
        return token

    def test_hub_rejection_is_not_retried(self):
        inst = self.rb.sign({"kind": "inst", "iid": "SYN-9999", "iname": "Ghost", "method": "REPORTER_CONFIRMED"})
        receipt = self.submit(self.rb_web, inst, self.verify_phone(self.rb_web)).json()
        self.assertEqual(receipt["sync_status"], "rejected")
        self.assertIn("422", receipt["last_error"])
        self.assertEqual(self.rb.sync_pending(), 0)


if __name__ == "__main__":
    unittest.main()
