"""Stalled-case and SLA alerts API (M10)."""
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import auth, starvation as service

router = APIRouter(prefix="/api/starvation", tags=["starvation"])


@router.get("")
def overview(as_of: date | None = None, limit: int = 20, db: Session = Depends(get_db), user=Depends(auth.current_user)):
    """Stalled, overdue, due-soon, pending, escalation-suggested and escalated cases the user may see, worst first.
    Computed live; as_of (YYYY-MM-DD) lets you see the picture on another date."""
    return service.overview(db, user, as_of, min(max(limit, 1), 200))


@router.post("/scan")
def scan(as_of: date | None = None, db: Session = Depends(get_db),
         _user=Depends(auth.require_roles("rb_officer", "pgrc_officer", "senior_management", "competent_authority"))):
    """Create, refresh and clear the time-based alerts now (the hub also does this on start and every 30 minutes).
    Safe to repeat. as_of is for demos and tests."""
    result = service.scan(db, as_of)
    db.commit()
    return result
