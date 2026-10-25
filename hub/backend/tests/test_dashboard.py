"""M8 backend test: KPIs, case list with search and filters, role scope, institution history, Needs Review,
and the "same reporter files twice counts once" boost rule.
Run from the project root:  python -m unittest discover -s hub/backend/tests -v
"""
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, func, select  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app import config, seed  # noqa: E402
from app import models as m  # noqa: E402
from app.db import get_db  # noqa: E402
from app.main import app  # noqa: E402

PORTAL = lambda p: {"X-API-Key": config.PORTAL_API_KEYS[p]}  # noqa: E731
TEXT = "The hostel water supply has failed for several days and nobody has repaired it."


def complaint(no, contact, inst="SYN-0040", category="Hostel/Mess", title="Hostel water supply failure", desc=TEXT, finder=None):
    return {"source_case_no": no, "verified_institution_id": inst, "resolution_method": "REPORTER_CONFIRMED" if inst else "UNLISTED",
            "finder_answers": finder, "reporter": {"contact": contact, "reporter_type": "student"},
            "category": category, "title": title, "description": desc, "severity": 3}


class DashboardTest(unittest.TestCase):
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

    def get(self, path, user="senior.mgmt"):
        r = self.client.get(path, headers=self.h(user))
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def db_count(self, *where):
        with Session(self.engine) as db:
            return db.scalar(select(func.count()).select_from(m.Case).where(*where))

    # ---- KPIs ----
    def test_kpis_add_up_and_match_the_database(self):
        k = self.get("/api/dashboard/kpis?as_of=2026-10-25")
        t = k["totals"]
        self.assertEqual(t["total"], 150)
        self.assertEqual(t["total"], sum(t[x] for x in ("pending", "under_process", "disposed", "transferred", "escalated", "unverified")))
        self.assertEqual(t["unverified"], 3)
        self.assertEqual(t["disposed"], self.db_count(m.Case.status == "Disposed"))
        self.assertEqual(sum(b["total"] for b in k["by_bureau"]), 150)
        self.assertGreater(k["suggestions_waiting"]["cross_bureau"], 0)
        self.assertGreater(len(k["by_institution"]), 5)

    def test_overdue_grows_with_the_reference_date(self):
        early = self.get("/api/dashboard/kpis?as_of=2026-08-01")["totals"]["overdue"]
        late = self.get("/api/dashboard/kpis?as_of=2026-12-31")["totals"]["overdue"]
        self.assertGreater(late, early)
        self.assertEqual(late, self.get("/api/dashboard/kpis?as_of=2026-12-31")["totals"]["open"])  # by Dec every open case is late
        listed = self.get("/api/cases?overdue=true&as_of=2026-12-31&page_size=100")
        self.assertEqual(listed["total"], late)

    def test_kpis_follow_the_role(self):
        rb = self.get("/api/dashboard/kpis", "rb.officer")
        self.assertEqual(rb["totals"]["total"], self.db_count(m.Case.assigned_bureau == "RB"))
        self.assertEqual([b["assigned_bureau"] for b in rb["by_bureau"]], ["RB"])
        south = self.get("/api/dashboard/kpis", "regional.south")
        self.assertTrue(0 < south["totals"]["total"] < 150)
        self.assertEqual([r["region"] for r in south["by_region"]], ["South"])
        self.assertEqual(self.get("/api/dashboard/kpis", "other.bureau")["totals"]["total"], 0)  # no cases assigned yet

    # ---- list, search, filters ----
    def test_search_by_case_id_aicte_id_and_name(self):
        self.assertEqual(self.get("/api/cases?q=RB-2026-0003")["items"][0]["source_case_no"], "RB-2026-0003")
        self.assertEqual(self.get("/api/cases?q=HUB-0005")["items"][0]["source_case_no"], "RB-2026-0003")
        by_id = self.get("/api/cases?q=SYN-0009&page_size=100")
        self.assertTrue(by_id["total"] >= 3 and all(i["institution_id"] == "SYN-0009" for i in by_id["items"]))
        with Session(self.engine) as db:
            inst = db.get(m.Institution, "SYN-0009")
            alias = db.scalars(select(m.InstitutionAlias).where(m.InstitutionAlias.institution_id == "SYN-0009")).first()
        for text in (inst.official_name.split()[0], inst.official_name.lower(), alias.alias):
            found = self.get(f"/api/cases?q={text}&page_size=100")
            self.assertIn("SYN-0009", {i["institution_id"] for i in found["items"]}, text)
        self.assertEqual(self.get("/api/cases?q=zzzzqqq")["total"], 0)

    def test_filters_and_pagination(self):
        opts = self.get("/api/cases/filters")
        self.assertIn("RB", opts["bureaus"])
        self.assertIn("South", opts["regions"])
        self.assertIn("Fee/Refund", opts["categories"])
        self.assertEqual(self.get("/api/cases?bureau=PGRC&page_size=100")["total"], self.db_count(m.Case.assigned_bureau == "PGRC"))
        self.assertEqual(self.get("/api/cases?status=Disposed")["total"], self.db_count(m.Case.status == "Disposed"))
        july = self.get("/api/cases?date_from=2026-07-01&date_to=2026-07-31&page_size=100")
        self.assertTrue(july["total"] > 0 and all(i["received_at"].startswith("2026-07") for i in july["items"]))
        self.assertTrue(all(i["region"] == "South" for i in self.get("/api/cases?region=South&page_size=100")["items"]))
        p1, p2 = self.get("/api/cases?page_size=10&page=1"), self.get("/api/cases?page_size=10&page=2")
        self.assertEqual((len(p1["items"]), p1["total"]), (10, 150))
        self.assertFalse({i["hub_case_id"] for i in p1["items"]} & {i["hub_case_id"] for i in p2["items"]})
        scores = [i["priority_score"] for i in p1["items"]]
        self.assertEqual(scores, sorted(scores, reverse=True))  # default order = highest priority first

    def test_officer_sees_only_own_bureau_and_cannot_open_others(self):
        items = self.get("/api/cases?page_size=100", "rb.officer")["items"]
        self.assertTrue(items and all(i["assigned_bureau"] == "RB" for i in items))
        self.assertEqual(self.get("/api/cases?bureau=PGRC", "rb.officer")["total"], 0)
        with Session(self.engine) as db:
            pgrc = db.scalars(select(m.Case).where(m.Case.assigned_bureau == "PGRC")).first().hub_case_id
        r = self.client.get(f"/api/cases/{pgrc}", headers=self.h("rb.officer"))
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.client.get(f"/api/cases/{pgrc}", headers=self.h("senior.mgmt")).status_code, 200)
        self.assertEqual(self.client.get("/api/cases").status_code, 401)

    def test_links_and_alerts_are_scoped_but_overlap_stays_visible_to_both_bureaus(self):
        rb_links = self.get("/api/matching/links?institution_id=SYN-0001", "rb.officer")
        self.assertTrue(any(l["link_type"] == "CROSS_BUREAU" for l in rb_links))  # S1 involves an RB case
        south_ids = {i["institution_id"] for i in self.get("/api/cases?page_size=100", "regional.south")["items"]}
        for l in self.get("/api/matching/links", "regional.south"):
            self.assertIn(l["institution"]["aicte_id"], south_ids)

    def test_global_search_and_institution_history(self):
        found = self.get("/api/search?q=SYN-0001")
        self.assertEqual(found["institutions"][0]["aicte_id"], "SYN-0001")
        self.assertTrue(found["cases"])
        hist = self.get("/api/institutions/SYN-0001/history")
        dates = [c["received_at"] for c in hist["cases"]]
        self.assertEqual(dates, sorted(dates))  # oldest first
        self.assertTrue(hist["links"] and hist["alerts"] is not None)
        self.assertEqual(self.client.get("/api/institutions/NOPE/history", headers=self.h("rb.officer")).status_code, 404)
        self.assertEqual(self.client.get("/api/institutions/SYN-0001/history").status_code, 401)
        s0040 = self.get("/api/institutions/SYN-0040/history")
        self.assertEqual(s0040["cases"], [])

    # ---- search suggestions for officers ----
    def suggest(self, q, user="rb.officer"):
        return [c["official_name"] for c in self.get(f"/api/institutions/suggest?q={q}", user)]

    def test_suggestions_find_partial_words_universities_and_places(self):
        vale = self.suggest("Vale")
        self.assertIn("Southern Vale University", vale)
        self.assertIn("Meridian Vale Technical Institute", vale)
        self.assertTrue(all("Vale" in n for n in vale[:4]))  # real name matches come first
        self.assertEqual(set(vale[4:]), {"Orbelis College of Technology", "Quoralis Institute of Engineering",
                                         "Zenvora College of Architecture"})  # then colleges of Southern Vale University (via aliases)
        self.assertEqual(self.suggest("Souther")[0], "Southern Vale University")  # a half-typed word
        self.assertEqual(self.suggest("Orbelis Chennai")[0], "Orbelis College of Technology")  # name + place
        self.assertEqual(self.suggest("Zenvra")[0].split()[0], "Zenvora")  # a typo
        self.assertEqual(self.suggest("SYN-0009")[0], "Eastern Meridian University")  # AICTE ID
        self.assertEqual(self.suggest("qqqqzz"), [])
        self.assertEqual(self.suggest("a"), [])  # too short
        cards = self.get("/api/institutions/suggest?q=Southern Vale", "senior.mgmt")
        self.assertEqual((cards[0]["aicte_id"], cards[0]["colleges"]), ("SYN-0001", 3))  # a university with 3 colleges
        self.assertEqual(self.client.get("/api/institutions/suggest?q=vale").status_code, 401)
        self.assertEqual(len(self.get("/api/institutions/suggest?q=college&limit=3")), 3)

    def test_picking_a_university_also_shows_its_colleges_cases(self):
        own = self.db_count(m.Case.institution_id == "SYN-0001")
        group = self.db_count(m.Case.institution_id.in_(["SYN-0001", "SYN-0002", "SYN-0003", "SYN-0004"]))
        self.assertGreater(group, own)
        self.assertEqual(self.get("/api/cases?institution_id=SYN-0001&page_size=100")["total"], group)
        self.assertEqual(self.get("/api/cases?institution_id=SYN-0002&page_size=100")["total"], self.db_count(m.Case.institution_id == "SYN-0002"))
        self.assertEqual(self.get("/api/cases?q=Souther&page_size=100")["total"], group)

    # ---- Needs Review ----
    def test_needs_review_and_assigning_a_college_learns_the_alias(self):
        r = self.client.post("/api/intake", headers=PORTAL("PGRC"), json=complaint(
            "PGRC-2026-9100", "9000000031", inst=None, finder=({"typed_name": "Zorbex Polytechnik Annex"})))
        self.assertEqual(r.status_code, 201)
        queue = self.get("/api/cases/needs-review", "pgrc.officer")
        mine = [q for q in queue if q["source_case_no"] == "PGRC-2026-9100"]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]["typed_details"]["typed_name"], "Zorbex Polytechnik Annex")
        self.assertFalse([q for q in self.get("/api/cases/needs-review", "rb.officer") if q["source_case_no"] == "PGRC-2026-9100"])
        hub_id = mine[0]["hub_case_id"]
        body = {"institution_id": "SYN-0040"}
        self.assertEqual(self.client.post(f"/api/cases/{hub_id}/assign-institution", json=body, headers=self.h("senior.mgmt")).status_code, 403)
        self.assertEqual(self.client.post(f"/api/cases/{hub_id}/assign-institution", json={"institution_id": "NOPE"}, headers=self.h("pgrc.officer")).status_code, 422)
        ok = self.client.post(f"/api/cases/{hub_id}/assign-institution", json=body, headers=self.h("pgrc.officer"))
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual(ok.json()["learned_alias"], "Zorbex Polytechnik Annex")
        detail = self.get(f"/api/cases/{hub_id}")
        self.assertEqual((detail["status"], detail["institution"]["aicte_id"], detail["resolution_method"]), ("Pending", "SYN-0040", "OFFICER_ASSIGNED"))
        again = self.client.post(f"/api/cases/{hub_id}/assign-institution", json=body, headers=self.h("pgrc.officer"))
        self.assertEqual(again.status_code, 409)
        search = self.client.get("/api/institutions/search", params={"q": "Zorbex Polytechnik Annex"}).json()
        self.assertEqual(search["outcome"], "RESOLVED")  # the learned alias now helps the next reporter
        audit = self.get("/api/audit?action=INSTITUTION_ASSIGNED")
        self.assertEqual(len(audit), 1)

    # ---- the rule sai asked to test ----
    def test_same_reporter_filing_twice_counts_as_one_corroborator(self):
        self.client.post("/api/intake", headers=PORTAL("PGRC"), json=complaint("PGRC-2026-9201", "9000000041"))   # reporter Y
        self.client.post("/api/intake", headers=PORTAL("RB"), json=complaint("RB-2026-9201", "9000000042"))       # reporter X, first complaint
        self.client.post("/api/intake", headers=PORTAL("RB"), json=complaint("RB-2026-9202", "9000000042"))       # reporter X again
        with Session(self.engine) as db:
            no = {c.hub_case_id: c.source_case_no for c in db.scalars(select(m.Case))}
            links = list(db.scalars(select(m.LinkSuggestion).where(m.LinkSuggestion.link_type == "CORROBORATION")))
            y_links = [l for l in links if "PGRC-2026-9201" in (no[l.case_a], no[l.case_b])]
            self.assertEqual(len(y_links), 2)  # Y is linked to both of X's complaints
            y_id = db.scalars(select(m.Case).where(m.Case.source_case_no == "PGRC-2026-9201")).one().hub_case_id
            ids = [l.id for l in y_links]
        before = self.get(f"/api/corroboration/{y_id}")
        self.assertEqual(before["potential_boost"], 5)  # two links, but one independent person: +5 not +10
        for i in ids:
            self.assertEqual(self.client.post(f"/api/matching/links/{i}/confirm", headers=self.h("competent.authority")).status_code, 200)
        after = self.get(f"/api/corroboration/{y_id}")
        self.assertEqual((after["confirmed_corroborators"], after["parts"]["corroboration"]), (1, 5))


if __name__ == "__main__":
    unittest.main()
