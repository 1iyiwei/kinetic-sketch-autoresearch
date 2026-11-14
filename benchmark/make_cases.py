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


# ---------------------------------------------------------------- added Sat afternoon (standard)

def ellipse(cx, cy, rx, ry, n=56):
    return arc(cx, cy, rx, -0.3, 2 * math.pi + 0.15, n, ry=ry)


def bouncing_ball():
    s = Sketch(11)
    s.stroke(line(60, 440, 452, 440))  # ground
    s.stroke(circle(256, 120, 34))  # ball, held high
    s.stroke(ellipse(256, 446, 30, 5, 30), width=2.5)  # shadow
    return s.svg()


def clock():
    s = Sketch(12)
    s.stroke(circle(256, 256, 170, 80))  # face
    for k in range(12):
        a = math.radians(k * 30)
        r0 = 146 if k % 3 else 136
        s.stroke(line(256 + r0 * math.cos(a), 256 + r0 * math.sin(a),
                      256 + 160 * math.cos(a), 256 + 160 * math.sin(a), 6), width=3)
    s.stroke(line(256, 256, 256, 168, 12), width=6)  # hour hand, pointing at 12
    s.stroke(line(256, 256, 382, 256, 14), width=4)  # minute hand, pointing at 3
    s.stroke(circle(256, 256, 7, 14), width=5)  # center
    return s.svg()


def flower():
    s = Sketch(13)
    s.stroke(line(150, 470, 362, 470))  # ground
    s.stroke(polyline((256, 470), (250, 380), (258, 300), (256, 228), per_seg=10), width=4)  # stem
    s.stroke(polyline((252, 400), (210, 370), (196, 384), (252, 400), per_seg=6), width=3)  # leaves
    s.stroke(polyline((256, 340), (300, 312), (312, 328), (256, 340), per_seg=6), width=3)
    for k in range(6):  # petals
        a = math.radians(k * 60 - 90)
        px, py = 256 + 46 * math.cos(a), 200 + 46 * math.sin(a)
        s.stroke(circle(px, py, 22, 30), width=3.5)
    s.stroke(circle(256, 200, 24, 30), width=4)  # center
    return s.svg()


def projectile():
    s = Sketch(14)
    s.stroke(line(40, 430, 480, 430), width=4)  # ground
    a = math.radians(40)
    bx, by = 90, 410
    tip = (bx + 70 * math.cos(a), by - 70 * math.sin(a))
    n = (math.sin(a) * 16, math.cos(a) * 16)
    s.stroke(polyline((bx - n[0], by - n[1]), (tip[0] - n[0], tip[1] - n[1]), (tip[0] + n[0], tip[1] + n[1]),
                      (bx + n[0], by + n[1]), (bx - n[0], by - n[1]), per_seg=8))  # barrel
    s.stroke(circle(92, 418, 18, 28), width=3.5)  # wheel
    mouth = (tip[0] + 14 * math.cos(a), tip[1] - 14 * math.sin(a))
    s.stroke(circle(*mouth, 13, 24), width=4)  # ball at the muzzle
    pts = [(mouth[0] + (440 - mouth[0]) * u, mouth[1] + (430 - mouth[1]) * u - 4 * 190 * u * (1 - u))
           for u in [i / 40 for i in range(41)]]
    s.stroke(pts, width=2.5, dash="9 9")  # the predicted arc
    s.stroke(polyline((426, 416), (440, 430), (452, 414)), width=2.5)  # landing mark
    return s.svg()


def bird():
    s = Sketch(15)
    s.stroke(ellipse(250, 270, 72, 44))  # body
    s.stroke(circle(326, 236, 28, 36))  # head
    s.stroke(polyline((350, 228), (382, 238), (350, 248)), width=3.5)  # beak
    s.stroke(circle(334, 228, 4, 10), width=4)  # eye
    s.stroke(polyline((232, 248), (196, 160), (290, 236)), width=4)  # raised wing
    s.stroke(polyline((182, 262), (136, 236), (148, 270), (134, 300), (184, 282)), width=4)  # tail
    s.stroke(polyline((240, 312), (236, 340)), width=3)  # legs
    s.stroke(polyline((268, 312), (272, 340)), width=3)
    return s.svg()


def car():
    s = Sketch(16)
    s.stroke(line(30, 374, 482, 374))  # road
    s.stroke(polyline((110, 336), (402, 336), (402, 284), (334, 280), (300, 228), (190, 228), (160, 280),
                      (110, 286), (110, 336), per_seg=8))  # body
    s.stroke(polyline((196, 240), (246, 240), (246, 278), (174, 278), (196, 240), per_seg=6), width=3)  # windows
    s.stroke(polyline((258, 240), (294, 240), (318, 278), (258, 278), (258, 240), per_seg=6), width=3)
    for wx in (180, 336):  # wheels with spokes
        s.stroke(circle(wx, 342, 30, 44))
        s.stroke(circle(wx, 342, 8, 14), width=3)
        s.stroke(line(wx - 22, 342, wx + 22, 342, 8), width=2.5)
    s.stroke(polyline((404, 300), (420, 300)), width=3)  # headlight
    return s.svg()


def star_logo():
    lg = Logo("#f8f0fc")
    def star(r_out, r_in):
        pts = []
        for k in range(10):
            r = r_out if k % 2 == 0 else r_in
            a = math.radians(-90 + 36 * k)
            pts.append(f"{256 + r * math.cos(a):.1f},{262 + r * math.sin(a):.1f}")
        return " ".join(pts)
    lg.add("polygon", points=star(180, 74), fill="#7048e8")
    lg.add("polygon", points=star(90, 37), fill="#b197fc")
    lg.add("circle", cx=256, cy=262, r=14, fill="#ffffff")
    return lg.svg()


def wave_logo():
    lg = Logo("#ffffff")
    for k, color in enumerate(["#1c7ed6", "#339af0", "#74c0fc"]):
        y0 = 200 + 56 * k
        pts = " ".join(f"{x},{y0 + 26 * math.sin((x - 96) / 320 * 2 * math.pi):.1f}" for x in range(96, 420, 8))
        lg.add("polyline", points=pts, fill="none", stroke=color, stroke_width=22,
               stroke_linecap="round", stroke_linejoin="round")
    return lg.svg()


# ---------------------------------------------------------------- complex tier (stress test)

def newtons_cradle():
    s = Sketch(21)
    s.stroke(line(116, 92, 396, 92), width=6)  # top bar
    s.stroke(polyline((126, 92), (126, 440)), width=4)  # frame
    s.stroke(polyline((386, 92), (386, 440)), width=4)
    s.stroke(line(90, 440, 422, 440), width=4)  # base
    xs = [168, 212, 256, 300, 344]
    a = math.radians(32)
    L = 222
    for i, x in enumerate(xs):  # leftmost ball pulled out and raised
        if i == 0:
            cx, cy = x - L * math.sin(a), 92 + L * math.cos(a)
        else:
            cx, cy = x, 92 + L
        s.stroke(line(x, 94, cx, cy - 22, 16), width=2.5)
        s.stroke(circle(cx, cy, 21, 32), width=4)
    return s.svg()


def gear_pts(cx, cy, r, teeth, depth=14, phase=0.0):
    pts = []
    for k in range(teeth):
        a0 = phase + 2 * math.pi * k / teeth
        da = 2 * math.pi / teeth
        for frac, rr in [(0.0, r), (0.18, r), (0.28, r + depth), (0.62, r + depth), (0.72, r), (1.0, r)]:
            ang = a0 + da * frac
            pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
    return pts + [pts[0]]


def gears():
    s = Sketch(22)
    s.stroke(gear_pts(196, 270, 104, 14), width=3.5)  # big gear
    s.stroke(circle(196, 270, 20, 28), width=3.5)
    s.stroke(line(196, 186, 196, 220, 6), width=3)  # spoke marks show rotation
    s.stroke(gear_pts(196 + 104 + 60 + 16, 270, 60, 8, phase=math.pi / 8), width=3.5)  # small gear
    s.stroke(circle(376, 270, 13, 22), width=3.5)
    s.stroke(line(376, 222, 376, 248, 6), width=3)
    return s.svg()


def dominoes():
    s = Sketch(23)
    s.stroke(line(30, 420, 482, 420))  # floor
    s.stroke(circle(80, 396, 24, 36))  # ball
    s.stroke(polyline((112, 396), (140, 396)), width=2.5)  # motion hint
    s.stroke(polyline((130, 388), (142, 396), (130, 404)), width=2.5)
    for k in range(7):
        x = 190 + 42 * k
        s.stroke(polyline((x, 420), (x, 330), (x + 18, 330), (x + 18, 420), per_seg=8), width=3.5)
        s.stroke(circle(x + 9, 352, 3, 8), width=3)
    return s.svg()


def cat_box():
    s = Sketch(24)
    s.stroke(line(40, 440, 472, 440))  # floor
    s.stroke(polyline((300, 440), (300, 318), (446, 318), (446, 440), per_seg=10))  # box
    s.stroke(line(300, 318, 446, 318), width=3)
    s.stroke(polyline((372, 318), (372, 360)), width=2.5)  # tape
    s.stroke(ellipse(150, 396, 58, 42))  # sitting body
    s.stroke(circle(150, 322, 34, 44))  # head
    s.stroke(polyline((124, 300), (118, 268), (142, 292)), width=3.5)  # ears
    s.stroke(polyline((158, 292), (182, 268), (176, 300)), width=3.5)
    s.stroke(circle(138, 320, 3, 8), width=4)  # eyes
    s.stroke(circle(162, 320, 3, 8), width=4)
    s.stroke(polyline((146, 334), (150, 338), (154, 334)), width=2.5)  # mouth
    s.stroke(polyline((206, 412), (240, 396), (252, 360), (240, 340)), width=4)  # tail
    s.stroke(polyline((122, 436), (126, 414)), width=3)  # paws
    s.stroke(polyline((176, 436), (172, 414)), width=3)
    return s.svg()


def story():
    s = Sketch(25)
    s.stroke(line(30, 450, 482, 450))  # ground
    s.stroke(circle(372, 112, 40, 50), color="#e8590c")  # sun
    for k in range(8):
        a = math.radians(k * 45)
        s.stroke(line(372 + 52 * math.cos(a), 112 + 52 * math.sin(a), 372 + 70 * math.cos(a),
                      112 + 70 * math.sin(a), 6), width=3, color="#e8590c")
    s.stroke(polyline((70, 150), (60, 120), (90, 96), (120, 70), (160, 76), (184, 98), (214, 104), (222, 132),
                      (200, 150), (70, 150), per_seg=6))  # cloud
    s.stroke(polyline((256, 450), (256, 410)), width=3.5, color="#2b8a3e")  # small sprout
    s.stroke(polyline((256, 424), (238, 410), (234, 418), (256, 424)), width=3, color="#2b8a3e")
    s.stroke(polyline((256, 414), (274, 400), (278, 408), (256, 414)), width=3, color="#2b8a3e")
    s.stroke(circle(256, 404, 6, 12), width=3, color="#c2255c")  # closed bud
    return s.svg()


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
    # added Sat afternoon
    ("bouncing_ball", "sketch", bouncing_ball, "The ball drops from where it is held and bounces three times, each bounce lower, squashing on impact and stretching as it falls, then rests on its shadow."),
    ("clock", "sketch", clock, "The minute hand sweeps one full turn while the hour hand advances by one hour; both turn about the center, and the face stays still."),
    ("flower", "cartoon", flower, "The flower sways gently in a breeze, bending from the base of the stem, while the petals flutter slightly."),
    ("projectile", "diagram", projectile, "Textbook diagram: the cannon recoils slightly as the ball is launched; the ball follows the drawn dashed arc and lands at the mark."),
    ("bird", "cartoon", bird, "The bird flaps its wings and flies from left to right out of the frame, bobbing up and down with each flap."),
    ("car", "cartoon", car, "The car drives to the right and out of the frame, its wheels rolling in step with its speed and the body bobbing slightly."),
    ("star_logo", "logo", star_logo, "Logo intro: the star spins in from nothing with a small overshoot, the inner star pops in, then the center sparkles once."),
    ("wave_logo", "logo", wave_logo, "Logo intro: the three wave stripes draw on from left to right one after another, then the finished logo ripples gently once and settles."),
    # complex tier: multi-object interaction, articulated characters, multi-beat stories
    ("newtons_cradle", "diagram", newtons_cradle, "Newton's cradle: the raised left ball swings down and strikes the row; the right ball swings out and back, and the exchange repeats while the middle balls stay nearly still."),
    ("gears", "diagram", gears, "The two meshing gears turn in opposite directions; the small gear turns faster in proportion to its size, and the teeth stay meshed without passing through each other."),
    ("dominoes", "sketch", dominoes, "The ball rolls right into the first domino; the dominoes topple one after another in a chain, and the last one falls flat."),
    ("cat_box", "cartoon", cat_box, "The cat crouches, leaps in an arc onto the box, lands with a little squash, and sits on top."),
    ("story", "cartoon", story, "A three-beat story: the cloud drifts over the sun and the scene dims, rain falls from the cloud, then the sprout grows taller and its bud opens into a flower."),
]


# Intros that build the drawing up from nothing: the drawing is the final frame, not the first.
BUILD_UP = {"sun_logo", "bolt_logo", "star_logo", "wave_logo"}

# Splits. train: the playbook learns from these. val: used to prune lessons. test: held-out numbers.
# complex: a stress tier, never learned from, reported separately. Each category appears in
# train and test, and so does a build-up intro.
SPLIT = {
    "train": {"pendulum", "ball_ramp", "stick_wave", "rocket", "sun_logo", "bouncing_ball", "bird", "star_logo"},
    "val": {"clock", "flower", "projectile"},
    "test": {"spring_mass", "windmill", "fish", "heart_logo", "bolt_logo", "car", "wave_logo"},
    "complex": {"newtons_cradle", "gears", "dominoes", "cat_box", "story"},
}
DURATION = {"story": 6.0}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    split_of = {cid: name for name, ids in SPLIT.items() for cid in ids}
    for cid, category, fn, intent in CASES:
        (OUT / f"{cid}.svg").write_text(fn())
        manifest.append({"id": cid, "category": category, "svg": f"{cid}.svg", "intent": intent,
                         "duration": DURATION.get(cid, 4.0), "anchor": "end" if cid in BUILD_UP else "start",
                         "split": split_of[cid]})
    (OUT / "cases.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {len(manifest)} cases to {OUT}")


if __name__ == "__main__":
    main()
