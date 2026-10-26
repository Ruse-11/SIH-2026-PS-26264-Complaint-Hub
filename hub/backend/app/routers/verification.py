"""Reporter identity verification with Aadhaar via DigiLocker (later, STUB).
Prototype: the portals use a mock OTP (shared/portal_core.py). Production: the portal would redirect the reporter to
DigiLocker (consent screen), receive a verified reference, and send the hub only a one-way hash, never the Aadhaar number."""
from ._stub import stub_router

router = stub_router("verification", "Aadhaar / DigiLocker reporter verification", "later", True)
