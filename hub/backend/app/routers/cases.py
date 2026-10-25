"""Cases, actions and case history API. M4: one case with its history. List/search/filters are added in M8."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import auth, cases as service
from ._stub import stub_router

router = APIRouter(prefix="/api/cases", tags=["cases"])

# POST /api/actions is where bureau systems would push actions in production. Stub only (CLAUDE.md section 5).
actions_router = stub_router("actions", "Bureau action sync", "later", future=True)


@router.get("/{hub_case_id}")
def get_case(hub_case_id: str, db: Session = Depends(get_db), _user=Depends(auth.current_user)):
    """One case with its full chronological action history. Needs a logged-in user."""
    data = service.case_detail(db, hub_case_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"No case {hub_case_id}")
    return data
