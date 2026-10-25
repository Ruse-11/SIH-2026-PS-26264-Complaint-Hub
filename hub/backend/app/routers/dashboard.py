"""Dashboard KPIs API (M8)."""
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import auth, dashboard as service

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/kpis")
def kpis(as_of: date | None = None, db: Session = Depends(get_db), user=Depends(auth.current_user)):
    """Totals by status, pending beyond timeline, bureau workload, institution-wise status, waiting suggestions.
    Limited to what the logged-in role may see. as_of (YYYY-MM-DD) is only for demos and tests."""
    return service.kpis(db, user, as_of)
