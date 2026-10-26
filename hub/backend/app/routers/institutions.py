"""Institution registry API (M2): live search/resolver, guided filters, institution profile."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import auth, institutions as service

router = APIRouter(prefix="/api/institutions", tags=["institutions"])


@router.get("/search")
def search(q: str = Query("", max_length=200), db: Session = Depends(get_db)):
    """What does this typed name mean? Returns outcome RESOLVED / AMBIGUOUS / NOT_LISTED and up to 3 cards."""
    answer = service.resolve(db, q)
    if answer["outcome"] != "RESOLVED":
        # Same engine as the dashboard. Never empty when a good guess exists: the portal shows these as
        # "closest matches" for the reporter to pick (the reporter still confirms; nothing is auto-picked).
        answer["suggestions"] = service.reporter_suggestions(db, q, 6)
    return answer


@router.get("/suggest")
def suggest(q: str = Query("", max_length=100), limit: int = Query(8, ge=1, le=20), db: Session = Depends(get_db),
            _user=Depends(auth.current_user)):
    """Search-box suggestions for officers: partial words, typos, place names and universities all match. Needs login."""
    return service.suggest(db, q, limit)


@router.get("/filters")
def filters(state: str | None = None, district: str | None = None, type: str | None = None,
            area: str | None = None, program: str | None = None, db: Session = Depends(get_db)):
    """Guided questions: the choices still possible after the answers so far, plus matching colleges."""
    return service.guided_filters(db, state, district, type, area, program)


@router.get("/{aicte_id}/history")
def history(aicte_id: str, db: Session = Depends(get_db), user=Depends(auth.current_user)):
    """Institution profile for officers: details, complaint history (oldest first), overlap suggestions and alerts,
    limited to what the logged-in role may see."""
    data = service.history(db, user, aicte_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"No institution with ID {aicte_id}")
    return data


@router.get("/{aicte_id}")
def get_institution(aicte_id: str, db: Session = Depends(get_db)):
    """One institution: details, parent, constituent colleges and case counts."""
    data = service.profile(db, aicte_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"No institution with ID {aicte_id}")
    return data
