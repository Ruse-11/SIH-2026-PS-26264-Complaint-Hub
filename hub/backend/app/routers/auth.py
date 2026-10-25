"""Login and roles API (M3)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..db import get_db
from ..services import auth as service

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginBody, db: Session = Depends(get_db)):
    """Check username + password, return a signed token (valid 8 hours) and the user's role and permissions."""
    result = service.login(db, body.username, body.password)
    if result is None:
        raise HTTPException(status_code=401, detail="Wrong username or password")
    token, user = result
    return {"token": token, "user": service.user_public(user)}


@router.get("/me")
def me(user: m.User = Depends(service.current_user)):
    """Who am I? Used by the dashboard to check that a saved token still works."""
    return service.user_public(user)


@router.get("/demo-accounts")
def demo_accounts(db: Session = Depends(get_db)):
    """Prototype only: lists the seeded accounts so the login page can offer one-click buttons."""
    users = db.scalars(select(m.User).order_by(m.User.id)).all()
    return {"password": service.DEMO_PASSWORD,
            "accounts": [{"username": u.username, "display_name": u.display_name, "role": u.role,
                          "role_label": service.ROLE_RULES[u.role]["label"], "bureau": u.bureau, "region": u.region}
                         for u in users]}
