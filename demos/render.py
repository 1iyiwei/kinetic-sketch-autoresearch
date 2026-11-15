"""Render an edit list into a demo video.

    python3 demos/render.py demos/cut-v1.json demos/output-v1.mp4      # the original list format

An edit list is a JSON object (paths are relative to the edit list's folder):

    {
      "sources": {"W": "foo.mp4", "C": "bar.mp4"},
      "size": [1920, 1080], "fps": 30, "background": "0xf4f4f1",
      "crops": {"ui": [8, 118, 1600, 900]},          # optional named crops: [x, y, w, h] in source pixels
      "segments": [
        {"src": "W", "in": 1.4, "out": 13.3, "crop": "ui", "note": "intro"},
        {"src": "W", "in": 62.8, "out": 82.8, "speed": 5, "crop": "ui"},       # sped up and labelled "5× speed"
        {"src": "C", "in": 77.4, "out": 87.6, "crop": [828, 248, 880, 495], "caption": "Claude Code + MCP"},
        {"src": "C", "in": 11.8, "out": 16.0, "crop": "term", "masks": [[832, 280, 860, 80]]}   # hide a repo URL
      ]
    }

Each segment is cropped (optional), scaled and padded to `size` at `fps`, with a 40 ms audio fade at each cut so
splices don't click. Sped-up segments get a small label, so the edit stays honest about time. Up to 2× they keep
their audio, sped up at the same pitch so speech stays clear; beyond that they're silent. `"label": false` on a
segment drops the speed label (e.g. when a whole talk is played uniformly faster).
Sources without an audio track (e.g. silent screen recordings) contribute silence.
An optional top-level `"tighten": {"silence_db": -35, "min_gap": 0.35, "pad": 0.12}` shortens pauses: inside every
normal-speed segment, each stretch quieter than `silence_db` for at least `min_gap` seconds is cut, keeping `pad`
seconds of it on each side so words aren't clipped. Segments can then be whole sentences rather than hand-made splices.
`caption` puts a lower-third label on a segment. `masks` paints boxes over private details (source pixels,
`mask_color` defaults to a dark terminal background); a mask can also be {"box": [x, y, w, h], "color": "0x...",
"from": s, "to": s} to give it its own colour or show it only for part of the segment (seconds into the segment),
e.g. to cover a browser's "press esc to exit full screen" toast.
`texts` places plain white text anywhere: [{"text": "Ada", "x": 320, "y": 980, "size": 30}], in output pixels,
with x the text's centre and y its top (e.g. names under video-call tiles after a mask hid the originals). Labels are drawn with Pillow (available in this workspace's venv).

The original format, a list of [source, start_s, end_s, note] rows with sources M = sketch_dynamics.mp4 and
S = sunrise.mp4, still renders as before. Needs an ffmpeg that understands -/filter_complex (7.1+).
"""

from __future__ import annotations

import bisect
import json
import subprocess
import sys
import tempfile
from pathlib import Path

LEGACY_SOURCES = {"M": "sketch_dynamics.mp4", "S": "sunrise.mp4"}
FADE = 0.04
MAX_AUDIO_SPEED = 2  # beyond this, speech is too fast to follow, so the segment goes silent


def load(path: Path) -> dict:
    data = json.loads(path.read_text())
    if isinstance(data, list):  # original format: [source, in, out, note] rows
        data = {"sources": LEGACY_SOURCES, "segments": [{"src": s, "in": a, "out": b, "note": n} for s, a, b, n in data]}
    data.setdefault("size", [1920, 1080])
    data.setdefault("fps", 30)
    data.setdefault("background", "0xf4f4f1")
    return data


def duration(path: Path) -> float | None:
    """A source's length in seconds (ffprobe), or None if it can't be read."""
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def has_audio(path: Path) -> bool:
    """Whether a source has an audio stream (screen recordings often don't)."""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0",
                        str(path)], capture_output=True, text=True)
    return bool(r.stdout.strip())


def check(cfg: dict, base: Path) -> None:
    """Catch edit-list mistakes before ffmpeg turns them into cryptic filter errors."""
    lengths = {k: duration(base / f) for k, f in cfg["sources"].items()}
    problems = []
    for i, seg in enumerate(cfg["segments"], 1):
        where = f"segment {i}" + (f" ({seg['note']})" if seg.get("note") else "")
        if seg["src"] not in lengths:
            problems.append(f"{where}: unknown source {seg['src']!r} (sources: {', '.join(lengths)})")
            continue
        a, b, n = float(seg["in"]), float(seg["out"]), lengths[seg["src"]]
        if b <= a:
            problems.append(f"{where}: out ({b:g}) must be after in ({a:g})")
        if n is not None and b > n + 0.05:
            problems.append(f"{where}: out ({b:g}) is past the end of {cfg['sources'][seg['src']]} ({n:.1f} s)")
    if problems:
        sys.exit("Edit list problems:\n  " + "\n  ".join(problems))


def frame_times(path: Path) -> list[float]:
    """Sorted video frame timestamps (from packets, no decoding)."""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return sorted(float(x) for x in r.stdout.split() if x.replace(".", "", 1).isdigit())


def silences(path: Path, db: float, min_gap: float) -> list[tuple[float, float]]:
    """Quiet stretches of a source's audio (ffmpeg silencedetect), as (start, end) seconds."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vn", "-af",
                        f"silencedetect=n={db}dB:d={min_gap}", "-f", "null", "-"], capture_output=True, text=True)
    starts = [float(l.split("silence_start:")[1]) for l in r.stderr.splitlines() if "silence_start:" in l]
    ends = [float(l.split("silence_end:")[1].split("|")[0]) for l in r.stderr.splitlines() if "silence_end:" in l]
    return list(zip(starts, ends + [duration(path) or 1e9] * (len(starts) - len(ends))))


def tighten(cfg: dict, base: Path) -> None:
    """Split normal-speed segments around long silences (see the "tighten" option)."""
    opt = cfg.get("tighten")
    if not opt:
        return
    db, gap, pad = opt.get("silence_db", -35), opt.get("min_gap", 0.35), opt.get("pad", 0.12)
    quiet = {k: silences(base / f, db, gap) if has_audio(base / f) else [] for k, f in cfg["sources"].items()}
    out = []
    for seg in cfg["segments"]:
        if float(seg.get("speed", 1)) != 1 or seg.get("tighten") is False:
            out.append(seg)
            continue
        a, b, pieces = float(seg["in"]), float(seg["out"]), []
        for s0, s1 in quiet[seg["src"]]:
            c0, c1 = max(s0 + pad, a), min(s1 - pad, b)  # the part of this silence to drop
            if c1 - c0 < 0.05:
                continue
            if c0 - a > 0.05:
                pieces.append((a, c0))
            a = c1
        if b - a > 0.05:
            pieces.append((a, b))
        out += [dict(seg, **{"in": round(x, 3), "out": round(y, 3)}) for x, y in pieces]
    cfg["segments"] = out


def label_png(text: str, out: Path, height: int, corner: bool, plain_size: int | None = None) -> None:
    """A rounded dark label with white text (Pillow), sized for a 1080p frame; or, with plain_size, just the text."""
    from PIL import Image, ImageDraw, ImageFont

    size = plain_size or round(height * (0.026 if corner else 0.032))
    font = None
    bold = ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", "DejaVuSans-Bold.ttf")
    regular = ("/System/Library/Fonts/Supplemental/Arial.ttf", "DejaVuSans.ttf", "Arial.ttf")
    for name in (regular + bold if plain_size else bold + regular):
        try:
            font = ImageFont.truetype(name, size)
            break
        except OSError:
            continue
    font = font or ImageFont.load_default()
    pad = 0 if plain_size else size // 2
    x0, y0, x1, y1 = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textbbox((0, 0), text, font=font)
    img = Image.new("RGBA", (x1 - x0 + 2 * pad, y1 - y0 + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if not plain_size:
        d.rounded_rectangle([0, 0, img.width - 1, img.height - 1], radius=pad, fill=(15, 17, 21, 215))
    d.text((pad - x0, pad - y0), text, font=font, fill=(255, 255, 255, 255))
    img.save(out)


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    edl, out = Path(sys.argv[1]), Path(sys.argv[2])
    cfg = load(edl)
    base = edl.parent
    W, H = cfg["size"]
    fps, bg = cfg["fps"], cfg["background"]
    crops = cfg.get("crops", {})
    check(cfg, base)
    tighten(cfg, base)
    audio = {k: has_audio(base / f) for k, f in cfg["sources"].items()}
    # Each segment gets its own input, seeked with -ss/-t, so ffmpeg decodes only what it needs and never buffers
    # a whole source for later segments (which matters with dozens of short cuts from a large, high-fps source).
    # Screen recordings are variable-frame-rate: a still slide may have no new frame for many seconds, so seeking
    # straight to `in` would skip ahead to the next frame. Seek to the last frame at or before `in` instead and
    # trim to the exact time after `fps` has filled in the held frames.
    frames = {k: frame_times(base / f) for k, f in cfg["sources"].items()}
    inputs, n_in = [], 0
    tmp = Path(tempfile.mkdtemp(prefix="render-"))
    parts, labels, total = [], [], 0.0

    for i, seg in enumerate(cfg["segments"]):
        a, b = float(seg["in"]), float(seg["out"])
        ft = frames[seg["src"]]
        j = bisect.bisect_right(ft, a + 1e-3) - 1
        start = max(ft[j] - 1e-3, 0) if j >= 0 else a  # seek point, at or just before the frame showing at `in`
        pre = a - start
        k, n_in = n_in, n_in + 1
        inputs += ["-ss", f"{start:.4f}", "-t", f"{b - start:.4f}", "-i", str(base / cfg["sources"][seg["src"]])]
        speed = float(seg.get("speed", 1))
        d = (b - a) / speed
        total += d
        crop = seg.get("crop")
        crop = crops.get(crop, crop) if isinstance(crop, str) else crop
        # fps also drops surplus frames before the expensive scale
        v = (f"[{k}:v]setpts=PTS-STARTPTS,fps={fps},trim=start={pre:.4f}:duration={b - a:.4f},"
             + ("setpts=PTS-STARTPTS" if speed == 1 else f"setpts=(PTS-STARTPTS)/{speed:g}"))
        for m in seg.get("masks", []):  # hide private details, in source pixels, before cropping
            m = m if isinstance(m, dict) else {"box": m}
            x, y, w, h = m["box"]
            v += f",drawbox=x={x}:y={y}:w={w}:h={h}:color={m.get('color', seg.get('mask_color', '0x1c222c'))}:t=fill"
            if "from" in m or "to" in m:
                v += f":enable='between(t,{m.get('from', 0)},{m.get('to', 1e9)})'"
        if crop:
            x, y, w, h = crop
            v += f",crop={w}:{h}:{x}:{y}"
        v += (f",scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos,"
              f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color={bg},fps={fps},setsar=1")
        overlays = []  # (text, corner, plain_size, overlay position)
        if speed != 1 and seg.get("label", True):
            overlays.append((f"{speed:g}× speed", True, None, "x=W-w-28:y=28"))
        if seg.get("caption"):
            overlays.append((seg["caption"], False, None, "x=(W-w)/2:y=H-h-48"))
        for t in seg.get("texts", []):
            overlays.append((t["text"], False, t.get("size", 30), f"x={t['x']}-w/2:y={t['y']}"))
        if overlays:
            parts.append(v + f"[base{i}]")
            cur = f"base{i}"
            for j, (text, corner, plain, pos) in enumerate(overlays):
                png = tmp / f"label{i}_{j}.png"
                label_png(text, png, H, corner, plain)
                inputs += ["-i", str(png)]
                idx, n_in = n_in, n_in + 1
                nxt = f"ov{i}_{j}"
                parts.append(f"[{cur}][{idx}:v]overlay={pos}:eof_action=repeat:format=auto[{nxt}]")
                cur = nxt
            parts.append(f"[{cur}]null[v{i}]")
        else:
            parts.append(v + f"[v{i}]")
        if speed > MAX_AUDIO_SPEED or not audio[seg["src"]]:  # very fast stretches and sources without audio are silent
            parts.append(f"anullsrc=channel_layout=stereo:sample_rate=48000,atrim=duration={d:.3f}[a{i}]")
        else:
            tempo = "" if speed == 1 else f"atempo={speed:g},"
            parts.append(f"[{k}:a]asetpts=PTS-STARTPTS,atrim=start={pre:.4f}:duration={b - a:.4f},asetpts=PTS-STARTPTS,{tempo}aresample=48000,"
                         f"afade=t=in:d={FADE},afade=t=out:st={d - FADE:.3f}:d={FADE}[a{i}]")
        labels.append(f"[v{i}][a{i}]")

    graph = edl.with_suffix(".filtergraph")
    graph.write_text(";".join(parts) + ";" + "".join(labels) + f"concat=n={len(labels)}:v=1:a=1[v][a]")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inputs, "-/filter_complex", str(graph),
                        "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)],
                       stderr=subprocess.PIPE, text=True)
    if r.returncode != 0:
        sys.exit(f"ffmpeg failed (exit {r.returncode}); filter graph: {graph}\n" + "\n".join(r.stderr.strip().splitlines()[-8:]))
    print(f"{out}: {total:.1f} s from {len(labels)} segments")


if __name__ == "__main__":
    main()
