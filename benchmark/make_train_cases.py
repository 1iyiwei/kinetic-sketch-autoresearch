"""Generate a training split of drawings for distillation, in the same style as the benchmark.

An LLM writes scene specs (geometry + intent); this script renders them with the same
hand-drawn stroke and flat-logo writers as make_cases.py, so train drawings look like the
benchmark but never reuse its subjects. The 10 benchmark cases stay held out.

Run:  uv run python benchmark/make_train_cases.py [--per-call 5] [--out benchmark/train]
"""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from make_cases import CASES, INK, SIZE, Logo, Sketch, arc, circle, line, polyline  # noqa: E402

from ksa import llm  # noqa: E402

DOMAINS = [
    "playground and sports", "kitchen and cooking", "weather and seasons", "cars, trains and boats",
    "farm and wild animals", "school physics lab", "gears, levers and machines", "space and astronomy",
    "ocean and beach", "music and instruments", "office and desk objects", "garden and plants",
    "city street", "toys and games", "workshop tools",
]
CATEGORIES = {
    "sketch": "a loose hand-drawn marker sketch of objects in a simple scene (strokes only)",
    "diagram": "a clean textbook-style diagram of a mechanism or physical process (strokes only; "
               "dashed strokes allowed for guides)",
    "cartoon": "a simple cartoon character or creature doing something (strokes only)",
    "logo": "a flat, filled vector logo mark with 2-6 solid shapes (shapes only, no strokes)",
}
HELD_OUT = "; ".join(f"{cid} ({intent})" for cid, _cat, _fn, intent in CASES)

STROKE = {
    "type": "object", "additionalProperties": False,
    "required": ["kind", "pts", "width", "color", "dashed"],
    "properties": {
        "kind": {"type": "string", "enum": ["line", "arc", "circle", "polyline"]},
        "pts": {"type": "array", "items": {"type": "number"}},
        "width": {"type": "number"}, "color": {"type": "string"}, "dashed": {"type": "boolean"},
    },
}
SHAPE = {
    "type": "object", "additionalProperties": False, "required": ["tag", "attrs"],
    "properties": {
        "tag": {"type": "string", "enum": ["circle", "ellipse", "rect", "polygon", "path"]},
        "attrs": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["name", "value"],
            "properties": {"name": {"type": "string"}, "value": {"type": "string"}}}},
    },
}
SCENE = {
    "type": "object", "additionalProperties": False,
    "required": ["slug", "intent", "anchor", "background", "strokes", "shapes"],
    "properties": {
        "slug": {"type": "string"}, "intent": {"type": "string"},
        "anchor": {"type": "string", "enum": ["start", "end"]}, "background": {"type": "string"},
        "strokes": {"type": "array", "items": STROKE}, "shapes": {"type": "array", "items": SHAPE},
    },
}
SCHEMA = {"name": "scenes", "schema": {
    "type": "object", "additionalProperties": False, "required": ["scenes"],
    "properties": {"scenes": {"type": "array", "items": SCENE}}}}

SYSTEM = f"""\
You design input drawings for an animation benchmark. Each drawing is a 512x512 canvas plus a one-
sentence animation intent. Write geometry, not SVG.

Stroke kinds (coordinates in pixels, origin top-left, keep everything inside 20..492):
- line: pts=[x0,y0,x1,y1]
- arc: pts=[cx,cy,r,start_deg,end_deg] (degrees, clockwise from +x since y points down)
- circle: pts=[cx,cy,r]
- polyline: pts=[x0,y0,x1,y1,x2,y2,...] (at least 2 points)
Strokes: width 3-6, color "{INK}" unless color matters, dashed only for guide lines.
Logo shapes: SVG element tag + attributes as name/value strings (e.g. cx, cy, r, fill, points, d,
transform). Use 2-4 flat colors.

Rules:
- Sketch, diagram and cartoon scenes use 4-20 strokes and NO shapes. Logo scenes use 2-8 shapes and
  NO strokes, background "#ffffff" or a flat color.
- Each object must be recognisable from geometry alone, with clear parts that can move (a pivot, a hub,
  a limb, a lid).
- Intents describe 3-4 seconds of stylized motion in one or two sentences, like a motion designer's
  brief (what moves, how, physics or easing). anchor="end" only for build-up intros where the drawing
  is the final frame; otherwise "start".
- slug: short snake_case name, unique.
- Do NOT reuse these held-out subjects or close variants: {HELD_OUT}.
"""


def to_points(kind: str, p: list[float]):
    if kind == "line" and len(p) >= 4:
        return line(*p[:4])
    if kind == "arc" and len(p) >= 5:
        return arc(p[0], p[1], p[2], math.radians(p[3]), math.radians(p[4]))
    if kind == "circle" and len(p) >= 3:
        return circle(*p[:3])
    if kind == "polyline" and len(p) >= 4:
        return polyline(*zip(p[0::2], p[1::2]))
    return None


def render(scene: dict, category: str, seed: int) -> str | None:
    if category == "logo":
        if not 2 <= len(scene["shapes"]) <= 12:
            return None
        logo = Logo(background=html.escape(scene["background"] or "#ffffff", quote=True))
        for s in scene["shapes"]:
            attrs = {a["name"]: html.escape(a["value"], quote=True) for a in s["attrs"]
                     if a["name"].replace("-", "").isalpha() and a["name"] != "id"}
            logo.add(s["tag"], **attrs)
        return logo.svg()
    if not 3 <= len(scene["strokes"]) <= 30:
        return None
    sk = Sketch(seed)
    for s in scene["strokes"]:
        pts = to_points(s["kind"], s["pts"])
        if not pts or not all(-20 <= c <= SIZE + 20 for xy in pts for c in xy):
            continue
        sk.stroke(pts, width=max(2.0, min(8.0, s["width"])), color=html.escape(s["color"] or INK, quote=True),
                  dash="10 8" if s["dashed"] else None)
    return sk.svg() if len(sk.items) >= 3 else None


async def batch(category: str, domain: str, n: int, log: Path) -> tuple[str, str, list[dict]]:
    text = (f"Design {n} different drawings of category '{category}': {CATEGORIES[category]}. "
            f"Theme: {domain}. Vary subjects, layouts and kinds of motion.")
    try:
        raw = await llm.call(role="casegen", model=llm.GEN_MODEL, effort="low", system=SYSTEM, text=text,
                             log=log, tags={"category": category, "domain": domain}, json_schema=SCHEMA)
        return category, domain, json.loads(raw)["scenes"]
    except llm.FatalAPIError:
        raise
    except Exception as e:  # noqa: BLE001 - one failed batch should not sink the split
        print(f"  {category}/{domain}: failed ({e})", flush=True)
        return category, domain, []


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-call", type=int, default=5)
    ap.add_argument("--domains", type=int, default=len(DOMAINS))
    ap.add_argument("--out", default=str(Path(__file__).parent / "train"))
    ap.add_argument("--concurrency", type=int, default=8)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    log = out / "casegen_calls.jsonl"
    held_out = {cid for cid, *_ in CASES}
    sem = asyncio.Semaphore(args.concurrency)

    async def limited(cat, dom):
        async with sem:
            return await batch(cat, dom, args.per_call, log)

    jobs = [limited(c, d) for c in CATEGORIES for d in DOMAINS[: args.domains]]
    manifest, seen = [], set()
    for category, domain, scenes in await asyncio.gather(*jobs):
        for scene in scenes:
            slug = "".join(ch for ch in scene["slug"].lower() if ch.isalnum() or ch == "_")[:40] or "scene"
            cid = f"t_{category}_{slug}"
            if cid in seen or slug in held_out:
                continue
            svg = render(scene, category, seed=len(manifest) + 1000)
            if svg is None:
                continue
            seen.add(cid)
            (out / f"{cid}.svg").write_text(svg)
            manifest.append({"id": cid, "category": category, "svg": f"{cid}.svg", "intent": scene["intent"],
                             "duration": 4.0, "anchor": scene["anchor"], "domain": domain})
    (out / "cases.json").write_text(json.dumps(manifest, indent=2) + "\n")
    by_cat = {c: sum(m["category"] == c for m in manifest) for c in CATEGORIES}
    print(f"wrote {len(manifest)} training cases to {out}  {by_cat}")


if __name__ == "__main__":
    asyncio.run(main())
