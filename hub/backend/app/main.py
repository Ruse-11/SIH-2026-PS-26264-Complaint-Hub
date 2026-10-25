"""Hub entry point.  Run from hub/backend:  python -m uvicorn app.main:app --port 8000"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .routers import ALL

app = FastAPI(title="Complaint Hub", version=config.VERSION)

app.add_middleware(
    CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"]
)


@app.get("/api/health")
def health():
    """Used by the dashboard header, run_all.py and the quick test."""
    return {"status": "ok", "service": "hub", "version": config.VERSION}


for module in ALL:  # every feature has a router; unbuilt ones answer 501 "planned"
    app.include_router(module.router)
