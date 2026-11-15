"""Local server for the drawing page: draw, describe, press Animate, watch the result.

  uv run ksa serve            # then open http://127.0.0.1:8765

GET  /                      tools/draw.html
GET  /api/config            which generator and critic models will run (so the page can say what it costs)
POST /api/animate           {svg, intent, name, category, anchor, method} -> {job}; runs `ksa animate` in the background
GET  /api/jobs/<job>        {state, log, run_dir, score, rounds}
GET  /api/jobs/<job>/program   the best program, with a looping player (play it in an iframe)
GET  /api/jobs/<job>/source    the best program exactly as generated (shown as code on the page)
GET  /runs/...              files under runs/ (the run's gallery page, GIFs, frames)

It binds to 127.0.0.1 only. Each job is a `ksa animate` subprocess, so it uses the same models as the command
line (KSA_GEN_MODEL / KSA_CRITIC_MODEL, from .env).
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import llm
from .export import playable
from .paths import resolve

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "runs"
INBOX = RUNS / "animate" / "inbox"
JOBS: dict[str, dict] = {}


def _job_status(job: dict) -> dict:
    log = job["log"].read_text() if job["log"].exists() else ""
    m = re.search(r"^run dir: (.+)$", log, re.M)
    out = {"state": "running" if job["proc"].poll() is None else ("done" if job["proc"].returncode == 0 else "failed"),
           "log": "\n".join(log.splitlines()[-40:]), "started": job["started"],
           "elapsed": round(time.time() - job["started"])}
    if m:
        run_dir = Path(m.group(1).strip())
        out["run_dir"] = str(run_dir.relative_to(RUNS)) if run_dir.is_relative_to(RUNS) else str(run_dir)
        res = run_dir / "results.json"
        if res.exists():
            r = json.loads(res.read_text())["results"][0]
            out["score"] = r["critique"]["overall"]
            out["rounds"] = r.get("best_score_by_round")
            out["issues"] = (r["critique"].get("issues") or [])[:3]
            out["has_program"] = bool(r.get("program")) and resolve(r["program"], run_dir).exists()
            job["run_dir"], job["result"] = run_dir, r
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):  # quiet: the page shows progress
        pass

    def _send(self, code: int, body: bytes | str, ctype: str = "application/json"):
        body = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj))

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/draw.html"):
            return self._send(200, (ROOT / "tools" / "draw.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/api/config":
            return self._json({"gen_model": llm.GEN_MODEL, "critic_model": llm.CRITIC_MODEL})
        m = re.fullmatch(r"/api/jobs/(\w+)(/program|/source)?", path)
        if m:
            job = JOBS.get(m.group(1))
            if not job:
                return self._json({"error": "no such job"}, 404)
            st = _job_status(job)
            if not m.group(2):
                return self._json(st)
            r = job.get("result")
            if not r or not r.get("program"):
                return self._json({"error": "no program yet"}, 404)
            prog = resolve(r["program"], job["run_dir"]).read_text()
            if m.group(2) == "/source":  # the program exactly as generated, without the player
                return self._send(200, prog, "text/plain; charset=utf-8")
            return self._send(200, playable(prog, job["duration"]), "text/html; charset=utf-8")
        if path.startswith("/runs/"):
            f = (RUNS / path.removeprefix("/runs/")).resolve()
            if f.is_relative_to(RUNS) and f.is_file():
                return self._send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path != "/api/animate":
            return self._json({"error": "not found"}, 404)
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            svg, intent = req["svg"], req["intent"].strip()
        except (ValueError, KeyError) as e:
            return self._json({"error": f"bad request: {e}"}, 400)
        if not intent:
            return self._json({"error": "Describe what should happen first."}, 400)
        if "<path" not in svg:
            return self._json({"error": "Draw something first."}, 400)
        name = re.sub(r"[^\w-]", "_", req.get("name") or "drawing")[:40] or "drawing"
        method = req.get("method") if req.get("method") in ("loop", "oneshot") else "loop"
        category = req.get("category") if req.get("category") in ("sketch", "diagram", "cartoon", "logo") else "sketch"
        anchor = "end" if req.get("anchor") == "end" else "start"
        duration = min(max(float(req.get("duration") or 4.0), 1.0), 10.0)
        job_id = time.strftime("%H%M%S") + f"{int(time.time() * 1000) % 1000:03d}"
        INBOX.mkdir(parents=True, exist_ok=True)
        f = INBOX / f"{job_id}-{name}.svg"
        f.write_text(svg)
        log = INBOX / f"{job_id}-{name}.log"
        cmd = [sys.executable, "-m", "ksa.cli", "animate", str(f), intent, "--no-open", "--method", method,
               "--category", category, "--anchor", anchor, "--duration", str(duration)]
        env = {**os.environ, "PYTHONWARNINGS": "ignore::FutureWarning,ignore::DeprecationWarning",
               "TRANSFORMERS_VERBOSITY": "error"}  # keep the page's log to the run's own progress
        proc = subprocess.Popen(cmd, stdout=log.open("w"), stderr=subprocess.STDOUT, cwd=ROOT, env=env)
        JOBS[job_id] = {"proc": proc, "log": log, "started": time.time(), "duration": duration}
        self._json({"job": job_id})


def main(port: int = 8765, open_browser: bool = True):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Sketch pad: {url}  (generator {llm.GEN_MODEL}, critic {llm.CRITIC_MODEL}; Ctrl-C to stop)", flush=True)
    if open_browser:
        threading.Timer(0.5, lambda: subprocess.run(["open", url], check=False)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for j in JOBS.values():
            if j["proc"].poll() is None:
                j["proc"].terminate()
