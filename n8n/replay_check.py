"""Plays the n8n "Complaint Journey Replay" in plain Python, so you can check every call before wiring it in n8n.
Run with the whole system running (python run_all.py) and the demo reset (python reset_demo.py):

    python n8n/replay_check.py

Two reporters file about the clean demo college SYN-0040: first on the RB portal, then on the PGRC portal.
The second submission must come back with alerts_created (the overlap alert). Exit code 0 = the replay works.
"""
import json
import sys

import httpx

HUB, RB, PGRC = "http://localhost:8000", "http://localhost:8001", "http://localhost:8002"
COLLEGE_QUERY = "Norvella Institute of Applied Sciences"  # SYN-0040, the clean college (no cases after reset_demo.py). "Norvella" alone is ambiguous.


def journey(portal, phone, category, title, text, reporter_type="student"):
    """The same calls the n8n workflow makes, in order."""
    c = httpx.Client(timeout=20)
    found = c.get(f"{HUB}/api/institutions/search", params={"q": COLLEGE_QUERY}).json()  # 1 finder search
    card = (found["candidates"] or found.get("suggestions") or [None])[0]
    assert card, "finder returned nothing: is the hub seeded?"
    assert card["aicte_id"] == "SYN-0040", f"the finder picked {card['aicte_id']}, not the clean demo college SYN-0040"
    details = c.get(f"{HUB}/api/institutions/{card['aicte_id']}").json()  # 2 institution details (map link uses lat/lng)
    osm = f"https://www.openstreetmap.org/?mlat={details['lat']}&mlon={details['lng']}#map=16/{details['lat']}/{details['lng']}"
    conf = c.post(f"{portal}/institution/confirm", json={"institution_id": card["aicte_id"], "resolution_method": "REPORTER_CONFIRMED"}).json()  # 3 confirm
    otp = c.post(f"{portal}/otp/request", json={"contact": phone}).json()  # 4 mock OTP (demo mode returns the code)
    ver = c.post(f"{portal}/otp/verify", json={"contact": phone, "code": otp["demo_otp"]}).json()  # 5 verify
    sub = c.post(f"{portal}/submit", json={"institution_token": conf["institution_token"], "verification_token": ver["verification_token"],
                                           "reporter_type": reporter_type, "category": category, "title": title, "description": text, "severity": 3})  # 6 submit
    sub.raise_for_status()
    return details, osm, sub.json()


def main():
    try:
        d, osm, first = journey(RB, "9000000101", "Infrastructure/Lab", "Laboratory equipment not working",
                                "The laboratory equipment has been out of order for months and students cannot do practicals.")
        print(f"1. RB portal   : {first['portal_case_no']} -> {first['hub_case_id']} at {d['official_name']} ({d['aicte_id']}); alerts: {len(first['alerts_created'])}")
        print(f"   map link    : {osm}")
        d, osm, second = journey(PGRC, "9000000102", "Fee/Refund", "Refund not returned",
                                 "My refundable deposit has not been returned after I withdrew from the programme.")
        print(f"2. PGRC portal : {second['portal_case_no']} -> {second['hub_case_id']}; alerts: {len(second['alerts_created'])}")
    except (httpx.HTTPError, AssertionError, KeyError) as e:
        print(f"FAILED: {type(e).__name__}: {e}\nIs everything running (python run_all.py) and did you run python reset_demo.py?")
        return 1
    alerts = second["alerts_created"]
    if not alerts:
        print("No alert came back. Did you run python reset_demo.py first? (a previous replay leaves cases at the college)")
        return 1
    a = alerts[0]
    print(f"3. ALERT       : {a['alert_type']} | {a['message']}")
    print(f"   lead bureau : {(a.get('suggested_lead') or {}).get('bureau')} (suggestion only)  |  dashboard: {a.get('dashboard_link')}")
    print("   alerts_created[0] =", json.dumps(a)[:300])
    print("\nReplay OK. In n8n: IF alerts_created is not empty -> Telegram message.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
