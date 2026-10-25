"""Complaint intake from the portals API (M4): POST /api/intake."""
from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import intake as service

router = APIRouter(prefix="/api/intake", tags=["intake"])


class ReporterIn(BaseModel):
    contact: str = Field(min_length=5, max_length=100)  # the phone/email the portal verified; only a hash is stored
    reporter_type: Literal["student", "parent", "alumni", "faculty", "other"] = "other"
    validation_method: str = "MOCK_OTP"


class ComplaintIn(BaseModel):
    source_case_no: str = Field(min_length=3, max_length=40)  # the portal's own case number
    verified_institution_id: str | None = None  # None = reporter could not find the college
    resolution_method: Literal["REPORTER_CONFIRMED", "GUIDED", "UNLISTED"] = "REPORTER_CONFIRMED"
    finder_answers: dict | None = None  # guided answers, or the free text typed for an unlisted college
    reporter: ReporterIn
    category: str
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=10, max_length=4000)
    severity: int = Field(default=3, ge=1, le=5)


@router.post("", status_code=201)
def intake(body: ComplaintIn, response: Response, portal: str = Depends(service.portal_from_api_key),
           db: Session = Depends(get_db)):
    """A portal hands over a complaint. 201 = new case; 200 = this case number was already received (safe retry)."""
    receipt, created = service.receive_complaint(db, portal, body)
    if not created:
        response.status_code = 200
    return receipt
