# Demos

Shareable result pages and demo material, newest first. Pages on claude.ai are private until
their owner shares them (Share menu on the page).

| When (PT) | What | Link | Source runs |
| --- | --- | --- | --- |
| Sat Nov 14, 13:50 | First results: loop vs. one-shot vs. best-of-6 on 10 cases. Headline judge scores, the pendulum search tree, all cases side by side, findings | [Kinetic Sketch Autoresearch](https://claude.ai/artifact/52zhVRsQdXewQp3pxPYqPH) | `runs/20261114-131334-{one_shot,best_of_6,loop_k2_b1_c2_r2}` |

## Local result pages

Run outputs live in `runs/` (gitignored), so these pages exist only on the machine that ran the experiments. Open them
with `open runs/<page>`.

| Page | Drawings | Columns | Source runs |
| --- | --- | --- | --- |
| `runs/compare.html` | First batch (10) | one-shot, best-of-6, loop | `runs/20261114-131334-*` |
| `runs/compare-test.html` | Test split (7) | one-shot, one-shot + playbook v2, loop | `runs/v2/{oneshot-test-1,pbsel-test-1,loop-test}` |
| `runs/compare-complex.html` | Complex tier (5) | one-shot, loop | `runs/v2/{oneshot-complex-1,loop-complex}` |

Where a method ran 3 times, the page shows run 1; the averages over all runs are in the README. Every run also has
its own gallery, `runs/<run>/index.html`, and every case its search tree, `runs/<run>/<case>/tree.json`.

To build a comparison page from any runs over the same drawings:

```bash
uv run ksa compare runs/<run A> runs/<run B> ... -o runs/compare-x.html --title "Name" --note "What it shows"
```

## Demo plan

**The one-sentence story:** a model that writes animation code can't see its mistakes; ours renders what it wrote,
watches it, fixes it, and keeps the lessons for the next drawing.

Judging is 5 × 20%: rigour, novelty, results, autonomy and self-improvement, interpretability. Every beat
below names the criterion it serves.

### 2-minute submission video (due Sun 14:30)

| Time | Show | Say (roughly) | Criterion |
| --- | --- | --- | --- |
| 0:00–0:15 | A rough pendulum sketch, then the one-shot animation swinging the wrong way | "Ask a model to animate a drawing and it writes code blind. This pendulum swings away from the arrow." | Problem |
| 0:15–0:40 | The loop on that sketch: render → contact sheet → critic issues → revision; the pendulum tree (r0n0 → r1n0 → r2n1) | "Our agent renders its program, a vision critic watches the frames, and the agent revises. Here it catches the wrong-way swing and fixes the physics." | Autonomy |
| 0:40–1:05 | The comparison page: three columns, green winners; the headline numbers | "On 10 drawings, judged by a different model three times each: one-shot 3.58, best-of-6 3.60, loop 3.91. Sampling more doesn't help; looking and revising does." | Results, rigour |
| 1:05–1:30 | `playbooks/train-v1.json` and its `history`; then the test table | "We also tried learning across drawings: after each one, it writes down general lessons. On new drawings those prompt lessons help when they fit and hurt when they don't, and on a larger test set they don't reliably help; the noise between identical runs is as big as the effect. The loop is what transfers. Next, we distill it into an open model's weights on Tinker." | Rigour, honest failure |
| 1:30–1:50 | Two findings, one visual each: the aliasing windmill, and the phantom "smaller and shifted" critique next to a pixel diff | "Vision critics hallucinate, so we measure what we can and keep the judge separate. Every call is logged." | Interpretability |
| 1:50–2:00 | The repo, and a gallery of the best animations | "Kinetic Sketch Autoresearch: sketches in, animations out, and it learns." | — |

**Record before Sunday 11:00:**
- Screen capture of `uv run ksa run --method loop --cases pendulum` with the terminal's per-round scores, sped up.
- The pendulum GIFs r0n0, r1n0 and r2n1 side by side.
- A scroll through the comparison page (the shared link above, or `runs/compare.html`).
- The playbook JSON: its lessons and its `history`.
- The windmill overview sheet against its consecutive strip; the fish frame 0 against the input, with F1 = 1.00.

### 3-minute round-1 pitch, plus 2 minutes of Q&A

1. **Problem (30 s):** stylized animation from drawings (cartoons, diagrams, logos), not photorealistic video. Code is
   editable and exact, but one-shot code generation is blind.
2. **Method (45 s):** one diagram covering generate → deterministic render → hybrid critic (measured fidelity +
   vision judgment of motion) → revise in a beam search, and the playbook as an outer loop.
3. **Results (60 s):** the results table and the pendulum tree; the test-split playbook result.
4. **What we learned (30 s):** aliasing, judge noise, hallucinated fidelity errors, and the metric that fought the intent.
5. **Next (15 s):** more cases and seeds, Modal fan-out, a live drawing input.

**Likely questions:**
- *Isn't the loop just overfitting its own critic?* The judge is a different model, run 3×, and best-of-6, which
  only selects, gains on the critic but not on the judge.
- *Equal compute?* Equal generator calls; the loop uses about 33% more tokens. Next: a token-matched best-of-K.
- *Why code instead of a video model?* Stylized, exact and editable output; the drawing is preserved by
  construction; motion can be checked and corrected.
- *Does it generalize?* The loop's gain holds on 7 held-out test drawings (+0.21, 6 of 7). The playbook of prompt lessons does not reliably transfer, and we show that. On 5 complex multi-object drawings, neither method does well yet.

### Finals (3 minutes on stage, live demo, no Q&A)

- **Live:** a judge draws on `tools/draw.html` and types the intent; you save the SVG and run `ksa animate` with the
  playbook. The terminal shows the best score after each round, and the result opens when it's done (about 2–3
  minutes; Modal would make it faster).
- **Fallback:** if anything stalls, switch to a pre-computed run in the gallery and the pendulum tree.

## Runbook: commands for each demo

Run everything from the repo root (`cd kinetic-sketch-autoresearch`). It needs `OPENAI_API_KEY` in `.env` and, once
per machine, `uv sync && uv run playwright install chromium-headless-shell`.

**1. Live: draw something and animate it**

```bash
open tools/draw.html
```

Draw, type what should happen, and press **Save SVG**; the file goes to `~/Downloads`. Then:

```bash
uv run ksa animate ~/Downloads/drawing.svg
```

- It prints `round 0: … best 3.50`, `round 1: …`, `round 2: …`, then opens a page with the input, the animation and
  the critic's notes. Output goes to `runs/animate/<time>-<name>/`.
- The intent comes from the drawing page; to override it, add it as a second argument in quotes.
- For a logo intro that builds up to the drawing, add `--anchor end`. For a textbook figure, add `--category diagram`.
- For a faster take (about 45 seconds, no revisions), add `--method oneshot`.
- The playbook is optional (`--playbook playbooks/train-v1.json`); it didn't reliably help on the larger test set.

**2. Video shot: the loop fixing the pendulum** (about 3 minutes; screen-record the terminal, then speed it up)

```bash
uv run ksa run --method loop --cases pendulum
```

Then open the candidates in order (r0n0 is the first sample, r1n* are revisions, the best is listed in `tree.json`):

```bash
open runs/*-loop_k2_b1_c2_r2/pendulum/nodes/*/render/anim.gif
```

**3. Video shot: the results comparison**

```bash
open runs/compare.html
```

The shareable version is the claude.ai page in the table at the top. To rebuild the comparison from other runs, use
`uv run ksa compare <one_shot run> <best_of_6 run> <loop run>`.

**4. Video shot: the playbook**

```bash
cat playbooks/train-v1.json
```

Scroll through `lessons`, then `history`, which records what changed after each training drawing and why.

**5. Numbers for the slides**

```bash
uv run ksa report runs/v2/*/2026* --split test
```

```bash
uv run ksa lessons --playbook playbooks/train-v2.json --baseline runs/v2/oneshot-val-*/2026* --with runs/v2/pbsel-val-*/2026*
```

**6. Submission checklist (by Sun 14:30)**
- [ ] Repo public, README results current, `playbooks/` committed.
- [ ] A 2-minute video (shots 1–4), uploaded to YouTube, Drive or Loom.
- [ ] A short description: the one-sentence story, plus the results table.
- [ ] Track: Open. Challenges: Originator (upload the Claude Code sessions); Modal if the fan-out lands.

## Good moments for the demo video

- **Pendulum, r0n0 → r1n0:** the first sample swings the wrong way; after seeing its own frames, the revision
  swings toward the arrow through the vertical (critic 3.00 → 4.00, final 4.25).
- **Spring–mass:** one-shot 3.17 vs. loop 4.17 under the held-out judge.
- **Sun and bolt logo intros:** build up from nothing to the finished logo, after the anchor-frame fix.
- **Windmill:** the contact-sheet aliasing story; a correct spin that the critic first called "jumpy".
