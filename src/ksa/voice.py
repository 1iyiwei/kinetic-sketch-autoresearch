"""Sketch-and-talk demo: say the intent, watch the animation, say a correction, watch the revision.

  uv run python -m ksa.voice [--port 8765]      # then open http://localhost:8765

Speech is transcribed in the browser (Web Speech API, free) when available, otherwise with OpenAI
(KSA_STT_MODEL, default gpt-4o-transcribe); typing works too. With KSA_GEN_MODEL/KSA_CRITIC_MODEL set to
Tinker models (e.g. the distilled student) the whole demo runs without OpenAI.
Each spoken correction goes through the same revise step as the research loop, as a human critique,
and is saved with the before/after programs and scores to runs/voice/<session>/feedback.jsonl,
which is preference data for training the Tinker student.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import critic, generate, llm
from .render import Renderer

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "runs" / "voice"
STT_MODEL = os.getenv("KSA_STT_MODEL", "gpt-4o-transcribe")
CASES = {c["id"]: c for c in json.loads((ROOT / "benchmark" / "cases" / "cases.json").read_text())}

loop = asyncio.new_event_loop()
renderer = Renderer(concurrency=2)
sessions: dict[str, dict] = {}


def run(coro):
    return asyncio.run_coroutine_threadsafe(coro, loop).result()


async def evaluate(s: dict, node_id: str, program: str | None) -> dict:
    case, sdir = s["case"], s["dir"]
    ndir = sdir / node_id
    ndir.mkdir(parents=True, exist_ok=True)
    if not program:
        return {"node": node_id, "ok": False, "error": "no html block in reply", "overall": 0.0}
    (ndir / "program.html").write_text(program)
    r = await renderer.render(program, ndir / "render", duration=case["duration"])
    if not r.ok:
        node = {"node": node_id, "ok": False, "error": "; ".join(r.errors[:2]), "overall": 0.0,
                "critique": critic.zero_score("render failed: " + "; ".join(r.errors[:3])), "render": r.to_json()}
    else:
        c = await critic.critique(case, s["png"], r.sheet, r.strip, r.frames[-1 if case.get("anchor") == "end" else 0],
                                  s["log"], tags={"method": "voice", "node": node_id})
        node = {"node": node_id, "ok": True, "overall": c["overall"], "critique": c, "render": r.to_json(),
                "gif": f"/file/{sdir.name}/{node_id}/render/{Path(r.gif).name}"}
    s["nodes"][node_id] = node
    return node


async def animate(case_id: str, intent: str, svg_text: str | None) -> dict:
    base = dict(CASES.get(case_id) or {"id": "upload", "category": "sketch", "duration": 4.0, "anchor": "start"})
    sid = time.strftime("%H%M%S-") + uuid.uuid4().hex[:4]
    sdir = OUT / sid
    sdir.mkdir(parents=True)
    svg = sdir / "input.svg"
    svg.write_text(svg_text or (ROOT / "benchmark" / "cases" / base["svg"]).read_text())
    case = {**base, "id": f"voice-{base['id']}", "intent": intent.strip() or base.get("intent", "")}
    s = {"case": case, "dir": sdir, "svg": svg, "log": sdir / "llm_calls.jsonl", "nodes": {}, "n": 0}
    s["png"] = await renderer.rasterize_svg(svg, sdir / "input.png")
    sessions[sid] = s
    program, _ = await generate.one_shot(case, svg, s["png"], s["log"], tags={"method": "voice"})
    node = await evaluate(s, "n0", program)
    return {"session": sid, "intent": case["intent"], **summary(node)}


async def revise(sid: str, parent_id: str, feedback: str) -> dict:
    s = sessions[sid]
    parent = s["nodes"][parent_id]
    s["n"] += 1
    node_id = f"n{s['n']}"
    crit = dict(parent.get("critique") or critic.zero_score("no critique"))
    human = {"scores": crit.get("scores", {}),
             "issues": [f"The director watched it and said: \"{feedback}\""] + crit.get("issues", [])[:2],
             "fixes": [f"Do what the director asked: {feedback}. This takes priority over other notes."]}
    rd = parent.get("render", {})
    sheet, strip = (Path(rd["sheet"]), Path(rd["strip"])) if rd.get("ok") else (None, None)
    program_path = s["dir"] / parent_id / "program.html"
    program, _ = await generate.revise(s["case"], s["svg"], s["png"], program_path.read_text(), human,
                                       rd.get("errors", []), sheet, strip, s["log"],
                                       tags={"method": "voice", "parent": parent_id})
    node = await evaluate(s, node_id, program)
    rec = {"case": s["case"]["id"], "intent": s["case"]["intent"], "feedback": feedback,
           "parent": str(program_path), "child": str(s["dir"] / node_id / "program.html"),
           "parent_score": parent["overall"], "child_score": node["overall"], "ts": time.time()}
    with (s["dir"] / "feedback.jsonl").open("a") as f:
        f.write(json.dumps(rec) + "\n")
    return {"session": sid, **summary(node)}


def summary(node: dict) -> dict:
    c = node.get("critique") or {}
    return {"node": node["node"], "ok": node["ok"], "overall": node["overall"], "gif": node.get("gif"),
            "scores": c.get("scores", {}), "issues": c.get("issues", [])[:3], "error": node.get("error")}


async def transcribe(audio: bytes, mime: str) -> str:
    ext = "webm" if "webm" in mime else "mp4" if "mp4" in mime else "wav"
    r = await llm.client().audio.transcriptions.create(model=STT_MODEL, file=(f"speech.{ext}", audio, mime))
    return r.text


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def json(self, obj, code=200):
        self.send(code, json.dumps(obj).encode(), "application/json")

    def do_GET(self):
        if self.path == "/":
            return self.send(200, PAGE.encode(), "text/html; charset=utf-8")
        if self.path == "/cases":
            return self.json([{"id": c["id"], "intent": c["intent"],
                               "svg": (ROOT / "benchmark" / "cases" / c["svg"]).read_text()} for c in CASES.values()])
        if self.path.startswith("/file/"):
            p = (OUT / self.path[len("/file/"):]).resolve()
            if p.is_file() and OUT.resolve() in p.parents:
                return self.send(200, p.read_bytes(), "image/gif" if p.suffix == ".gif" else "image/png")
        self.send(404, b"not found", "text/plain")

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            if self.path == "/transcribe":
                return self.json({"text": run(transcribe(body, self.headers.get("Content-Type", "audio/webm")))})
            req = json.loads(body or b"{}")
            if self.path == "/animate":
                return self.json(run(animate(req.get("case", ""), req.get("intent", ""), req.get("svg"))))
            if self.path == "/revise":
                return self.json(run(revise(req["session"], req["node"], req["feedback"])))
        except Exception as e:  # noqa: BLE001 - surface errors in the page
            return self.json({"error": f"{type(e).__name__}: {e}"}, 500)
        self.send(404, b"not found", "text/plain")


PAGE = """<!doctype html><meta charset="utf-8"><title>Kinetic Sketch: sketch and talk</title>
<style>
body{font:15px system-ui;margin:0;background:#f6f5f2;color:#1d1d1f}
header{padding:14px 24px;background:#1d1d1f;color:#fff;font-weight:600}
main{display:grid;grid-template-columns:340px 1fr;gap:20px;padding:20px 24px}
.panel{background:#fff;border:1px solid #ddd;border-radius:10px;padding:14px}
select,textarea,button{font:inherit;width:100%;box-sizing:border-box;margin:6px 0}
textarea{height:70px}
button{padding:10px;border:0;border-radius:8px;background:#2563eb;color:#fff;cursor:pointer}
button.mic{background:#dc2626}button.mic.rec{background:#7f1d1d;animation:p 1s infinite}
@keyframes p{50%{opacity:.6}}
#preview svg,#preview img{width:100%;height:auto;border:1px solid #eee}
.hist{display:flex;gap:14px;flex-wrap:wrap}
.node{width:300px}.node img{width:300px;height:300px;border:1px solid #ddd;background:#fff}
.node .s{font-size:13px;color:#555}.node .fb{font-style:italic;color:#7c2d12}
#status{color:#555;min-height:20px}
</style>
<header>Kinetic Sketch Autoresearch: sketch and talk</header>
<main>
<div class="panel">
 <label>Drawing</label><select id="case"></select>
 <input type="file" id="upload" accept=".svg">
 <div id="preview"></div>
 <label>Say or type what should happen</label>
 <textarea id="intent"></textarea>
 <button class="mic" data-target="intent">Hold to talk</button>
 <button id="go">Animate</button>
 <hr><label>Say or type a correction</label>
 <textarea id="feedback" placeholder="slower, and more bounce at the end"></textarea>
 <button class="mic" data-target="feedback">Hold to talk</button>
 <button id="rev">Revise</button>
 <label><input type="checkbox" id="speak" checked style="width:auto"> narrate critic</label>
 <div id="status"></div>
</div>
<div class="panel"><div class="hist" id="hist"></div></div>
</main>
<script>
let cases=[],session=null,last=null,uploaded=null;
const $=id=>document.getElementById(id), st=t=>$('status').textContent=t;
fetch('/cases').then(r=>r.json()).then(cs=>{cases=cs;$('case').innerHTML=cs.map(c=>`<option>${c.id}</option>`).join('');pick()});
function pick(){const c=cases.find(c=>c.id==$('case').value);uploaded=null;$('preview').innerHTML=c.svg;$('intent').value=c.intent}
$('case').onchange=pick;
$('upload').onchange=async e=>{uploaded=await e.target.files[0].text();$('preview').innerHTML=uploaded;$('intent').value=''};
function say(t){if($('speak').checked&&window.speechSynthesis){speechSynthesis.cancel();speechSynthesis.speak(new SpeechSynthesisUtterance(t))}}
function card(r,fb){const d=document.createElement('div');d.className='node';
 d.innerHTML=(r.gif?`<img src="${r.gif}">`:`<div style="height:300px;color:#c00">no render: ${r.error||''}</div>`)+
 (fb?`<div class="fb">“${fb}”</div>`:'<div class="fb">first take</div>')+
 `<div class="s"><b>${r.overall.toFixed(2)} / 5</b> · ${Object.entries(r.scores).map(([k,v])=>k+' '+v.toFixed(1)).join(' · ')}<br>${(r.issues||[]).slice(0,2).join('<br>')}</div>`;
 $('hist').appendChild(d);
 say(`Score ${r.overall.toFixed(1)}. `+((r.issues||[])[0]||''));}
async function post(url,body){const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const j=await r.json();if(j.error)throw new Error(j.error);return j}
$('go').onclick=async()=>{st('generating, rendering, critiquing… (~1 min)');$('hist').innerHTML='';
 try{const r=await post('/animate',{case:$('case').value,intent:$('intent').value,svg:uploaded});session=r.session;last=r.node;card(r);st('done, now say a correction')}catch(e){st(e.message)}};
$('rev').onclick=async()=>{if(!session)return st('animate first');const fb=$('feedback').value.trim();if(!fb)return;st('revising…');
 try{const r=await post('/revise',{session,node:last,feedback:fb});last=r.node;card(r,fb);$('feedback').value='';st('done')}catch(e){st(e.message)}};
const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
document.querySelectorAll('.mic').forEach(b=>{let rec,chunks;
 if(SR){let sr=null;
  const go=()=>{sr=new SR();sr.lang='en-US';sr.interimResults=true;b.classList.add('rec');st('listening…');
   sr.onresult=e=>{const t=[...e.results].map(r=>r[0].transcript).join('');$(b.dataset.target).value=t;st('heard: '+t)};
   sr.onend=()=>b.classList.remove('rec');sr.onerror=e=>st('speech: '+e.error);sr.start()};
  b.onmousedown=b.ontouchstart=e=>{e.preventDefault();go()};b.onmouseup=b.ontouchend=b.onmouseleave=()=>{if(sr){sr.stop();sr=null}};return}
 const start=async()=>{const s=await navigator.mediaDevices.getUserMedia({audio:true});rec=new MediaRecorder(s);chunks=[];
  rec.ondataavailable=e=>chunks.push(e.data);rec.onstop=async()=>{s.getTracks().forEach(t=>t.stop());b.classList.remove('rec');st('transcribing…');
   const blob=new Blob(chunks,{type:rec.mimeType});const r=await fetch('/transcribe',{method:'POST',headers:{'Content-Type':rec.mimeType},body:blob});
   const j=await r.json();if(j.error)return st(j.error);$(b.dataset.target).value=j.text;st('heard: '+j.text)};rec.start();b.classList.add('rec')};
 b.onmousedown=b.ontouchstart=e=>{e.preventDefault();start()};b.onmouseup=b.ontouchend=b.onmouseleave=()=>{if(rec&&rec.state=='recording')rec.stop()}});
</script>"""


def main():
    ap = argparse.ArgumentParser(prog="ksa.voice")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=loop.run_forever, daemon=True).start()
    run(renderer.__aenter__())
    print(f"sketch-and-talk on http://localhost:{args.port}  (generator {llm.GEN_MODEL})", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
