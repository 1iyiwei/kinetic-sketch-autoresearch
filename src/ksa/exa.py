"""Exa web search, used in two places:

1. In the loop (`--exa`): before revising a program, search the web for how the intended motion really looks
   (physics, timing, animation references), steered by the critic's top issue, and give the reviser short
   excerpts with their sources. Each search is logged to <run>/exa.jsonl and recorded on the revised nodes.
2. As an input (`ksa serve`, "Find a drawing"): search open-licence SVG sites for a text description; the
   chosen SVG is downloaded, sanitized and normalized to a 512x512 drawing.

Needs EXA_API_KEY (in .env). Uses the REST API directly: https://api.exa.ai/search
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)

API = "https://api.exa.ai/search"
UA = "ksa-sketch-pad/0.1"
SVG_SITES = ["svgrepo.com", "commons.wikimedia.org", "openclipart.org"]
MAX_SVG_BYTES = 600_000


class ExaError(RuntimeError):
    pass


def available() -> bool:
    return bool(os.getenv("EXA_API_KEY"))


def _post(body: dict) -> dict:
    key = os.getenv("EXA_API_KEY")
    if not key:
        raise ExaError("EXA_API_KEY is not set (add it to .env)")
    req = urllib.request.Request(API, data=json.dumps(body).encode(), method="POST",
                                 headers={"x-api-key": key, "Content-Type": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise ExaError(f"Exa search failed: HTTP {e.code} {e.read()[:300]!r}") from e


async def search(query: str, num: int = 5, domains: list[str] | None = None,
                 highlight_query: str | None = None) -> list[dict]:
    body: dict = {"query": query, "numResults": num, "type": "auto"}
    if domains:
        body["includeDomains"] = domains
    if highlight_query:
        body["contents"] = {"highlights": {"query": highlight_query, "numSentences": 3, "highlightsPerUrl": 2}}
    out = await asyncio.to_thread(_post, body)
    return out.get("results", [])


# ---------------------------------------------------------------- 1. motion references in the loop

def _clip(text: str, n: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= n else text[: n].rsplit(" ", 1)[0] + " …"


def motion_query(case: dict, critique: dict | None) -> tuple[str, str]:
    """(search query, highlight query): what the motion should look like, aimed at the critic's top
    motion or intent issue (fidelity issues are about the drawing, not something the web can answer)."""
    issues = [i for i in (critique or {}).get("issues", []) if "ink-overlap" not in i and "first frame does not" not in i
              and "last frame does not" not in i]
    focus = f" Problem to fix: {_clip(issues[0], 200)}" if issues else ""
    query = f"How does this move in real life, as a reference for animating it: {case['intent']}{focus}"
    hq = (f"{_clip(issues[0], 160)} — " if issues else "") + \
        f"how it moves: direction, pivot, timing, period, amplitude, easing; {case['intent']}"
    return query, hq


async def motion_reference(case: dict, critique: dict | None, run_dir: Path, node: str = "") -> dict:
    """Search, and return {"query", "results": [{title, url, excerpt}], "text"}: `text` goes into the
    reviser's prompt. Errors return empty text, so a failed search never stops the loop."""
    query, hq = motion_query(case, critique)
    t0 = time.time()
    try:
        res = await search(query, num=4, highlight_query=hq)
        err = None
    except Exception as e:  # noqa: BLE001 - a failed search is logged, the loop goes on
        res, err = [], str(e)
    found = [{"title": r.get("title") or r.get("url"), "url": r.get("url"),
              "excerpt": _clip(" … ".join(r.get("highlights") or []), 450)} for r in res]
    found = [f for f in found if f["excerpt"]][:3]
    text = ""
    if found:
        text = ("\nWeb references found by Exa for this motion (real-world behaviour; use what helps the issues "
                "above, ignore the rest, and keep the drawing's style):\n"
                + "\n".join(f"- {f['title']} ({f['url']}): {f['excerpt']}" for f in found) + "\n")
    rec = {"ts": t0, "case": case["id"], "node": node, "query": query, "seconds": round(time.time() - t0, 2),
           "results": found, "error": err}
    with (run_dir / "exa.jsonl").open("a") as f:
        f.write(json.dumps(rec) + "\n")
    return {**rec, "text": text}


# ---------------------------------------------------------------- 2. find a drawing (SVG) for a description

def _svg_url(r: dict) -> str | None:
    url, img = r.get("url", ""), r.get("image") or ""
    if "svgrepo.com" in url:
        m = re.search(r"svgrepo\.com/svg/(\d+)/([\w-]+)", url)
        return f"https://www.svgrepo.com/show/{m.group(1)}/{m.group(2)}.svg" if m else None
    if "commons.wikimedia.org" in url:
        m = re.search(r"/wiki/File:(.+\.svg)$", url, re.I)
        return f"https://commons.wikimedia.org/wiki/Special:FilePath/{m.group(1)}" if m else None
    if "openclipart.org" in url:
        m = re.search(r"openclipart\.org/detail/(\d+)", url)
        return f"openclipart:{m.group(1)}" if m else None
    return img if img.lower().endswith(".svg") else None


async def find_svgs(description: str, n: int = 8) -> list[dict]:
    res = await search(f"simple line drawing of {description}, SVG file", num=n + 4, domains=SVG_SITES)
    out = []
    for r in res:
        u = _svg_url(r)
        if u:
            out.append({"title": r.get("title") or "", "page": r.get("url"), "svg_url": u,
                        "source": next((s for s in SVG_SITES if s in r.get("url", "")), "")})
    return out[:n]


def _get(url: str, limit: int = MAX_SVG_BYTES) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise ExaError(f"file too large (over {limit // 1000} KB)")
    return data


def _resolve_openclipart(ref: str) -> str:
    page = _get(f"https://openclipart.org/detail/{ref.split(':')[1]}", 2_000_000).decode("utf-8", "replace")
    page = page.replace("\\/", "/")  # the link sits in escaped JSON
    m = re.search(r'href="(/download/\d+/[^"]+\.svg)"', page) or re.search(r'(https://openclipart\.org/download/\d+/[^"\\]+\.svg)', page)
    if not m:
        raise ExaError("no SVG download on the Openclipart page")
    return m.group(1) if m.group(1).startswith("http") else "https://openclipart.org" + m.group(1)


SVG_NS = "http://www.w3.org/2000/svg"
XLINK = "http://www.w3.org/1999/xlink"
DROP_TAGS = {"script", "foreignObject", "iframe", "object", "embed", "audio", "video", "metadata", "title"}
SHAPES = {"path", "circle", "ellipse", "rect", "line", "polyline", "polygon", "g", "text", "use"}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def sanitize(svg_bytes: bytes) -> str:
    """Make a downloaded SVG safe and uniform: drop scripts, event handlers, external references and
    metadata; give unnamed shapes ids (p1, p2, ...) so the generator can refer to parts; and wrap it in a
    512x512 drawing on white, like the benchmark's."""
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", XLINK)
    if b"<!ENTITY" in svg_bytes:
        raise ExaError("SVG with entity declarations refused")
    root = ET.fromstring(svg_bytes)
    if _local(root.tag) != "svg":
        raise ExaError("not an SVG")
    n = 0
    for parent in list(root.iter()):
        for el in list(parent):
            if not isinstance(el.tag, str) or _local(el.tag) in DROP_TAGS or el.tag.startswith("{") and SVG_NS not in el.tag:
                parent.remove(el)
    for el in root.iter():
        for a in list(el.attrib):
            v = el.attrib[a]
            name = _local(a)
            if name.lower().startswith("on") or (name == "href" and not v.startswith("#")) \
                    or "url(http" in v.replace(" ", "") or "javascript:" in v.lower() or a.startswith("{") and "sodipodi" in a or "inkscape" in a:
                del el.attrib[a]
        if _local(el.tag) == "style" and el.text:
            el.text = re.sub(r"@import[^;]*;|url\((?!#)[^)]*\)", "", el.text)
        if _local(el.tag) in SHAPES and "id" not in el.attrib:
            n += 1
            el.set("id", f"p{n}")
    vb = root.get("viewBox")
    if not vb:
        w = re.sub(r"[^\d.]", "", root.get("width", "") or "") or "512"
        h = re.sub(r"[^\d.]", "", root.get("height", "") or "") or "512"
        vb = f"0 0 {w} {h}"
    inner = ET.Element(f"{{{SVG_NS}}}svg", {"x": "32", "y": "32", "width": "448", "height": "448", "viewBox": vb,
                                           "preserveAspectRatio": "xMidYMid meet", "id": "found"})
    for k, v in root.attrib.items():  # keep presentation attributes such as fill/stroke on the root
        if _local(k) in ("fill", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin", "style", "color"):
            inner.set(k, v)
    inner.extend(list(root))
    outer = ET.Element(f"{{{SVG_NS}}}svg", {"viewBox": "0 0 512 512", "width": "512", "height": "512"})
    ET.SubElement(outer, f"{{{SVG_NS}}}rect", {"width": "512", "height": "512", "fill": "#ffffff"})
    outer.append(inner)
    return ET.tostring(outer, encoding="unicode") + "\n"


async def fetch_svg(svg_url: str) -> str:
    def work():
        url = _resolve_openclipart(svg_url) if svg_url.startswith("openclipart:") else svg_url
        if not re.match(r"https://([\w-]+\.)*(svgrepo\.com|wikimedia\.org|openclipart\.org)/", url):
            raise ExaError("only SVG Repo, Wikimedia Commons and Openclipart files are fetched")
        return sanitize(_get(url))
    return await asyncio.to_thread(work)
