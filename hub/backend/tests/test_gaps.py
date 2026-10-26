"""Gap tests: next action required and manual linking of cases.
Run from the project root:  python -m unittest discover -s hub/backend/tests -v
"""
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app import seed  # noqa: E402
from app import models as m  # noqa: E402
from app.db import get_db  # noqa: E402
from app.main import app  # noqa: E402


class GapsTest(unittest.TestCase):
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

    def open_rb_case(self):
        with Session(self.engine) as db:
            return db.scalars(select(m.Case).where(m.Case.assigned_bureau == "RB", m.Case.status == "Pending",
                                                   m.Case.institution_id.is_not(None))).first().hub_case_id

    def detail(self, cid, who="senior.mgmt"):
        return self.client.get(f"/api/cases/{cid}", headers=self.h(who)).json()

    def log(self, cid, **body):
        return self.client.post(f"/api/cases/{cid}/actions", json=body, headers=self.h("rb.officer"))

    # ---- gap 1: next action required ----
    def test_rule_gives_a_default_next_action(self):
        cid = self.open_rb_case()
        self.assertEqual(self.log(cid, action_type="Show-Cause Notice Issued", remarks="notice sent").status_code, 201)
        na = self.detail(cid)["next_action"]
        self.assertEqual(na["source"], "rule")
        self.assertIn("show-cause", na["text"].lower())
        self.assertTrue(na["due"])

    def test_officer_value_overrides_rule_and_shows_in_list_and_csv(self):
        cid = self.open_rb_case()
        due = (date.today() + timedelta(days=9)).isoformat()
        r = self.log(cid, action_type="Under Review", remarks="checking", next_step="Call the principal", next_due=due)
        self.assertEqual(r.status_code, 201)
        na = self.detail(cid)["next_action"]
        self.assertEqual((na["source"], na["text"], na["due"]), ("officer", "Call the principal", due))
        rows = self.client.get("/api/cases?page_size=500", headers=self.h("senior.mgmt")).json()
        items = rows["items"] if isinstance(rows, dict) else rows
        mine = [i for i in items if i["hub_case_id"] == cid][0]
        self.assertEqual(mine["next_action"], "Call the principal")
        csv = self.client.get("/api/cases/export", headers=self.h("senior.mgmt")).text
        self.assertIn("Next action required", csv.splitlines()[0])
        self.assertIn("Call the principal", csv)

    def test_past_due_date_and_date_without_text_are_rejected(self):
        cid = self.open_rb_case()
        past = (date.today() - timedelta(days=2)).isoformat()
        self.assertEqual(self.log(cid, action_type="Under Review", remarks="x", next_step="Call", next_due=past).status_code, 422)
        future = (date.today() + timedelta(days=2)).isoformat()
        self.assertEqual(self.log(cid, action_type="Under Review", remarks="x", next_due=future).status_code, 422)

    def test_closing_a_case_clears_next_action(self):
        cid = self.open_rb_case()
        self.log(cid, action_type="Under Review", remarks="x", next_step="Call the principal")
        r = self.log(cid, action_type="Disposed - Action Taken", remarks="done and closed")
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(self.detail(cid)["next_action"]["source"], "none")

    def test_case_file_has_next_action(self):
        cid = self.open_rb_case()
        self.log(cid, action_type="Under Review", remarks="x", next_step="Call the principal")
        f = self.client.get(f"/api/cases/{cid}/file", headers=self.h("senior.mgmt"))
        self.assertIn("Next action required", f.text)

    # ---- gap 2: manual linking ----
    def pick_pair(self):
        cid = self.open_rb_case()
        for o in self.client.get(f"/api/matching/linkable?case_id={cid}", headers=self.h("rb.officer")).json():
            if not o["existing_links"]:
                return cid, o["hub_case_id"]
        self.fail("no unlinked case at the same college")

    def link(self, who, cid, other, **kw):
        body = {"case_id": cid, "other_case_id": other, "link_type": "RELATED", "note": "same building complaint"}
        body.update(kw)
        return self.client.post("/api/matching/links/manual", json=body, headers=self.h(who))

    def test_officer_links_two_cases_confirmed_and_audited(self):
        cid, other = self.pick_pair()
        r = self.link("rb.officer", cid, other)
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()["status"], "CONFIRMED")
        for c in (cid, other):
            ls = [l for l in self.detail(c)["links"] if l["link_type"] == "RELATED"]
            self.assertEqual(len(ls), 1)
            self.assertTrue(ls[0]["reasons"]["manual"])
        with Session(self.engine) as db:
            self.assertTrue(db.scalars(select(m.AuditLog).where(m.AuditLog.action == "LINK_CREATED_MANUALLY")).first())

    def test_manual_link_rules(self):
        cid, other = self.pick_pair()
        self.assertEqual(self.link("senior.mgmt", cid, other).status_code, 403)
        self.assertEqual(self.link("rb.officer", cid, cid).status_code, 422)
        self.assertEqual(self.link("rb.officer", cid, other, note="x").status_code, 422)
        self.assertEqual(self.link("rb.officer", cid, other, link_type="CROSS_BUREAU").status_code, 422)
        self.assertEqual(self.link("rb.officer", cid, "NOPE").status_code, 404)
        self.assertEqual(self.link("rb.officer", cid, other).status_code, 201)
        self.assertEqual(self.link("rb.officer", cid, other).status_code, 409)  # already linked
        with Session(self.engine) as db:
            inst = {c.institution_id for c in db.scalars(select(m.Case).where(m.Case.hub_case_id.in_([cid])))}
            far = db.scalars(select(m.Case).where(m.Case.institution_id.not_in(inst), m.Case.institution_id.is_not(None))).first().hub_case_id
        self.assertEqual(self.link("rb.officer", cid, far).status_code, 422)  # different college


    # ---- gap 3: a third bureau (Quality Assurance Cell) with data and transfers ----
    def test_other_bureau_user_has_its_own_cases(self):
        r = self.client.get("/api/cases?page_size=100", headers=self.h("other.bureau")).json()
        self.assertEqual(r["total"], 12)
        self.assertEqual({i["assigned_bureau"] for i in r["items"]}, {"QAC"})
        self.assertEqual(self.client.get("/api/auth/me", headers=self.h("other.bureau")).json()["bureau"], "QAC")

    def test_rb_officer_can_transfer_to_qac_and_qac_officer_acts(self):
        cid = self.open_rb_case()
        r = self.log(cid, action_type="Transferred", remarks="needs quality review", to_bureau="QAC")
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(self.detail(cid)["assigned_bureau"], "QAC")
        r = self.client.post(f"/api/cases/{cid}/actions", json={"action_type": "Under Review", "remarks": "taken up"}, headers=self.h("other.bureau"))
        self.assertEqual(r.status_code, 201, r.text)
        last = self.detail(cid)["actions"][-1]
        self.assertEqual(last["bureau"], "QAC")
        self.assertEqual(self.client.post(f"/api/cases/{cid}/actions", json={"action_type": "Transferred", "to_bureau": "RB"},
                                          headers=self.h("other.bureau")).status_code, 403)  # other bureaus cannot transfer

    def test_unknown_bureau_cannot_be_transferred_to(self):
        cid = self.open_rb_case()
        self.assertEqual(self.log(cid, action_type="Transferred", remarks="x", to_bureau="NOPE").status_code, 422)

    def test_qac_can_be_decided_as_lead(self):
        with Session(self.engine) as db:
            l = db.scalars(select(m.LinkSuggestion).where(m.LinkSuggestion.link_type == "CONFLICT")).first()
            lid = l.id
        r = self.client.post(f"/api/conflicts/{lid}/lead", json={"bureau": "QAC", "note": "quality angle leads"}, headers=self.h("competent.authority"))
        self.assertEqual(r.status_code, 200, r.text)


if __name__ == "__main__":
    unittest.main()
