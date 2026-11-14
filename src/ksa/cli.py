"""Command line entry point.

  uv run ksa baseline [--cases ball_ramp,fish] [--out runs]

Runs the one-shot baseline on the benchmark: generate -> render -> critique,
and writes per-case artifacts, results.json, summary.md, a gallery index.html
and llm_calls.jsonl (every model call, for the decision trace).
"""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import time
from pathlib import Path

from . import critic, generate, llm
from .render import Renderer

ROOT = Path(__file__).resolve().parents[2]
CASES_DIR = ROOT / "benchmark" / "cases"


def load_cases(only: str | None) -> list[dict]:
    cases = json.loads((CASES_DIR / "cases.json").read_text())
    if only:
        keep = set(only.split(","))
        cases = [c for c in cases if c["id"] in keep]
    return cases


async def run_case(case: dict, renderer: Renderer, run_dir: Path, log: Path) -> dict:
    cdir = run_dir / case["id"]
    cdir.mkdir(parents=True, exist_ok=True)
    svg = CASES_DIR / case["svg"]
    png = await renderer.rasterize_svg(svg, cdir / "input.png")
    t0 = time.time()
    rec: dict = {"case": case["id"], "category": case["category"], "method": "one_shot"}
    try:
        program, raw = await generate.one_shot(case, svg, png, log)
    except Exception as e:  # noqa: BLE001 - a failed call is a result, not a crash
        rec.update(error=f"generator call failed: {e}", critique=critic.zero_score("generator call failed"))
        return rec
    (cdir / "generator_raw.txt").write_text(raw)
    if program is None:
        rec.update(error="no ```html block in reply", critique=critic.zero_score("no program returned"))
        return rec
    (cdir / "program.html").write_text(program)
    rendered = await renderer.render(program, cdir / "render", duration=case["duration"])
    rec["render"] = rendered.to_json()
    if not rendered.ok:
        rec["critique"] = critic.zero_score("render failed: " + "; ".join(rendered.errors[:3]))
    else:
        rec["critique"] = await critic.critique(case, png, rendered.sheet, rendered.strip, log, tags={"method": "one_shot"})
    rec["seconds"] = round(time.time() - t0, 1)
    (cdir / "critique.json").write_text(json.dumps(rec["critique"], indent=2))
    print(f'  {case["id"]:<12} overall={rec["critique"]["overall"]:.2f}  ({rec["seconds"]}s)', flush=True)
    return rec


def write_reports(run_dir: Path, results: list[dict], meta: dict):
    (run_dir / "results.json").write_text(json.dumps({"meta": meta, "results": results}, indent=2))
    keys = list(critic.RUBRIC)
    lines = [f"# Run {run_dir.name}", "", "```", json.dumps(meta, indent=2), "```", "",
             "| case | category | " + " | ".join(keys) + " | overall |",
             "|---|---|" + "---|" * (len(keys) + 1)]
    for r in results:
        s = r["critique"]["scores"]
        lines.append(f'| {r["case"]} | {r["category"]} | ' + " | ".join(f"{s[k]:.0f}" for k in keys)
                     + f' | {r["critique"]["overall"]:.2f} |')
    mean = sum(r["critique"]["overall"] for r in results) / max(1, len(results))
    lines += ["", f"**Mean overall: {mean:.2f} / 5**", ""]
    (run_dir / "summary.md").write_text("\n".join(lines))

    cards = []
    for r in results:
        cid, c = r["case"], r["critique"]
        gif = f"{cid}/render/anim.gif" if r.get("render", {}).get("ok") else None
        issues = "".join(f"<li>{html.escape(i)}</li>" for i in c.get("issues", [])[:4])
        scores = " · ".join(f"{k} {v:.0f}" for k, v in c["scores"].items())
        cards.append(f"""<div class="card"><h3>{cid} <span>{c["overall"]:.2f}</span></h3>
<div class="pair"><img src="{cid}/input.png">{f'<img src="{gif}">' if gif else '<div class="fail">no render</div>'}</div>
<p class="s">{scores}</p><ul>{issues}</ul></div>""")
    (run_dir / "index.html").write_text(f"""<!doctype html><meta charset="utf-8"><title>{run_dir.name}</title>
<style>body{{font:14px system-ui;margin:24px;background:#fafafa}}.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:16px}}
.card{{background:#fff;border:1px solid #ddd;border-radius:8px;padding:12px}}h3{{margin:0 0 8px;display:flex;justify-content:space-between}}
.pair{{display:flex;gap:8px}}.pair img,.fail{{width:200px;height:200px;border:1px solid #eee}}.fail{{display:grid;place-items:center;color:#c00}}
.s{{color:#555}}ul{{padding-left:18px;color:#333}}</style>
<h1>{run_dir.name}: mean {mean:.2f} / 5</h1><div class="grid">{"".join(cards)}</div>""")
    return mean


async def baseline(args):
    cases = load_cases(args.cases)
    run_dir = Path(args.out) / time.strftime("%Y%m%d-%H%M%S-baseline")
    run_dir.mkdir(parents=True)
    log = run_dir / "llm_calls.jsonl"
    meta = {"method": "one_shot", "gen_model": llm.GEN_MODEL, "gen_effort": llm.GEN_EFFORT,
            "critic_model": llm.CRITIC_MODEL, "critic_effort": llm.CRITIC_EFFORT,
            "cases": [c["id"] for c in cases]}
    print(f"run dir: {run_dir}")
    async with Renderer(concurrency=args.concurrency) as renderer:
        results = await asyncio.gather(*(run_case(c, renderer, run_dir, log) for c in cases))
    mean = write_reports(run_dir, results, meta)
    print(f"mean overall {mean:.2f} / 5 -> {run_dir / 'index.html'}")


async def judge(args):
    """Re-score the renders of an existing run (e.g. with a held-out judge model)
    without regenerating anything."""
    run_dir = Path(args.run_dir)
    data = json.loads((run_dir / "results.json").read_text())
    cases = {c["id"]: c for c in load_cases(None)}
    model = args.model or llm.CRITIC_MODEL
    log = run_dir / "llm_calls.jsonl"

    async def rescore(rec):
        cdir = run_dir / rec["case"]
        if not rec.get("render", {}).get("ok"):
            return rec
        rec["critique"] = await critic.critique(
            cases[rec["case"]], cdir / "input.png", cdir / "render" / "sheet.png",
            cdir / "render" / "strip.png", log, model=model, tags={"method": rec["method"], "rejudge": True})
        (cdir / "critique.json").write_text(json.dumps(rec["critique"], indent=2))
        print(f'  {rec["case"]:<12} overall={rec["critique"]["overall"]:.2f}', flush=True)
        return rec

    results = await asyncio.gather(*(rescore(r) for r in data["results"]))
    meta = {**data["meta"], "critic_model": model, "rejudged": True}
    mean = write_reports(run_dir, results, meta)
    print(f"mean overall {mean:.2f} / 5 -> {run_dir / 'index.html'}")


def main():
    p = argparse.ArgumentParser(prog="ksa")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("baseline", help="one-shot generation on the benchmark")
    b.add_argument("--cases", help="comma-separated case ids (default: all)")
    b.add_argument("--out", default=str(ROOT / "runs"))
    b.add_argument("--concurrency", type=int, default=6)
    j = sub.add_parser("judge", help="re-score an existing run's renders")
    j.add_argument("run_dir")
    j.add_argument("--model", help="judge model (default: KSA_CRITIC_MODEL)")
    args = p.parse_args()
    if args.cmd == "baseline":
        asyncio.run(baseline(args))
    elif args.cmd == "judge":
        asyncio.run(judge(args))


if __name__ == "__main__":
    main()
