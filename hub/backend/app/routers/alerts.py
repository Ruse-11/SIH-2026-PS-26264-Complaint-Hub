"""Alerts API (M6)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import alerts as service, auth, decisions

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("")
def alerts(type: str | None = None, institution_id: str | None = None, open_only: bool = False,
           db: Session = Depends(get_db), _user=Depends(auth.current_user)):
    """Alerts, newest first. type: OVERLAP / DUPLICATE / CORROBORATION. open_only hides acknowledged ones."""
    return service.list_alerts(db, type, institution_id, open_only)


@router.post("/{alert_id}/acknowledge")
def acknowledge(alert_id: int, db: Session = Depends(get_db), user=Depends(auth.current_user)):
    """Mark an alert as seen. Confirming or rejecting its link does this automatically."""
    return decisions.acknowledge_alert(db, user, alert_id)
