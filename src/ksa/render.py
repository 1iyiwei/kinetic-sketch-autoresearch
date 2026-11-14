"""Headless, deterministic rendering of animation programs.

The animation contract: a self-contained HTML document on a 512x512 stage that
defines `window.ksaRender(t)`, which draws the frame at time `t` seconds as a
pure function of `t` (no timers, no requestAnimationFrame, no randomness that
is not seeded). The renderer steps `t` itself, so every run of the same program
gives the same frames, and a broken program fails loudly instead of silently.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw
from playwright.async_api import Browser, async_playwright

SIZE = 512


@dataclass
class RenderResult:
    ok: bool
    frames: list[Path] = field(default_factory=list)
    gif: Path | None = None
    sheet: Path | None = None
    strip: Path | None = None
    errors: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "ok": self.ok,
            "frames": [str(p) for p in self.frames],
            "gif": str(self.gif) if self.gif else None,
            "sheet": str(self.sheet) if self.sheet else None,
            "strip": str(self.strip) if self.strip else None,
            "errors": self.errors,
        }


class Renderer:
    """Owns one headless Chromium; render many programs concurrently through it."""

    def __init__(self, concurrency: int = 4):
        self._sem = asyncio.Semaphore(concurrency)
        self._pw = None
        self._browser: Browser | None = None

    async def __aenter__(self):
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch()
        return self

    async def __aexit__(self, *exc):
        await self._browser.close()
        await self._pw.stop()

    async def rasterize_svg(self, svg_path: Path, out_png: Path) -> Path:
        """Render an input SVG to PNG, for the vision models."""
        async with self._sem:
            page = await self._browser.new_page(viewport={"width": SIZE, "height": SIZE})
            try:
                html = f"<html><body style='margin:0'>{svg_path.read_text()}</body></html>"
                await page.set_content(html)
                await page.screenshot(path=str(out_png), clip={"x": 0, "y": 0, "width": SIZE, "height": SIZE})
            finally:
                await page.close()
        return out_png

    async def render(self, html: str, out_dir: Path, duration: float = 4.0, fps: int = 12,
                     sheet_frames: int = 8) -> RenderResult:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "frames").mkdir(exist_ok=True)
        res = RenderResult(ok=False)
        async with self._sem:
            page = await self._browser.new_page(viewport={"width": SIZE, "height": SIZE})
            page.on("pageerror", lambda e: res.errors.append(f"pageerror: {e}"))
            page.on("console", lambda m: res.errors.append(f"console.{m.type}: {m.text}")
                    if m.type == "error" else None)
            try:
                await page.set_content(html, wait_until="load", timeout=15_000)
                has_fn = await page.evaluate("typeof window.ksaRender === 'function'")
                if not has_fn:
                    res.errors.append("contract: window.ksaRender(t) is not defined")
                    return res
                n = max(2, int(round(duration * fps)) + 1)
                for i in range(n):
                    t = duration * i / (n - 1)
                    try:
                        await page.evaluate(f"(async () => {{ await window.ksaRender({json.dumps(t)}); }})()")
                    except Exception as e:  # noqa: BLE001 - surface any JS error to the critic
                        res.errors.append(f"ksaRender({t:.2f}) threw: {str(e).splitlines()[0]}")
                        return res
                    p = out_dir / "frames" / f"f{i:03d}.png"
                    await page.screenshot(path=str(p), clip={"x": 0, "y": 0, "width": SIZE, "height": SIZE})
                    res.frames.append(p)
            except Exception as e:  # noqa: BLE001
                res.errors.append(f"render failed: {str(e).splitlines()[0]}")
                return res
            finally:
                await page.close()
        res.gif = write_gif(res.frames, out_dir / "anim.gif", fps)
        res.sheet = write_sheet(res.frames, out_dir / "sheet.png", duration, sheet_frames)
        # Consecutive frames: evenly spaced samples alias on fast or symmetric motion
        # (a 4-blade rotor looks like it jumps between repeated poses), so the critic
        # also gets a dense strip to judge continuity.
        res.strip = write_sheet(res.frames, out_dir / "strip.png", duration, sheet_frames,
                                idx=list(range(min(sheet_frames, len(res.frames)))))
        res.ok = True
        return res


def write_gif(frames: list[Path], out: Path, fps: int) -> Path:
    imgs = [Image.open(p).convert("RGB").resize((256, 256)) for p in frames]
    imgs[0].save(out, save_all=True, append_images=imgs[1:], duration=int(1000 / fps), loop=0)
    return out


def write_sheet(frames: list[Path], out: Path, duration: float, k: int = 8, cell: int = 256,
                idx: list[int] | None = None) -> Path:
    """Contact sheet of k frames (evenly spaced unless idx is given) with timestamps:
    one image a vision model can read instead of dozens of frames."""
    if idx is None:
        idx = [round(i * (len(frames) - 1) / (k - 1)) for i in range(k)]
    k = len(idx)
    cols = 4
    rows = (k + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + 22)), "white")
    draw = ImageDraw.Draw(sheet)
    for j, i in enumerate(idx):
        im = Image.open(frames[i]).convert("RGB").resize((cell, cell))
        x, y = (j % cols) * cell, (j // cols) * (cell + 22)
        sheet.paste(im, (x, y + 22))
        t = duration * i / (len(frames) - 1)
        draw.text((x + 6, y + 4), f"#{j + 1}  t={t:.2f}s", fill="black")
        draw.rectangle([x, y + 22, x + cell - 1, y + 22 + cell - 1], outline="#bbbbbb")
    sheet.save(out)
    return out
