"""M9 test: conflict + duplicate-action rules, logging actions, lead-bureau suggestion and the final decision.
Run from the project root:  python -m unittest discover -s hub/backend/tests -v
"""
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app import config, seed  # noqa: E402
from app import models as m  # noqa: E402
from app.db import get_db  # noqa: E402
from app.main import app  # noqa: E402

PORTAL = lambda p: {"X-API-Key": config.PORTAL_API_KEYS[p]}  # noqa: E731
SHOW_CAUSE, CLOSED, DOCS = "Show-Cause Notice Issued", "Closed - No Action", "Documents Sought"


def complaint(no, contact, category="Approval/Affiliation", inst="SYN-0040"):
    return {"source_case_no": no, "verified_institution_id": inst, "resolution_method": "REPORTER_CONFIRMED",
            "finder_answers": None, "reporter": {"contact": contact, "reporter_type": "student"}, "category": category,
            "title": "Approval documents unclear", "description": "The approval documents shown are not current.", "severity": 3}


class ConflictTest(unittest.TestCase):
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

    def two_cases(self, rb_category="Approval/Affiliation", pgrc_category="Approval/Affiliation"):
        """One RB and one PGRC complaint at the empty demo college SYN-0040. Returns their hub IDs."""
        a = self.client.post("/api/intake", headers=PORTAL("RB"), json=complaint("RB-2026-9301", "9000000051", rb_category)).json()
        b = self.client.post("/api/intake", headers=PORTAL("PGRC"), json=complaint("PGRC-2026-9301", "9000000052", pgrc_category)).json()
        return a["hub_case_id"], b["hub_case_id"]

    def act(self, user, case, action, **extra):
        return self.client.post(f"/api/cases/{case}/actions", json={"action_type": action, **extra}, headers=self.h(user))

    def links(self, link_type):
        return self.client.get(f"/api/matching/links?link_type={link_type}", headers=self.h("senior.mgmt")).json()

    # ---- the planted scenarios ----
    def test_seed_finds_exactly_s4_conflict_and_s5_duplicate_action(self):
        conflicts = self.links("CONFLICT")
        dups = self.links("DUPLICATE_ACTION")
        self.assertEqual([{c["source_case_no"] for c in l["cases"]} for l in conflicts], [{"RB-2026-0005", "PGRC-2026-0004"}])
        self.assertEqual([{c["source_case_no"] for c in l["cases"]} for l in dups], [{"RB-2026-0006", "PGRC-2026-0005"}])
        top = conflicts[0]["reasons"]["matches"][0]
        self.assertEqual((top["enforcing"]["bureau"], top["enforcing"]["action_type"], top["closing"]["bureau"]), ("RB", SHOW_CAUSE, "PGRC"))
        lead = conflicts[0]["reasons"]["suggested_lead"]
        self.assertEqual(lead["bureau"], "RB")
        self.assertTrue(lead["rule"].startswith("Rule 1"))  # approval/affiliation belongs to RB (assumed mandate)
        listed = self.client.get("/api/conflicts", headers=self.h("competent.authority")).json()
        self.assertEqual(len(listed), 2)

    # ---- live: officers log actions ----
    def test_show_cause_then_closure_in_other_bureau_raises_conflict_alert(self):
        rb, pgrc = self.two_cases()
        self.assertEqual(self.act("rb.officer", rb, SHOW_CAUSE, remarks="Documents appear expired").status_code, 201)
        r = self.act("pgrc.officer", pgrc, CLOSED, remarks="Nothing found")
        self.assertEqual(r.status_code, 201, r.text)
        body = r.json()
        self.assertEqual(body["status"], "Disposed")
        conflict = [a for a in body["alerts_created"] if a["alert_type"] == "CONFLICT"]
        self.assertEqual(len(conflict), 1)
        self.assertEqual(conflict[0]["severity"], "critical")
        self.assertIn("Conflicting actions", conflict[0]["message"])
        listed = self.client.get("/api/alerts?type=CONFLICT&institution_id=SYN-0040", headers=self.h("rb.officer")).json()
        self.assertEqual(len(listed), 1)  # the RB officer sees it although the PGRC case triggered it
        detail = self.client.get(f"/api/cases/{rb}", headers=self.h("rb.officer")).json()
        self.assertEqual(detail["actions"][-1]["action_type"], SHOW_CAUSE)
        self.assertEqual(detail["last_action"], SHOW_CAUSE)

    def test_no_conflict_for_other_category_same_bureau_or_outside_window(self):
        rb, pgrc = self.two_cases(pgrc_category="Fee/Refund")  # unrelated categories
        self.act("rb.officer", rb, SHOW_CAUSE)
        self.assertEqual([a for a in self.act("pgrc.officer", pgrc, CLOSED).json()["alerts_created"] if a["alert_type"] == "CONFLICT"], [])
        # same category but the actions are 90 days apart
        a = self.client.post("/api/intake", headers=PORTAL("RB"), json=complaint("RB-2026-9302", "9000000053", inst="SYN-0039")).json()["hub_case_id"]
        b = self.client.post("/api/intake", headers=PORTAL("PGRC"), json=complaint("PGRC-2026-9302", "9000000054", inst="SYN-0039")).json()["hub_case_id"]
        self.act("rb.officer", a, SHOW_CAUSE)
        with Session(self.engine) as db:
            for act in db.scalars(select(m.CaseAction).where(m.CaseAction.case_id == a, m.CaseAction.action_type == SHOW_CAUSE)):
                act.at = datetime.now() - timedelta(days=90)
            db.commit()
        self.assertEqual([x for x in self.act("pgrc.officer", b, CLOSED).json()["alerts_created"] if x["alert_type"] == "CONFLICT"], [])

    def test_same_documents_sought_by_both_bureaus_is_a_duplicate_action(self):
        rb, pgrc = self.two_cases()
        self.act("rb.officer", rb, DOCS)
        r = self.act("pgrc.officer", pgrc, DOCS)
        dup = [a for a in r.json()["alerts_created"] if a["alert_type"] == "DUPLICATE_ACTION"]
        self.assertEqual(len(dup), 1)
        self.assertIn("duplicate action", dup[0]["message"])
        self.assertEqual([a for a in r.json()["alerts_created"] if a["alert_type"] == "CONFLICT"], [])

    def test_rejected_conflict_is_never_suggested_again(self):
        rb, pgrc = self.two_cases()
        self.act("rb.officer", rb, SHOW_CAUSE)
        self.act("pgrc.officer", pgrc, CLOSED)
        lid = self.links("CONFLICT")
        live = [l for l in lid if {c["hub_case_id"] for c in l["cases"]} == {rb, pgrc}][0]["id"]
        self.assertEqual(self.client.post(f"/api/matching/links/{live}/reject", headers=self.h("rb.officer")).status_code, 200)
        again = self.act("rb.officer", rb, "Inspection Ordered")
        self.assertEqual([a for a in again.json()["alerts_created"] if a["alert_type"] == "CONFLICT"], [])

    # ---- logging actions: rules ----
    def test_who_may_log_what(self):
        rb, pgrc = self.two_cases()
        self.assertEqual(self.act("senior.mgmt", rb, DOCS).status_code, 403)
        self.assertEqual(self.act("rb.officer", pgrc, DOCS).status_code, 403)  # not their bureau's case
        self.assertEqual(self.act("rb.officer", rb, "Made Up Action").status_code, 403)
        self.assertEqual(self.act("rb.officer", rb, "Acknowledged").status_code, 403)  # written by the system only
        self.assertEqual(self.act("other.bureau", rb, DOCS).status_code, 403)  # no cases in its view
        self.assertEqual(self.act("rb.officer", rb, "Transferred").status_code, 422)  # needs the other bureau
        self.assertEqual(self.client.post(f"/api/cases/{rb}/actions", json={"action_type": DOCS}).status_code, 401)
        types = {u: {t["action_type"] for t in self.client.get("/api/cases/action-types", headers=self.h(u)).json()}
                 for u in ("rb.officer", "other.bureau", "regional.south", "senior.mgmt")}
        self.assertIn("Transferred", types["rb.officer"])
        self.assertNotIn("Transferred", types["other.bureau"])
        self.assertEqual(types["regional.south"], {"Escalated to Competent Authority"})
        self.assertEqual(types["senior.mgmt"], set())

    def test_transfer_escalate_and_close_change_status(self):
        rb, pgrc = self.two_cases()
        moved = self.act("rb.officer", rb, "Transferred", to_bureau="PGRC").json()
        self.assertEqual((moved["status"], moved["assigned_bureau"]), ("Transferred", "PGRC"))
        detail = self.client.get(f"/api/cases/{rb}", headers=self.h("pgrc.officer")).json()  # now in PGRC's view
        self.assertEqual((detail["actions"][-1]["from_bureau"], detail["actions"][-1]["to_bureau"]), ("RB", "PGRC"))
        self.assertEqual(self.act("pgrc.officer", pgrc, "Escalated to Competent Authority").json()["status"], "Escalated")
        self.assertEqual(self.act("pgrc.officer", pgrc, "Under Review").json()["status"], "Escalated")  # other actions keep it
        self.assertEqual(self.act("pgrc.officer", pgrc, "Disposed - Action Taken").json()["status"], "Disposed")
        self.assertEqual(self.act("pgrc.officer", pgrc, DOCS).status_code, 409)  # disposed: nothing more to log
        audit = self.client.get("/api/audit?action=ACTION_LOGGED", headers=self.h("senior.mgmt")).json()
        self.assertEqual(len(audit), 4)  # the refused 409 attempt is not recorded

    def test_first_action_moves_pending_to_under_process(self):
        rb, _ = self.two_cases()
        self.assertEqual(self.act("rb.officer", rb, DOCS).json()["status"], "Under Process")

    # ---- lead bureau ----
    def test_lead_suggestion_follows_the_latest_actions(self):
        rb, pgrc = self.two_cases(rb_category="Infrastructure/Lab", pgrc_category="Fee/Refund")  # owners differ (RB vs PGRC)
        lid = self.client.get(f"/api/matching/links?link_type=CROSS_BUREAU&institution_id=SYN-0040", headers=self.h("senior.mgmt")).json()[0]["id"]
        first = self.client.get(f"/api/matching/links/{lid}", headers=self.h("senior.mgmt")).json()["reasons"]["suggested_lead"]
        self.assertTrue(first["rule"].startswith("Rule 3"))
        self.act("pgrc.officer", pgrc, SHOW_CAUSE)
        second = self.client.get(f"/api/matching/links/{lid}", headers=self.h("senior.mgmt")).json()["reasons"]["suggested_lead"]
        self.assertEqual((second["bureau"], second["rule"][:6]), ("PGRC", "Rule 2"))

    def test_only_competent_authority_decides_the_lead_and_it_is_audited(self):
        conflict = self.links("CONFLICT")[0]["id"]
        body = {"bureau": "PGRC", "note": "Student grievance route"}
        for user in ("rb.officer", "pgrc.officer", "senior.mgmt", "regional.south"):
            self.assertEqual(self.client.post(f"/api/conflicts/{conflict}/lead", json=body, headers=self.h(user)).status_code, 403, user)
        self.assertEqual(self.client.post(f"/api/conflicts/{conflict}/lead", json={"bureau": "XYZ"}, headers=self.h("competent.authority")).status_code, 422)
        corroboration = self.links("CORROBORATION")[0]["id"]
        self.assertEqual(self.client.post(f"/api/conflicts/{corroboration}/lead", json=body, headers=self.h("competent.authority")).status_code, 404)
        ok = self.client.post(f"/api/conflicts/{conflict}/lead", json=body, headers=self.h("competent.authority"))
        self.assertEqual(ok.status_code, 200, ok.text)
        reasons = ok.json()["reasons"]
        self.assertEqual((reasons["final_lead"]["bureau"], reasons["final_lead"]["decided_by"]), ("PGRC", "competent.authority"))
        self.assertEqual(reasons["suggested_lead"]["bureau"], "RB")  # the system's suggestion is kept beside the decision
        audit = self.client.get("/api/audit?action=LEAD_BUREAU_DECIDED", headers=self.h("senior.mgmt")).json()
        self.assertEqual(audit[0]["detail"]["bureau"], "PGRC")
        again = self.client.get(f"/api/matching/links/{conflict}", headers=self.h("senior.mgmt")).json()
        self.assertEqual(again["reasons"]["final_lead"]["bureau"], "PGRC")  # survives a reload

    def test_dashboard_counts_conflicts(self):
        k = self.client.get("/api/dashboard/kpis", headers=self.h("competent.authority")).json()["suggestions_waiting"]
        self.assertEqual((k["conflict"], k["duplicate_action"]), (1, 1))


if __name__ == "__main__":
    unittest.main()
