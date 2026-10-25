"""Login and roles (M3): password hashing, JWT tokens, role rules, and the FastAPI guards other routers use."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from .. import models as m
from ..db import get_db

PBKDF2_ROUNDS = 120_000  # PBKDF2 is in Python's standard library, so no bcrypt install problems on Windows
TOKEN_HOURS = 8
DEMO_PASSWORD = "demo123"  # all seeded demo accounts share it (synthetic prototype only)

# What each role may do (CLAUDE.md section 12). view_scope: which cases the role sees.
ROLE_RULES = {
    "rb_officer": {"label": "RB officer", "view_scope": "bureau", "can_log_actions": True,
                   "can_decide_links": True, "can_transfer": True, "can_escalate": True, "can_export": True},
    "pgrc_officer": {"label": "PGRC officer", "view_scope": "bureau", "can_log_actions": True,
                     "can_decide_links": True, "can_transfer": True, "can_escalate": True, "can_export": True},
    "other_bureau": {"label": "Other bureau officer", "view_scope": "assigned", "can_log_actions": True,
                     "can_decide_links": False, "can_transfer": False, "can_escalate": False, "can_export": False},
    "regional_office": {"label": "Regional office", "view_scope": "region", "can_log_actions": False,
                        "can_decide_links": False, "can_transfer": False, "can_escalate": True, "can_export": True},
    "senior_management": {"label": "Senior management", "view_scope": "all", "can_log_actions": False,
                          "can_decide_links": False, "can_transfer": False, "can_escalate": False, "can_export": True},
    "competent_authority": {"label": "Competent authority", "view_scope": "all", "can_log_actions": False,
                            "can_decide_links": True, "can_transfer": False, "can_escalate": True, "can_export": True,
                            "can_decide_lead": True},
}


def permissions(role: str) -> dict:
    """Role rules with every flag present (missing ones are False)."""
    rules = dict(ROLE_RULES[role])
    rules.setdefault("can_decide_lead", False)
    return rules


# ---- passwords ----
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ROUNDS).hex()
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, rounds, salt, digest = stored.split("$")
        check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(rounds)).hex()
    except ValueError:
        return False
    return hmac.compare_digest(check, digest)  # constant-time compare


# ---- tokens ----
def create_token(user: m.User) -> str:
    claims = {"sub": user.username, "role": user.role,
              "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS)}
    return jwt.encode(claims, config.JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> dict:
    """Raises jwt.PyJWTError if the token is forged or expired."""
    return jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])


def user_public(user: m.User) -> dict:
    """What the browser may know about the user (never the password hash)."""
    return {"username": user.username, "display_name": user.display_name, "role": user.role,
            "role_label": ROLE_RULES[user.role]["label"], "bureau": user.bureau, "region": user.region,
            "permissions": permissions(user.role)}


def login(db: Session, username: str, password: str):
    """Returns (token, user) or None. The same answer for 'no such user' and 'wrong password'."""
    user = db.scalars(select(m.User).where(m.User.username == username.strip().lower())).first()
    if not user or not verify_password(password, user.password_hash):
        return None
    return create_token(user), user


# ---- guards for other routers:  user = Depends(current_user)  or  Depends(require_roles("rb_officer", ...)) ----
bearer = HTTPBearer(auto_error=False)


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer),
                 db: Session = Depends(get_db)) -> m.User:
    if creds is None:
        raise HTTPException(status_code=401, detail="Not logged in")
    try:
        username = decode_token(creds.credentials)["sub"]
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Session expired or invalid. Please log in again.")
    user = db.scalars(select(m.User).where(m.User.username == username)).first()
    if user is None:
        raise HTTPException(status_code=401, detail="Unknown user")
    return user


def require_roles(*roles: str):
    """Guard that only lets the listed roles through (403 for everyone else)."""
    def guard(user: m.User = Depends(current_user)) -> m.User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail=f"{ROLE_RULES[user.role]['label']} cannot do this")
        return user
    return guard
