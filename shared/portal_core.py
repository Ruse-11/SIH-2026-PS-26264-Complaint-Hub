"""Shared engine of the two MOCK portals (RB and PGRC). They are not the real AICTE portals.

Each portal has its own database and its own case numbers. It never decides anything about the institution:
it asks the hub's registry, lets the reporter confirm, and hands the complaint to the hub (POST /api/intake).
If the hub is down, the complaint is kept with sync_status=pending and re-sent automatically (outbox).
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from contextlib import asynccontextmanager, closing
from datetime import datetime
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

CATEGORIES = [  # the categories this mock portal offers on its form (same list the hub knows)
    "Fee/Refund", "Faculty Shortage/Qualification", "Infrastructure/Lab", "Admission Irregularity",
    "Approval/Affiliation", "Ragging/Harassment", "Placement Misrepresentation", "Exam/Result", "Hostel/Mess",
    "Scholarship", "Misleading Advertisement/Accreditation Claim",
]
REPORTER_TYPES = ["student", "parent", "alumni", "faculty", "other"]
TOKEN_MINUTES = 30      # institution and phone confirmations expire after this
OTP_MINUTES = 5
MAX_OTP_TRIES = 5
FIRST_CASE_NUMBER = 1001  # the dataset already uses RB-2026-0001..; portal numbers start higher so they never clash
RETRY_SECONDS = 10      # how often the outbox tries to re-send waiting complaints
CONTACT_RE = re.compile(r"^(\+?\d[\d\s-]{8,14}|[^@\s]+@[^@\s]+\.[^@\s]+)$")  # a phone number or an email


def normalize_contact(contact: str) -> str:
    c = contact.strip().lower()
    return re.sub(r"[^\d+]", "", c) if "@" not in c else c


class ConfirmBody(BaseModel):
    institution_id: str | None = Field(default=None, max_length=40)  # None = "my institution isn't listed"
    resolution_method: Literal["REPORTER_CONFIRMED", "GUIDED", "UNLISTED"] = "REPORTER_CONFIRMED"
    finder_answers: dict | None = None  # guided answers, or the details typed for an unlisted college


class OtpRequestBody(BaseModel):
    contact: str = Field(min_length=5, max_length=100)


class OtpVerifyBody(BaseModel):
    contact: str = Field(min_length=5, max_length=100)
    code: str = Field(min_length=4, max_length=8)


class SubmitBody(BaseModel):
    institution_token: str
    verification_token: str
    reporter_type: Literal["student", "parent", "alumni", "faculty", "other"] = "other"
    category: str
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=10, max_length=4000)
    severity: int = Field(default=3, ge=1, le=5)


class Portal:
    def __init__(self, code, name, folder, shared_dir, default_api_key, db_path=None, hub_client=None):
        self.code, self.name = code, name
        self.folder, self.shared_dir = Path(folder), Path(shared_dir)
        self.db_path = str(db_path or self.folder / f"{code.lower()}.db")
        self.api_key = os.getenv("PORTAL_API_KEY", default_api_key)
        self.public_hub_url = os.getenv("PUBLIC_HUB_URL", "http://localhost:8000")  # what the BROWSER calls
        self.secret = os.getenv("PORTAL_TOKEN_SECRET", "dev-portal-token-secret-change-me").encode()
        # hub_client is replaced by a test client in the unit tests
        self.hub = hub_client or httpx.Client(base_url=os.getenv("HUB_URL", "http://127.0.0.1:8000"), timeout=5.0)
        self._stop = threading.Event()
        self._init_db()

    # ---------------- own database ----------------
    def _connect(self):
        return closing(sqlite3.connect(self.db_path, timeout=10))

    def _init_db(self):
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS otp (contact TEXT PRIMARY KEY, code_hash TEXT, expires REAL, tries INTEGER);
                CREATE TABLE IF NOT EXISTS submissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, portal_case_no TEXT UNIQUE, payload TEXT,
                    institution_id TEXT, institution_name TEXT, sync_status TEXT, hub_case_id TEXT, hub_status TEXT,
                    alerts TEXT, attempts INTEGER DEFAULT 0, last_error TEXT, created_at TEXT);
            """)
            db.commit()

    # ---------------- signed tokens (HMAC) ----------------
    def sign(self, payload: dict, minutes: float = TOKEN_MINUTES) -> str:
        body = dict(payload, portal=self.code, exp=time.time() + minutes * 60)
        raw = base64.urlsafe_b64encode(json.dumps(body, separators=(",", ":")).encode()).decode().rstrip("=")
        return raw + "." + hmac.new(self.secret, raw.encode(), hashlib.sha256).hexdigest()

    def verify(self, token: str, kind: str) -> dict:
        """Returns the payload if the token is genuine, unexpired, of this kind and from this portal."""
        try:
            raw, sig = token.split(".")
            good = hmac.new(self.secret, raw.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, good):
                raise ValueError
            body = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        except Exception:
            raise HTTPException(401, "Invalid confirmation. Please start again.")
        if body.get("portal") != self.code or body.get("kind") != kind:
            raise HTTPException(401, "Invalid confirmation. Please start again.")
        if body["exp"] < time.time():
            raise HTTPException(401, "Your confirmation expired. Please start again.")
        return body

    # ---------------- talking to the hub ----------------
    def _send(self, row_id: int):
        """Try to hand one stored complaint to the hub and record the outcome."""
        with self._connect() as db:
            payload, attempts = db.execute("SELECT payload, attempts FROM submissions WHERE id=?", (row_id,)).fetchone()
        try:
            r = self.hub.post("/api/intake", json=json.loads(payload), headers={"X-API-Key": self.api_key})
        except httpx.HTTPError as e:  # hub down or slow: keep it pending, the outbox retries
            return self._record(row_id, "pending", attempts + 1, error=f"hub unreachable: {type(e).__name__}")
        if r.status_code in (200, 201):
            body = r.json()
            return self._record(row_id, "synced", attempts + 1, hub=body)
        detail = r.json().get("detail", r.text) if r.headers.get("content-type", "").startswith("application/json") else r.text
        if r.status_code >= 500:
            return self._record(row_id, "pending", attempts + 1, error=f"hub error {r.status_code}")
        return self._record(row_id, "rejected" if r.status_code != 401 else "failed", attempts + 1,
                            error=f"{r.status_code}: {detail}")  # 4xx will not succeed by retrying

    def _record(self, row_id, status, attempts, hub=None, error=None):
        with self._connect() as db:
            db.execute("UPDATE submissions SET sync_status=?, attempts=?, last_error=?, hub_case_id=COALESCE(?, hub_case_id),"
                       " hub_status=COALESCE(?, hub_status), alerts=COALESCE(?, alerts) WHERE id=?",
                       (status, attempts, error, hub and hub["hub_case_id"], hub and hub["status"],
                        hub and json.dumps(hub.get("alerts_created", [])), row_id))
            db.commit()

    def sync_pending(self) -> int:
        """Outbox: re-send every complaint still waiting. Safe to repeat, the hub ignores a case number it already has."""
        with self._connect() as db:
            ids = [r[0] for r in db.execute("SELECT id FROM submissions WHERE sync_status='pending' ORDER BY id")]
        for i in ids:
            self._send(i)
        return len(ids)

    def _outbox_loop(self):
        while not self._stop.wait(RETRY_SECONDS):
            try:
                self.sync_pending()
            except Exception as e:  # never let the retry thread die
                print(f"[{self.code}] outbox error: {e}", flush=True)

    # ---------------- receipts ----------------
    def receipt(self, portal_case_no: str) -> dict:
        with self._connect() as db:
            row = db.execute("SELECT portal_case_no, institution_id, institution_name, sync_status, hub_case_id,"
                             " hub_status, alerts, last_error FROM submissions WHERE portal_case_no=?",
                             (portal_case_no,)).fetchone()
        if row is None:
            raise HTTPException(404, "No such complaint")
        no, iid, iname, sync, hub_id, hub_status, alerts, err = row
        return {"portal_case_no": no, "hub_case_id": hub_id, "sync_status": sync, "hub_status": hub_status,
                "institution": {"aicte_id": iid, "official_name": iname} if iid else None,
                "pending_verification": iid is None, "alerts_created": json.loads(alerts) if alerts else [],
                "last_error": err}

    # ---------------- the web app ----------------
    def build_app(self) -> FastAPI:
        @asynccontextmanager
        async def lifespan(_app):
            threading.Thread(target=self._outbox_loop, daemon=True).start()
            yield
            self._stop.set()

        app = FastAPI(title=f"{self.code} Portal (mock)", lifespan=lifespan)
        app.state.portal = self

        @app.get("/health")
        def health():
            return {"status": "ok", "service": f"portal_{self.code.lower()}"}

        @app.get("/config")
        def config():
            """The page asks for its name and where the hub's registry lives."""
            return {"portal_code": self.code, "portal_name": self.name, "hub_url": self.public_hub_url,
                    "categories": CATEGORIES, "reporter_types": REPORTER_TYPES}

        @app.post("/institution/confirm")
        def confirm_institution(body: ConfirmBody):
            """Step 1 ends here: the reporter confirmed a college (or says it is not listed). Returns a signed token."""
            if body.institution_id is None:
                typed = ((body.finder_answers or {}).get("typed_name") or "").strip()
                if len(typed) < 3:
                    raise HTTPException(422, "Please type the name of the institution.")
                token = self.sign({"kind": "inst", "iid": None, "method": "UNLISTED", "answers": body.finder_answers})
                return {"institution_token": token, "institution": None, "resolution_method": "UNLISTED",
                        "pending_verification": True, "expires_in_minutes": TOKEN_MINUTES}
            if body.resolution_method == "UNLISTED":
                raise HTTPException(422, "An institution ID cannot be combined with 'not listed'.")
            try:
                r = self.hub.get(f"/api/institutions/{body.institution_id}")
            except httpx.HTTPError:
                raise HTTPException(503, "The institution registry is not reachable. Please try again shortly.")
            if r.status_code == 404:
                raise HTTPException(422, "That institution is not in the registry.")
            inst = r.json()
            if inst["children"]:
                raise HTTPException(422, "That is a university with several colleges. Please choose your college.")
            token = self.sign({"kind": "inst", "iid": inst["aicte_id"], "iname": inst["official_name"],
                               "method": body.resolution_method, "answers": body.finder_answers})
            return {"institution_token": token, "resolution_method": body.resolution_method,
                    "institution": {"aicte_id": inst["aicte_id"], "official_name": inst["official_name"]},
                    "pending_verification": False, "expires_in_minutes": TOKEN_MINUTES}

        @app.post("/otp/request")
        def otp_request(body: OtpRequestBody):
            """MOCK OTP: in demo mode the code is returned to the page instead of being sent by SMS."""
            if not CONTACT_RE.match(body.contact.strip()):
                raise HTTPException(422, "Enter a 10-digit mobile number or an email address.")
            contact, code = normalize_contact(body.contact), f"{secrets.randbelow(10**6):06d}"
            with self._connect() as db:
                db.execute("INSERT OR REPLACE INTO otp VALUES (?,?,?,0)",
                           (contact, hashlib.sha256(f"{contact}:{code}".encode()).hexdigest(), time.time() + OTP_MINUTES * 60))
                db.commit()
            return {"demo_mode": True, "demo_otp": code, "expires_in_minutes": OTP_MINUTES,
                    "message": "Demo mode: no SMS is sent, the code is shown here."}

        @app.post("/otp/verify")
        def otp_verify(body: OtpVerifyBody):
            contact = normalize_contact(body.contact)
            with self._connect() as db:
                row = db.execute("SELECT code_hash, expires, tries FROM otp WHERE contact=?", (contact,)).fetchone()
                if row is None or row[1] < time.time():
                    raise HTTPException(400, "No valid code. Please request a new one.")
                if row[2] >= MAX_OTP_TRIES:
                    raise HTTPException(429, "Too many wrong attempts. Please request a new code.")
                good = hashlib.sha256(f"{contact}:{body.code.strip()}".encode()).hexdigest()
                if not hmac.compare_digest(good, row[0]):
                    db.execute("UPDATE otp SET tries=tries+1 WHERE contact=?", (contact,))
                    db.commit()
                    raise HTTPException(400, "Wrong code.")
                db.execute("DELETE FROM otp WHERE contact=?", (contact,))  # a code works once
                db.commit()
            return {"verification_token": self.sign({"kind": "contact", "c": contact}), "expires_in_minutes": TOKEN_MINUTES}

        @app.post("/submit", status_code=201)
        def submit(body: SubmitBody):
            """Needs BOTH tokens: the confirmed institution and the verified phone. Stores first, then sends to the hub."""
            inst = self.verify(body.institution_token, "inst")
            contact = self.verify(body.verification_token, "contact")["c"]
            if body.category not in CATEGORIES:
                raise HTTPException(422, "Unknown category.")
            payload = {
                "source_case_no": "", "verified_institution_id": inst["iid"],
                "resolution_method": inst["method"], "finder_answers": inst.get("answers"),
                "reporter": {"contact": contact, "reporter_type": body.reporter_type, "validation_method": "MOCK_OTP"},
                "category": body.category, "title": body.title.strip(), "description": body.description.strip(),
                "severity": body.severity}
            with self._connect() as db:
                cur = db.execute("INSERT INTO submissions (payload, institution_id, institution_name, sync_status,"
                                 " created_at) VALUES (?,?,?,?,?)",
                                 ("{}", inst["iid"], inst.get("iname"), "pending", datetime.now().isoformat(timespec="seconds")))
                row_id = cur.lastrowid
                number = f"{self.code}-2026-{FIRST_CASE_NUMBER - 1 + row_id:04d}"
                payload["source_case_no"] = number
                db.execute("UPDATE submissions SET portal_case_no=?, payload=? WHERE id=?", (number, json.dumps(payload), row_id))
                db.commit()
            self._send(row_id)  # first attempt now; if the hub is down the outbox keeps trying
            return self.receipt(number)

        @app.get("/submission/{portal_case_no}")
        def submission(portal_case_no: str):
            """The page polls this to show whether a waiting complaint has reached the hub."""
            return self.receipt(portal_case_no)

        @app.get("/")
        def index():
            return FileResponse(self.folder / "static" / "index.html")

        app.mount("/shared", StaticFiles(directory=self.shared_dir), name="shared")
        app.mount("/static", StaticFiles(directory=self.folder / "static"), name="static")
        return app
