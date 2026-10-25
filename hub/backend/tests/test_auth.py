"""M3 test: password hashing, login, token checks and the role rules.
Run from the project root:  python -m unittest discover -s hub/backend/tests -v
"""
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # makes `import app` work from anywhere

import jwt  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app import config, seed  # noqa: E402
from app.db import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import auth  # noqa: E402


class AuthTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
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

    def login(self, username="rb.officer", password="demo123"):
        return self.client.post("/api/auth/login", json={"username": username, "password": password})

    def test_password_hash_round_trip(self):
        stored = auth.hash_password("secret")
        self.assertTrue(auth.verify_password("secret", stored))
        self.assertFalse(auth.verify_password("Secret", stored))
        self.assertNotIn("secret", stored)
        self.assertNotEqual(auth.hash_password("secret"), stored)  # a new random salt every time

    def test_login_ok_and_me(self):
        r = self.login()
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["user"]["role"], "rb_officer")
        self.assertTrue(body["user"]["permissions"]["can_decide_links"])
        self.assertNotIn("password_hash", str(body))
        me = self.client.get("/api/auth/me", headers={"Authorization": "Bearer " + body["token"]})
        self.assertEqual(me.json()["username"], "rb.officer")

    def test_bad_password_and_unknown_user_look_the_same(self):
        a, b = self.login(password="wrong"), self.login(username="nobody")
        self.assertEqual((a.status_code, b.status_code), (401, 401))
        self.assertEqual(a.json(), b.json())

    def test_me_needs_a_valid_token(self):
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        self.assertEqual(self.client.get("/api/auth/me", headers={"Authorization": "Bearer junk"}).status_code, 401)
        expired = jwt.encode({"sub": "rb.officer", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
                             config.JWT_SECRET, algorithm="HS256")
        self.assertEqual(self.client.get("/api/auth/me", headers={"Authorization": "Bearer " + expired}).status_code, 401)
        forged = jwt.encode({"sub": "rb.officer"}, "another-secret-another-secret-another", algorithm="HS256")
        self.assertEqual(self.client.get("/api/auth/me", headers={"Authorization": "Bearer " + forged}).status_code, 401)

    def test_six_demo_roles_with_the_right_permissions(self):
        accounts = self.client.get("/api/auth/demo-accounts").json()
        self.assertEqual(len(accounts["accounts"]), 6)
        perms = {}
        for acc in accounts["accounts"]:
            perms[acc["role"]] = self.login(acc["username"], accounts["password"]).json()["user"]["permissions"]
        self.assertFalse(any(perms["senior_management"][k] for k in
                             ("can_log_actions", "can_decide_links", "can_transfer", "can_escalate")))  # read-only
        self.assertTrue(perms["competent_authority"]["can_decide_lead"])
        self.assertFalse(perms["rb_officer"]["can_decide_lead"])
        self.assertTrue(perms["regional_office"]["can_escalate"])
        self.assertEqual(perms["regional_office"]["view_scope"], "region")

    def test_require_roles_guard(self):
        guard = auth.require_roles("competent_authority")
        with self.assertRaises(Exception) as ctx:
            guard(user=type("U", (), {"role": "rb_officer"})())
        self.assertEqual(ctx.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
