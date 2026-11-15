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
