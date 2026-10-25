"""Cases, actions and case history API (M4 detail, M8 list/search/filters/needs-review)."""
from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import actions as action_service, auth, cases as service
from ._stub import stub_router

router = APIRouter(prefix="/api/cases", tags=["cases"])

# POST /api/actions is where bureau systems would push actions in production. Stub only (CLAUDE.md section 5).
actions_router = stub_router("actions", "Bureau action sync", "later", future=True)


@router.get("")
def list_cases(q: str | None = Query(None, max_length=100), bureau: str | None = None, region: str | None = None,
               category: str | None = None, status: str | None = None, institution_id: str | None = None,
               date_from: date | None = None, date_to: date | None = None, overdue: bool = False,
               sort: str = "priority", page: int = 1, page_size: int = 25, as_of: date | None = None,
               db: Session = Depends(get_db), user=Depends(auth.current_user)):
    """Cases the user may see. q searches institution name, AICTE ID and case ID; the rest are filters."""
    return service.list_cases(db, user, q, bureau, region, category, status, institution_id, date_from, date_to,
                              overdue, sort, page, page_size, as_of)


# These fixed paths must stay above /{hub_case_id}, or "filters" would be read as a case ID.
@router.get("/filters")
def filters(db: Session = Depends(get_db), user=Depends(auth.current_user)):
    """Choices for the filter dropdowns."""
    return service.filter_options(db, user)


@router.get("/needs-review")
def needs_review(db: Session = Depends(get_db), user=Depends(auth.current_user)):
    """Complaints whose college could not be identified; an officer picks the right one."""
    return service.needs_review(db, user)


class AssignBody(BaseModel):
    institution_id: str = Field(max_length=40)


@router.post("/{hub_case_id}/assign-institution")
def assign_institution(hub_case_id: str, body: AssignBody, db: Session = Depends(get_db), user=Depends(auth.current_user)):
    return service.assign_institution(db, user, hub_case_id, body.institution_id)


class ActionBody(BaseModel):
    action_type: str = Field(max_length=80)
    remarks: str | None = Field(default=None, max_length=500)
    doc_ref: str | None = Field(default=None, max_length=200)
    to_bureau: str | None = Field(default=None, max_length=20)  # only for a transfer


@router.get("/action-types")
def action_types(db: Session = Depends(get_db), user=Depends(auth.current_user)):
    """The action types the logged-in role may log, with each one's stance (enforcing / requesting / closing / neutral)."""
    return action_service.allowed_action_types(db, user)


@router.post("/{hub_case_id}/actions", status_code=201)
def log_action(hub_case_id: str, body: ActionBody, db: Session = Depends(get_db), user=Depends(auth.current_user)):
    """An officer logs an action. Conflicts and duplicate actions with the other bureau are checked straight away."""
    return action_service.log_action(db, user, hub_case_id, body.action_type, body.remarks, body.doc_ref, body.to_bureau)


@router.get("/{hub_case_id}")
def get_case(hub_case_id: str, db: Session = Depends(get_db), user=Depends(auth.current_user)):
    """One case with its full chronological action history, links and priority. Only cases in the user's scope."""
    service.get_visible_case(db, user, hub_case_id)
    return service.case_detail(db, hub_case_id)
