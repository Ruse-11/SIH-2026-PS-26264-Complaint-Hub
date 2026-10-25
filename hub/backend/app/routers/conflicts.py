"""Conflicts, duplicate actions and the lead-bureau decision API (M9)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import auth, conflicts as service, matching, scope

router = APIRouter(prefix="/api/conflicts", tags=["conflicts"])


@router.get("")
def list_conflicts(status: str | None = None, db: Session = Depends(get_db), user=Depends(auth.current_user)):
    """Suggested conflicts and duplicate actions the user may see (newest first). status: SUGGESTED / CONFIRMED / REJECTED."""
    visible = scope.visible_case_ids(db, user)
    rows = matching.list_links(db, status=status, link_type="CONFLICT", visible=visible)
    rows += matching.list_links(db, status=status, link_type="DUPLICATE_ACTION", visible=visible)
    return sorted(rows, key=lambda r: -r["id"])


class LeadBody(BaseModel):
    bureau: str = Field(max_length=20)
    note: str | None = Field(default=None, max_length=500)


@router.post("/{link_id}/lead")
def decide_lead(link_id: int, body: LeadBody, db: Session = Depends(get_db), user=Depends(auth.current_user)):
    """Competent authority only: record the final lead bureau (the system's suggestion stays visible beside it)."""
    return service.decide_lead(db, user, link_id, body.bureau, body.note)
