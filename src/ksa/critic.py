"""Vision critic: scores a rendered animation against the input drawing and intent.

It sees the input drawing and a contact sheet of 8 evenly spaced frames with
timestamps. The same rubric serves two roles: feedback inside the research loop,
and (with a different model or prompt seed) a held-out judge for the benchmark.
"""

from __future__ import annotations

from pathlib import Path

from . import llm

RUBRIC = {
    "fidelity": "Frame #1 matches the input drawing, and the drawing's style (strokes, colors, "
                "proportions) is preserved throughout.",
    "intent": "The motion described in the intent actually happens, with the right objects doing "
              "the right things.",
    "motion": "Animation craft: timing, easing, arcs, anticipation and follow-through; plausible "
              "cartoon physics; motion reads clearly.",
    "integrity": "Objects stay whole and attached where they should be (no parts flying off, "
                 "tearing, wrong pivots, vanishing, or unintended clipping out of frame).",
}

SYSTEM = """\
You are a strict animation director reviewing a short stylized animation made from a drawing.
You see (1) the input drawing, (2) an overview sheet of 8 evenly spaced frames across the whole
animation, and (3) a strip of the first 8 consecutive frames (1/12 s apart). Each frame is labeled
with its timestamp. Use the overview for the overall story and the strip for continuity: evenly
spaced samples can alias (a symmetric rotor can look like it repeats or jumps between poses), so
do not call motion jumpy or shapes deformed unless the consecutive strip confirms it.
Judge only what is visible. Be specific: name the timestamps and the objects.

Score each criterion from 1 (failed) to 5 (excellent):
""" + "\n".join(f"- {k}: {v}" for k, v in RUBRIC.items()) + """

Reply with only a JSON object:
{"scores": {"fidelity": n, "intent": n, "motion": n, "integrity": n},
 "issues": ["<concrete problem, with frame numbers>", ...],
 "fixes": ["<concrete change to the program that would fix an issue>", ...]}
"""


SCHEMA = {
    "name": "critique",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["scores", "issues", "fixes"],
        "properties": {
            "scores": {
                "type": "object",
                "additionalProperties": False,
                "required": list(RUBRIC),
                "properties": {k: {"type": "integer", "minimum": 1, "maximum": 5} for k in RUBRIC},
            },
            "issues": {"type": "array", "items": {"type": "string"}},
            "fixes": {"type": "array", "items": {"type": "string"}},
        },
    },
}


def zero_score(reason: str) -> dict:
    return {"scores": {k: 0 for k in RUBRIC}, "overall": 0.0, "issues": [reason], "fixes": []}


async def critique(case: dict, input_png: Path, sheet_png: Path, strip_png: Path, log: Path,
                   model: str | None = None, tags: dict | None = None) -> dict:
    text = (f'Intent: {case["intent"]}\nDuration: {case["duration"]} s\n'
            "Image 1: input drawing. Image 2: overview sheet. Image 3: consecutive-frame strip.")
    raw = await llm.call(
        role="critic", model=model or llm.CRITIC_MODEL, effort=llm.CRITIC_EFFORT, system=SYSTEM,
        text=text, images=[input_png, sheet_png, strip_png], log=log,
        tags={"case": case["id"], **(tags or {})}, json_schema=SCHEMA,
    )
    try:
        out = llm.extract_json(raw)
        scores = {k: float(out["scores"][k]) for k in RUBRIC}
    except (ValueError, KeyError, TypeError) as e:
        return zero_score(f"critic reply unparseable: {e}")
    out["scores"] = scores
    out["overall"] = round(sum(scores.values()) / len(scores), 3)
    return out
