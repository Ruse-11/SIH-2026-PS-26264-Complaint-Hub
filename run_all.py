"""Starts everything with one command:   python run_all.py   (Ctrl+C stops all)

  hub backend  http://localhost:8000   (API docs at /docs)
  RB portal    http://localhost:8001
  PGRC portal  http://localhost:8002
  dashboard    http://localhost:5173   (needs `npm install` once in hub/frontend)

Options:  --no-frontend   skip the React dashboard
"""
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable
UVICORN = [PY, "-m", "uvicorn"]

SERVICES = [  # (label, command, working folder, health URL)
    ("hub", UVICORN + ["app.main:app", "--port", "8000"], ROOT / "hub" / "backend", "http://127.0.0.1:8000/api/health"),
    ("rb", UVICORN + ["app:app", "--port", "8001"], ROOT / "portal_rb", "http://127.0.0.1:8001/health"),
    ("pgrc", UVICORN + ["app:app", "--port", "8002"], ROOT / "portal_pgrc", "http://127.0.0.1:8002/health"),
]


def frontend_service():
    """The dashboard, only if npm is installed and `npm install` was done."""
    folder = ROOT / "hub" / "frontend"
    npm = shutil.which("npm")
    if not npm or not (folder / "node_modules").exists():
        print("[run_all] dashboard skipped: run `npm install` in hub/frontend first (needs Node.js).")
        return None
    return ("web", [npm, "run", "dev"], folder, "http://127.0.0.1:5173/")


def pipe_output(label, proc):
    """Print each line of a child's output with its label."""
    for line in proc.stdout:
        print(f"[{label}] {line.rstrip()}", flush=True)


def stop(proc):
    """Stop a child and its children (npm starts node under it; on Windows taskkill /T gets the whole tree)."""
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    else:
        proc.terminate()


def is_up(url):
    try:
        urllib.request.urlopen(url, timeout=1)
        return True
    except Exception:
        return False


def main():
    services = list(SERVICES)
    if "--no-frontend" not in sys.argv:
        web = frontend_service()
        if web:
            services.append(web)

    procs = []
    try:
        for label, cmd, cwd, url in services:
            proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            procs.append((label, proc, url))
            threading.Thread(target=pipe_output, args=(label, proc), daemon=True).start()

        time.sleep(0.5)
        deadline = time.time() + 40
        pending = {label: url for label, _, url in procs}
        while pending and time.time() < deadline:
            for label in list(pending):
                if is_up(pending[label]):
                    print(f"[run_all] {label} is up: {pending.pop(label)}", flush=True)
            time.sleep(0.5)
        for label in pending:
            print(f"[run_all] WARNING: {label} did not answer at {pending[label]}", flush=True)
        print("[run_all] running. Press Ctrl+C to stop everything.", flush=True)

        while True:  # exit if any service dies, so errors are not hidden
            for label, proc, _ in procs:
                if proc.poll() is not None:
                    print(f"[run_all] {label} stopped with code {proc.returncode}. Stopping all.", flush=True)
                    return
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[run_all] stopping...", flush=True)
    finally:
        for _, proc, _ in procs:
            stop(proc)


if __name__ == "__main__":
    main()
