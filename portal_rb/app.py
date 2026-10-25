"""RB mock portal (port 8001), Regulation Bureau. Not the real AICTE portal.
M0: health check + placeholder page. The Institution Finder, mock OTP, signed token and submit-to-hub come in M5.
Run from this folder:  python -m uvicorn app:app --port 8001
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="RB Portal (mock)")


@app.get("/health")
def health():
    return {"status": "ok", "service": "portal_rb"}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
