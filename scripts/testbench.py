"""Run the real frontend against the real backend, for clicking through turns in the browser.

Starts the backend (uvicorn, first free port from 8000) with its own database, data/testbench.db, and the frontend
(Vite, port 5173) with scripts/testbench/vite.config.mjs, which proxies /api to the backend. The frontend runs
its own client (frontend/src/api.js) in real mode (VITE_USE_MOCK=false). frontend/ is not changed. Ctrl+C stops both.

Usage: python scripts/testbench.py           keep data/testbench.db between runs
       python scripts/testbench.py --fresh   start with an empty database
First time: cd frontend; npm ci
Then open http://localhost:5173 (add ?new to start a new session). The browser only talks to port 5173,
so a server you already run on 8000 (with data/tutor.db) is left alone.
"""
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
CONFIG = ROOT / "scripts" / "testbench" / "vite.config.mjs"
VITE = FRONTEND / "node_modules" / "vite" / "bin" / "vite.js"
DB = ROOT / "data" / "testbench.db"
BACKEND_PORT, FRONTEND_PORT = 8000, 5173


def port_in_use(port: int) -> bool:
    """Something listens on the port, over IPv4 or IPv6 (Vite on Windows may listen on ::1 only)."""
    try:
        socket.create_connection(("localhost", port), timeout=1).close()
        return True
    except OSError:
        return False


def wait_for(url: str, seconds: float = 30) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def main():
    node = shutil.which("node")
    if not node or not VITE.is_file():
        sys.exit("The frontend is not installed. Run:  cd frontend; npm ci")
    if port_in_use(FRONTEND_PORT):
        sys.exit(f"Port {FRONTEND_PORT} is already in use (another Vite dev server?). Stop it first.")
    backend_port = next((p for p in range(BACKEND_PORT, BACKEND_PORT + 10) if not port_in_use(p)), None)
    if backend_port is None:
        sys.exit(f"Ports {BACKEND_PORT}-{BACKEND_PORT + 9} are all in use.")
    if "--fresh" in sys.argv and DB.exists():
        DB.unlink()
    if not (ROOT / "audio_cache").is_dir():
        print("No audio yet: run python scripts/pregen_audio.py for the Listen button and hints.")

    env = {**os.environ, "DB_PATH": str(DB), "TESTBENCH_BACKEND": f"http://127.0.0.1:{backend_port}",
           # The frontend's own client (src/api.js) in real mode, through Vite's /api proxy.
           "VITE_USE_MOCK": "false", "VITE_API_BASE_URL": f"http://localhost:{FRONTEND_PORT}"}
    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--port", str(backend_port)], cwd=ROOT, env=env)
    frontend = None
    try:
        if not wait_for(f"http://127.0.0.1:{backend_port}/api/health"):
            sys.exit("The backend did not start; see the error above.")
        frontend = subprocess.Popen([node, str(VITE), "--config", str(CONFIG)], cwd=FRONTEND, env=env)
        if not wait_for(f"http://localhost:{FRONTEND_PORT}/"):
            sys.exit("The frontend did not start; see the error above.")
        print(f"\nTestbench ready: http://localhost:{FRONTEND_PORT}   (?new = new session)")
        print(f"Backend docs:    http://localhost:{backend_port}/docs   database: {DB}")
        print("Ctrl+C to stop.\n")
        while backend.poll() is None and frontend.poll() is None:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for p in (frontend, backend):
            if p and p.poll() is None:
                p.terminate()
        for p in (frontend, backend):
            if p:
                try:
                    p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    p.kill()


if __name__ == "__main__":
    main()
