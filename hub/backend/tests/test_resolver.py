"""M2 test: the resolver passes all of data/institution_name_tests.csv, and the registry API works.
Run from the project root:  python -m unittest discover -s hub/backend/tests -v
"""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # makes `import app` work from anywhere

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app import config, seed  # noqa: E402
from app.db import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services.institutions import resolve  # noqa: E402


class ResolverTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()  # temp database; hub.db is never touched
        cls.engine = create_engine(f"sqlite:///{Path(cls.tmp.name, 'test.db').as_posix()}",
                                   connect_args={"check_same_thread": False})
        seed.run(cls.engine)
        Session_ = sessionmaker(bind=cls.engine)

        def override():
            db = Session_()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        cls.engine.dispose()
        cls.tmp.cleanup()

    def test_all_name_tests_from_the_dataset(self):
        with open(config.DATA_DIR / "institution_name_tests.csv", newline="", encoding="utf-8-sig") as f:
            tests = list(csv.DictReader(f))
        self.assertGreaterEqual(len(tests), 45)
        with Session(self.engine) as db:
            for t in tests:
                r = resolve(db, t["typed_input"])
                got = {c["aicte_id"] for c in r["candidates"]}
                want = {x for x in t["expected_institution_id"].split(";") if x}
                with self.subTest(test=t["test_id"], typed=t["typed_input"]):
                    self.assertEqual(r["outcome"], t["expected_outcome"])
                    if t["expected_outcome"] == "RESOLVED":
                        self.assertEqual(got, want)
                    elif t["expected_outcome"] == "AMBIGUOUS":
                        self.assertTrue(want <= got and len(got) <= 3)
                    else:
                        self.assertEqual(got, set())

    def test_never_offers_a_parent_university(self):
        with Session(self.engine) as db:
            r = resolve(db, "SVU")  # acronym of Southern Vale University (SYN-0001)
            self.assertEqual(r["outcome"], "AMBIGUOUS")
            self.assertNotIn("SYN-0001", {c["aicte_id"] for c in r["candidates"]})

    def test_typo_and_live_typing(self):
        with Session(self.engine) as db:
            r = resolve(db, "Zenvora Colege of Architecure")
            self.assertEqual((r["outcome"], r["candidates"][0]["aicte_id"]), ("RESOLVED", "SYN-0004"))
            r = resolve(db, "zenv")  # half-typed word
            self.assertTrue(r["candidates"] and all("Zenvora" in c["official_name"] for c in r["candidates"]))

    def test_exact_id(self):
        with Session(self.engine) as db:
            self.assertEqual(resolve(db, "syn-0005")["candidates"][0]["aicte_id"], "SYN-0005")

    def test_api_search(self):
        r = self.client.get("/api/institutions/search", params={"q": "Kestora Institute of Pharmacy"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual((body["outcome"], body["candidates"][0]["aicte_id"]), ("RESOLVED", "SYN-0036"))
        self.assertIn("lat", body["candidates"][0])  # the confirm card needs the map pin

    def test_api_filters_narrow_step_by_step(self):
        everything = self.client.get("/api/institutions/filters").json()
        self.assertEqual(everything["count"], 40)
        state = everything["facets"]["states"][0]
        narrowed = self.client.get("/api/institutions/filters", params={"state": state}).json()
        self.assertLess(narrowed["count"], 40)
        self.assertEqual(narrowed["facets"]["states"], [state])

    def test_api_profile(self):
        r = self.client.get("/api/institutions/SYN-0032").json()
        self.assertEqual(r["cases"]["total"], 17)  # the repeat-complaint college
        parent = self.client.get("/api/institutions/SYN-0001").json()
        self.assertEqual(len(parent["children"]), 3)
        self.assertEqual(self.client.get("/api/institutions/SYN-9999").status_code, 404)
        self.assertEqual(self.client.get("/api/institutions/SYN-0040").json()["cases"]["total"], 0)


if __name__ == "__main__":
    unittest.main()
