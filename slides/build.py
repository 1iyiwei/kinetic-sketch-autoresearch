"""Build the demo slides: one HTML file per slide, linked previous/next.

  uv run python slides/build.py        # then: open slides/index.html

Input drawings are the committed SVGs and animations are the committed, playable programs in
results/ (see `ksa export`), so the slides play the exact animations the judge scored. Headline
numbers that average several runs come from the README tables and are set in NUMBERS below.
"""

from __future__ import annotations

import html
import json
import shutil
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
RES = ROOT / "results"

# Averages over several runs, from the README (held-out judge gpt-5.4, 3x per animation).
NUMBERS = {
    "first": {"one_shot": 3.58, "best_of_6": 3.60, "loop": 3.91, "critic": {"one_shot": 3.75, "best_of_6": 4.03, "loop": 4.25}},
    "test": {"one_shot": 3.78, "loop": 3.99, "wins": "6 of 7"},
    "complex": {"one_shot": 3.60, "loop": 3.52},
    "playbook_v1": {"none": 3.60, "all": 3.68, "select": 3.74},
    "playbook_v2": {"none": 3.78, "select": 3.63, "pruned": 3.74},
}
LOOP = "loop_k2_b1_c2_r2"


def man(name: str) -> dict:
    return json.loads((RES / name / "manifest.json").read_text())


def e(s) -> str:
    return html.escape(str(s))


def anim(src: str, k: float = .42, label: str = "", score: float | None = None, cls: str = "") -> str:
    sc = f'<span class="score">{score:.2f}</span> ' if score is not None else ""
    return (f'<div class="tile {cls}"><div class="frame" style="--k:{k}">'
            f'<iframe src="{e(src)}" title="{e(label)}" loading="lazy" tabindex="-1"></iframe></div>'
            f'<div class="cap">{sc}{label}</div></div>')


def drawing(src: str, k: float = .42, label: str = "") -> str:
    return (f'<div class="tile"><div class="frame" style="--k:{k}"><img src="{e(src)}" alt="{e(label)}"></div>'
            f'<div class="cap">{label}</div></div>')


def intent(text: str, cls: str = "") -> str:
    return f'<p class="intent {cls}"><span>intent</span> {e(text)}</p>'


def bars(rows: list[tuple[str, str, float, bool]], lo: float = 3.0, hi: float = 4.5, compact: bool = False) -> str:
    out = ['<div class="bars compact">' if compact else '<div class="bars">']
    for lab, sub, v, lead in rows:
        w = max(0, min(1, (v - lo) / (hi - lo))) * 100
        out.append(f'<div class="lab">{lab}<small>{sub}</small></div><div class="track">'
                   f'<div class="fill{" lead" if lead else ""}" style="width:{w:.1f}%"></div></div>'
                   f'<div class="val">{v:.2f}</div>')
    mid = "" if compact else "<span>held-out judge score (1–5)</span>"
    out.append(f'<div></div><div class="axis"><span>{lo:.1f}</span>{mid}<span>{hi:.1f}</span></div><div></div></div>')
    return "".join(out)


ARCH = """
<svg viewBox="0 0 1150 430" width="1000" height="374" role="img" aria-label="System diagram: inner loop and outer loop">
  <defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
    <path d="M0,0 L10,5 L0,10 z" fill="#5d6678"/></marker></defs>
  <style>
    .b{fill:#fff;stroke:#1c2230;stroke-width:2;rx:12}
    .code{fill:#f1f3f6}
    .llm{fill:#e4ebfa;stroke:#2457c5}
    .t{font:600 19px Inter,system-ui,sans-serif;fill:#1c2230}
    .s{font:15px Inter,system-ui,sans-serif;fill:#5d6678}
    .k{font:500 13px 'JetBrains Mono',monospace;fill:#2457c5;letter-spacing:.08em}
    .ln{stroke:#5d6678;stroke-width:2;fill:none;marker-end:url(#ah)}
    .loop{stroke:#2457c5;stroke-width:2.5;fill:none;marker-end:url(#ah);stroke-dasharray:7 6}
    .zone{fill:none;stroke:#2457c5;stroke-width:1.5;stroke-dasharray:4 6;rx:18}
  </style>
  <rect class="zone" x="200" y="18" width="740" height="250"/>
  <text class="k" x="220" y="44">INNER LOOP · ONE DRAWING · BEAM SEARCH</text>
  <rect class="b code" x="10" y="100" width="160" height="90"/>
  <text class="t" x="28" y="138">Drawing</text><text class="s" x="28" y="164">SVG + intent</text>
  <rect class="b llm" x="230" y="70" width="180" height="90"/>
  <text class="t" x="248" y="108">Generator</text><text class="s" x="248" y="134">writes ksaRender(t)</text>
  <rect class="b code" x="470" y="70" width="190" height="90"/>
  <text class="t" x="488" y="108">Renderer</text><text class="s" x="488" y="134">headless, exact frames</text>
  <rect class="b llm" x="720" y="70" width="200" height="90"/>
  <text class="t" x="738" y="108">Critic</text><text class="s" x="738" y="134">measured + vision</text>
  <rect class="b llm" x="470" y="180" width="190" height="70"/>
  <text class="t" x="488" y="212">Reviser</text><text class="s" x="488" y="236">sees its own frames</text>
  <path class="ln" d="M170,145 L228,120"/>
  <path class="ln" d="M410,115 L468,115"/>
  <path class="ln" d="M660,115 L718,115"/>
  <path class="loop" d="M820,162 C820,215 720,215 662,215"/>
  <path class="loop" d="M470,215 C330,215 320,200 320,162"/>
  <text class="s" x="680" y="240">issues + fixes</text>
  <rect class="b code" x="980" y="70" width="160" height="90"/>
  <text class="t" x="998" y="108">Best program</text><text class="s" x="998" y="134">highest critic score</text>
  <path class="ln" d="M920,115 L978,115"/>
  <rect class="b" x="980" y="200" width="160" height="80" style="fill:#e3f3e8;stroke:#1f7a43"/>
  <text class="t" x="998" y="234">Judge</text><text class="s" x="998" y="258">other model, 3×</text>
  <path class="ln" d="M1060,160 L1060,198"/>
  <rect class="zone" x="200" y="300" width="740" height="118" style="stroke:#1f7a43"/>
  <text class="k" x="220" y="326" style="fill:#1f7a43">OUTER LOOP · ACROSS DRAWINGS</text>
  <rect class="b llm" x="560" y="340" width="190" height="66"/>
  <text class="t" x="578" y="370">Analyst</text><text class="s" x="578" y="393">lessons from the tree</text>
  <rect class="b code" x="230" y="340" width="230" height="66"/>
  <text class="t" x="248" y="370">Playbook</text><text class="s" x="248" y="393">≤ 12 lessons, selected</text>
  <path class="ln" d="M1000,160 C1000,370 860,373 752,373"/>
  <path class="ln" d="M558,373 L462,373"/>
  <path class="ln" d="M300,338 L300,162"/>
  <rect x="30" y="250" width="16" height="16" class="b llm"/><text class="s" x="54" y="263">model call</text>
  <rect x="30" y="278" width="16" height="16" class="b code"/><text class="s" x="54" y="291">plain code</text>
</svg>
"""


def slides() -> list[tuple[str, str, str]]:
    fb, tree, test, cx, af = man("first-batch"), man("pendulum-tree"), man("test"), man("complex"), man("anchor-fix")
    nodes = {n["id"]: n for n in tree["nodes"]}
    T = "../results/pendulum-tree/"
    S = []

    # 1. title
    S.append(("title", "Kinetic Sketch Autoresearch", f"""
<div class="eyebrow">SF AI Research Hackathon · Open Track</div>
<div class="row" style="margin-top:20px">
  <div class="col grow" style="gap:24px">
    <h1>Kinetic Sketch Autoresearch</h1>
    <p class="lede">A model that writes animation code can't see its mistakes. Ours renders what it wrote, watches it,
    fixes it, and tests whether the lessons carry to new drawings.</p>
    <p class="muted small">Sketches, textbook diagrams, cartoons and logos in; stylized animation programs out.</p>
  </div>
  <div class="row" style="gap:16px">
    {drawing(T + "input.svg", .44, "a textbook drawing")}
    {anim(T + tree["best"] + ".html", .44, "the loop's animation")}
  </div>
</div>"""))

    # 2. problem
    n0 = nodes["r0n0"]
    S.append(("problem", "Writing animation code blind", f"""
<div class="eyebrow">The problem</div>
<h2>Code is the right medium for stylized animation, but one-shot generation is blind</h2>
{intent(tree["intent"])}
<div class="row">
  {drawing(T + "input.svg", .5, "<b>input:</b> released pendulum, arrow shows the swing")}
  <div class="arrow">→</div>
  {anim(T + "r0n0.html", .5, "<b>first attempt</b> (gpt-5.5, one shot)", n0["score"], "bad")}
  <div class="col grow">
    <p>Programs are exact, editable and keep the drawing's own strokes. But the model never sees the result.</p>
    <div class="quote"><span class="who">critic, after watching the frames</span>{e(n0["issues"][0])}</div>
  </div>
</div>"""))

    # 3. architecture
    S.append(("system", "The system", f"""
<div class="eyebrow">The system</div>
<h2>Render, watch, revise; then learn across drawings</h2>
<div>{ARCH}</div>
<p class="small muted">One deterministic program runs the search; models are called at fixed points. No weights are updated.
Fidelity to the drawing is measured in code; the vision model judges only the motion. The judge never steers the loop.</p>"""))

    # 4. loop fixes the pendulum
    chain = ["r0n0", "r1n0", "r2n1"]
    tiles = '<div class="arrow">→</div>'.join(
        anim(T + f"{i}.html", .4, f"<b>{i}</b> · {'first sample' if nodes[i]['parent'] is None else 'revision of ' + nodes[i]['parent']}",
             nodes[i]["score"], "win" if i == tree["best"] else ("bad" if i == "r0n0" else "")) for i in chain)
    S.append(("loop", "Watching the loop fix it", f"""
<div class="eyebrow">Inner loop, one drawing</div>
<h2>It catches the wrong-way swing and fixes the physics</h2>
<div class="row center" style="gap:14px">{tiles}</div>
{intent(tree["intent"])}
<div class="row">
  <div class="quote grow"><span class="who">critic's suggested fix for r0n0</span>{e(nodes["r0n0"]["fixes"][1])}</div>
  <p class="small muted" style="max-width:34ch">Six candidates in all: 2 samples, then 2 rounds revising the best into 2.
  Critic score per round: {" → ".join(f"{x:.2f}" for x in tree["best_score_by_round"])}.</p>
</div>"""))

    # 5. headline results
    n = NUMBERS["first"]
    S.append(("results", "Sampling more vs. revising", f"""
<div class="eyebrow">Results · 10 drawings · equal generator calls</div>
<h2>Sampling more doesn't help. Looking and revising does.</h2>
{bars([("One-shot", "1 program", n["one_shot"], False),
       ("Best-of-6", "6 programs, keep the critic's best", n["best_of_6"], False),
       ("Loop", "2 samples + 4 revisions", n["loop"], True)])}
<p class="small">Held-out judge: a different model (gpt-5.4), 3× per animation. Best-of-6 raises the in-loop critic's score
({n["critic"]["one_shot"]:.2f} → {n["critic"]["best_of_6"]:.2f}) but not the judge's: picking the max of a noisy critic mostly
selects for its noise. The loop's gain holds under both. It wins on 7 of 10 drawings.</p>"""))

    # 6. side by side, first batch
    def trio(cid):
        c = fb["cases"][cid]
        ms = [("one_shot", "one-shot"), ("best_of_6", "best-of-6"), (LOOP, "loop")]
        best = max(c["methods"][m]["judge"] for m, _ in ms)
        return (f'<div class="col" style="gap:8px"><div class="row" style="gap:14px;align-items:baseline"><h3>{cid.replace("_", "–")}</h3>{intent(c["intent"], "tight")}</div><div class="row" style="gap:12px">'
                + drawing(f"../results/first-batch/{cid}/input.svg", .3, "input")
                + "".join(anim(f"../results/first-batch/{c['methods'][m]['file']}", .3, lab, c["methods"][m]["judge"],
                               "win" if c["methods"][m]["judge"] == best and sum(c["methods"][x]["judge"] == best for x, _ in ms) == 1 else "") for m, lab in ms)
                + "</div></div>")
    S.append(("side-by-side", "Side by side", f"""
<div class="eyebrow">Same drawing, three methods</div>
<h2>Where one-shot misreads the physics, the loop recovers</h2>
{trio("pendulum")}
{trio("spring_mass")}"""))

    # 7. held-out test
    t = NUMBERS["test"]
    def duo(cid, cases, base):
        c = cases["cases"][cid]
        a, b = c["methods"]["one_shot"], c["methods"][LOOP]
        return (f'<div class="col" style="gap:6px">{intent(c["intent"], "tight")}<div class="row" style="gap:12px">' + drawing(f"../results/{base}/{cid}/input.svg", .26, cid.replace("_", " "))
                + anim(f"../results/{base}/{a['file']}", .26, "one-shot", a["judge"], "win" if a["judge"] > b["judge"] else "")
                + anim(f"../results/{base}/{b['file']}", .26, "loop", b["judge"], "win" if b["judge"] > a["judge"] else "")
                + "</div></div>")
    S.append(("test", "Held-out test drawings", f"""
<div class="eyebrow">Held-out test · 7 drawings never used for tuning</div>
<h2>The gain holds on new drawings</h2>
<div class="row">
  <div class="col" style="width:440px">
    {bars([("One-shot", "3 runs", t["one_shot"], False), ("Loop", "1 run", t["loop"], True)], compact=True)}
    <p class="small muted">Held-out judge score, 1–5.</p>
    <p class="small">The loop wins on {t["wins"]} test drawings. Shown: run 1 of the one-shot runs.</p>
  </div>
  <div class="col grow">{duo("spring_mass", test, "test")}{duo("fish", test, "test")}</div>
</div>"""))

    # 8. findings about critics
    S.append(("critics", "What we learned about critics", f"""
<div class="eyebrow">What we learned · 1</div>
<h2>Vision critics need help seeing motion</h2>
<div class="cards">
  <div class="card"><span class="pill">aliasing</span><h3>Eight evenly spaced frames lie about rotation</h3>
    <div class="row" style="gap:12px"><img src="assets/windmill-sheet.png" alt="overview sheet" style="width:250px;border:1px solid var(--line);border-radius:6px">
    <img src="assets/windmill-strip.png" alt="consecutive strip" style="width:250px;border:1px solid var(--line);border-radius:6px"></div>
    <p>A correct 4-blade spin looked "jumpy" (3.25). Adding consecutive frames fixed the verdict (4.25).</p></div>
  <div class="card"><span class="pill">hallucination</span><h3>Critics invent fidelity errors, and revisers chase them</h3>
    <p>The critic called pixel-identical first frames "smaller and shifted"; revising against that made programs worse
    (pendulum 2.25 → 1.75). Fidelity is now measured in code (ink-overlap F1), and the vision model judges only motion.</p>
    <span class="pill">judge noise</span>
    <p>The same render scored 4.00, then 2.50. Final scores average 3 runs of a separate judge model.</p></div>
</div>"""))

    # 9. metric fought the intent
    def ba(cid):
        c = af["cases"][cid]
        b, a = c["methods"]["before_anchor_fix"], c["methods"]["after_anchor_fix"]
        return (f'<div class="col" style="gap:6px;width:560px">{intent(c["intent"], "tight")}<div class="row" style="gap:12px">' + drawing(f"../results/anchor-fix/{cid}/input.svg", .3, "the drawing (end frame)")
                + anim(f"../results/anchor-fix/{b['file']}", .3, "before: frame 0 forced to match", b["judge"], "bad")
                + anim(f"../results/anchor-fix/{a['file']}", .3, "after: anchor at the end", a["judge"], "win") + "</div></div>")
    S.append(("anchor", "A metric that fought the intent", f"""
<div class="eyebrow">What we learned · 2</div>
<h2>Our own metric fought the intent</h2>
<p>"The sun scales up from nothing" can't start on the finished logo. Requiring frame 0 to match the drawing made the
generator flash the whole logo, then reset. Each drawing now names its anchor frame: first, or last for build-ups.</p>
<div class="row" style="gap:28px">{ba("sun_logo")}{ba("bolt_logo")}</div>"""))

    # 10. playbook
    v1, v2 = NUMBERS["playbook_v1"], NUMBERS["playbook_v2"]
    S.append(("playbook", "Learning across drawings", f"""
<div class="eyebrow">Outer loop · the playbook</div>
<h2>Lessons in the prompt help when they fit, but don't reliably transfer</h2>
<div class="row">
  <div class="col grow">
    <p>After each training drawing, an analyst reads the search tree and writes general lessons, e.g. <i>"for a released
    oscillator drawn at an extreme, start from that pose with zero velocity"</i>. A selector gives each new drawing only the
    lessons that match its motion.</p>
    <p class="small muted">Helped where a lesson fit: the spring–mass gained in every run from the pendulum's lessons.
    Hurt where one didn't: the windmill got launch and bounce advice and turned "strobey".</p>
  </div>
  <table>
    <tr><th>One-shot on held-out drawings</th><th>5 test</th><th>7 test</th></tr>
    <tr><td>no playbook</td><td class="num">{v1["none"]:.2f}</td><td class="num">{v2["none"]:.2f}</td></tr>
    <tr><td>all lessons</td><td class="num">{v1["all"]:.2f}</td><td class="num">—</td></tr>
    <tr><td>selected lessons</td><td class="num">{v1["select"]:.2f}</td><td class="num">{v2["select"]:.2f}</td></tr>
    <tr><td>selected, pruned on val (identical lessons)</td><td class="num">—</td><td class="num">{v2["pruned"]:.2f}</td></tr>
  </table>
</div>
<p class="small">Two runs with identical lessons differ by 0.11: run-to-run noise is as large as every playbook effect.
The inner loop's gain (+0.21 to +0.33) is the one that holds.</p>"""))

    # 11. limits
    c = NUMBERS["complex"]
    S.append(("limits", "Where it breaks", f"""
<div class="eyebrow">Limits · 5 complex drawings</div>
<h2>Multi-object physics is still hard</h2>
<div class="row">
  <div class="col" style="width:420px">
    {bars([("One-shot", "3 runs", c["one_shot"], False), ("Loop", "1 run", c["loop"], False)], 2.0, 4.5, compact=True)}
    <p class="small muted">Held-out judge score, 1–5.</p>
    <p class="small">The critic names the problem ("the right ball should swing out as the left one hits"), but two
    rounds of revision don't fix coordinated physics across several bodies.</p>
  </div>
  <div class="col grow">{duo("newtons_cradle", cx, "complex")}{duo("gears", cx, "complex")}</div>
</div>"""))

    # 12. next
    S.append(("next", "Next, and try it", f"""
<div class="eyebrow">Next</div>
<h2>Put the loop's improvements into the weights</h2>
<div class="cards">
  <div class="card"><span class="pill">Tinker</span><h3>Distill the loop into an open model</h3>
    <p>Fine-tune Qwen3.6-35B-A3B with LoRA on the best programs the loop found for training drawings, then compare
    one-shot before and after on the test drawings. Base Qwen already wrote a 4.50 windmill in one shot.</p></div>
  <div class="card"><span class="pill">Modal</span><h3>Revise in parallel</h3>
    <p>Render and critique all candidates of a round at once, so a loop takes about as long as one shot, and more
    rounds become affordable for complex drawings.</p></div>
  <div class="card"><span class="pill">try it</span><h3>Draw, then animate</h3>
    <p><code>uv run ksa serve</code> → draw, describe the motion → <b>Animate</b></p></div>
  <div class="card"><span class="pill">open</span><h3>Everything is logged</h3>
    <p>Every model call, search tree, critique and program is saved; results replay from ~8 KB programs in <code>results/</code>.</p></div>
</div>"""))
    return S


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Kinetic Sketch Autoresearch</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Inter:wght@400;600&family=JetBrains+Mono:wght@500&display=swap">
<link rel="stylesheet" href="style.css"></head>
<body><main class="stage">
{body}
<nav class="nav"><a rel="prev" href="{prev}" class="{prev_cls}">← previous</a><span>{n} / {total}</span><a rel="next" href="{next}" class="{next_cls}">next →</a></nav>
</main><script src="nav.js"></script></body></html>
"""


def main():
    assets = HERE / "assets"
    assets.mkdir(exist_ok=True)
    runs = ROOT / "runs"
    for src, dst in [("20261114-120252-baseline/windmill/render/sheet.png", "windmill-sheet.png"),
                     ("20261114-131334-loop_k2_b1_c2_r2/windmill/nodes/r0n0/render/strip.png", "windmill-strip.png")]:
        if (runs / src).exists():
            shutil.copy(runs / src, assets / dst)
    S = slides()
    names = [f"{i + 1:02d}-{slug}.html" for i, (slug, _, _) in enumerate(S)]
    for old in HERE.glob("[0-9][0-9]-*.html"):
        old.unlink()
    for i, (slug, title, body) in enumerate(S):
        (HERE / names[i]).write_text(PAGE.format(
            title=e(title), body=body, n=i + 1, total=len(S),
            prev=names[i - 1] if i else "", prev_cls="" if i else "off",
            next=names[i + 1] if i + 1 < len(S) else "", next_cls="" if i + 1 < len(S) else "off"))
    (HERE / "index.html").write_text(f'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0; url={names[0]}">'
                                     f'<title>Kinetic Sketch Autoresearch</title><a href="{names[0]}">Open the slides</a>\n')
    print(f"wrote {len(S)} slides to {HERE}")


if __name__ == "__main__":
    main()
