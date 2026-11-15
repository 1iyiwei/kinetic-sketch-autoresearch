"""Side-by-side comparison page for several runs of the same cases.

  uv run ksa compare runs/<one_shot> runs/<best_of_6> runs/<loop> [-o runs/compare.html]

One row per case: the input drawing, then each method's final animation with its
held-out judge score (if `ksa judge` was run) and its in-loop critic score. The
best judge score in each row is highlighted.
"""

from __future__ import annotations

import html
import json
import os
import statistics
from pathlib import Path

from .paths import resolve


def load_run(run_dir: Path) -> dict:
    data = json.loads((run_dir / "results.json").read_text())
    judges = sorted(run_dir.glob("judge-*.json"))
    judge = json.loads(judges[-1].read_text()) if judges else None
    jmap = {p["case"]: statistics.mean(p["overall"]) for p in judge["per_case"]} if judge else {}
    return {"dir": run_dir, "method": data["meta"]["method"], "results": {r["case"]: r for r in data["results"]},
            "judge": jmap, "judge_model": judge["judge"] if judge else None}


def write_compare(run_dirs: list[Path], out: Path, title: str = "Method comparison", note: str = "") -> Path:
    runs = [load_run(Path(d)) for d in run_dirs]
    cases = list(runs[0]["results"])
    base = out.parent

    def rel(p):
        return html.escape(os.path.relpath(p, base))

    head = "".join(f"<th>{html.escape(r['method'])}</th>" for r in runs)
    means = "".join(
        f"<td class='mean'>judge {statistics.mean(r['judge'].values()):.2f}</td>" if r["judge"] else "<td></td>"
        for r in runs)
    rows = []
    for c in cases:
        best = max((r["judge"].get(c, -1) for r in runs), default=-1)
        first = runs[0]["results"][c]
        cells = [f"<td><img src='{rel(runs[0]['dir'] / c / 'input.png')}'><div>{html.escape(c)}</div>"
                 f"<div class='cat'>{html.escape(first['category'])}</div></td>"]
        for r in runs:
            rec = r["results"][c]
            rd = rec.get("render", {})
            img = f"<img src='{rel(resolve(rd['gif'], r['dir']))}'>" if rd.get("ok") else "<div class='fail'>no render</div>"
            j = r["judge"].get(c)
            jtxt = f"judge <b>{j:.2f}</b>" if j is not None else ""
            win = " win" if j is not None and j == best else ""
            traj = rec.get("best_score_by_round", [])
            ttxt = f"<div class='traj'>rounds {' → '.join(f'{x:.2f}' for x in traj)}</div>" if len(traj) > 1 else ""
            cells.append(f"<td class='m{win}'>{img}<div>{jtxt} · critic {rec['critique']['overall']:.2f}</div>{ttxt}</td>")
        rows.append(f"<tr>{''.join(cells)}</tr>")
    jm = next((r["judge_model"] for r in runs if r["judge_model"]), None)
    out.write_text(f"""<!doctype html><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>body{{font:14px system-ui;margin:24px;background:#fafafa;color:#222}}table{{border-collapse:collapse}}
th,td{{padding:8px;text-align:center;vertical-align:top;border-bottom:1px solid #ddd}}img{{width:200px;height:200px;border:1px solid #eee;background:#fff}}
.win{{background:#e6f4ea}}.mean{{font-weight:600}}.cat,.traj{{color:#777;font-size:12px}}.fail{{width:200px;height:200px;display:grid;place-items:center;color:#c00}}</style>
<h1>{html.escape(title)}</h1><p>{html.escape(note)}</p><p>Held-out judge: {html.escape(jm or "none")} (mean of repeats). Green = best judge score in the row.</p>
<table><tr><th>input</th>{head}</tr><tr><td></td>{means}</tr>{''.join(rows)}</table>""")
    return out
