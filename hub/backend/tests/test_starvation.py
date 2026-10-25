"""M10 test: stalled and SLA alerts (S9-S12), repeat-safe scan, clearing, thresholds and scope.
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

AS_OF = "2026-10-25"  # the demo date the planted scenarios were written for


class StarvationTest(unittest.TestCase):
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

    def scan(self, as_of=AS_OF, user="competent.authority"):
        r = self.client.post(f"/api/starvation/scan?as_of={as_of}", headers=self.h(user))
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def hub_id(self, source_no):
        with Session(self.engine) as db:
            return db.scalars(select(m.Case).where(m.Case.source_case_no == source_no)).one().hub_case_id

    def alerts_of(self, source_no, include_cleared=False):
        """Time-based alert types currently open for one case."""
        hub = self.hub_id(source_no)
        with Session(self.engine) as db:
            rows = db.scalars(select(m.Alert).where(m.Alert.case_id == hub)).all()
            return {a.type for a in rows if include_cleared or a.acknowledged_by is None}

    # ---- planted scenarios ----
    def test_s9_s10_s12_alerts_on_the_demo_date(self):
        self.scan()
        self.assertEqual(self.alerts_of("RB-2026-0010") & {"STALLED", "ESCALATION_SUGGESTED"}, {"STALLED", "ESCALATION_SUGGESTED"})  # S9
        self.assertIn("DUE_SOON", self.alerts_of("PGRC-2026-0009"))     # S10 due in 1 day
        self.assertIn("OVERDUE", self.alerts_of("RB-2026-0011"))        # S10 overdue by 10 days
        self.assertNotIn("ESCALATION_SUGGESTED", self.alerts_of("RB-2026-0011"))  # only 10 days late
        self.assertIn("ESCALATED", self.alerts_of("PGRC-2026-0011"))    # S12
        self.assertNotIn("ESCALATION_SUGGESTED", self.alerts_of("PGRC-2026-0011"))  # already escalated

    def test_disposed_and_transferred_cases_never_get_time_alerts(self):
        self.scan()
        with Session(self.engine) as db:
            closed = db.scalars(select(m.Case.hub_case_id).where(m.Case.status.in_(["Disposed", "Transferred"]))).all()
            bad = db.scalars(select(m.Alert).where(m.Alert.case_id.in_(closed), m.Alert.type.in_(
                ["STALLED", "OVERDUE", "DUE_SOON", "ESCALATION_SUGGESTED", "PENDING_REMINDER"]), m.Alert.acknowledged_by.is_(None))).all()
            self.assertEqual(bad, [])

    def test_one_alert_per_track_per_case(self):
        self.scan()
        with Session(self.engine) as db:
            rows = db.scalars(select(m.Alert).where(m.Alert.type.in_(["OVERDUE", "ESCALATION_SUGGESTED", "DUE_SOON"]), m.Alert.acknowledged_by.is_(None))).all()
            cases = [a.case_id for a in rows]
            self.assertEqual(len(cases), len(set(cases)))  # never both OVERDUE and ESCALATION_SUGGESTED for a case

    def test_scan_is_repeat_safe(self):
        self.scan()
        again = self.scan()
        self.assertEqual((again["created"], again["cleared"]), (0, 0))

    def test_time_travel_clears_and_restores_alerts(self):
        self.scan()
        self.assertIn("OVERDUE", self.alerts_of("RB-2026-0011"))
        earlier = self.scan("2026-10-01")  # on 1 Oct that case was not yet overdue
        self.assertGreater(earlier["cleared"], 0)
        self.assertNotIn("OVERDUE", self.alerts_of("RB-2026-0011"))
        self.scan()
        self.assertIn("OVERDUE", self.alerts_of("RB-2026-0011"))  # comes back when the date is reached again

    def test_acknowledged_alert_is_not_raised_again(self):
        self.scan()
        alerts = self.client.get("/api/alerts?type=OVERDUE&open_only=true", headers=self.h("rb.officer")).json()
        mine = [a for a in alerts if a["source_case_no"] == "RB-2026-0011"][0]
        self.client.post(f"/api/alerts/{mine['id']}/acknowledge", headers=self.h("rb.officer"))
        self.assertEqual(self.scan()["created"], 0)
        self.assertNotIn("OVERDUE", self.alerts_of("RB-2026-0011"))  # still acknowledged

    # ---- actions change the picture ----
    def test_logging_an_action_clears_stalled_and_closing_clears_deadline_alerts(self):
        self.scan()
        hub = self.hub_id("RB-2026-0011")
        self.assertIn("STALLED", self.alerts_of("RB-2026-0011"))
        self.client.post(f"/api/cases/{hub}/actions", json={"action_type": "Under Review"}, headers=self.h("rb.officer"))
        self.assertNotIn("STALLED", self.alerts_of("RB-2026-0011"))
        self.assertIn("OVERDUE", self.alerts_of("RB-2026-0011"))  # still past its date
        self.client.post(f"/api/cases/{hub}/actions", json={"action_type": "Disposed - Action Taken"}, headers=self.h("rb.officer"))
        self.assertEqual(self.alerts_of("RB-2026-0011") & {"OVERDUE", "STALLED", "ESCALATION_SUGGESTED"}, set())

    def test_escalating_raises_an_escalated_alert(self):
        self.scan()
        hub = self.hub_id("RB-2026-0010")
        self.assertIn("ESCALATION_SUGGESTED", self.alerts_of("RB-2026-0010"))
        r = self.client.post(f"/api/cases/{hub}/actions", json={"action_type": "Escalated to Competent Authority"}, headers=self.h("rb.officer"))
        self.assertEqual(r.json()["status"], "Escalated")
        now = self.alerts_of("RB-2026-0010")
        self.assertIn("ESCALATED", now)
        self.assertNotIn("ESCALATION_SUGGESTED", now)  # suggestion done, the officer escalated

    # ---- configuration and scope ----
    def test_thresholds_are_configurable(self):
        with Session(self.engine) as db:
            db.get(m.Threshold, "STARVATION_DAYS").value = 1000
            db.commit()
        self.scan()
        with Session(self.engine) as db:
            self.assertEqual(db.scalars(select(m.Alert).where(m.Alert.type == "STALLED", m.Alert.acknowledged_by.is_(None))).all(), [])

    def test_overview_counts_and_scope(self):
        k = self.client.get(f"/api/starvation?as_of={AS_OF}&limit=5", headers=self.h("senior.mgmt")).json()
        self.assertEqual(k["thresholds"]["STARVATION_DAYS"], 30)
        self.assertEqual(k["counts"]["due_soon"], 2)  # S10 plus one filler case due on the demo date
        self.assertTrue(k["counts"]["stalled"] >= 1 and len(k["stalled"]) <= 5)
        self.assertEqual(k["stalled"][0]["idle_days"], max(i["idle_days"] for i in k["stalled"]))  # worst first
        full = self.client.get(f"/api/starvation?as_of={AS_OF}&limit=200", headers=self.h("senior.mgmt")).json()
        self.assertIn("RB-2026-0010", {i["source_case_no"] for i in full["stalled"]})
        rb = self.client.get(f"/api/starvation?as_of={AS_OF}&limit=200", headers=self.h("rb.officer")).json()
        self.assertTrue(all(i["bureau"] == "RB" for kind in ("stalled", "overdue", "due_soon") for i in rb[kind]))
        self.assertLess(rb["counts"]["stalled"], k["counts"]["stalled"])
        self.assertEqual(self.client.get("/api/starvation").status_code, 401)

    def test_who_may_scan(self):
        for user in ("regional.south", "other.bureau"):
            self.assertEqual(self.client.post("/api/starvation/scan", headers=self.h(user)).status_code, 403, user)
        self.assertEqual(self.client.post("/api/starvation/scan").status_code, 401)
        self.assertEqual(self.client.post("/api/starvation/scan", headers=self.h("senior.mgmt")).status_code, 200)

    def test_alert_list_shows_critical_first_and_scopes_time_alerts(self):
        self.scan()
        all_alerts = self.client.get("/api/alerts?open_only=true", headers=self.h("senior.mgmt")).json()
        self.assertEqual(all_alerts[0]["severity"], "critical")  # the S4 conflict comes before routine reminders
        rb = self.client.get("/api/alerts?type=STALLED&open_only=true", headers=self.h("rb.officer")).json()
        self.assertTrue(rb)
        with Session(self.engine) as db:
            bureau = {c.hub_case_id: c.assigned_bureau for c in db.scalars(select(m.Case))}
        self.assertTrue(all(bureau[a["case_id"]] == "RB" for a in rb))

    def test_kpis_include_time_counts(self):
        k = self.client.get("/api/dashboard/kpis", headers=self.h("senior.mgmt")).json()
        self.assertIn("overdue", k["totals"])


if __name__ == "__main__":
    unittest.main()
