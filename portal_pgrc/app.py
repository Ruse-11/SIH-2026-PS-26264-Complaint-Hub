"""PGRC mock portal (Public Grievance Redressal Cell), port 8002. Not the real AICTE portal.
All logic is in shared/portal_core.py (the two portals are identical apart from name and API key).
Run from this folder:  python -m uvicorn app:app --port 8002
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))

from portal_core import Portal  # noqa: E402

portal = Portal(code="PGRC", name="Public Grievance Redressal Cell", folder=Path(__file__).resolve().parent,
                shared_dir=ROOT / "shared", default_api_key="dev-pgrc-key")
app = portal.build_app()
