"""M12 test: optional embeddings blend in when available, TF-IDF fallback otherwise (no model download needed).
Run from the project root:  python -m unittest discover -s hub/backend/tests -v
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app import models as m, seed  # noqa: E402
from app.db import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import embeddings, matching, similarity  # noqa: E402


class FakeModel:
    """Stands in for fastembed: texts with the word 'refund' get one direction, everything else another."""
    def embed(self, texts):
        for t in texts:
            yield [1.0, 0.0] if "refund" in t.lower() else [0.0, 1.0]


class EmbeddingTest(unittest.TestCase):
    def setUp(self):
        embeddings.reset_for_tests()

    def tearDown(self):
        embeddings.reset_for_tests()

    def test_off_by_default_uses_tfidf(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("HUB_EMBEDDINGS", None)
            self.assertIsNone(embeddings.embed_many(["a refund problem"]))
            self.assertEqual(embeddings.status()["similarity"], "tfidf")
            self.assertEqual(embeddings.status()["embeddings"], "off")

    def test_missing_package_falls_back_quietly(self):
        with mock.patch.dict(os.environ, {"HUB_EMBEDDINGS": "on"}), mock.patch.dict(sys.modules, {"fastembed": None}):
            self.assertIsNone(embeddings.embed_many(["a refund problem"]))
            st = embeddings.status()
            self.assertEqual((st["similarity"], st["embeddings"]), ("tfidf", "unavailable"))
            self.assertIn("Error", st["detail"])

    def test_model_failure_while_embedding_falls_back(self):
        class Broken:
            def embed(self, texts):
                raise RuntimeError("boom")
        embeddings._state.update({"model": Broken(), "tried": True})
        with mock.patch.dict(os.environ, {"HUB_EMBEDDINGS": "on"}):
            self.assertIsNone(embeddings.embed_many(["x"]))
            self.assertEqual(embeddings.status()["embeddings"], "unavailable")

    def test_scaled_cosine(self):
        self.assertEqual(embeddings.scaled([1, 0], [1, 0]), 1.0)
        self.assertEqual(embeddings.scaled([1, 0], [0, 1]), 0.0)  # below the floor -> 0
        self.assertAlmostEqual(embeddings.scaled([1, 0], [0.8, 0.6]), 0.6)  # cosine 0.8 -> (0.8-0.5)/0.5

    def test_compare_blends_only_when_vectors_exist(self):
        a, b = "Refund not returned after withdrawal", "Money refund still pending for withdrawn student"
        plain, _ = similarity.compare(a, b)
        same_meaning, _ = similarity.compare(a, b, vectors={a: [1, 0], b: [1, 0]})
        different, _ = similarity.compare(a, b, vectors={a: [1, 0], b: [0, 1]})
        self.assertGreater(same_meaning, different)
        self.assertAlmostEqual(same_meaning, round(0.5 * plain + 0.5, 3))
        self.assertAlmostEqual(different, round(0.5 * plain, 3))
        # vectors for only one text: ignored, plain TF-IDF score
        self.assertEqual(similarity.compare(a, b, vectors={a: [1, 0]})[0], plain)

    def test_detection_records_method_and_health_reports_it(self):
        embeddings._state.update({"model": FakeModel(), "tried": True})
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"HUB_EMBEDDINGS": "on"}):
            engine = create_engine(f"sqlite:///{Path(tmp, 't.db').as_posix()}", connect_args={"check_same_thread": False})
            seed.run(engine)
            S = sessionmaker(bind=engine, autoflush=False)
            with S() as db:
                links = list(db.scalars(select(m.LinkSuggestion).where(m.LinkSuggestion.link_type.in_(["SAME_REPORTER", "CORROBORATION"]))))
                self.assertTrue(links)
                self.assertTrue(all(l.reasons["method"] == "embeddings" for l in links))
            def override():
                with S() as db:
                    yield db
            app.dependency_overrides[get_db] = override
            try:
                health = TestClient(app).get("/api/health").json()
            finally:
                app.dependency_overrides.clear()
            self.assertEqual((health["similarity"], health["embeddings"]), ("embeddings", "active"))

    def test_seed_without_embeddings_still_records_tfidf(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {}):
            os.environ.pop("HUB_EMBEDDINGS", None)
            engine = create_engine(f"sqlite:///{Path(tmp, 't.db').as_posix()}", connect_args={"check_same_thread": False})
            seed.run(engine)
            with sessionmaker(bind=engine, autoflush=False)() as db:
                links = list(db.scalars(select(m.LinkSuggestion).where(m.LinkSuggestion.link_type == "CORROBORATION")))
                self.assertTrue(links)
                self.assertTrue(all(l.reasons["method"] == "tfidf" for l in links))


if __name__ == "__main__":
    unittest.main()
