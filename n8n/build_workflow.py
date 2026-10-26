"""Writes the two importable n8n workflows from one definition:
    n8n/complaint_journey_replay.json          live: calls the real hub and portals
    n8n/complaint_journey_replay_pinned.json   fallback: same nodes with recorded answers pinned (hub not contacted)
Run with the whole system up and freshly reset (the pinned answers are recorded from a real run):
    python reset_demo.py   then   python run_all.py   then   python n8n/build_workflow.py
You only need this to regenerate the files; to use the workflow just import a JSON file in n8n.
"""
import json
import sys
import uuid
from pathlib import Path

import httpx

OUT = Path(__file__).resolve().parent
HUB, RB, PGRC = "http://localhost:8000", "http://localhost:8001", "http://localhost:8002"
S = "$('Settings').first().json"  # n8n expression prefix for the settings node

N = {  # node names (the number shows the step order on the canvas)
    "trigger": "Start replay", "settings": "Settings", "search": "1 Finder search", "details": "2 Institution details",
    "card": "3 Confirm card + map link", "rb_conf": "4 RB: confirm institution", "rb_otp": "5 RB: request OTP",
    "rb_ver": "6 RB: verify OTP", "rb_sub": "7 RB: submit complaint", "pg_conf": "8 PGRC: confirm institution",
    "pg_otp": "9 PGRC: request OTP", "pg_ver": "10 PGRC: verify OTP", "pg_sub": "11 PGRC: submit complaint",
    "if": "12 Overlap alert raised?", "msg": "13 Build alert message", "tg": "14 Telegram: notify officer", "none": "No overlap, nothing to send",
}
RB_PHONE, PG_PHONE = "9000000201", "9000000202"  # different from n8n/replay_check.py so the two never collide


def uid():
    return str(uuid.uuid4())


def assignments(pairs):
    return {"assignments": {"assignments": [{"id": uid(), "name": k, "value": v, "type": "string"}
                                             for k, v in pairs]}, "options": {}}


def http(name, pos, method, url, body=None, query=None):
    p = {"method": method, "url": url, "options": {}}
    if query:
        p.update({"sendQuery": True, "queryParameters": {"parameters": [{"name": k, "value": v} for k, v in query.items()]}})
    if body:
        p.update({"sendBody": True, "specifyBody": "json", "jsonBody": body})
    return {"id": uid(), "name": name, "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": pos, "parameters": p}


def j(expr):  # a JSON body written as a JavaScript object, sent with JSON.stringify
    return "={{ JSON.stringify(" + expr + ") }}"


def nodes(pinned: bool):
    col = lambda i: [260 + 240 * i, 300]  # noqa: E731
    row2 = lambda i: [260 + 240 * i, 560]  # noqa: E731
    title = "Illustrative replay (pinned data, the hub is not contacted)" if pinned else "Demo replay: production portals call the hub directly"
    out = [
        {"id": uid(), "name": N["trigger"], "type": "n8n-nodes-base.manualTrigger", "typeVersion": 1, "position": [20, 300], "parameters": {}},
        {"id": uid(), "name": N["settings"], "type": "n8n-nodes-base.set", "typeVersion": 3.4, "position": [240, 300], "parameters": assignments([
            ("hub_url", HUB), ("rb_url", RB), ("pgrc_url", PGRC), ("dashboard_url", "http://localhost:5173"),
            ("college_query", "Norvella Institute of Applied Sciences"), ("telegram_chat_id", "REPLACE_WITH_YOUR_CHAT_ID")])},
        http(N["search"], col(1), "GET", f"={{{{ {S}.hub_url }}}}/api/institutions/search", query={"q": f"={{{{ {S}.college_query }}}}"}),
        http(N["details"], col(2), "GET", f"={{{{ {S}.hub_url }}}}/api/institutions/{{{{ $json.candidates[0].aicte_id }}}}"),
        {"id": uid(), "name": N["card"], "type": "n8n-nodes-base.set", "typeVersion": 3.4, "position": col(3), "parameters": assignments([
            ("college_id", "={{ $json.aicte_id }}"), ("college_name", "={{ $json.official_name }}"),
            ("address", "={{ [$json.address_line, $json.area, $json.district, $json.state].filter(Boolean).join(', ') }}"),
            ("map_link", "=https://www.openstreetmap.org/?mlat={{ $json.lat }}&mlon={{ $json.lng }}#map=16/{{ $json.lat }}/{{ $json.lng }}")])},
        http(N["rb_conf"], col(4), "POST", f"={{{{ {S}.rb_url }}}}/institution/confirm",
             j('{ institution_id: $json.college_id, resolution_method: "REPORTER_CONFIRMED" }')),
        http(N["rb_otp"], col(5), "POST", f"={{{{ {S}.rb_url }}}}/otp/request", j(f'{{ contact: "{RB_PHONE}" }}')),
        http(N["rb_ver"], col(6), "POST", f"={{{{ {S}.rb_url }}}}/otp/verify", j(f'{{ contact: "{RB_PHONE}", code: $json.demo_otp }}')),
        http(N["rb_sub"], col(7), "POST", f"={{{{ {S}.rb_url }}}}/submit", j(
            '{ institution_token: $("' + N["rb_conf"] + '").first().json.institution_token, verification_token: $json.verification_token, reporter_type: "student", '
            'category: "Infrastructure/Lab", title: "Laboratory equipment not working", severity: 3, '
            'description: "The laboratory equipment has been out of order for months and students cannot do practicals." }')),
        http(N["pg_conf"], row2(0), "POST", f"={{{{ {S}.pgrc_url }}}}/institution/confirm",
             j('{ institution_id: $("' + N["card"] + '").first().json.college_id, resolution_method: "REPORTER_CONFIRMED" }')),
        http(N["pg_otp"], row2(1), "POST", f"={{{{ {S}.pgrc_url }}}}/otp/request", j(f'{{ contact: "{PG_PHONE}" }}')),
        http(N["pg_ver"], row2(2), "POST", f"={{{{ {S}.pgrc_url }}}}/otp/verify", j(f'{{ contact: "{PG_PHONE}", code: $json.demo_otp }}')),
        http(N["pg_sub"], row2(3), "POST", f"={{{{ {S}.pgrc_url }}}}/submit", j(
            '{ institution_token: $("' + N["pg_conf"] + '").first().json.institution_token, verification_token: $json.verification_token, reporter_type: "student", '
            'category: "Fee/Refund", title: "Refund not returned", severity: 3, '
            'description: "My refundable deposit has not been returned after I withdrew from the programme." }')),
        {"id": uid(), "name": N["if"], "type": "n8n-nodes-base.if", "typeVersion": 2, "position": row2(4), "parameters": {
            "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                           "conditions": [{"id": uid(), "leftValue": "={{ $json.alerts_created.length }}", "rightValue": 0,
                                           "operator": {"type": "number", "operation": "gt"}}], "combinator": "and"}, "options": {}}},
        {"id": uid(), "name": N["msg"], "type": "n8n-nodes-base.set", "typeVersion": 3.4, "position": [260 + 240 * 5, 480], "parameters": assignments([
            ("text", "={{ '🚨 ' + $json.alerts_created[0].message + '\\n\\nCollege: ' + $json.alerts_created[0].institution + '\\nCases: ' + "
                     "$json.alerts_created[0].cases.join(', ') + '\\nSuggested lead bureau (suggestion only): ' + "
                     "($json.alerts_created[0].suggested_lead.bureau || 'none') + '\\nOpen on the dashboard: ' + " + S + ".dashboard_url + "
                     "$json.alerts_created[0].dashboard_link + '\\n\\n" + title + ". Officers decide.' }}")])},
        {"id": uid(), "name": N["tg"], "type": "n8n-nodes-base.telegram", "typeVersion": 1.2, "position": [260 + 240 * 6, 480], "parameters": {
            "chatId": f"={{{{ {S}.telegram_chat_id }}}}", "text": "={{ $json.text }}", "additionalFields": {"appendAttribution": False}}},
        {"id": uid(), "name": N["none"], "type": "n8n-nodes-base.noOp", "typeVersion": 1, "position": [260 + 240 * 5, 660], "parameters": {}},
        {"id": uid(), "name": "Note", "type": "n8n-nodes-base.stickyNote", "typeVersion": 1, "position": [20, 40], "parameters": {
            "width": 1200, "height": 190, "content":
            f"## Complaint Journey Replay\n**{title}.**\nReporter 1 files on the RB portal, reporter 2 on the PGRC portal, both about the clean college SYN-0040. "
            "The hub finds the cross-bureau overlap and returns it in `alerts_created`; the IF node sends it to Telegram.\n"
            "Before a run: `python reset_demo.py`. Edit URLs and the Telegram chat ID in the **Settings** node (inside Docker use host.docker.internal instead of localhost)."}},
    ]
    return out


CHAIN = ["trigger", "settings", "search", "details", "card", "rb_conf", "rb_otp", "rb_ver", "rb_sub", "pg_conf", "pg_otp", "pg_ver", "pg_sub", "if"]


def connections():
    c = {}
    for a, b in zip(CHAIN, CHAIN[1:]):
        c[N[a]] = {"main": [[{"node": N[b], "type": "main", "index": 0}]]}
    c[N["if"]] = {"main": [[{"node": N["msg"], "type": "main", "index": 0}], [{"node": N["none"], "type": "main", "index": 0}]]}
    c[N["msg"]] = {"main": [[{"node": N["tg"], "type": "main", "index": 0}]]}
    return c


def record():
    """Run the replay once for real and keep each step's answer (these become the pinned data)."""
    c = httpx.Client(timeout=20)
    r = {}
    r["search"] = c.get(f"{HUB}/api/institutions/search", params={"q": "Norvella Institute of Applied Sciences"}).json()
    cid = r["search"]["candidates"][0]["aicte_id"]
    assert cid == "SYN-0040", "run python reset_demo.py first, and make sure SYN-0040 is the college found"
    r["details"] = c.get(f"{HUB}/api/institutions/{cid}").json()
    for pre, base, phone, cat, title, text in (
            ("rb", RB, RB_PHONE, "Infrastructure/Lab", "Laboratory equipment not working", "The laboratory equipment has been out of order for months and students cannot do practicals."),
            ("pg", PGRC, PG_PHONE, "Fee/Refund", "Refund not returned", "My refundable deposit has not been returned after I withdrew from the programme.")):
        r[pre + "_conf"] = c.post(f"{base}/institution/confirm", json={"institution_id": cid, "resolution_method": "REPORTER_CONFIRMED"}).json()
        r[pre + "_otp"] = c.post(f"{base}/otp/request", json={"contact": phone}).json()
        r[pre + "_ver"] = c.post(f"{base}/otp/verify", json={"contact": phone, "code": r[pre + "_otp"]["demo_otp"]}).json()
        sub = c.post(f"{base}/submit", json={"institution_token": r[pre + "_conf"]["institution_token"], "verification_token": r[pre + "_ver"]["verification_token"],
                                              "reporter_type": "student", "category": cat, "title": title, "description": text, "severity": 3})
        sub.raise_for_status()
        r[pre + "_sub"] = sub.json()
    assert r["pg_sub"]["alerts_created"], "no overlap alert came back: reset the demo first"
    return r


def workflow(name, pinned, rec=None):
    wf = {"name": name, "nodes": nodes(pinned), "connections": connections(), "active": False,
          "settings": {"executionOrder": "v1"}, "meta": {"templateCredsSetupCompleted": False}, "pinData": {}}
    if pinned:
        for key in ("search", "details", "rb_conf", "rb_otp", "rb_ver", "rb_sub", "pg_conf", "pg_otp", "pg_ver", "pg_sub"):
            wf["pinData"][N[key]] = [{"json": rec[key]}]
    return wf


def main():
    try:
        rec = record()
    except (httpx.HTTPError, AssertionError, KeyError) as e:
        print(f"Could not record the replay: {e}\nStart everything (python run_all.py) after python reset_demo.py, then run this again.")
        return 1
    (OUT / "complaint_journey_replay.json").write_text(json.dumps(workflow("Complaint Journey Replay", False), indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "complaint_journey_replay_pinned.json").write_text(
        json.dumps(workflow("Complaint Journey Replay (pinned, illustrative)", True, rec), indent=2, ensure_ascii=False), encoding="utf-8")
    print("Wrote complaint_journey_replay.json and complaint_journey_replay_pinned.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
