"""Export chosen results as small, playable, committable files.

  uv run ksa export <run dirs...> --name test            # final program of every case, per run/method
  uv run ksa export-tree <run dir> <case> --name pendulum-tree   # every candidate of one search

Writes results/<name>/:
  manifest.json                 cases, intents, and for each method its file and scores
  <case>/input.svg              the drawing
  <case>/<label>.html           the animation program, plus a tiny player that loops ksaRender(t)

The programs are pure functions of time, so these files replay the exact animation the
judge scored, at about 8 KB each (a GIF of the same animation is about 180 KB).
Open one directly to watch it loop; add ?t=1.5 to the URL to freeze it at t = 1.5 s.
"""

from __future__ import annotations

import json
import shutil
import statistics as st
from pathlib import Path

from .paths import resolve

PLAYER = """
<script>
/* ksa player: loops window.ksaRender(t) over the animation's duration, holding the last frame briefly.
   ?t=<seconds> freezes it at that time. Added by `ksa export`; not part of the generated program. */
(function () {
  var D = %(duration)s, HOLD = 0.8;
  var q = new URLSearchParams(location.search), fixed = q.get("t");
  var t0 = null;
  function tick(now) {
    if (t0 === null) t0 = now;
    var t = fixed !== null ? parseFloat(fixed) : ((now - t0) / 1000) %% (D + HOLD);
    Promise.resolve(window.ksaRender(Math.min(t, D))).then(function () {
      if (fixed === null) requestAnimationFrame(tick);
    });
  }
  function start() { if (typeof window.ksaRender === "function") requestAnimationFrame(tick); }
  if (document.readyState === "complete") start(); else window.addEventListener("load", start);
})();
</script>
"""


def playable(program: str, duration: float) -> str:
    snippet = PLAYER % {"duration": duration}
    i = program.lower().rfind("</body>")
    return program[:i] + snippet + program[i:] if i >= 0 else program + snippet


def judge_means(run_dir: Path) -> dict[str, float]:
    j = sorted(run_dir.glob("judge-*.json"))
    if not j:
        return {}
    return {p["case"]: round(st.mean(p["overall"]), 2) for p in json.loads(j[-1].read_text())["per_case"]}


def _case_meta(case: dict, root: Path) -> dict:
    return {"intent": case["intent"], "category": case["category"], "anchor": case.get("anchor", "start"),
            "duration": case["duration"], "split": case.get("split"), "methods": {}}


def _load_manifest(out: Path) -> dict:
    p = out / "manifest.json"
    return json.loads(p.read_text()) if p.exists() else {"cases": {}}


def export_runs(run_dirs: list[str], out: Path, cases_by_id: dict, cases_dir: Path, only: set | None = None) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest(out)
    for spec in run_dirs:
        # "runs/<dir>=label" overrides the method label (e.g. two runs of one method, before/after a fix)
        d, _, label = str(spec).partition("=")
        d = Path(d)
        data = json.loads((d / "results.json").read_text())
        method = label or data["meta"]["method"]
        judged = judge_means(d)
        for r in data["results"]:
            cid = r["case"]
            if only and cid not in only:
                continue
            case = cases_by_id[cid]
            cdir = out / cid
            cdir.mkdir(exist_ok=True)
            shutil.copy(cases_dir / case["svg"], cdir / "input.svg")
            entry = manifest["cases"].setdefault(cid, _case_meta(case, cases_dir))
            prog = resolve(r["program"], d)
            rec = {"run": d.name, "critic": r["critique"]["overall"], "judge": judged.get(cid),
                   "best_score_by_round": r.get("best_score_by_round"), "issue": (r["critique"].get("issues") or [""])[0]}
            if prog.exists():
                (cdir / f"{method}.html").write_text(playable(prog.read_text(), case["duration"]))
                rec["file"] = f"{cid}/{method}.html"
            entry["methods"][method] = rec
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return out


def export_tree(run_dir: Path, case_id: str, out: Path, cases_by_id: dict, cases_dir: Path) -> Path:
    case = cases_by_id[case_id]
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy(cases_dir / case["svg"], out / "input.svg")
    tree = json.loads((run_dir / case_id / "tree.json").read_text())
    nodes = []
    for n in tree["nodes"]:
        prog = run_dir / case_id / "nodes" / n["id"] / "program.html"
        rec = {"id": n["id"], "parent": n["parent"], "round": n["round"], "origin": n["origin"], "score": n["score"],
               "scores": n["critique"].get("scores"), "issues": n["critique"].get("issues", [])[:3],
               "fixes": n["critique"].get("fixes", [])[:3]}
        if prog.exists():
            (out / f"{n['id']}.html").write_text(playable(prog.read_text(), case["duration"]))
            rec["file"] = f"{n['id']}.html"
        nodes.append(rec)
    meta = {"case": case_id, "intent": case["intent"], "run": run_dir.name, "best": tree["best"],
            "best_score_by_round": tree["best_score_by_round"], "nodes": nodes}
    (out / "manifest.json").write_text(json.dumps(meta, indent=2) + "\n")
    return out


# ---------------------------------------------------------------- pages (committed, program-based)

SET_INFO = {
    "first-batch": ("First batch: 10 drawings", "One-shot, best-of-6 and the loop on the first 10 drawings, one run each."),
    "test": ("Held-out test: 7 drawings", "Drawings never used for tuning. One-shot shows run 1 of 3; the playbook column uses playbook v2 with selected lessons; the loop ran once."),
    "complex": ("Complex: 5 drawings", "Multi-object interactions, an articulated character and a three-beat story; never used for learning. One-shot shows run 1 of 3; the loop ran once."),
    "pendulum-tree": ("One search: the pendulum", "Every candidate of one loop search: 2 first samples, then 2 rounds revising the best into 2 children."),
    "anchor-fix": ("Anchor-frame fix: logo intros", "Loop results for two build-up logo intros, before and after each drawing named its anchor frame (the last frame for build-ups)."),
}
METHOD_NAMES = {"one_shot": "one-shot", "best_of_6": "best-of-6", "loop_k2_b1_c2_r2": "loop",
                "one_shot+train-v2_select": "one-shot + playbook v2", "before_anchor_fix": "before the fix",
                "after_anchor_fix": "after the fix"}

PAGE_HEAD = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{ --bg:#f6f7f9; --panel:#fff; --fg:#1c2230; --muted:#5d6678; --line:#dde1e8; --accent:#2457c5; --win:#e3f3e8; --wink:#1f7a43; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#12151c; --panel:#1a1f29; --fg:#e6e9ef; --muted:#9aa3b5; --line:#2b3240; --accent:#7ea2ff; --win:#163524; --wink:#7fd6a0; color-scheme:dark; }} }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:15px/1.5 Inter,system-ui,sans-serif; padding:24px max(16px,env(safe-area-inset-left)); }}
main {{ max-width:1180px; margin:0 auto; display:grid; gap:22px; }}
h1 {{ font:700 28px "Space Grotesk",system-ui,sans-serif; margin:0; }} h2 {{ font:600 19px "Space Grotesk",system-ui,sans-serif; margin:0; }}
p {{ margin:0; max-width:75ch; }} .muted {{ color:var(--muted); }} .small {{ font-size:13px; }}
a {{ color:var(--accent); }} code,.mono {{ font-family:"JetBrains Mono",ui-monospace,monospace; font-variant-numeric:tabular-nums; }}
.case {{ background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:14px; display:grid; gap:10px; }}
.intent {{ font-size:15px; }} .intent b {{ color:var(--muted); font-weight:600; }}
.tiles {{ display:flex; flex-wrap:wrap; gap:12px; }}
.tile {{ display:grid; gap:4px; width:206px; padding:6px; border-radius:8px; align-content:start; }}
.tile.win {{ background:var(--win); }} .tile.win .mono {{ color:var(--wink); font-weight:700; }}
.frame {{ width:194px; height:194px; border:1px solid var(--line); border-radius:6px; overflow:hidden; background:#fff; }}
.frame iframe {{ width:512px; height:512px; border:0; transform:scale(.3789); transform-origin:0 0; }}
.frame img {{ width:100%; height:100%; display:block; }}
.lab {{ font-size:13px; font-weight:600; }} .note {{ font-size:12px; color:var(--muted); }}
.pill {{ font:500 12px "JetBrains Mono",monospace; padding:1px 8px; border-radius:99px; border:1px solid var(--line); color:var(--muted); }}
ul {{ margin:0; padding-left:18px; }} li {{ font-size:13px; }}
</style></head><body><main>
"""


def _e(s) -> str:
    import html
    return html.escape(str(s))


def _tile(src: str, label: str, line: str = "", note: str = "", win: bool = False, img: bool = False) -> str:
    inner = f'<img src="{_e(src)}" alt="{_e(label)}">' if img else f'<iframe src="{_e(src)}" title="{_e(label)}" loading="lazy"></iframe>'
    return (f'<div class="tile{" win" if win else ""}"><div class="frame">{inner}</div><div class="lab">{_e(label)}</div>'
            + (f'<div class="mono small">{line}</div>' if line else "") + (f'<div class="note">{_e(note)}</div>' if note else "") + "</div>")


def _intent(meta: dict) -> str:
    extra = f'{meta["category"]} · {meta["duration"]:g} s · anchor: {"last frame (builds up)" if meta.get("anchor") == "end" else "first frame"}'
    return (f'<p class="intent"><b>Intent:</b> {_e(meta["intent"])}</p>'
            f'<p class="small muted">{_e(extra)} · <a href="{_e(meta["prompt"])}">full prompt</a></p>')


def write_prompt(cdir: Path, case: dict, svg_text: str) -> str:
    from . import generate
    (cdir / "prompt.txt").write_text(generate.build_prompt(case, svg_text))
    return "prompt.txt"


def write_set_page(out: Path, cases_by_id: dict) -> Path:
    m = json.loads((out / "manifest.json").read_text())
    title, desc = SET_INFO.get(out.name, (out.name, ""))
    parts = [PAGE_HEAD.format(title=_e(title)), f'<p><a href="../index.html">← all results</a></p><h1>{_e(title)}</h1>',
             f'<p class="muted">{_e(desc)} Score under each animation: held-out judge (gpt-5.4, mean of 3), then the in-loop critic. '
             'Green: best judge score in the row (no highlight on ties).</p>']
    for cid, c in m["cases"].items():
        write_prompt(out / cid, cases_by_id[cid], (out / cid / "input.svg").read_text())
        c["prompt"] = f"{cid}/prompt.txt"
        judges = [v["judge"] for v in c["methods"].values() if v.get("judge") is not None]
        best = max(judges) if judges else None
        unique = judges.count(best) == 1 if judges else False
        tiles = [_tile(f"{cid}/input.svg", "input drawing", img=True)]
        for meth, v in c["methods"].items():
            if "file" not in v:
                continue
            traj = v.get("best_score_by_round") or []
            line = (f'judge {v["judge"]:.2f} · critic {v["critic"]:.2f}' if v.get("judge") is not None else f'critic {v["critic"]:.2f}')
            line += (" · rounds " + " → ".join(f"{x:.2f}" for x in traj)) if len(traj) > 1 else ""
            tiles.append(_tile(v["file"], METHOD_NAMES.get(meth, meth), line, v.get("issue", "")[:160],
                               win=unique and v.get("judge") == best))
        parts.append(f'<section class="case"><h2>{_e(cid)} <span class="pill">{_e(c.get("split") or "")}</span></h2>'
                     f'{_intent(c)}<div class="tiles">{"".join(tiles)}</div></section>')
    parts.append("</main></body></html>\n")
    (out / "index.html").write_text("".join(parts))
    return out / "index.html"


def write_tree_page(out: Path, cases_by_id: dict) -> Path:
    m = json.loads((out / "manifest.json").read_text())
    case = cases_by_id[m["case"]]
    write_prompt(out, case, (out / "input.svg").read_text())
    meta = {**case, "prompt": "prompt.txt"}
    title, desc = SET_INFO.get(out.name, (out.name, ""))
    parts = [PAGE_HEAD.format(title=_e(title)), f'<p><a href="../index.html">← all results</a></p><h1>{_e(title)}</h1>',
             f'<p class="muted">{_e(desc)} Best critic score per round: '
             f'{" → ".join(f"{x:.2f}" for x in m["best_score_by_round"])}. Green: the candidate the search kept.</p>',
             f'<section class="case">{_intent(meta)}<div class="tiles">{_tile("input.svg", "input drawing", img=True)}</div></section>']
    for rnd in sorted({n["round"] for n in m["nodes"]}):
        tiles = []
        for n in [x for x in m["nodes"] if x["round"] == rnd]:
            src = "first sample" if n["parent"] is None else f'revision of {n["parent"]}'
            tiles.append(_tile(n["file"], f'{n["id"]} · {src}', f'critic {n["score"]:.2f}',
                               (n["issues"] or [""])[0][:160], win=n["id"] == m["best"]))
        parts.append(f'<section class="case"><h2>Round {rnd}</h2><div class="tiles">{"".join(tiles)}</div></section>')
    parts.append("</main></body></html>\n")
    (out / "index.html").write_text("".join(parts))
    return out / "index.html"


def write_pages(results_root: Path, cases_by_id: dict) -> list[Path]:
    """Rebuild every set's index.html, prompts, the shared system prompt and the top-level index."""
    from . import generate
    (results_root / "system-prompt.txt").write_text(generate.SYSTEM)
    written, items = [], []
    for out in sorted(p for p in results_root.iterdir() if (p / "manifest.json").exists()):
        m = json.loads((out / "manifest.json").read_text())
        written.append(write_tree_page(out, cases_by_id) if "nodes" in m else write_set_page(out, cases_by_id))
        title, desc = SET_INFO.get(out.name, (out.name, ""))
        items.append(f'<section class="case"><h2><a href="{_e(out.name)}/index.html">{_e(title)}</a></h2><p class="muted">{_e(desc)}</p></section>')
    (results_root / "index.html").write_text(
        PAGE_HEAD.format(title="Kinetic Sketch Autoresearch results")
        + '<h1>Kinetic Sketch Autoresearch: results</h1><p class="muted">Every animation on these pages plays from its committed '
        'program (a pure function of time), so it is exactly what the judge scored. Each drawing is given with a text intent; '
        'the generator also gets a fixed <a href="system-prompt.txt">system prompt</a>. '
        'Slides: <a href="../slides/index.html">slides/index.html</a>.</p>' + "".join(items) + "</main></body></html>\n")
    return written + [results_root / "index.html"]
