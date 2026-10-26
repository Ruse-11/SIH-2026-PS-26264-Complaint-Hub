"""M11 test: reports, CSV export, scope, injection-safe cells, and insights.
Run from the project root:  python -m unittest discover -s hub/backend/tests -v
"""
import csv
import io
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, func, select  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app import seed  # noqa: E402
from app import models as m  # noqa: E402
from app.db import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import reports  # noqa: E402

AS_OF = "2026-10-25"


class ReportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{Path(self.tmp.name, 'test.db').as_posix()}", connect_args={"check_same_thread": False})
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

    def rep(self, key, user="senior.mgmt", extra=""):
        r = self.client.get(f"/api/reports/{key}?as_of={AS_OF}{extra}", headers=self.h(user))
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def count(self, *where):
        with Session(self.engine) as db:
            return db.scalar(select(func.count()).select_from(m.Case).where(*where))

    # ---- the PS report list ----
    def test_catalogue_has_every_report_the_ps_names(self):
        keys = {c["key"] for c in self.client.get("/api/reports", headers=self.h("rb.officer")).json()}
        self.assertEqual(keys, {"bureau", "region", "status", "institution", "institution_history", "ageing", "disposal", "overlaps", "monthly", "quarterly"})
        for key in keys - {"institution_history"}:
            data = self.rep(key)
            self.assertTrue(data["columns"] and data["rows"], key)

    def test_bureau_report_matches_the_database(self):
        rows = {r["bureau"]: r for r in self.rep("bureau")["rows"]}
        for b in ("RB", "PGRC"):
            self.assertEqual(rows[b]["total"], self.count(m.Case.assigned_bureau == b))
            self.assertEqual(rows[b]["disposed"], self.count(m.Case.assigned_bureau == b, m.Case.status == "Disposed"))
            self.assertEqual(rows[b]["total"], sum(rows[b][k] for k in ("pending", "under_process", "disposed", "transferred", "escalated")) + rows[b]["needs_review"])
        self.assertEqual(sum(r["total"] for r in rows.values()), 162)
        kpi = self.client.get(f"/api/dashboard/kpis?as_of={AS_OF}", headers=self.h("senior.mgmt")).json()["totals"]
        self.assertEqual(sum(r["beyond_timeline"] for r in rows.values()), kpi["overdue"])  # report and dashboard agree

    def test_region_and_status_reports(self):
        regions = self.rep("region")["rows"]
        self.assertEqual(sum(r["total"] for r in regions), 162)
        self.assertIn("(not identified)", {r["region"] for r in regions})  # the 3 unlisted cases
        statuses = {r["status"]: r["cases"] for r in self.rep("status")["rows"]}
        self.assertEqual(sum(statuses.values()), 162)
        self.assertEqual(statuses["Disposed"], self.count(m.Case.status == "Disposed"))

    def test_ageing_buckets_add_up(self):
        rows = {r["group"]: r for r in self.rep("ageing")["rows"]}
        allr = rows["All bureaus"]
        self.assertEqual(allr["open_cases"], sum(allr[b] for b in ("0-7 days", "8-15 days", "16-30 days", "Over 30 days")))
        self.assertEqual(allr["open_cases"], rows["RB"]["open_cases"] + rows["PGRC"]["open_cases"] + rows["QAC"]["open_cases"])
        self.assertEqual(allr["open_cases"], self.count(m.Case.status.in_(["Pending", "Under Process", "Escalated"])))
        self.assertGreaterEqual(allr["oldest_days"], allr["average_age_days"])

    def test_disposal_report(self):
        rows = self.rep("disposal")["rows"]
        total = rows[0]
        self.assertEqual((total["group_type"], total["disposed"]), ("All", self.count(m.Case.status == "Disposed")))
        self.assertAlmostEqual(total["disposal_rate_pct"], round(100 * total["disposed"] / 159, 1))  # 3 unlisted cases excluded
        self.assertTrue({"Bureau", "Category"} <= {r["group_type"] for r in rows})

    def test_monthly_and_quarterly_performance(self):
        months = self.rep("monthly")["rows"]
        self.assertEqual(sum(r["received"] for r in months), 162)
        self.assertEqual([r["period"] for r in months], sorted(r["period"] for r in months))
        self.assertEqual(months[-1]["period"], "2026-10")
        self.assertEqual(months[-1]["open_at_end"], self.count(m.Case.status.in_(["Pending", "Under Process", "Escalated"])))  # last month ends today
        self.assertEqual(sum(r["disposed"] for r in months), self.count(m.Case.status == "Disposed"))
        quarters = self.rep("quarterly")["rows"]
        self.assertEqual(sum(r["received"] for r in quarters), 162)
        self.assertEqual([r["period"] for r in quarters], ["FY2026-27 Q1", "FY2026-27 Q2", "FY2026-27 Q3"])  # Apr-Jun, Jul-Sep, Oct-Dec

    def test_financial_year_quarters(self):
        self.assertEqual(reports._fy_quarter(date(2026, 4, 1))[0], "FY2026-27 Q1")
        self.assertEqual(reports._fy_quarter(date(2026, 3, 31))[0], "FY2025-26 Q4")
        self.assertEqual(reports._fy_quarter(date(2026, 12, 31))[0], "FY2026-27 Q3")
        label, start, end = reports._fy_quarter(date(2027, 2, 10))
        self.assertEqual((label, start, end), ("FY2026-27 Q4", date(2027, 1, 1), date(2027, 3, 31)))

    def test_institution_report_and_history(self):
        inst = self.rep("institution")["rows"]
        self.assertEqual(inst[0]["institution_id"], "SYN-0032")  # the planted repeat-complaint college is first
        self.assertEqual(inst[0]["repeat_complaints"], "yes")
        hist = self.rep("institution_history", extra="&institution_id=SYN-0001")
        dates = [r["received"] for r in hist["rows"]]
        self.assertEqual(dates, sorted(dates))
        self.assertIn("Southern Vale University", hist["title"])
        group = self.rep("institution_history", extra="&institution_id=SYN-0001")["rows"]
        self.assertGreater(len(group), self.count(m.Case.institution_id == "SYN-0001"))  # university includes its colleges
        self.assertEqual(self.rep("institution_history")["rows"], [])  # no institution chosen

    def test_overlap_report(self):
        rows = self.rep("overlaps")["rows"]
        types = {r["type"] for r in rows}
        self.assertTrue({"CROSS_BUREAU", "CONFLICT", "DUPLICATE_ACTION", "CORROBORATION", "SAME_REPORTER"} <= types)
        self.assertTrue(all(r["status"] == "SUGGESTED" for r in rows[:5]))  # waiting items first
        s4 = [r for r in rows if r["type"] == "CONFLICT"][0]
        self.assertEqual({s4["case_a"], s4["case_b"]}, {"RB-2026-0005", "PGRC-2026-0004"})
        self.assertEqual(s4["suggested_lead"], "RB")

    # ---- scope, permissions, export ----
    def test_reports_are_limited_to_the_role(self):
        rb = {r["bureau"]: r for r in self.rep("bureau", "rb.officer")["rows"]}
        self.assertEqual(list(rb), ["RB"])
        self.assertEqual(rb["RB"]["total"], self.count(m.Case.assigned_bureau == "RB"))
        south = self.rep("region", "regional.south")["rows"]
        self.assertEqual([r["region"] for r in south], ["South"])
        overlaps = self.rep("overlaps", "regional.south")["rows"]
        self.assertTrue(len(overlaps) < len(self.rep("overlaps")["rows"]))
        self.assertEqual([r["bureau"] for r in self.rep("bureau", "other.bureau")["rows"]], ["QAC"])  # only its own bureau
        self.assertEqual(self.client.get("/api/reports/bureau").status_code, 401)
        self.assertEqual(self.client.get("/api/reports/nope", headers=self.h("rb.officer")).status_code, 404)

    def test_csv_export_rules_and_audit(self):
        r = self.client.get(f"/api/reports/bureau?format=csv&as_of={AS_OF}", headers=self.h("rb.officer"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/csv", r.headers["content-type"])
        self.assertIn("attachment", r.headers["content-disposition"])
        rows = list(csv.reader(io.StringIO(r.text.lstrip("﻿"))))
        self.assertEqual(rows[0][0], "Bureau / cell")
        self.assertEqual(rows[1][0], "RB")
        self.assertEqual(self.client.get("/api/reports/bureau?format=csv", headers=self.h("other.bureau")).status_code, 403)
        self.assertEqual(self.client.get("/api/reports/bureau?format=xml", headers=self.h("rb.officer")).status_code, 422)
        audit = self.client.get("/api/audit?action=REPORT_EXPORTED", headers=self.h("senior.mgmt")).json()
        self.assertEqual((len(audit), audit[0]["actor"], audit[0]["entity_id"]), (1, "rb.officer", "bureau"))

    def test_case_file_export_follows_filters_and_scope(self):
        def rows(user, qs=""):
            r = self.client.get("/api/cases/export" + qs, headers=self.h(user))
            self.assertEqual(r.status_code, 200)
            self.assertIn("case_file_", r.headers["content-disposition"])
            return list(csv.reader(io.StringIO(r.text.lstrip("\ufeff"))))
        everything = rows("senior.mgmt")
        self.assertEqual(len(everything) - 1, 162)  # every case, not one page of 25
        self.assertEqual(everything[0][0], "Hub case ID")
        pending = rows("senior.mgmt", "?status=Pending")
        self.assertEqual(len(pending) - 1, self.count(m.Case.status == "Pending"))
        self.assertLess(len(rows("regional.south")) - 1, 162)  # scope still applies
        self.assertEqual(self.client.get("/api/cases/export", headers=self.h("other.bureau")).status_code, 403)
        audit = self.client.get("/api/audit?action=CASE_FILE_EXPORTED", headers=self.h("senior.mgmt")).json()
        self.assertEqual(len(audit), 3)

    def test_single_case_file(self):
        cid = "HUB-0001"
        r = self.client.get(f"/api/cases/{cid}/file", headers=self.h("senior.mgmt"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/html", r.headers["content-type"])
        self.assertIn("PGRC-2026-0001_case_file.html", r.headers["content-disposition"])
        for needle in ("1. Summary", "Reporter-entered summary", "Action history", "Linked and suggested cases", "Alerts", "Audit trail", "Southern Vale University"):
            self.assertIn(needle, r.text)
        self.assertIn("Cross-bureau overlap", r.text)  # a collaboration section with the other bureau's case
        self.assertNotIn("Shown to senior management", r.text)  # senior management gets the audit section
        # roles: PGRC officer sees it (own bureau) but no audit trail; RB officer cannot see a PGRC case; other bureau cannot export
        pg = self.client.get(f"/api/cases/{cid}/file", headers=self.h("pgrc.officer"))
        self.assertEqual(pg.status_code, 200)
        self.assertIn("Shown to senior management", pg.text)
        self.assertEqual(self.client.get(f"/api/cases/{cid}/file", headers=self.h("rb.officer")).status_code, 403)
        self.assertEqual(self.client.get(f"/api/cases/{cid}/file", headers=self.h("other.bureau")).status_code, 403)
        self.assertEqual(self.client.get("/api/cases/HUB-9999/file", headers=self.h("senior.mgmt")).status_code, 404)
        audit = self.client.get("/api/audit?action=CASE_FILE_DOWNLOADED", headers=self.h("senior.mgmt")).json()
        self.assertEqual(len(audit), 2)

    def test_case_file_escapes_complaint_text(self):
        with Session(self.engine) as db:  # one more place the text could leak into markup
            case = db.get(m.Case, "HUB-0001")
            case.description = "<script>alert(1)</script> & more"
            db.commit()
        r = self.client.get("/api/cases/HUB-0001/file", headers=self.h("senior.mgmt"))
        self.assertNotIn("<script>alert(1)", r.text)
        self.assertIn("&lt;script&gt;", r.text)

    def test_csv_cells_cannot_run_as_spreadsheet_formulas(self):
        self.assertEqual(reports._safe('=HYPERLINK("http://x")'), "'=HYPERLINK(\"http://x\")")
        self.assertEqual(reports._safe("+1"), "'+1")
        self.assertEqual(reports._safe("@SUM(A1)"), "'@SUM(A1)")
        self.assertEqual(reports._safe(-3), -3)
        self.assertEqual(reports._safe(None), "")
        csv_text = reports.to_csv({"columns": [{"key": "t", "label": "Title"}], "rows": [{"t": "=cmd|' /C calc'!A0"}]})
        self.assertIn("'=cmd", csv_text)

    # ---- insights ----
    def test_insights_are_explained_and_scoped(self):
        data = self.client.get(f"/api/reports/insights?as_of={AS_OF}", headers=self.h("senior.mgmt")).json()
        ids = {i["id"] for i in data["insights"]}
        self.assertTrue({"repeat", "timeline", "stalled", "waiting", "disposal"} <= ids)
        for i in data["insights"]:
            self.assertTrue(i["title"] and i["rule"], i["id"])  # nothing without an explanation
        repeat = [i for i in data["insights"] if i["id"] == "repeat"][0]
        self.assertIn("Maventra College of Technology", repeat["title"])
        self.assertEqual(repeat["link"], "/institutions/SYN-0032")
        tones = [i["tone"] for i in data["insights"]]
        self.assertEqual(tones, sorted(tones, key=["bad", "warning", "neutral", "good"].index))  # worst first
        waiting = [i for i in data["insights"] if i["id"] == "waiting"][0]
        self.assertEqual(waiting["tone"], "bad")  # an unresolved conflict exists
        empty = self.client.get("/api/reports/insights", headers=self.h("other.bureau")).json()
        self.assertNotIn("repeat", [i["id"] for i in empty["insights"]])  # the QAC officer sees only its own 12 cases


if __name__ == "__main__":
    unittest.main()
