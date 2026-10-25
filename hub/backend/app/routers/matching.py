"""Duplicate / overlap suggestions API (M6). Read only; officers confirm or reject in M7."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models as m
from ..db import get_db
from ..services import auth, decisions, matching, scope

router = APIRouter(prefix="/api/matching", tags=["matching"])


@router.get("/links")
def links(status: str | None = None, link_type: str | None = None, institution_id: str | None = None,
          case_id: str | None = None, db: Session = Depends(get_db), user=Depends(auth.current_user)):
    """Suggested links, newest first. Filters: status (SUGGESTED/CONFIRMED/REJECTED), link_type, institution_id, case_id."""
    return matching.list_links(db, status, link_type, institution_id, case_id, visible=scope.visible_case_ids(db, user))


@router.get("/links/{link_id}")
def link(link_id: int, db: Session = Depends(get_db), user=Depends(auth.current_user)):
    row = db.get(m.LinkSuggestion, link_id)
    if row is None:
        raise HTTPException(404, f"No link suggestion {link_id}")
    visible = scope.visible_case_ids(db, user)
    if visible is not None and row.case_a not in visible and row.case_b not in visible:
        raise HTTPException(403, "This link is outside your view")
    return matching.link_view(db, row)


class DecisionBody(BaseModel):
    note: str | None = Field(default=None, max_length=500)  # the officer's reason, kept in the audit trail


@router.post("/links/{link_id}/confirm")
def confirm(link_id: int, body: DecisionBody | None = None, db: Session = Depends(get_db),
            user=Depends(auth.current_user)):
    """An officer confirms the suggestion: the cases are now linked (and corroboration raises priority)."""
    return decisions.decide(db, user, link_id, "CONFIRMED", body.note if body else None)


@router.post("/links/{link_id}/reject")
def reject(link_id: int, body: DecisionBody | None = None, db: Session = Depends(get_db),
           user=Depends(auth.current_user)):
    """An officer rejects the suggestion. The pair is never suggested again."""
    return decisions.decide(db, user, link_id, "REJECTED", body.note if body else None)
