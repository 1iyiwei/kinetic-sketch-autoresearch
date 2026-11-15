"""Command line entry point.

  uv run ksa run --method oneshot              # one-shot baseline
  uv run ksa run --method bestof --k 6         # equal-compute baseline: sample K, keep the critic's best
  uv run ksa run --method loop [--k 2 --beam 1 --children 2 --rounds 2]
  uv run ksa run ... --cases ball_ramp,fish    # subset
  uv run ksa run ... --split test --playbook playbooks/train.json   # held-out cases, with learned lessons
  uv run ksa learn --split train --out playbooks/train.json          # learn a playbook, case by case
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
from . import playbook as pbk
from .paths import relativize, resolve
from .render import Renderer
from .search import SearchConfig, search

ROOT = Path(__file__).resolve().parents[2]
CASES_DIR = ROOT / "benchmark" / "cases"


def load_cases(only: str | None, split: str | None = None) -> list[dict]:
    cases = json.loads((CASES_DIR / "cases.json").read_text())
    if split:
        cases = [c for c in cases if c.get("split") == split]
    if only:  # keep the order given (it is the learning order for `ksa learn`)
        by_id = {c["id"]: c for c in cases}
        cases = [by_id[i] for i in only.split(",") if i in by_id]
    return cases


def tokens(meter: dict) -> int:
    return sum(m["input_tokens"] + m["output_tokens"] for m in meter.values())


def gen_calls(meter: dict) -> int:
    return meter.get("generator", {}).get("calls", 0)


async def run_case(case: dict, renderer: Renderer, run_dir: Path, log: Path, cfg: SearchConfig,
                   pb: dict | None = None, lessons: str = "all", label: str | None = None) -> dict:
    """lessons: "all" gives the generator every playbook lesson; "select" first picks the
    lessons that apply to this drawing and intent."""
    cdir = run_dir / case["id"]
    cdir.mkdir(parents=True, exist_ok=True)
    svg = Path(case["svg_path"]) if "svg_path" in case else CASES_DIR / case["svg"]
    png = await renderer.rasterize_svg(svg, cdir / "input.png")
    t0 = time.time()
    sel_meter: dict = {}
    selection = None
    if pb and pb.get("lessons") and lessons == "select":
        selection = await pbk.select(pb, case, png, log, meter=sel_meter)
        (cdir / "playbook_selected.json").write_text(json.dumps(
            {**selection, "lessons": [pb["lessons"][i - 1] for i in selection["selected"]]}, indent=2))
        text = pbk.prompt_text(pb, only=selection["selected"])
    else:
        text = pbk.prompt_text(pb)
    rec = await search(case, svg, png, renderer, cdir, log, cfg, playbook=text)
    rec["meter"].update(sel_meter)
    if selection is not None:
        rec["playbook_selected"] = selection["selected"]
    if label:
        rec["method"] = label
    rec["seconds"] = round(time.time() - t0, 1)
    traj = " -> ".join(f"{s:.2f}" for s in rec["best_score_by_round"])
    print(f'  {case["id"]:<12} {traj:<28} nodes={rec["n_nodes"]:<3} gen_calls={gen_calls(rec["meter"]):<3} '
          f'tokens={tokens(rec["meter"]):>7}  ({rec["seconds"]}s)', flush=True)
    return rec


def rel(run_dir: Path, p: str | None) -> str | None:
    return os.path.relpath(p, run_dir) if p else None


def write_reports(run_dir: Path, results: list[dict], meta: dict) -> float:
    (run_dir / "results.json").write_text(
        json.dumps(relativize({"meta": meta, "results": results}, run_dir), indent=2))
    keys = list(critic.RUBRIC)
    lines = [f"# Run {run_dir.name}", "", "```", json.dumps(meta, indent=2), "```", "",
             "| case | category | " + " | ".join(keys) + " | overall | by round | gen calls | tokens |",
             "|---|---|" + "---|" * (len(keys) + 4)]
    for r in results:
        s = r["critique"]["scores"]
        traj = " → ".join(f"{x:.2f}" for x in r.get("best_score_by_round", []))
        lines.append(f'| {r["case"]} | {r["category"]} | ' + " | ".join(f"{s[k]:.1f}" for k in keys)
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


def run_meta(label: str, cfg: SearchConfig, cases: list[dict], **extra) -> dict:
    return {"method": label, "config": cfg.__dict__, "gen_model": llm.GEN_MODEL, "gen_effort": llm.GEN_EFFORT,
            "critic_model": llm.CRITIC_MODEL, "critic_effort": llm.CRITIC_EFFORT,
            "cases": [c["id"] for c in cases], **extra}


async def run(args):
    cases = load_cases(args.cases, args.split)
    cfg = config_from(args)
    cfg.verbose = args.verbose
    pb = pbk.load(Path(args.playbook)) if args.playbook else None
    label = cfg.method + (f"+{Path(args.playbook).stem}_{args.lessons}" if pb else "")  # e.g. one_shot+train-v2_select
    run_dir = Path(args.out).resolve() / f'{time.strftime("%Y%m%d-%H%M%S")}-{label}'
    run_dir.mkdir(parents=True)
    log = run_dir / "llm_calls.jsonl"
    meta = run_meta(label, cfg, cases, split=args.split, playbook=args.playbook, lessons=args.lessons,
                    playbook_lessons=len(pb["lessons"]) if pb else 0)
    if pb:
        (run_dir / "playbook_used.json").write_text(json.dumps(pb, indent=2))
    print(f"run dir: {run_dir}")
    async with Renderer(concurrency=args.concurrency) as renderer:
        results = await asyncio.gather(*(run_case(c, renderer, run_dir, log, cfg, pb, args.lessons, label)
                                         for c in cases))
    mean = write_reports(run_dir, results, meta)
    print(f"mean overall {mean:.2f} / 5 -> {run_dir / 'index.html'}")


async def learn(args):
    """Learn a playbook: run the loop on each case in order, and after each one let the
    analyst update the playbook from that case's search tree. Later cases see the lessons
    from earlier ones. Saves the playbook after every case, so it can be inspected live."""
    cases = load_cases(args.cases, args.split)
    cfg = config_from(args)
    out = Path(args.out_playbook)
    pb = pbk.load(out) if args.resume else pbk.empty()
    label = f"learn_{cfg.method}" + ("_sel" if args.lessons == "select" else "")
    run_dir = Path(args.out).resolve() / f'{time.strftime("%Y%m%d-%H%M%S")}-{label}'
    run_dir.mkdir(parents=True)
    log = run_dir / "llm_calls.jsonl"
    print(f"run dir: {run_dir}\nplaybook: {out}")
    results = []
    async with Renderer(concurrency=args.concurrency) as renderer:
        for case in cases:
            rec = await run_case(case, renderer, run_dir, log, cfg, pb, args.lessons, label)
            rec["playbook_lessons_before"] = len(pb["lessons"])
            results.append(rec)
            pb = await pbk.update(pb, case, run_dir / case["id"] / "tree.json", log, meter=rec["meter"])
            pbk.save(pb, out)
            print(f'    playbook: {len(pb["lessons"])} lessons; {pb["history"][-1]["change_note"]}', flush=True)
    (run_dir / "playbook_learned.json").write_text(json.dumps(pb, indent=2))
    mean = write_reports(run_dir, results, run_meta(label, cfg, cases, split=args.split, playbook_out=str(out)))
    print(f"mean overall {mean:.2f} / 5 (scores while learning) -> {out}")


async def animate(args):
    """Animate any SVG (for example one saved from tools/draw.html) with the loop, and open the result."""
    import re
    import shutil
    import subprocess
    svg = Path(args.svg).expanduser().resolve()
    intent = args.intent
    if not intent:  # tools/draw.html stores the intent in <desc>
        m = re.search(r"<desc>(.*?)</desc>", svg.read_text(), re.S)
        intent = html.unescape(m.group(1).strip()) if m else None
    if not intent:
        raise SystemExit("No intent: pass it as the second argument, or type it in the drawing page before saving.")
    cfg = config_from(args)
    cfg.verbose = True
    pb = pbk.load(Path(args.playbook)) if args.playbook else None
    label = cfg.method + (f"+{Path(args.playbook).stem}_{args.lessons}" if pb else "")
    run_dir = Path(args.out).resolve() / f'{time.strftime("%Y%m%d-%H%M%S")}-{svg.stem}'
    run_dir.mkdir(parents=True)
    shutil.copy(svg, run_dir / svg.name)
    case = {"id": svg.stem, "category": args.category, "svg": svg.name, "svg_path": str(run_dir / svg.name),
            "intent": intent, "duration": args.duration, "anchor": args.anchor}
    print(f"animating {svg.name}: {intent}\nrun dir: {run_dir}", flush=True)
    async with Renderer(concurrency=args.concurrency) as renderer:
        rec = await run_case(case, renderer, run_dir, run_dir / "llm_calls.jsonl", cfg, pb, args.lessons, label)
    write_reports(run_dir, [rec], run_meta(label, cfg, [case], playbook=args.playbook, intent=intent))
    gif = resolve(rec["render"]["gif"], run_dir) if rec.get("render", {}).get("ok") else None
    print(f"best {rec['critique']['overall']:.2f} / 5 -> {run_dir / 'index.html'}")
    if gif and not args.no_open:
        subprocess.run(["open", str(run_dir / "index.html")], check=False)


async def judge(args):
    """Re-score the final renders of an existing run with a (held-out) judge, `repeats`
    times each, without regenerating anything. Writes judge-<model>.json next to the run."""
    run_dir = Path(args.run_dir)
    data = json.loads((run_dir / "results.json").read_text())
    cases = {c["id"]: c for c in load_cases(None)}
    model = args.model or llm.CRITIC_MODEL
    log = run_dir / "llm_calls.jsonl"

    async def rescore(rec):
        rd = rec.get("render", {})
        if not rd.get("ok"):
            return {"case": rec["case"], "overall": [0.0] * args.repeats}
        outs = await asyncio.gather(*(
            critic.critique(cases[rec["case"]], run_dir / rec["case"] / "input.png", resolve(rd["sheet"], run_dir),
                            resolve(rd["strip"], run_dir),
                            resolve(rd["frames"][-1 if cases[rec["case"]].get("anchor") == "end" else 0], run_dir),
                            log, model=model,
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
    out = run_dir / f'judge-{model.replace("/", "_").replace(":", "_")}.json'
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
    r.add_argument("--out", default=str(ROOT / "runs"))
    r.add_argument("--concurrency", type=int, default=8)
    r.add_argument("--verbose", action="store_true", help="print the best score after each round")
    for sp in (r,):
        sp.add_argument("--split", choices=["train", "val", "test", "complex"], help="only cases in this split")
        sp.add_argument("--playbook", help="playbook JSON whose lessons the generator gets")
        sp.add_argument("--lessons", choices=["all", "select"], default="select",
                        help="give every lesson, or only those selected for each drawing (default)")
    lp = sub.add_parser("learn", help="learn a playbook from loop runs, case by case")
    lp.add_argument("--split", choices=["train", "val", "test", "complex"], default="train")
    lp.add_argument("--cases", help="comma-separated case ids, in learning order (default: the split)")
    lp.add_argument("--out-playbook", default=str(ROOT / "playbooks" / "train.json"))
    lp.add_argument("--resume", action="store_true", help="start from the existing playbook file")
    lp.add_argument("--lessons", choices=["all", "select"], default="select")
    lp.add_argument("--method", default="loop", choices=["loop"])
    lp.add_argument("--k", type=int, default=2)
    lp.add_argument("--beam", type=int, default=1)
    lp.add_argument("--children", type=int, default=2)
    lp.add_argument("--rounds", type=int, default=2)
    lp.add_argument("--patience", type=int, default=2)
    lp.add_argument("--out", default=str(ROOT / "runs"))
    lp.add_argument("--concurrency", type=int, default=8)
    an = sub.add_parser("animate", help="animate any SVG drawing with the loop and open the result")
    an.add_argument("svg")
    an.add_argument("intent", nargs="?", help="what should happen (default: the SVG's <desc>)")
    an.add_argument("--method", choices=["oneshot", "bestof", "loop"], default="loop")
    an.add_argument("--k", type=int, default=2)
    an.add_argument("--beam", type=int, default=1)
    an.add_argument("--children", type=int, default=2)
    an.add_argument("--rounds", type=int, default=2)
    an.add_argument("--patience", type=int, default=2)
    an.add_argument("--playbook", help="playbook JSON (lessons are selected for this drawing)")
    an.add_argument("--lessons", choices=["all", "select"], default="select")
    an.add_argument("--category", default="sketch", choices=["sketch", "diagram", "cartoon", "logo"])
    an.add_argument("--anchor", default="start", choices=["start", "end"],
                    help="which frame must look like the drawing: start, or end for build-up intros")
    an.add_argument("--duration", type=float, default=4.0)
    an.add_argument("--out", default=str(ROOT / "runs" / "animate"))
    an.add_argument("--concurrency", type=int, default=8)
    an.add_argument("--no-open", action="store_true")
    j = sub.add_parser("judge", help="re-score an existing run's final renders")
    j.add_argument("run_dir")
    j.add_argument("--model", help="judge model (default: KSA_CRITIC_MODEL)")
    j.add_argument("--repeats", type=int, default=3)
    c = sub.add_parser("compare", help="side-by-side page for several runs")
    c.add_argument("run_dirs", nargs="+")
    c.add_argument("-o", "--out", default=str(ROOT / "runs" / "compare.html"))
    c.add_argument("--title", default="Method comparison")
    c.add_argument("--note", default="")
    rp = sub.add_parser("report", help="markdown table of judged runs, grouped by method")
    rp.add_argument("run_dirs", nargs="+")
    rp.add_argument("--cases", help="restrict to these case ids")
    rp.add_argument("--split", choices=["train", "val", "test", "complex"], help="restrict to cases in this split")
    rp.add_argument("--baseline", default="one_shot")
    rp.add_argument("--judge", help="judge model whose scores to use (default gpt-5.4 when present)")
    ls = sub.add_parser("lessons", help="per-lesson effect on judged runs; optionally prune")
    ls.add_argument("--playbook", required=True)
    ls.add_argument("--baseline", nargs="+", required=True, help="judged runs without a playbook")
    ls.add_argument("--with", dest="with_runs", nargs="+", required=True, help="judged runs with selected lessons")
    ls.add_argument("--prune-to", help="write a playbook without lessons whose mean effect is negative")
    ls.add_argument("--min-uses", type=int, default=2)
    ex = sub.add_parser("export", help="copy final programs of runs into results/<name>, playable")
    ex.add_argument("run_dirs", nargs="+", help="run folders; append =label to rename a method")
    ex.add_argument("--name", required=True)
    ex.add_argument("--cases", help="only these case ids")
    ex.add_argument("--judge", help="judge model whose scores to show (default gpt-5.4 when present)")
    et = sub.add_parser("export-tree", help="copy every candidate of one search into results/<name>, playable")
    et.add_argument("run_dir")
    et.add_argument("case")
    et.add_argument("--name", required=True)
    sub.add_parser("results-pages", help="rebuild the HTML pages and prompt files in results/")
    args = p.parse_args()
    if args.cmd in ("export", "export-tree"):
        from . import export as exp
        by_id = {c["id"]: c for c in load_cases(None)}
        out = ROOT / "results" / args.name
        if args.cmd == "export":
            only = set(args.cases.split(",")) if args.cases else None
            print(exp.export_runs(args.run_dirs, out, by_id, CASES_DIR, only, args.judge))
        else:
            print(exp.export_tree(Path(args.run_dir), args.case, out, by_id, CASES_DIR))
        exp.write_pages(ROOT / "results", by_id)
        return
    if args.cmd == "results-pages":
        from . import export as exp
        for f in exp.write_pages(ROOT / "results", {c["id"]: c for c in load_cases(None)}):
            print(f)
        return
    if args.cmd == "lessons":
        from . import lessons as lsn
        pb = pbk.load(Path(args.playbook))
        res = lsn.effects(pb, [Path(d) for d in args.baseline], [Path(d) for d in args.with_runs])
        print(lsn.table(res))
        if args.prune_to:
            pruned, drop = lsn.prune(pb, res, args.min_uses)
            pbk.save(pruned, Path(args.prune_to))
            print(f"\ndropped {drop or 'nothing'}; {len(pruned['lessons'])} lessons -> {args.prune_to}")
        return
    if args.cmd == "compare":
        from .compare import write_compare
        print(write_compare([Path(d) for d in args.run_dirs], Path(args.out), args.title, args.note))
        return
    if args.cmd == "report":
        from .report import table
        keep = [c["id"] for c in load_cases(args.cases, args.split)] if (args.cases or args.split) else None
        print(table([Path(d) for d in args.run_dirs], keep, args.baseline, args.judge))
        return
    asyncio.run({"run": run, "learn": learn, "judge": judge, "animate": animate}[args.cmd](args))


if __name__ == "__main__":
    main()
