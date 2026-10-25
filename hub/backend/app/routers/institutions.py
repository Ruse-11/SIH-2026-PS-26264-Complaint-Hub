"""Institution registry API (M2): live search/resolver, guided filters, institution profile."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import institutions as service

router = APIRouter(prefix="/api/institutions", tags=["institutions"])


@router.get("/search")
def search(q: str = Query("", max_length=200), db: Session = Depends(get_db)):
    """What does this typed name mean? Returns outcome RESOLVED / AMBIGUOUS / NOT_LISTED and up to 3 cards."""
    return service.resolve(db, q)


@router.get("/filters")
def filters(state: str | None = None, district: str | None = None, type: str | None = None,
            area: str | None = None, program: str | None = None, db: Session = Depends(get_db)):
    """Guided questions: the choices still possible after the answers so far, plus matching colleges."""
    return service.guided_filters(db, state, district, type, area, program)


@router.get("/{aicte_id}")
def get_institution(aicte_id: str, db: Session = Depends(get_db)):
    """One institution: details, parent, constituent colleges and case counts."""
    data = service.profile(db, aicte_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"No institution with ID {aicte_id}")
    return data
