"""Reports, CSV export and Insights API (M11)."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import auth, insights as insight_service, reports as service
from ..services.audit import log_event

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("")
def catalogue(_user=Depends(auth.current_user)):
    """The reports that exist."""
    return service.CATALOGUE


# fixed path: must stay above /{key}
@router.get("/insights")
def insights(as_of: date | None = None, db: Session = Depends(get_db), user=Depends(auth.current_user)):
    """Data-driven insights for the logged-in role, each with the rule that produced it."""
    return insight_service.build(db, user, as_of)


@router.get("/{key}")
def report(key: str, format: str = "json", as_of: date | None = None, institution_id: str | None = None,
           db: Session = Depends(get_db), user=Depends(auth.current_user)):
    """One report as JSON, or as CSV with format=csv (roles that may export). Always limited to the user's scope."""
    data = service.build(db, user, key, as_of, institution_id)
    if data is None:
        raise HTTPException(404, f"No report called '{key}'")
    if format == "json":
        return data
    if format != "csv":
        raise HTTPException(422, "format must be json or csv")
    if not auth.permissions(user.role)["can_export"]:
        raise HTTPException(403, f"{auth.permissions(user.role)['label']} cannot export reports")
    log_event(db, actor=user.username, role=user.role, action="REPORT_EXPORTED", entity_type="report", entity_id=key,
              detail={"rows": len(data["rows"]), "as_of": data["as_of"], "institution_id": institution_id})
    db.commit()
    name = f"{key}_{data['as_of']}.csv"
    return Response("﻿" + service.to_csv(data), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})  # BOM so Excel reads UTF-8
