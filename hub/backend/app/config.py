"""Central settings for the hub. Everything tunable lives here (or in config tables from M1)."""
import os
from pathlib import Path

VERSION = "0.5.0-m5"

# sih-hub/ (this file is sih-hub/hub/backend/app/config.py)
ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"
DB_PATH = ROOT / "hub" / "backend" / "hub.db"
DATABASE_URL = os.getenv("HUB_DATABASE_URL", f"sqlite:///{DB_PATH.as_posix()}")

# Dev-only secrets. Real deployments would read these from the environment.
JWT_SECRET = os.getenv("HUB_JWT_SECRET", "dev-only-change-me-dev-only-change-me")
FINGERPRINT_SECRET = os.getenv("HUB_FINGERPRINT_SECRET", "dev-only-fingerprint-key")  # key for hashing reporter contacts
PORTAL_API_KEYS = {"RB": "dev-rb-key", "PGRC": "dev-pgrc-key"}  # one key per portal (used from M4)

# Browser pages (dashboard :5173, portals :8001/:8002) call the hub directly, so allow them.
CORS_ORIGINS = [
    "http://localhost:5173", "http://127.0.0.1:5173",
    "http://localhost:8001", "http://127.0.0.1:8001",
    "http://localhost:8002", "http://127.0.0.1:8002",
]
