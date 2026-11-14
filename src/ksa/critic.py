"""Hybrid critic: measured checks plus a vision model, scoring a rendered animation
against the input drawing and its intent.

What can be measured is measured. Fidelity (does frame 0 match the input drawing?)
is an ink-overlap F1 between the input and the first frame. A vision model asked
to compare them hallucinated "the fish is smaller and shifted" on frames that were
pixel-identical to the input, and the generator then chased those phantom issues.

What needs judgment goes to the vision model: intent, motion craft and integrity.
It sees the input, an overview sheet of 8 evenly spaced frames, and a strip of 8
consecutive frames (evenly spaced samples alias on fast or symmetric motion).

The same critic serves inside the loop and, with a different model and repeats,
as the held-out judge.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageFilter

from . import llm

RUBRIC = {
    "fidelity": "(measured, not judged) the anchor frame (first, or last for build-up intros) matches the input drawing: ink-overlap F1 mapped to 1-5.",
    "intent": "The motion described in the intent actually happens, with the right objects doing "
              "the right things.",
    "motion": "Animation craft: timing, easing, arcs, anticipation and follow-through; plausible "
              "cartoon physics; motion reads clearly; the drawing's style is kept while moving.",
    "integrity": "Objects stay whole and attached where they should be (no parts flying off, "
                 "tearing, wrong pivots, vanishing, or unintended clipping out of frame).",
}
JUDGED = ["intent", "motion", "integrity"]

SYSTEM = """\
You are a strict animation director reviewing a short stylized animation made from a drawing.
You see (1) the input drawing, (2) an overview sheet of 8 evenly spaced frames across the whole
animation, and (3) a strip of the first 8 consecutive frames (1/12 s apart). Each frame is labeled
with its timestamp. Frames in the sheets are shown at half size; that is not a change in scale.
Use the overview for the overall story and the strip for continuity: evenly spaced samples can
alias (a symmetric rotor can look like it repeats or jumps between poses), so do not call motion
jumpy or shapes deformed unless the consecutive strip confirms it.

Whether the anchor frame (the first frame, or the last for build-up intros) matches the input drawing is measured separately and given to you; do not
re-judge it. Focus on the motion. Judge only what is visible. Be specific: name the timestamps and
the objects.

Score each criterion from 1 (failed) to 5 (excellent):
""" + "\n".join(f"- {k}: {RUBRIC[k]}" for k in JUDGED) + """

Reply with a JSON object: {"scores": {...}, "issues": [...], "fixes": [...]}, where issues are concrete
problems with timestamps and fixes are concrete changes to the program that would fix them.
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
                "required": JUDGED,
                "properties": {k: {"type": "integer", "minimum": 1, "maximum": 5} for k in JUDGED},
            },
            "issues": {"type": "array", "items": {"type": "string"}},
            "fixes": {"type": "array", "items": {"type": "string"}},
        },
    },
}


def zero_score(reason: str) -> dict:
    return {"scores": {k: 0.0 for k in RUBRIC}, "overall": 0.0, "issues": [reason], "fixes": [],
            "measured": {}}


def _ink(img: Image.Image) -> Image.Image:
    """Mask of pixels that differ from the background (taken from the corner pixel)."""
    rgb = img.convert("RGB")
    bg = Image.new("RGB", rgb.size, rgb.getpixel((2, 2)))
    diff = ImageChops.difference(rgb, bg).convert("L")
    return diff.point(lambda v: 255 if v > 40 else 0)


def fidelity_f1(input_png: Path, frame0_png: Path, tol: int = 2) -> float:
    """Ink-overlap F1 between input and the anchor frame, tolerating `tol` px misalignment."""
    a, b = _ink(Image.open(input_png)), _ink(Image.open(frame0_png).resize(Image.open(input_png).size))
    size = 2 * tol + 1
    a_d, b_d = a.filter(ImageFilter.MaxFilter(size)), b.filter(ImageFilter.MaxFilter(size))

    def count(m):
        return sum(1 for v in m.getdata() if v)

    na, nb = count(a), count(b)
    if na == 0 or nb == 0:
        return 0.0
    recall = count(ImageChops.multiply(a, b_d)) / na
    precision = count(ImageChops.multiply(b, a_d)) / nb
    return 0.0 if recall + precision == 0 else 2 * recall * precision / (recall + precision)


async def critique(case: dict, input_png: Path, sheet_png: Path, strip_png: Path, anchor_png: Path,
                   log: Path, model: str | None = None, tags: dict | None = None,
                   meter: dict | None = None) -> dict:
    f1 = fidelity_f1(input_png, anchor_png)
    which = "last" if case.get("anchor") == "end" else "first"
    fid_score = round(1 + 4 * f1, 2)
    fid_note = (f"Measured: the {which} frame (the anchor) matches the input drawing with ink-overlap F1 = {f1:.2f} "
                f"(1.00 = identical).")
    text = (f'Intent: {case["intent"]}\nDuration: {case["duration"]} s\n{fid_note}\n'
            "Image 1: input drawing. Image 2: overview sheet. Image 3: consecutive-frame strip.")
    raw = await llm.call(
        role="critic", model=model or llm.CRITIC_MODEL, effort=llm.CRITIC_EFFORT, system=SYSTEM,
        text=text, images=[input_png, sheet_png, strip_png], log=log,
        tags={"case": case["id"], **(tags or {})}, json_schema=SCHEMA, meter=meter,
    )
    try:
        out = llm.extract_json(raw)
        scores = {"fidelity": fid_score, **{k: float(out["scores"][k]) for k in JUDGED}}
    except (ValueError, KeyError, TypeError) as e:
        return zero_score(f"critic reply unparseable: {e}")
    if f1 < 0.9:  # make a real fidelity problem visible to the reviser
        out["issues"] = [f"The {which} frame does not match the input drawing (ink-overlap F1 {f1:.2f}): "
                         f"the {which} frame must reproduce the drawing exactly."] + out["issues"]
    out["scores"] = scores
    out["measured"] = {"fidelity_f1": round(f1, 3)}
    out["overall"] = round(sum(scores.values()) / len(scores), 3)
    return out
