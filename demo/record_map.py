"""Records ONLY the map moment on the RB portal and the PGRC portal (two short clips, about 19 s each).
Nothing is submitted, so no cases are created and the other clips stay valid.

    python run_all.py                 <- running in another terminal (needs internet for the real map)
    python demo/record_map.py
Output: demo/output/map/map_rb.mp4 and map_pgrc.mp4 (and .webm). Send both back; they replace the map moment in clips 2 and 3.
"""
import shutil
import subprocess

from playwright.sync_api import sync_playwright

import record_demo as rd  # same folder: reuses the Scene recorder, URLs and sizes


def record(browser, name, url, caption):
    s = rd.Scene(browser, name, caption)
    s.go(url, wait=0.8)
    s.type("input[type=text]", rd.COLLEGE, delay=30, wait=1.4)
    s.click(".fcard", wait=1)
    s.caption(caption + ": the location comes from the official registry, for verification")
    s.page.wait_for_timeout(9000)  # map tiles need a few seconds to load
    s.page.mouse.move(900, 700)
    s.pause(1.5)
    return s.finish()


def main():
    rd.check_ready()
    out = rd.OUT / "map"
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        files = [record(browser, "map_rb", rd.RB, "Regulation Bureau portal"), record(browser, "map_pgrc", rd.PGRC, "PGRC portal")]
        browser.close()
    shutil.rmtree(rd.OUT / "_raw", ignore_errors=True)
    for f in files:
        dest = out / f.name
        shutil.move(str(f), dest)
        if shutil.which("ffmpeg"):
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(dest), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", str(dest.with_suffix(".mp4"))], check=True)
        print("saved", dest.with_suffix(".mp4").name if shutil.which("ffmpeg") else dest.name)


if __name__ == "__main__":
    main()
