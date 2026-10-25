"""Hub entry point.  Run from hub/backend:  python -m uvicorn app.main:app --port 8000"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config, models  # noqa: F401  (models must be imported so the tables are registered)
from .db import Base, engine
from .routers import ALL
from .routers.cases import actions_router

@asynccontextmanager
async def lifespan(_app):
    """On start-up make sure the tables exist (data is loaded separately by `python -m app.seed`)."""
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Complaint Hub", version=config.VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"]
)


@app.get("/api/health")
def health():
    """Used by the dashboard header, run_all.py and the quick test."""
    return {"status": "ok", "service": "hub", "version": config.VERSION}


app.include_router(actions_router)  # POST /api/actions placeholder
for module in ALL:  # every feature has a router; unbuilt ones answer 501 "planned"
    app.include_router(module.router)
