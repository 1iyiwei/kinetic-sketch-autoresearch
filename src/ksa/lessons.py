"""Per-lesson credit assignment: which playbook lessons help, and which hurt?

  uv run ksa lessons --playbook playbooks/train-v1.json \\
      --baseline runs/<no-playbook runs...> --with runs/<+playbook_sel runs...> [--prune-to playbooks/x.json]

For each case, effect = (mean judge score with selected lessons) - (mean judge score
without a playbook). A lesson's effect is the mean of that over the cases it was
selected for. With few cases this is noisy evidence, so pruning only drops lessons
with a negative mean effect over at least `min_uses` cases.
"""

from __future__ import annotations

import json
import statistics as st
from collections import defaultdict
from pathlib import Path


def judged(run_dir: Path) -> dict[str, float]:
    j = sorted(run_dir.glob("judge-*.json"))
    if not j:
        return {}
    return {p["case"]: st.mean(p["overall"]) for p in json.loads(j[-1].read_text())["per_case"]}


def effects(pb: dict, baseline: list[Path], with_runs: list[Path]) -> dict:
    base = defaultdict(list)
    for d in baseline:
        for c, v in judged(d).items():
            base[c].append(v)
    case_scores, picks = defaultdict(list), defaultdict(set)
    for d in with_runs:
        scores = judged(d)
        for r in json.loads((d / "results.json").read_text())["results"]:
            if r["case"] in scores and "playbook_selected" in r:
                case_scores[r["case"]].append(scores[r["case"]])
                picks[r["case"]] |= set(r["playbook_selected"])
    case_effect = {c: st.mean(v) - st.mean(base[c]) for c, v in case_scores.items() if base.get(c)}
    per_lesson = {}
    for i, lesson in enumerate(pb["lessons"], start=1):
        used = [c for c in case_effect if i in picks[c]]
        per_lesson[i] = {"applies_to": lesson["applies_to"], "cases": used,
                         "effect": round(st.mean(case_effect[c] for c in used), 3) if used else None}
    return {"case_effect": {c: round(v, 3) for c, v in case_effect.items()},
            "picks": {c: sorted(v) for c, v in picks.items()}, "lessons": per_lesson}


def table(res: dict) -> str:
    lines = ["| Case | Lessons selected | Effect vs. no playbook |", "| --- | --- | --- |"]
    for c, e in sorted(res["case_effect"].items()):
        lines.append(f"| {c} | {', '.join(map(str, res['picks'][c])) or 'none'} | {e:+.2f} |")
    lines += ["", "| # | Lesson applies to | Used on | Mean effect |", "| --- | --- | --- | --- |"]
    for i, l in res["lessons"].items():
        eff = "—" if l["effect"] is None else f"{l['effect']:+.2f}"
        lines.append(f"| {i} | {l['applies_to']} | {', '.join(l['cases']) or '—'} | {eff} |")
    return "\n".join(lines)


def prune(pb: dict, res: dict, min_uses: int = 2) -> tuple[dict, list[int]]:
    drop = [i for i, l in res["lessons"].items()
            if l["effect"] is not None and l["effect"] < 0 and len(l["cases"]) >= min_uses]
    kept = [l for i, l in enumerate(pb["lessons"], start=1) if i not in drop]
    note = f"pruned lessons {drop} (negative mean judge effect over >= {min_uses} held-out cases)"
    return {"lessons": kept, "history": pb.get("history", []) + [{"change_note": note}]}, drop
