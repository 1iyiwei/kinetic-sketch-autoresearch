"""Generate the benchmark inputs: hand-drawn-looking sketches, a textbook-style
diagram, cartoons and flat logos, each as a 512x512 SVG plus an intent.

Sketch strokes are jittered polylines with ids s1, s2, ... and no semantic
names, so a generator has to work out what the parts are from geometry, as it
would for a real user sketch. Logos are flat filled shapes with ids p1, p2, ...

Run:  uv run python benchmark/make_cases.py
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

OUT = Path(__file__).parent / "cases"
SIZE = 512
INK = "#1d1d1f"


# ---------------------------------------------------------------- geometry

def line(x0, y0, x1, y1, n=24):
    return [(x0 + (x1 - x0) * i / (n - 1), y0 + (y1 - y0) * i / (n - 1)) for i in range(n)]


def arc(cx, cy, r, a0, a1, n=48, ry=None):
    ry = r if ry is None else ry
    return [
        (cx + r * math.cos(a0 + (a1 - a0) * i / (n - 1)), cy + ry * math.sin(a0 + (a1 - a0) * i / (n - 1)))
        for i in range(n)
    ]


def circle(cx, cy, r, n=56):
    # overshoot a little past 2*pi, the way a hand closes a circle
    return arc(cx, cy, r, -0.3, 2 * math.pi + 0.15, n)


def polyline(*pts, per_seg=14):
    out = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        seg = line(x0, y0, x1, y1, per_seg)
        out.extend(seg if not out else seg[1:])
    return out


def jitter(pts, rng, amp=1.6):
    """Low-frequency wobble: a smoothed random walk perpendicular-ish to the stroke."""
    out, dx, dy = [], 0.0, 0.0
    for x, y in pts:
        dx = 0.8 * dx + rng.uniform(-amp, amp) * 0.45
        dy = 0.8 * dy + rng.uniform(-amp, amp) * 0.45
        out.append((x + dx, y + dy))
    return out


def path_d(pts):
    head, *rest = pts
    return f"M{head[0]:.1f},{head[1]:.1f} " + " ".join(f"L{x:.1f},{y:.1f}" for x, y in rest)


# ---------------------------------------------------------------- writers

class Sketch:
    def __init__(self, seed: int):
        self.rng = random.Random(seed)
        self.items: list[str] = []

    def stroke(self, pts, width=4.0, color=INK, dash=None):
        sid = f"s{len(self.items) + 1}"
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        self.items.append(
            f'<path id="{sid}" d="{path_d(jitter(pts, self.rng))}" fill="none" stroke="{color}" '
            f'stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"{dash_attr}/>'
        )

    def svg(self):
        body = "\n  ".join(self.items)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}" width="{SIZE}" height="{SIZE}">\n'
            f'  <rect width="{SIZE}" height="{SIZE}" fill="#ffffff"/>\n  {body}\n</svg>\n'
        )


class Logo:
    def __init__(self, background="#ffffff"):
        self.items: list[str] = []
        self.background = background

    def add(self, tag: str, **attrs):
        pid = f"p{len(self.items) + 1}"
        a = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in attrs.items())
        self.items.append(f'<{tag} id="{pid}" {a}/>')

    def svg(self):
        body = "\n  ".join(self.items)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}" width="{SIZE}" height="{SIZE}">\n'
            f'  <rect width="{SIZE}" height="{SIZE}" fill="{self.background}"/>\n  {body}\n</svg>\n'
        )


# ---------------------------------------------------------------- cases

def ball_ramp():
    s = Sketch(1)
    s.stroke(polyline((40, 150), (330, 400), (480, 400)))  # ramp into floor
    s.stroke(circle(78, 128, 26))  # ball resting at the top
    return s.svg()


def pendulum():
    s = Sketch(2)
    s.stroke(line(170, 70, 342, 70), width=5)  # ceiling
    for x in range(180, 340, 22):  # hatching above the ceiling
        s.stroke(line(x, 70, x + 14, 52), width=2.5)
    s.stroke(line(256, 72, 352, 300))  # string, displaced to the right
    s.stroke(circle(362, 324, 26))  # bob
    s.stroke(line(256, 72, 256, 340), width=2, dash="8 8")  # vertical reference
    s.stroke(arc(256, 72, 205, math.radians(62), math.radians(112), 30), width=2.5)  # swing arc
    s.stroke(polyline((200, 262), (183, 255), (196, 243)), width=2.5)  # arrowhead
    return s.svg()


def spring_mass():
    s = Sketch(3)
    s.stroke(line(60, 140, 60, 380), width=5)  # wall
    for y in range(150, 380, 24):
        s.stroke(line(60, y, 42, y + 16), width=2.5)
    s.stroke(line(40, 380, 480, 380), width=4)  # floor
    zig = [(60, 300)] + [(80 + i * 18, 280 if i % 2 == 0 else 320) for i in range(10)] + [(268, 300)]
    s.stroke(polyline(*zig, per_seg=5), width=3.5)  # spring
    s.stroke(polyline((268, 240), (360, 240), (360, 378), (268, 378), (268, 240)))  # block
    s.stroke(polyline((385, 300), (450, 300)), width=2.5)  # velocity arrow
    s.stroke(polyline((436, 290), (452, 300), (436, 310)), width=2.5)
    return s.svg()


def windmill():
    s = Sketch(4)
    s.stroke(polyline((236, 470), (248, 250), (264, 250), (276, 470)))  # tower
    s.stroke(line(150, 470, 380, 470))  # ground
    hub = (256, 236)
    s.stroke(circle(*hub, 12, 30), width=3.5)
    for k in range(4):
        a = math.radians(20 + 90 * k)
        tip = (hub[0] + 170 * math.cos(a), hub[1] + 170 * math.sin(a))
        side = (hub[0] + 150 * math.cos(a + 0.18), hub[1] + 150 * math.sin(a + 0.18))
        s.stroke(polyline((hub[0] + 14 * math.cos(a), hub[1] + 14 * math.sin(a)), tip, side,
                          (hub[0] + 20 * math.cos(a + 0.5), hub[1] + 20 * math.sin(a + 0.5))))
    return s.svg()


def stick_wave():
    s = Sketch(5)
    s.stroke(circle(256, 130, 38))  # head
    s.stroke(line(256, 168, 256, 320))  # body
    s.stroke(polyline((256, 210), (200, 260), (176, 300)))  # left arm, down
    s.stroke(polyline((256, 210), (316, 170), (340, 104)))  # right arm, raised
    s.stroke(polyline((256, 320), (214, 440)))  # legs
    s.stroke(polyline((256, 320), (298, 440)))
    s.stroke(arc(256, 140, 18, math.radians(20), math.radians(160), 16), width=3)  # smile
    s.stroke(circle(242, 120, 3, 10), width=4)
    s.stroke(circle(270, 120, 3, 10), width=4)
    return s.svg()


def fish():
    s = Sketch(6)
    s.stroke(arc(220, 256, 110, math.radians(-150), math.radians(150), 60, ry=62))  # body
    s.stroke(polyline((316, 228), (400, 190), (384, 256), (400, 322), (316, 284)))  # tail
    s.stroke(circle(160, 238, 9, 16), width=4)  # eye
    s.stroke(arc(250, 256, 40, math.radians(-60), math.radians(60), 20, ry=46), width=3)  # gill
    s.stroke(arc(130, 330, 10, 0, 2 * math.pi, 16), width=2.5)  # bubbles
    s.stroke(arc(110, 370, 7, 0, 2 * math.pi, 14), width=2.5)
    return s.svg()


def rocket():
    s = Sketch(7)
    s.stroke(polyline((256, 80), (296, 150), (296, 330), (216, 330), (216, 150), (256, 80)))  # body
    s.stroke(circle(256, 190, 20, 36), width=3.5)  # window
    s.stroke(polyline((216, 270), (176, 340), (216, 330)))  # fins
    s.stroke(polyline((296, 270), (336, 340), (296, 330)))
    s.stroke(polyline((226, 336), (240, 400), (256, 360), (272, 410), (286, 336)), color="#e8590c")  # flame
    s.stroke(line(120, 470, 392, 470))  # launch pad
    return s.svg()


def sun_logo():
    lg = Logo("#fff8e7")
    cx, cy = 256, 256
    lg.add("circle", cx=cx, cy=cy, r=86, fill="#f59f00")
    for k in range(8):
        a = math.radians(k * 45)
        pts = [
            (cx + 112 * math.cos(a - 0.13), cy + 112 * math.sin(a - 0.13)),
            (cx + 190 * math.cos(a), cy + 190 * math.sin(a)),
            (cx + 112 * math.cos(a + 0.13), cy + 112 * math.sin(a + 0.13)),
        ]
        lg.add("polygon", points=" ".join(f"{x:.1f},{y:.1f}" for x, y in pts), fill="#fab005")
    return lg.svg()


def heart_logo():
    lg = Logo("#ffffff")
    lg.add("path", d="M256 400 C 120 310, 96 220, 150 170 C 196 128, 244 150, 256 190 "
                     "C 268 150, 316 128, 362 170 C 416 220, 392 310, 256 400 Z", fill="#e03131")
    lg.add("path", d="M176 196 C 186 176, 206 168, 222 172", fill="none", stroke="#ffffff",
           stroke_width=10, stroke_linecap="round")
    return lg.svg()


def bolt_logo():
    lg = Logo("#f1f3f5")
    lg.add("path", d="M150 250 C 120 250, 110 200, 150 190 C 150 140, 220 130, 240 170 "
                     "C 270 130, 350 150, 340 200 C 390 200, 390 250, 350 250 Z", fill="#868e96")
    lg.add("polygon", points="250,240 200,350 245,350 220,440 310,320 262,320 290,240", fill="#fcc419")
    return lg.svg()


CASES = [
    ("ball_ramp", "sketch", ball_ramp, "The ball rolls down the ramp, speeds up, and comes to rest on the floor after a small bounce."),
    ("pendulum", "diagram", pendulum, "Textbook diagram: the pendulum is released from the drawn position and swings back and forth, slowly losing amplitude."),
    ("spring_mass", "diagram", spring_mass, "Textbook diagram: the block oscillates horizontally on the spring, which stretches and compresses with it."),
    ("windmill", "sketch", windmill, "The windmill blades spin steadily around the hub while the tower stays still."),
    ("stick_wave", "cartoon", stick_wave, "The stick figure waves hello with the raised arm, with a little bounce in the body."),
    ("fish", "cartoon", fish, "The fish swims across the frame from right to left, wagging its tail; the bubbles drift upward."),
    ("rocket", "cartoon", rocket, "The rocket shakes on the pad with flickering flames, then launches up and out of the frame."),
    ("sun_logo", "logo", sun_logo, "Logo intro: the sun disc scales up from nothing, the rays pop in one by one around it, then the whole logo settles with a gentle pulse."),
    ("heart_logo", "logo", heart_logo, "Logo animation: the heart beats twice (quick double pulse) and the highlight glints."),
    ("bolt_logo", "logo", bolt_logo, "Logo animation: the cloud drifts in, the lightning bolt strikes down with a flash, and everything settles."),
]


# Intros that build the drawing up from nothing: the drawing is the final frame, not the first.
BUILD_UP = {"sun_logo", "bolt_logo"}

# Train/test split for the playbook (lessons learned on train cases, measured on test cases).
# Each category appears on both sides; so does a build-up intro.
TRAIN = {"pendulum", "ball_ramp", "stick_wave", "rocket", "sun_logo"}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for cid, category, fn, intent in CASES:
        (OUT / f"{cid}.svg").write_text(fn())
        manifest.append({"id": cid, "category": category, "svg": f"{cid}.svg", "intent": intent,
                         "duration": 4.0, "anchor": "end" if cid in BUILD_UP else "start",
                         "split": "train" if cid in TRAIN else "test"})
    (OUT / "cases.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {len(manifest)} cases to {OUT}")


if __name__ == "__main__":
    main()
