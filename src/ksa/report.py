"""Aggregate held-out judge results across runs into one markdown table.

  uv run ksa report runs/A runs/B ... [--cases fish,windmill] [--baseline one_shot]

Runs are grouped by method label (repeated runs of a method are averaged per case first),
restricted to the cases every method has, and compared with the baseline per case:
mean judge score, mean difference, wins / losses / ties. Only runs that have been judged
(`ksa judge`) count.
"""

from __future__ import annotations

import json
import statistics as st
from collections import defaultdict
from pathlib import Path


def judge_file(d: Path, judge_model: str | None = None) -> Path | None:
    """The run's judge-<model>.json for this judge; without one, gpt-5.4's if present, else the last."""
    if judge_model:
        f = d / f"judge-{judge_model.replace('/', '_').replace(':', '_')}.json"
        return f if f.exists() else None
    if (d / "judge-gpt-5.4.json").exists():
        return d / "judge-gpt-5.4.json"
    js = sorted(d.glob("judge-*.json"))
    return js[-1] if js else None


def method_label(meta: dict) -> str:
    """Method label, plus the generator when it is not the default OpenAI one (e.g. one_shot@Qwen3.6-35B-A3B)."""
    gen = meta.get("gen_model", "")
    return meta["method"] + (f"@{gen.split('/')[-1]}" if gen.startswith("tinker:") else "")


def collect(run_dirs: list[Path], judge_model: str | None = None) -> dict:
    """method -> case -> list of per-run judge means; plus tokens per method per run."""
    scores: dict = defaultdict(lambda: defaultdict(list))
    tokens: dict = defaultdict(list)
    for d in run_dirs:
        jf = judge_file(d, judge_model)
        if jf is None:
            continue
        method = method_label(json.loads((d / "results.json").read_text())["meta"])
        j = json.loads(jf.read_text())
        for p in j["per_case"]:
            scores[method][p["case"]].append(st.mean(p["overall"]))
        res = json.loads((d / "results.json").read_text())["results"]
        tokens[method].append({r["case"]: sum(m["input_tokens"] + m["output_tokens"] for m in r["meter"].values())
                               for r in res})
    return {"scores": scores, "tokens": tokens}


def table(run_dirs: list[Path], cases: list[str] | None = None, baseline: str | None = None,
          judge_model: str | None = None) -> str:
    data = collect(run_dirs, judge_model)
    scores = data["scores"]
    if not scores:
        return "(no judged runs)"
    shared = set.intersection(*(set(v) for v in scores.values()))
    if cases:
        shared &= set(cases)
    shared = sorted(shared)
    per_case = {m: {c: st.mean(v[c]) for c in shared} for m, v in scores.items()}
    base = baseline if baseline in per_case else next(iter(per_case))
    lines = [f"Cases ({len(shared)}): {', '.join(shared)}", "",
             f"| Method | Runs | Judge mean | vs. {base}: mean diff | wins / losses / ties | Tokens per case |",
             "| --- | --- | --- | --- | --- | --- |"]
    for m in sorted(per_case, key=lambda m: st.mean(per_case[m].values())):
        runs = max(len(scores[m][c]) for c in shared)
        mean = st.mean(per_case[m].values())
        tok = st.mean(t[c] for t in data["tokens"][m] for c in shared if c in t)
        if m == base:
            cmp = "—", "—"
        else:
            d = [per_case[m][c] - per_case[base][c] for c in shared]
            w, l = sum(x > 0.0 for x in d), sum(x < 0.0 for x in d)
            cmp = f"{st.mean(d):+.2f}", f"{w} / {l} / {len(d) - w - l}"
        lines.append(f"| {m} | {runs} | {mean:.2f} | {cmp[0]} | {cmp[1]} | {tok / 1000:.0f}K |")
    lines += ["", "| Case | " + " | ".join(per_case) + " |", "| --- |" + " --- |" * len(per_case)]
    for c in shared:
        lines.append(f"| {c} | " + " | ".join(f"{per_case[m][c]:.2f}" for m in per_case) + " |")
    return "\n".join(lines)
