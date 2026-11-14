"""One-shot generator: sketch + intent -> animation program (HTML with ksaRender).

This is the baseline the autoresearch loop has to beat.
"""

from __future__ import annotations

from pathlib import Path

from . import llm

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
- Frame 0 (t=0) must look like the input drawing.
""" + CONTRACT


def build_prompt(case: dict, svg: str) -> str:
    return f"""\
Animate this drawing.

Intent: {case["intent"]}
Category: {case["category"]}
DURATION: {case["duration"]} seconds

The drawing is attached as an image, and here is its SVG source (512x512):
```svg
{svg}
```
"""


async def one_shot(case: dict, svg_path: Path, png_path: Path, log: Path) -> tuple[str | None, str]:
    """Returns (html or None, raw model text)."""
    raw = await llm.call(
        role="generator", model=llm.GEN_MODEL, effort=llm.GEN_EFFORT, system=SYSTEM,
        text=build_prompt(case, svg_path.read_text()), images=[png_path], log=log,
        tags={"case": case["id"], "method": "one_shot"},
    )
    return llm.extract_block(raw, "html"), raw
