"""Hub entry point.  Run from hub/backend:  python -m uvicorn app.main:app --port 8000"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config, models  # noqa: F401  (models must be imported so the tables are registered)
from .services import embeddings
from .db import Base, engine
from .routers import ALL
from .routers.cases import actions_router

log = logging.getLogger("hub")
SCAN_EVERY_SECONDS = 30 * 60


def _scan_once():
    """Refresh the time-based alerts (stalled, due soon, overdue). Never lets an error stop the hub."""
    from .db import SessionLocal
    from .services import starvation
    try:
        with SessionLocal() as db:
            result = starvation.scan(db)
            db.commit()
            log.info("alert scan: %s", result)
    except Exception:  # noqa: BLE001 - a failed scan must not crash the app; the next round retries
        log.exception("alert scan failed")


async def _scan_loop():
    while True:
        await asyncio.to_thread(_scan_once)
        await asyncio.sleep(SCAN_EVERY_SECONDS)


@asynccontextmanager
async def lifespan(_app):
    """On start-up make sure the tables exist (data is loaded separately by `python -m app.seed`),
    then keep the stalled / SLA alerts fresh in the background."""
    Base.metadata.create_all(engine)
    task = asyncio.create_task(_scan_loop())
    yield
    task.cancel()


app = FastAPI(title="Complaint Hub", version=config.VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"]
)


@app.get("/api/health")
def health():
    """Used by the dashboard header, run_all.py and the quick test."""
    return {"status": "ok", "service": "hub", "version": config.VERSION, **embeddings.status()}


app.include_router(actions_router)  # POST /api/actions placeholder
for module in ALL:  # every feature has a router; unbuilt ones answer 501 "planned"
    app.include_router(module.router)
