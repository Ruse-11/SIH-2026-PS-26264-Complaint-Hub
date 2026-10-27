"""Records the SIH demo as six silent screen clips, one per team member, plus one joined video (if ffmpeg is installed).
The team records the voice-over on top (see demo/DEMO_SCRIPT.md).

Before you run it (from the project folder, with the apps running):
    python reset_demo.py          <- clean data, SYN-0040 has no cases
    python run_all.py             <- leave it running in another terminal
    pip install -r demo/requirements-demo.txt
    python -m playwright install chromium
    python demo/record_demo.py
Clips are written to demo/output/. Run reset_demo.py again before every new recording.
"""
import json
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "demo" / "output"
SLIDES = (ROOT / "demo" / "slides").as_uri()
HUB, RB, PGRC = "http://localhost:5173", "http://localhost:8001", "http://localhost:8002"
COLLEGE = "Norvella Institute of Applied Sciences"  # SYN-0040, the clean demo college
SIZE = {"width": 1920, "height": 1080}  # full page visible (no zoomed or cropped look)

CURSOR_JS = """
(() => {
  const dot = document.createElement('div');
  dot.id = 'demo-cursor';
  dot.style.cssText = 'position:fixed;z-index:2147483647;width:18px;height:18px;border-radius:50%;background:rgba(224,123,0,.85);border:2px solid #fff;pointer-events:none;left:-30px;top:-30px;transform:translate(-50%,-50%);box-shadow:0 0 0 2px rgba(0,0,0,.25)';
  const add = () => document.body && document.body.appendChild(dot);
  document.addEventListener('DOMContentLoaded', add); if (document.body) add();
  window.addEventListener('mousemove', e => { dot.style.left = e.clientX + 'px'; dot.style.top = e.clientY + 'px'; }, true);
})();
"""
CAPTION_JS = """
(text) => {
  let b = document.getElementById('demo-caption');
  if (!b) { b = document.createElement('div'); b.id = 'demo-caption';
    b.style.cssText = 'position:fixed;left:0;right:0;bottom:0;z-index:2147483646;background:#12294d;color:#fff;font:600 17px Segoe UI,Arial,sans-serif;padding:9px 20px;border-top:3px solid #e07b00';
    document.body.appendChild(b); }
  b.textContent = text;
}
"""


class Scene:
    """One clip: its own browser context with video on, a caption bar and a visible cursor."""

    def __init__(self, browser, name, caption):
        self.name, self.cap = name, caption
        self.ctx = browser.new_context(viewport=SIZE, record_video_dir=str(OUT / "_raw"), record_video_size=SIZE)
        self.ctx.add_init_script(CURSOR_JS)
        self.page = self.ctx.new_page()
        self.page.set_default_timeout(20000)

    def caption(self, text=None):
        self.cap = text or self.cap
        self.page.evaluate(CAPTION_JS, self.cap)

    def go(self, url, wait=1.0):
        self.page.goto(url)
        self.page.wait_for_load_state("domcontentloaded")
        time.sleep(0.6)
        self.caption()
        time.sleep(wait)

    def pause(self, seconds):
        time.sleep(seconds)

    def click(self, target, wait=0.8):
        loc = target if not isinstance(target, str) else self.page.locator(target).first
        loc.scroll_into_view_if_needed()
        box = loc.bounding_box()
        self.page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=18)
        time.sleep(0.25)
        loc.click()
        time.sleep(wait)

    def type(self, selector, text, delay=70, wait=0.6):
        loc = self.page.locator(selector).first
        loc.scroll_into_view_if_needed()
        box = loc.bounding_box()
        self.page.mouse.move(box["x"] + 40, box["y"] + box["height"] / 2, steps=15)
        loc.click()
        loc.press_sequentially(text, delay=delay)
        time.sleep(wait)

    def scroll(self, pixels, seconds=2.0, steps=20):
        for _ in range(steps):
            self.page.mouse.wheel(0, pixels / steps)
            time.sleep(seconds / steps)

    def login(self, username, then=None):
        """Sign in without typing (saves screen time): ask the hub for a token and store it the way the app does."""
        body = json.dumps(json.load(urllib.request.urlopen(urllib.request.Request(
            "http://localhost:8000/api/auth/login", data=json.dumps({"username": username, "password": "demo123"}).encode(),
            headers={"Content-Type": "application/json"}), timeout=10)))
        self.page.goto(HUB + "/login")
        self.page.evaluate("b => localStorage.setItem('hub_auth', b)", body)
        self.go(HUB + (then or "/"), wait=0.3)

    def finish(self):
        video = self.page.video
        self.ctx.close()
        target = OUT / f"{self.name}.webm"
        shutil.move(video.path(), target)
        print("  saved", target.name)
        return target


def check_ready():
    for name, url in [("hub", "http://localhost:8000/api/health"), ("RB portal", RB + "/config"), ("PGRC portal", PGRC + "/config"), ("dashboard", HUB)]:
        try:
            urllib.request.urlopen(url, timeout=5).read()
        except Exception as e:  # noqa: BLE001
            sys.exit(f"The {name} is not running ({e}). Start it with: python run_all.py")


def post(base, path, body, token=None):
    headers = {"Content-Type": "application/json", **({"Authorization": "Bearer " + token} if token else {})}
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), headers=headers)
    return json.load(urllib.request.urlopen(req, timeout=20))


def link_id(kind):
    """The id of the waiting suggestion of this kind (CORROBORATION, CROSS_BUREAU...) at the demo college SYN-0040."""
    token = post("http://localhost:8000", "/api/auth/login", {"username": "rb.officer", "password": "demo123"})["token"]
    req = urllib.request.Request("http://localhost:8000/api/matching/links?status=SUGGESTED", headers={"Authorization": "Bearer " + token})
    for l in json.load(urllib.request.urlopen(req, timeout=10)):
        if l["institution"]["aicte_id"] == "SYN-0040" and l["link_type"] == kind:
            return l["id"]
    sys.exit(f"No {kind} suggestion at SYN-0040. Run python reset_demo.py and record again from scene 1.")


RB_TEXT = "The laboratory equipment has been out of order for months and students cannot do practicals."
PG_TEXT = "Laboratory equipment has been broken for months and the students are unable to do their practicals."


def fill_form_and_submit(s, phone, text, title, wait_after=2.0, d=12):
    """Steps 1 to 4 of the reporter journey once the college has been confirmed on the card."""
    s.click("#finder-yes", wait=0.4)
    s.type("#contact", phone, delay=20, wait=0.2)
    s.click("#send-otp", wait=0.5)
    s.click("#use-code", wait=0.3)
    s.click("#verify-otp", wait=0.6)
    s.page.select_option("#f-category", "Infrastructure/Lab")
    s.type("#f-title", title, delay=d, wait=0.1)
    s.type("#f-description", text, delay=4, wait=0.3)
    s.click("#submit-complaint", wait=wait_after)


def main():
    want = {int(a) for a in sys.argv[1:]} or {1, 2, 3, 4, 5, 6}  # e.g. "python demo/record_demo.py 4 5" records only scenes 4 and 5
    check_ready()
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob("*"):
        if f.is_file() and f.name[0].isdigit() and int(f.name[0]) in want:
            f.unlink()
        elif f.is_file() and f.name.startswith("demo_full"):
            f.unlink()
    with sync_playwright() as p:
        browser = p.chromium.launch()

        # ---- 1. Member 1 (about 17 s): the problem and the architecture ----
        if 1 in want:
            s = Scene(browser, "1_member1_architecture", "1 · One hub behind the two existing portals")
            s.go(SLIDES + "/architecture.html", wait=10)
            s.go(RB, wait=1.4)
            s.caption("1 · Regulation Bureau portal")
            s.go(PGRC, wait=1.9)
            s.caption("1 · Public Grievance Redressal Cell portal: a different portal and database")
            s.finish()

        # ---- 2. Member 2 (about 38 s): search power, guided questions, map, verification ----
        if 2 in want:
            s = Scene(browser, "2_member2_finder_and_map", "2 · Institution Finder: not sure? Answer a few questions")
            s.go(RB, wait=0.8)
            s.click("text=Not sure? Answer a few questions", wait=2.5)
            s.click("button:has-text('Back to search')", wait=0.5)
            s.caption("2 · Not listed? The reporter says so, and an officer assigns it later")
            s.click("text=My institution isn't listed", wait=2.2)
            s.click("button:has-text('Back to search')", wait=0.5)
            s.caption("2 · Search power: a missing first letter ('kstora') still finds the college")
            s.type("input[type=text]", "kstora", delay=70, wait=1.6)
            s.caption("2 · Or a spelling slip ('estora')")
            s.page.fill("input[type=text]", "")
            s.type("input[type=text]", "estora", delay=70, wait=1.6)
            s.caption("2 · Typing the college name with typos")
            s.page.fill("input[type=text]", "")
            s.type("input[type=text]", "norvela institue of applied", delay=30, wait=1.6)
            s.click(".fcard", wait=6)  # the confirm card with the location
            s.caption("2 · The college's location is shown from the registry, for verification")
            s.pause(1.5)
            s.caption("2 · Mock OTP in the prototype. In production: Aadhaar through DigiLocker")
            fill_form_and_submit(s, "9000000301", RB_TEXT, "Laboratory equipment not working", wait_after=2.5)
            s.finish()

        # ---- 3. Member 3 (about 55 s): live corroboration, human in the loop ----
        if 3 in want:
            s = Scene(browser, "3_member3_corroboration_live", "3 · A second, independent reporter files on the other portal")
            s.go(PGRC, wait=0.5)
            s.type("input[type=text]", COLLEGE, delay=12, wait=1.2)
            s.click(".fcard", wait=1.2)
            fill_form_and_submit(s, "9000000302", PG_TEXT, "Lab equipment broken for months", wait_after=2)
            s.caption("3 · The complaint hub: role-based sign-in, one account per role")
            s.go(HUB + "/login", wait=3)
            s.click("button:has-text('RB officer')", wait=2.5)
            s.caption("3 · Corroboration: independent reporters, same problem (potential priority boost)")
            s.go(HUB + f"/overlaps?link={link_id('CORROBORATION')}", wait=1.5)
            s.page.locator("#link-" + str(link_id("CORROBORATION"))).scroll_into_view_if_needed()
            s.pause(9)
            s.caption("3 · Human in the loop: the officer confirms, and only then does priority rise")
            card = "#link-" + str(link_id("CORROBORATION"))
            s.type(card + " input[placeholder='Note (optional)']", "Two reporters, same lab problem.", delay=25, wait=0.4)
            s.click(card + " button:has-text('Confirm link')", wait=4)
            s.caption("3 · Priority updated. The case file downloads for the record")
            s.go(HUB + "/cases?q=RB-2026-1001", wait=1.5)
            s.click("a:has-text('RB-2026-1001')", wait=3)
            s.click("#download-case-file", wait=3)
            s.caption("3 · Other overlap types: cross-bureau, conflicting actions, same-reporter duplicates")
            s.go(HUB + "/overlaps", wait=1)
            s.click("button:has-text('Conflicting actions')", wait=2)
            s.click("button:has-text('Same reporter')", wait=2)
            s.finish()

        # ---- 4. Member 4 (about 26 s): officer actions, audit ----
        if 4 in want:
            s = Scene(browser, "4_member4_officer_actions", "4 · Officer actions: the hub checks them against the other bureau")
            s.login("rb.officer", "/cases?q=RB-2026-1001")
            s.pause(0.8)
            s.click("a:has-text('RB-2026-1001')", wait=1.2)
            s.scroll(450, 1.2)
            s.click("button:has-text('Take enforcement action')", wait=0.8)
            s.click("text=Show-Cause Notice Issued", wait=0.6)
            s.type("#action-remarks", "Notice issued on the lab conditions.", delay=20, wait=0.2)
            s.type("#next-step", "Review the institution's reply", delay=20, wait=0.3)
            s.click("button:has-text('Log action')", wait=2.5)
            s.caption("4 · Action history and next action. Also: transfer, escalate, link related cases")
            s.scroll(-700, 1)
            s.pause(2.5)
            s.login("senior.mgmt", "/audit")
            s.caption("4 · Audit trail: every decision is recorded")
            s.pause(3.5)
            s.finish()

        # ---- 5. Member 5 (about 26 s): dashboard, search, alerts, reports ----
        if 5 in want:
            s = Scene(browser, "5_member5_dashboard_and_reports", "5 · Dashboard for senior management: live numbers")
            s.login("senior.mgmt", "/")
            s.pause(2.5)
            s.scroll(560, 2)
            s.pause(1)
            s.caption("5 · Search and filters: institution, AICTE ID, case ID, bureau, region, status, date")
            s.go(HUB + "/cases?q=Maventra", wait=3)
            s.caption("5 · Alerts: what needs a decision, and the time watch")
            s.go(HUB + "/alerts", wait=1)
            s.click("text=Time watch", wait=2.5)
            s.caption("5 · Reports with CSV export")
            s.go(HUB + "/reports", wait=3)
            s.caption("5 · Insights: plain rules over live data")
            s.go(HUB + "/insights", wait=3)
            s.finish()

        # ---- 6. Member 6 (about 20 s): government fit and close ----
        if 6 in want:
            s = Scene(browser, "6_member6_government_fit", "6 · Built for government servers and legacy systems")
            s.go(SLIDES + "/govfit.html", wait=12)
            s.caption("6 · One hub, one view, and officers decide")
            s.login("competent.authority", "/")
            s.pause(2)
            s.finish()
        browser.close()

    shutil.rmtree(OUT / "_raw", ignore_errors=True)
    clips = sorted(OUT.glob("[1-6]_*.webm"))  # all six, including ones recorded in an earlier run
    if shutil.which("ffmpeg"):
        mp4s = []
        for c in clips:
            m = c.with_suffix(".mp4")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(c), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", str(m)], check=True)
            mp4s.append(m)
        lst = OUT / "list.txt"
        lst.write_text("".join(f"file '{m.name}'\n" for m in mp4s))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(OUT / "demo_full.mp4")], check=True)
        lst.unlink()
        print("Joined video: demo/output/demo_full.mp4")
    else:
        print("ffmpeg not found: use the six .webm clips (any video editor can join them).")
    print(json.dumps([c.name for c in clips], indent=1))


if __name__ == "__main__":
    main()
