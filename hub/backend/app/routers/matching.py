"""Duplicate / overlap suggestions API (M6). Read only; officers confirm or reject in M7."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models as m
from ..db import get_db
from ..services import auth, matching

router = APIRouter(prefix="/api/matching", tags=["matching"])


@router.get("/links")
def links(status: str | None = None, link_type: str | None = None, institution_id: str | None = None,
          case_id: str | None = None, db: Session = Depends(get_db), _user=Depends(auth.current_user)):
    """Suggested links, newest first. Filters: status (SUGGESTED/CONFIRMED/REJECTED), link_type, institution_id, case_id."""
    return matching.list_links(db, status, link_type, institution_id, case_id)


@router.get("/links/{link_id}")
def link(link_id: int, db: Session = Depends(get_db), _user=Depends(auth.current_user)):
    row = db.get(m.LinkSuggestion, link_id)
    if row is None:
        raise HTTPException(404, f"No link suggestion {link_id}")
    return matching.link_view(db, row)
