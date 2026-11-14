"""Command line entry point.

  uv run ksa run --method oneshot              # one-shot baseline
  uv run ksa run --method bestof --k 6         # equal-compute baseline: sample K, keep the critic's best
  uv run ksa run --method loop [--k 2 --beam 1 --children 2 --rounds 2]
  uv run ksa run ... --cases ball_ramp,fish    # subset
  uv run ksa judge runs/<run-dir> [--model gpt-5.4] [--repeats 3]

Each run writes runs/<stamp>-<method>/ with per-case search trees, results.json,
summary.md, a gallery index.html and llm_calls.jsonl (every model call).
"""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import os
import statistics
import time
from pathlib import Path

from . import critic, llm
from .render import Renderer
from .search import SearchConfig, search

ROOT = Path(__file__).resolve().parents[2]
CASES_DIR = ROOT / "benchmark" / "cases"


def load_cases(only: str | None, cases_file: str | None = None) -> list[dict]:
    path = Path(cases_file) if cases_file else CASES_DIR / "cases.json"
    cases = json.loads(path.read_text())
    for c in cases:  # absolute svg paths, so other splits (benchmark/train) work unchanged
        c["svg"] = str((path.parent / c["svg"]).resolve())
    if only:
        keep = set(only.split(","))
        cases = [c for c in cases if c["id"] in keep]
    return cases


def tokens(meter: dict) -> int:
    return sum(m["input_tokens"] + m["output_tokens"] for m in meter.values())


def gen_calls(meter: dict) -> int:
    return meter.get("generator", {}).get("calls", 0)


async def run_case(case: dict, renderer: Renderer, run_dir: Path, log: Path, cfg: SearchConfig) -> dict:
    cdir = run_dir / case["id"]
    cdir.mkdir(parents=True, exist_ok=True)
    svg = CASES_DIR / case["svg"]
    png = await renderer.rasterize_svg(svg, cdir / "input.png")
    t0 = time.time()
    rec = await search(case, svg, png, renderer, cdir, log, cfg)
    rec["seconds"] = round(time.time() - t0, 1)
    traj = " -> ".join(f"{s:.2f}" for s in rec["best_score_by_round"])
    print(f'  {case["id"]:<12} {traj:<28} nodes={rec["n_nodes"]:<3} gen_calls={gen_calls(rec["meter"]):<3} '
          f'tokens={tokens(rec["meter"]):>7}  ({rec["seconds"]}s)', flush=True)
    return rec


def rel(run_dir: Path, p: str | None) -> str | None:
    return os.path.relpath(p, run_dir) if p else None


def write_reports(run_dir: Path, results: list[dict], meta: dict) -> float:
    (run_dir / "results.json").write_text(json.dumps({"meta": meta, "results": results}, indent=2))
    keys = list(critic.RUBRIC)
    lines = [f"# Run {run_dir.name}", "", "```", json.dumps(meta, indent=2), "```", "",
             "| case | category | " + " | ".join(keys) + " | overall | by round | gen calls | tokens |",
             "|---|---|" + "---|" * (len(keys) + 4)]
    for r in results:
        s = r["critique"]["scores"]
        traj = " → ".join(f"{x:.2f}" for x in r.get("best_score_by_round", []))
        lines.append(f'| {r["case"]} | {r["category"]} | ' + " | ".join(f"{s.get(k, 0.0):.1f}" for k in keys)
                     + f' | {r["critique"]["overall"]:.2f} | {traj} | {gen_calls(r.get("meter", {}))} '
                     f'| {tokens(r.get("meter", {}))} |')
    mean = statistics.mean(r["critique"]["overall"] for r in results) if results else 0.0
    total_tokens = sum(tokens(r.get("meter", {})) for r in results)
    lines += ["", f"**Mean overall: {mean:.2f} / 5** · total tokens {total_tokens:,}", ""]
    (run_dir / "summary.md").write_text("\n".join(lines))

    cards = []
    for r in results:
        cid, c = r["case"], r["critique"]
        gif = rel(run_dir, r.get("render", {}).get("gif")) if r.get("render", {}).get("ok") else None
        issues = "".join(f"<li>{html.escape(i)}</li>" for i in c.get("issues", [])[:4])
        scores = " · ".join(f"{k} {v:.1f}" for k, v in c["scores"].items())
        traj = " → ".join(f"{x:.2f}" for x in r.get("best_score_by_round", []))
        cards.append(f"""<div class="card"><h3>{cid} <span>{c["overall"]:.2f}</span></h3>
<div class="pair"><img src="{cid}/input.png">{f'<img src="{gif}">' if gif else '<div class="fail">no render</div>'}</div>
<p class="s">{scores}<br>best by round: {traj} · node {r.get("best_node", "")} of {r.get("n_nodes", 1)}</p><ul>{issues}</ul></div>""")
    (run_dir / "index.html").write_text(f"""<!doctype html><meta charset="utf-8"><title>{run_dir.name}</title>
<style>body{{font:14px system-ui;margin:24px;background:#fafafa}}.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:16px}}
.card{{background:#fff;border:1px solid #ddd;border-radius:8px;padding:12px}}h3{{margin:0 0 8px;display:flex;justify-content:space-between}}
.pair{{display:flex;gap:8px}}.pair img,.fail{{width:200px;height:200px;border:1px solid #eee}}.fail{{display:grid;place-items:center;color:#c00}}
.s{{color:#555}}ul{{padding-left:18px;color:#333}}</style>
<h1>{run_dir.name}: mean {mean:.2f} / 5</h1><p>{html.escape(json.dumps(meta))}</p><div class="grid">{"".join(cards)}</div>""")
    return mean


def config_from(args) -> SearchConfig:
    if args.method == "oneshot":
        return SearchConfig(k=1, rounds=0)
    if args.method == "bestof":
        return SearchConfig(k=args.k, rounds=0)
    return SearchConfig(k=args.k, beam=args.beam, children=args.children, rounds=args.rounds,
                        patience=args.patience)


async def run(args):
    cases = load_cases(args.cases, args.cases_file)
    cfg = config_from(args)
    run_dir = Path(args.out) / f'{time.strftime("%Y%m%d-%H%M%S")}-{cfg.method}'
    run_dir.mkdir(parents=True)
    log = run_dir / "llm_calls.jsonl"
    meta = {"method": cfg.method, "config": cfg.__dict__, "gen_model": llm.GEN_MODEL, "gen_effort": llm.GEN_EFFORT,
            "critic_model": llm.CRITIC_MODEL, "critic_effort": llm.CRITIC_EFFORT,
            "cases": [c["id"] for c in cases], "cases_file": args.cases_file}
    print(f"run dir: {run_dir}")
    async with Renderer(concurrency=args.concurrency) as renderer:
        results = await asyncio.gather(*(run_case(c, renderer, run_dir, log, cfg) for c in cases))
    mean = write_reports(run_dir, results, meta)
    print(f"mean overall {mean:.2f} / 5 -> {run_dir / 'index.html'}")


async def judge(args):
    """Re-score the final renders of an existing run with a (held-out) judge, `repeats`
    times each, without regenerating anything. Writes judge-<model>.json next to the run."""
    run_dir = Path(args.run_dir)
    data = json.loads((run_dir / "results.json").read_text())
    cases = {c["id"]: c for c in load_cases(None, data["meta"].get("cases_file"))}
    model = args.model or llm.CRITIC_MODEL
    log = run_dir / "llm_calls.jsonl"

    async def rescore(rec):
        rd = rec.get("render", {})
        if not rd.get("ok"):
            return {"case": rec["case"], "overall": [0.0] * args.repeats}
        outs = await asyncio.gather(*(
            critic.critique(cases[rec["case"]], run_dir / rec["case"] / "input.png", Path(rd["sheet"]),
                            Path(rd["strip"]), Path(rd["frames"][-1 if cases[rec["case"]].get("anchor") == "end" else 0]), log, model=model,
                            tags={"method": rec["method"], "judge": model, "repeat": i})
            for i in range(args.repeats)))
        o = [x["overall"] for x in outs]
        print(f'  {rec["case"]:<12} {statistics.mean(o):.2f} ± {statistics.pstdev(o):.2f}  {o}', flush=True)
        return {"case": rec["case"], "overall": o, "critiques": outs}

    per_case = await asyncio.gather(*(rescore(r) for r in data["results"]))
    means = [statistics.mean(p["overall"]) for p in per_case]
    noise = statistics.mean(statistics.pstdev(p["overall"]) for p in per_case)
    summary = {"run": run_dir.name, "method": data["meta"]["method"], "judge": model, "repeats": args.repeats,
               "mean": round(statistics.mean(means), 3), "mean_within_case_sd": round(noise, 3),
               "per_case": per_case}
    out = run_dir / f'judge-{llm.slug(model)}.json'
    out.write_text(json.dumps(summary, indent=2))
    print(f"judge {model}: mean {summary['mean']:.2f} / 5, within-case sd {noise:.2f} -> {out}")


def main():
    p = argparse.ArgumentParser(prog="ksa")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run a method on the benchmark")
    r.add_argument("--method", choices=["oneshot", "bestof", "loop"], default="loop")
    r.add_argument("--k", type=int, default=2, help="initial samples (bestof: K)")
    r.add_argument("--beam", type=int, default=1)
    r.add_argument("--children", type=int, default=2)
    r.add_argument("--rounds", type=int, default=2)
    r.add_argument("--patience", type=int, default=2)
    r.add_argument("--cases", help="comma-separated case ids (default: all)")
    r.add_argument("--cases-file", help="cases.json of another split, e.g. benchmark/train/cases.json")
    r.add_argument("--out", default=str(ROOT / "runs"))
    r.add_argument("--concurrency", type=int, default=8)
    j = sub.add_parser("judge", help="re-score an existing run's final renders")
    j.add_argument("run_dir")
    j.add_argument("--model", help="judge model (default: KSA_CRITIC_MODEL)")
    j.add_argument("--repeats", type=int, default=3)
    args = p.parse_args()
    asyncio.run(run(args) if args.cmd == "run" else judge(args))


if __name__ == "__main__":
    main()
