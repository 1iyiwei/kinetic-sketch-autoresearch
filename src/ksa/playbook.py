"""Playbook: lessons the system learns from its own search trees and carries to new drawings.

After the loop finishes a training case, an analyst model reads the evidence in its
search tree: what the first attempts got wrong (critic issues), the code diff from
the first-round best program to the final best one (what actually fixed it), the score
trajectory, and what is still wrong. It then rewrites the playbook: at most MAX_LESSONS
short, general lessons, merging duplicates and dropping weak ones. The generator gets
the playbook in its prompt, both for first samples and for revisions.

Lessons must transfer to new drawings, so the analyst is told never to name the case.
The playbook keeps its history (which case changed it, and how), so the learning can be
audited, and it is a plain JSON file meant to be committed and read.
"""

from __future__ import annotations

import difflib
import json
import os
import time
from pathlib import Path

from . import llm

MAX_LESSONS = 12
ANALYST_EFFORT = os.getenv("KSA_ANALYST_EFFORT", "medium")

SYSTEM = f"""\
You maintain a playbook of lessons for an agent that turns static drawings (sketches, textbook
diagrams, cartoons, logos) into short stylized animation programs (HTML with a pure ksaRender(t)).

You get the current playbook and the evidence from one finished search: what the first attempts got
wrong, the code change that raised the score, the score trajectory, and what is still wrong.
Return the updated playbook.

Rules for lessons:
- General and transferable: about kinds of objects, motions, physics, timing, rigging, pivots,
  layering, the program contract, or build-up intros. Never name the specific drawing or its ids
  (no "the fish", no "s3"); say "a hinged object", "a rotor", "a logo intro" instead.
- Actionable for a programmer writing ksaRender(t): say what to do, concretely, in one or two sentences.
- Backed by the evidence. Do not add a lesson the evidence does not support. If a search gained
  nothing, a lesson may say what did not help.
- Keep at most {MAX_LESSONS} lessons: merge duplicates, sharpen vague ones, drop the weakest.
  Keep existing lessons unless the new evidence contradicts or supersedes them.
- For each lesson give `applies_to` (a few words: which drawings or motions) and `evidence`
  (one short line: which observation supports it).
Also return `change_note`: one sentence on what you changed in this update and why.
"""

SCHEMA = {
    "name": "playbook",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["lessons", "change_note"],
        "properties": {
            "lessons": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["text", "applies_to", "evidence"],
                    "properties": {"text": {"type": "string"}, "applies_to": {"type": "string"},
                                   "evidence": {"type": "string"}},
                },
            },
            "change_note": {"type": "string"},
        },
    },
}


def empty() -> dict:
    return {"lessons": [], "history": []}


def load(path: Path | None) -> dict | None:
    if path is None:
        return None
    path = Path(path)
    return json.loads(path.read_text()) if path.exists() else empty()


def save(pb: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pb, indent=2) + "\n")


def prompt_text(pb: dict | None, only: list[int] | None = None) -> str:
    """The playbook as it appears in generator prompts ('' when there is none).
    `only`: 1-based lesson numbers to include (after selection); None means all."""
    if not pb or not pb.get("lessons"):
        return ""
    picked = [(i + 1, l) for i, l in enumerate(pb["lessons"]) if only is None or i + 1 in only]
    if not picked:
        return ""
    lines = [f"- {l['text']} (applies to: {l['applies_to']})" for _, l in picked]
    head = ("Lessons learned from earlier drawings that apply to this one:" if only is not None else
            "Lessons learned from earlier drawings. Apply the ones that fit this drawing; ignore the rest:")
    return head + "\n" + "\n".join(lines)


# ---------------------------------------------------------------- selection

SELECT_MODEL = os.getenv("KSA_SELECT_MODEL", "gpt-5.4-mini")

SELECT_SYSTEM = """\
You decide which lessons from a playbook apply to animating one specific drawing. The lessons were
learned on other drawings, so match on the kind of motion and physics the intent asks for, not on the
object's name: a lesson learned on one oscillator applies to any oscillating system, one learned on a
rolling object applies to other rolling objects, one about rigging parts to a pivot applies to anything
that turns about a pivot, one about a logo intro applies to other build-up intros.
A lesson does not apply when this animation has no such motion. Misapplied lessons make results worse
(for example, launch-shake or bounce advice applied to a steady rotor). Select every lesson whose
motion or physics this animation needs, and only those. Selecting none is fine.
Return the selected lesson numbers and one short reason for each decision you are unsure about.
"""

SELECT_SCHEMA = {
    "name": "lesson_selection",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["selected", "reasons"],
        "properties": {
            "selected": {"type": "array", "items": {"type": "integer"}},
            "reasons": {"type": "string"},
        },
    },
}


async def select(pb: dict, case: dict, png: Path, log: Path, meter: dict | None = None) -> dict:
    """Pick the lessons that apply to this drawing and intent. Returns
    {"selected": [1-based numbers], "reasons": str}."""
    if not pb or not pb.get("lessons"):
        return {"selected": [], "reasons": "empty playbook"}
    listing = "\n".join(f"{i + 1}. [{l['applies_to']}] {l['text']}" for i, l in enumerate(pb["lessons"]))
    text = (f"Drawing category: {case['category']}\nIntent: {case['intent']}\n"
            f"The drawing is attached.\n\nPlaybook:\n{listing}")
    raw = await llm.call(role="selector", model=SELECT_MODEL, effort="low", system=SELECT_SYSTEM, text=text,
                         images=[png], log=log, tags={"case": case["id"], "method": "lesson_selection"},
                         json_schema=SELECT_SCHEMA, meter=meter)
    out = llm.extract_json(raw)
    n = len(pb["lessons"])
    out["selected"] = sorted({i for i in out["selected"] if 1 <= i <= n})
    return out


def evidence(tree_path: Path) -> str:
    """Summarize one search tree for the analyst."""
    tree = json.loads(tree_path.read_text())
    nodes = tree["nodes"]
    first = max((n for n in nodes if n["round"] == 0), key=lambda n: n["score"])
    best = next(n for n in nodes if n["id"] == tree["best"])
    parts = [f"Score trajectory (best per round): {tree['best_score_by_round']}",
             f"First-round best ({first['id']}) scores {first['critique'].get('scores')}; issues:"]
    parts += [f"- {i}" for i in first["critique"].get("issues", [])[:5]]
    for n in nodes:
        if n["round"] > 0:
            parts.append(f"Revision {n['id']} (from {n['parent']}): score {n['score']:.2f} "
                         f"{'(kept as best)' if n['id'] == best['id'] else ''}")
    parts.append(f"Final best ({best['id']}) scores {best['critique'].get('scores')}; remaining issues:")
    parts += [f"- {i}" for i in best["critique"].get("issues", [])[:4]]
    if best["id"] != first["id"]:
        case_dir = tree_path.parent
        a = (case_dir / "nodes" / first["id"] / "program.html")
        b = (case_dir / "nodes" / best["id"] / "program.html")
        if a.exists() and b.exists():
            diff = list(difflib.unified_diff(a.read_text().splitlines(), b.read_text().splitlines(),
                                             "first_best", "final_best", n=1, lineterm=""))
            if len(diff) > 220:
                diff = diff[:220] + [f"... ({len(diff) - 220} more diff lines)"]
            parts.append("Code change from the first-round best to the final best program:\n" + "\n".join(diff))
    else:
        parts.append("No revision beat the first-round best.")
    return "\n".join(parts)


async def update(pb: dict, case: dict, tree_path: Path, log: Path, meter: dict | None = None) -> dict:
    current = json.dumps({"lessons": pb.get("lessons", [])}, indent=1)
    text = (f"Drawing category: {case['category']}. Intent: {case['intent']}\n"
            f"(Do not name this drawing in lessons.)\n\nCurrent playbook:\n{current}\n\n"
            f"Evidence from the finished search:\n{evidence(tree_path)}")
    raw = await llm.call(role="analyst", model=llm.GEN_MODEL, effort=ANALYST_EFFORT, system=SYSTEM, text=text,
                         log=log, tags={"case": case["id"], "method": "playbook_update"}, json_schema=SCHEMA,
                         meter=meter)
    out = llm.extract_json(raw)
    lessons = out["lessons"][:MAX_LESSONS]
    history = pb.get("history", []) + [{
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"), "case": case["id"], "change_note": out["change_note"],
        "n_lessons": len(lessons), "best_score_by_round": json.loads(tree_path.read_text())["best_score_by_round"],
    }]
    return {"lessons": lessons, "history": history}
