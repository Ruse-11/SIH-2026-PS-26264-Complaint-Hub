"""Priority breakdown and corroboration boost API (M7)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models as m
from ..db import get_db
from ..services import auth, priority

router = APIRouter(prefix="/api/corroboration", tags=["corroboration"])


@router.get("/{hub_case_id}")
def case_priority(hub_case_id: str, db: Session = Depends(get_db), _user=Depends(auth.current_user)):
    """Why a case has its priority: severity, confirmed corroborators, age, and the 'potential +X' still waiting."""
    case = db.get(m.Case, hub_case_id)
    if case is None:
        raise HTTPException(404, f"No case {hub_case_id}")
    return {"hub_case_id": hub_case_id, "cluster_id": case.cluster_id, **priority.breakdown(db, case)}
