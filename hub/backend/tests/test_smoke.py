"""M0 smoke test: the hub starts, /api/health works, every unbuilt feature answers 501.
Run from the project root:  python -m unittest discover -s hub/backend/tests -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # makes `import app` work from anywhere

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.routers import ALL  # noqa: E402


class Smoke(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")

    def test_every_feature_has_a_501_stub(self):
        self.assertEqual(len(ALL), 20)
        for module in ALL:
            if not getattr(module.router, "is_stub", False):
                continue  # real routers (built modules) have their own tests
            prefix = module.router.prefix
            for url in (prefix, prefix + "/anything"):
                r = self.client.get(url)
                self.assertEqual(r.status_code, 501, url)
                self.assertIn(r.json()["status"], ("planned", "stub"), url)

    def test_unknown_url_is_404(self):
        self.assertEqual(self.client.get("/api/nope").status_code, 404)


if __name__ == "__main__":
    unittest.main()
