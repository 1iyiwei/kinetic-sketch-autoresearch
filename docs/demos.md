# Demos

Shareable result pages and demo material, newest first. Pages on claude.ai are private until
their owner shares them (Share menu on the page).

| When (PT) | What | Link | Source runs |
| --- | --- | --- | --- |
| Sat Nov 14, 13:50 | First results: loop vs. one-shot vs. best-of-6 on 10 cases. Headline judge scores, the pendulum search tree, all cases side by side, findings | [Kinetic Sketch Autoresearch](https://claude.ai/artifact/52zhVRsQdXewQp3pxPYqPH) | `runs/20261114-131334-{one_shot,best_of_6,loop_k2_b1_c2_r2}` |

## Regenerating locally

Run outputs live in `runs/` (gitignored). To rebuild the side-by-side page from any set of runs:

```bash
uv run ksa compare runs/<one_shot> runs/<best_of_6> runs/<loop>   # writes runs/compare.html
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
| 1:05–1:30 | `playbooks/train.json` growing case by case; then a held-out drawing animated with the playbook | "After each drawing it writes down what fixed it, as general lessons. On drawings it never saw, lessons help where they fit (spring–mass, every run) and hurt where they are misapplied (windmill); selecting lessons per drawing removes the misapplied ones (one-shot 3.60 → 3.74)." | Self-improvement |
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
- *Does it generalize?* The playbook is learned on 8 training drawings, pruned on 3 validation drawings, and measured on 7 held-out ones; 5 complex drawings form a separate stress test.

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
uv run ksa animate ~/Downloads/drawing.svg --playbook playbooks/train-v2.json
```

- It prints `round 0: … best 3.50`, `round 1: …`, `round 2: …`, then opens a page with the input, the animation and
  the critic's notes. Output goes to `runs/animate/<time>-<name>/`.
- The intent comes from the drawing page; to override it, add it as a second argument in quotes.
- For a logo intro that builds up to the drawing, add `--anchor end`. For a textbook figure, add `--category diagram`.
- For a faster take (about 45 seconds, no revisions), add `--method oneshot`.
- Before the playbook-v2 runs finish, use `playbooks/train-v1.json`.

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
cat playbooks/train-v2.json
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
