"""PGRC mock portal (port 8002), Public Grievance Redressal Cell. Not the real AICTE portal.
M0: health check + placeholder page. The Institution Finder, mock OTP, signed token and submit-to-hub come in M5.
Run from this folder:  python -m uvicorn app:app --port 8002
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="PGRC Portal (mock)")


@app.get("/health")
def health():
    return {"status": "ok", "service": "portal_pgrc"}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
