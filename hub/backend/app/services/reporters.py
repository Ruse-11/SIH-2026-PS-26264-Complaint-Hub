"""Reporter identity. The hub never stores a phone or email, only this keyed hash."""
import hashlib
import hmac
import re

from .. import config


def make_fingerprint(contact: str) -> str:
    """Same person -> same fingerprint on both portals. Phones are reduced to digits so '+91 98..' == '9898..'."""
    c = contact.strip().lower()
    if re.fullmatch(r"[+\d\s\-()]+", c):
        c = re.sub(r"\D", "", c)
    return hmac.new(config.FINGERPRINT_SECRET.encode(), c.encode(), hashlib.sha256).hexdigest()
