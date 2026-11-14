"""One-shot generator: sketch + intent -> animation program (HTML with ksaRender).

This is the baseline the autoresearch loop has to beat.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import llm


def anchor_text(case: dict) -> str:
    if case.get("anchor") == "end":
        return ("ANCHOR: the final frame (t=DURATION) must look exactly like the drawing: the animation "
                "builds up to it, so earlier frames, including t=0, may show only part of it or nothing.")
    return "ANCHOR: the first frame (t=0) must look exactly like the drawing: the animation starts from it."

CONTRACT = """\
Output contract (the renderer enforces it; violations score zero):
- Return ONE complete, self-contained HTML document in a single ```html code block. No external
  resources (no CDN scripts, fonts, or images).
- The stage is 512x512 CSS pixels at the top-left of the page (body margin 0, white or the
  drawing's own background).
- Define `window.ksaRender = (t) => { ... }` that draws the frame at time t seconds, for
  0 <= t <= DURATION. It must be a pure function of t: the renderer calls it with arbitrary t,
  in any order, and screenshots right after. Do not use requestAnimationFrame, setTimeout,
  CSS animations/transitions, SMIL, Date.now() or unseeded randomness.
"""

SYSTEM = """\
You are a motion designer and creative coder. You turn a static drawing into a short stylized
animation (cartoon, whiteboard, motion-graphics or logo style, not photorealism).

Principles:
- Keep the drawing's look: reuse the given SVG paths verbatim (same ids, strokes, fills) and
  animate them with transforms and attributes. Do not redraw the artwork in a different style.
  You may add a few small elements the motion needs (motion lines, a flash, dust), in the same style.
- Work out which strokes form which object from their geometry, and which point each object moves
  or turns about (a hub, a pivot, a hinge, a contact point).
- Use animation craft: easing, anticipation, follow-through, overlap, arcs, squash and stretch where
  it suits the style, and plausible cartoon physics (gravity, bounce, oscillation that decays).
- The anchor frame named in the request (the first or the last) must look exactly like the input drawing.
""" + CONTRACT


def build_prompt(case: dict, svg: str) -> str:
    return f"""\
Animate this drawing.

Intent: {case["intent"]}
Category: {case["category"]}
DURATION: {case["duration"]} seconds
{anchor_text(case)}

The drawing is attached as an image, and here is its SVG source (512x512):
```svg
{svg}
```
"""


async def one_shot(case: dict, svg_path: Path, png_path: Path, log: Path,
                   meter: dict | None = None, tags: dict | None = None) -> tuple[str | None, str]:
    """Returns (html or None, raw model text)."""
    raw = await llm.call(
        role="generator", model=llm.GEN_MODEL, effort=llm.GEN_EFFORT, system=SYSTEM,
        text=build_prompt(case, svg_path.read_text()), images=[png_path], log=log,
        tags={"case": case["id"], "method": "one_shot", **(tags or {})}, meter=meter,
    )
    return llm.extract_block(raw, "html"), raw


def build_revise_prompt(case: dict, svg: str, program: str, critique: dict, errors: list[str],
                        has_render: bool) -> str:
    issues = "\n".join(f"- {i}" for i in critique.get("issues", [])) or "- (none)"
    fixes = "\n".join(f"- {f}" for f in critique.get("fixes", [])) or "- (none)"
    errs = "\n".join(f"- {e}" for e in errors[:8]) or "- (none)"
    seen = ("Image 1 is the input drawing. Image 2 is an overview of 8 evenly spaced frames of your "
            "current program; image 3 is its first 8 consecutive frames (1/12 s apart)."
            if has_render else "Image 1 is the input drawing. Your current program did not render.")
    return f"""\
Revise your animation program. {seen}

Intent: {case["intent"]}
Category: {case["category"]}
DURATION: {case["duration"]} seconds
{anchor_text(case)}

A reviewer scored the current version (1-5): {json.dumps(critique.get("scores", {}))}
Issues found:
{issues}
Suggested fixes:
{fixes}
Render or runtime errors:
{errs}

Think about the root cause of each issue (wrong part grouping, wrong pivot, wrong direction or
physics, timing), fix those, and keep what already works. The reviewer can be wrong: if a claim is
contradicted by the frames, do not chase it. Return the complete revised HTML document.

Original drawing SVG (512x512), for reference:
```svg
{svg}
```

Current program:
```html
{program}
```
"""


async def revise(case: dict, svg_path: Path, png_path: Path, program: str, critique: dict,
                 errors: list[str], sheet: Path | None, strip: Path | None, log: Path,
                 meter: dict | None = None, tags: dict | None = None) -> tuple[str | None, str]:
    images = [png_path] + ([sheet, strip] if sheet and strip else [])
    raw = await llm.call(
        role="generator", model=llm.GEN_MODEL, effort=llm.GEN_EFFORT, system=SYSTEM,
        text=build_revise_prompt(case, svg_path.read_text(), program, critique, errors, sheet is not None),
        images=images, log=log, tags={"case": case["id"], "method": "revise", **(tags or {})}, meter=meter,
    )
    return llm.extract_block(raw, "html"), raw
