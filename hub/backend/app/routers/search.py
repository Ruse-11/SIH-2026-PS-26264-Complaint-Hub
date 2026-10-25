"""Global search API (M8): one box, finds institutions and cases."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..db import get_db
from ..services import auth, cases as service

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
def search(q: str = Query(..., min_length=2, max_length=100), db: Session = Depends(get_db), user=Depends(auth.current_user)):
    """Top 5 institutions (by name, alias or AICTE ID) and top 10 cases (by case ID or institution) for the typed text."""
    ids = service._institution_ids_for_name(db, q) | set(db.scalars(
        select(m.Institution.aicte_id).where(m.Institution.aicte_id.ilike(f"%{q.strip()}%"))))
    insts = db.scalars(select(m.Institution).where(m.Institution.aicte_id.in_(ids)).order_by(m.Institution.aicte_id).limit(5)).all()
    cases = service.list_cases(db, user, q=q, page_size=10)
    return {"institutions": [{"aicte_id": i.aicte_id, "official_name": i.official_name, "district": i.district, "state": i.state} for i in insts],
            "cases": cases["items"], "total_cases": cases["total"]}
