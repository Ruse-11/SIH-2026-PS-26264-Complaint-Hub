"""Search engine test: initials, typos, partial words, never-empty tiers, speed on a large registry, shared by the portals.
Run from the project root:  python -m unittest discover -s hub/backend/tests -v
"""
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app import models as m, seed  # noqa: E402
from app.db import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import institutions, searchengine  # noqa: E402


class SearchEngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.engine = create_engine(f"sqlite:///{Path(cls.tmp.name, 't.db').as_posix()}", connect_args={"check_same_thread": False})
        seed.run(cls.engine)
        cls.S = sessionmaker(bind=cls.engine, autoflush=False)

        def override():
            with cls.S() as db:
                yield db
        app.dependency_overrides[get_db] = override
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        cls.tmp.cleanup()

    def names(self, q, limit=8):
        with self.S() as db:
            return [c["official_name"] for c in searchengine.find(db, q, limit)]

    def first(self, q):
        return (self.names(q) or [None])[0]

    def test_initials_find_the_college(self):
        # "Kestora Institute of Pharmacy" -> KIP (the case that failed before), also partial initials
        for q in ("KIP", "kip", "ki", "KIP indore"):
            self.assertEqual(self.first(q), "Kestora Institute of Pharmacy", q)

    def test_typos_partial_words_places_and_ids(self):
        self.assertEqual(self.first("kiop"), "Kestora Institute of Pharmacy")
        self.assertTrue(self.first("kestra").startswith("Kestora"))
        self.assertTrue(self.first("zenvra").startswith("Zenvora"))
        self.assertEqual(self.first("Souther"), "Southern Vale University")
        self.assertEqual(self.first("orbelis chennai"), "Orbelis College of Technology")
        self.assertEqual(self.first("SYN-0009"), "Eastern Meridian University")
        self.assertIn("Kestora Institute of Pharmacy", self.names("phrmacy inst", 40))

    def test_tiers_never_empty_when_a_word_matches(self):
        with self.S() as db:
            r = searchengine.find(db, "kestora nonsenseword")
        self.assertTrue(r and r[0]["tier"] == "partial" and r[0]["official_name"].startswith("Kestora"))
        with self.S() as db:
            self.assertTrue(all(c["tier"] == "match" for c in searchengine.find(db, "kestora")))
        self.assertEqual(self.names("qqqqzz"), [])  # real nonsense stays empty
        self.assertEqual(self.names("a"), [])
        self.assertEqual(self.names("xyz college"), [])  # the word "college" alone is not evidence

    def test_portal_search_returns_suggestions_instead_of_nothing(self):
        for q in ("ki", "pharmcy%20indore"):  # the strict resolver says NOT_LISTED; the engine still has a good guess
            r = self.client.get("/api/institutions/search?q=" + q).json()
            self.assertEqual(r["outcome"], "NOT_LISTED", q)
            self.assertEqual(r["suggestions"][0]["official_name"], "Kestora Institute of Pharmacy", q)
        r = self.client.get("/api/institutions/search?q=KIP").json()
        self.assertEqual(r["candidates"][0]["official_name"], "Kestora Institute of Pharmacy")
        # a university is never offered to a reporter, only its colleges
        r = self.client.get("/api/institutions/search?q=Southern%20Vale").json()
        self.assertTrue(all(not s.get("colleges") for s in r.get("suggestions", [])))
        # a clear winner has no extra list
        self.assertNotIn("suggestions", self.client.get("/api/institutions/search?q=SYN-0009").json())

    def test_case_search_uses_the_same_engine(self):
        total = self.client.post("/api/auth/login", json={"username": "senior.mgmt", "password": "demo123"}).json()["token"]
        h = {"Authorization": "Bearer " + total}
        by_initials = self.client.get("/api/cases?q=KIP&page_size=100", headers=h).json()
        by_id = self.client.get("/api/cases?institution_id=SYN-0036&page_size=100", headers=h).json()
        self.assertGreater(by_id["total"], 0)
        self.assertGreaterEqual(by_initials["total"], by_id["total"])

    def test_index_rebuilds_when_an_alias_is_learned(self):
        with self.S() as db:
            self.assertEqual(searchengine.find(db, "zzquirk"), [])
            db.add(m.InstitutionAlias(alias="zzquirk", alias_normalized="zzquirk", institution_id="SYN-0036", alias_type="LEARNED", source="learned"))
            db.commit()
            found = searchengine.find(db, "zzquirk")
            self.assertEqual(found[0]["aicte_id"], "SYN-0036")
            db.query(m.InstitutionAlias).filter_by(alias_normalized="zzquirk").delete()
            db.commit()

    def test_fast_on_a_large_registry(self):
        """15,000 colleges (about AICTE's size): build once, then each search is quick."""
        tmp = tempfile.TemporaryDirectory()
        eng = create_engine(f"sqlite:///{Path(tmp.name, 'big.db').as_posix()}")
        m.Base.metadata.create_all(eng)
        first = ["Kestora", "Orbelis", "Zenvora", "Quoralis", "Avenor", "Deltora", "Crestora", "Meridian", "Astermere", "Vantera"]
        kind = ["Institute of Pharmacy", "College of Technology", "College of Engineering", "Institute of Management", "School of Architecture"]
        place = ["Indore", "Chennai", "Pune", "Lucknow", "Jaipur", "Patna", "Kochi", "Nagpur", "Surat", "Bhopal"]
        rows = []
        for n in range(15000):
            name = f"{first[n % 10]}{n // 50} {kind[(n // 10) % 5]}"
            rows.append(m.Institution(aicte_id=f"BIG-{n:05d}", official_name=name, name_normalized=institutions.normalize_name(name),
                                      district=place[(n // 3) % 10], state="Test State", region="Test", type="College"))
        with sessionmaker(bind=eng, autoflush=False)() as db:
            db.add_all(rows)
            db.commit()
            t = time.perf_counter()
            searchengine.reset_cache()
            searchengine.get_index(db)
            build = time.perf_counter() - t
            worst = 0.0
            for q in ("kip", "kestora5 phrmacy", "orbel", "zenvra indore", "college", "xqzv"):
                t = time.perf_counter()
                searchengine.find(db, q, 8)
                worst = max(worst, time.perf_counter() - t)
            print(f"\n[15,000 colleges] index build {build:.2f}s, slowest search {worst * 1000:.0f} ms")
            self.assertLess(build, 15)
            self.assertLess(worst, 0.5)
        searchengine.reset_cache()
        tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
