# Kinetic Sketch Autoresearch

Built at the [SF AI Research Hackathon](https://iterate.inc/ai-research) (Iterate, Nov 14–15, 2026), Open Track.

**Question:** can an autonomous research loop (generate an animation program → render it → have a
vision critic review it → revise) turn static drawings into better *stylized* animations than one-shot
LLM generation? Inputs are rough sketches, textbook diagrams, cartoons and flat logos. The target is
cartoon, whiteboard and motion-graphics motion, not photorealism.

## Status

| Piece | State |
| --- | --- |
| Benchmark: 10 cases (sketch, diagram, cartoon, logo) with intents | done: `benchmark/` |
| Deterministic headless renderer (frames, GIF, contact sheets) | done: `src/ksa/render.py` |
| One-shot baseline generator | done: `src/ksa/generate.py` |
| Hybrid critic: measured fidelity + vision rubric, structured output | done: `src/ksa/critic.py` |
| Research loop: beam search with critique → revise | done: `src/ksa/search.py` |
| Equal-compute baselines (one-shot, best-of-K), held-out repeated judge | done: `src/ksa/cli.py` |
| Playbook: lessons distilled from search trees, train/test split | done: `src/ksa/playbook.py`, `playbooks/` |
| Report across runs (grouped by method, paired wins) | done: `src/ksa/report.py` |
| Per-drawing lesson selection; prune lessons that hurt | next |
| Parallel rendering and critique on Modal | next |

## Results (Sat 13:15, 10 cases)

Generator `gpt-5.5` at low effort. The in-loop critic is `gpt-5.5` with measured fidelity. The **held-out judge**
is a different model (`gpt-5.4`), run 3× per final animation and averaged; its within-case sd is 0.08–0.18.
Every method gets the same number of generator calls: best-of-6 and the loop each make 6 per case.

| Method | Judge (held-out) | Critic (in-loop) | Tokens (all cases) |
| --- | --- | --- | --- |
| One-shot | 3.58 | 3.75 | 91K |
| Best-of-6 (sample 6, keep the critic's best) | 3.60 | 4.03 | 540K |
| **Loop** (2 samples, then 2 rounds revising the best into 2 children) | **3.91** | 4.25 | 721K |

Per case, under the judge, the loop beats one-shot on 7 of 10 cases (2 losses, 1 tie; mean +0.33)
and beats best-of-6 on 6 of 10 (2 losses, 2 ties; mean +0.31). Its biggest wins are where one-shot misreads the
physics: pendulum 3.08 → 4.25, spring–mass 3.17 → 4.17. Run directories: `runs/20261114-131334-*`.

- **Sampling more doesn't help; revising does.** Best-of-6 raises the critic's score (3.75 → 4.03) but not the
  judge's (3.58 → 3.60), so picking the max of noisy critic scores mostly selects for critic noise. The loop's
  gain survives the change of judge.
- **Caveats.** Only 10 cases and one seed per method. The loop used about 33% more tokens than best-of-6 (its
  revise prompts include the program and its renders). The critic and judge share the measured fidelity term.
  Next: more cases, more seeds, and a token-matched best-of-K.

## Playbook: does learning carry over to new drawings? (Sat 14:50)

`ksa learn` runs the loop on the 5 **train** drawings one at a time. After each one, an analyst model reads that
search tree: the first attempts' issues, the code diff of the fix that won, and what is still wrong. It then
rewrites the playbook, keeping at most 12 general lessons and never naming the drawing. Later drawings get the
lessons in their prompts. Result: [`playbooks/train-v1.json`](playbooks/train-v1.json), with 12 lessons and a
`history` of each update and its reason (for example "added lessons on damped oscillator phase and fixed-pivot
rigging, because the search improved by replacing an incorrect outward drift with a damped cosine rotation about
the drawn pivot").

Measured on the 5 **test** drawings, which it never saw (held-out judge `gpt-5.4`, 3× each; one-shot ran 3 times
with and 3 times without the playbook):

| Method | Runs | Judge (held-out) | vs. one-shot | Wins / losses / ties |
| --- | --- | --- | --- | --- |
| One-shot | 3 | 3.60 | — | — |
| One-shot + playbook | 3 | 3.68 | +0.08 | 4 / 1 / 0 |
| Loop | 1 | 3.90 | +0.30 | 3 / 1 / 1 |
| Loop + playbook | 1 | 3.87 | +0.27 | 3 / 2 / 0 |

**The overall gain is small, within run-to-run noise; per drawing it is clear in both directions:**
- **Positive transfer where a lesson fits.** The spring–mass is an oscillator the playbook never saw, but its
  lessons came from the pendulum. It improved in every run: 3.17–3.50 without, 3.67–4.25 with.
- **Negative transfer where a lesson is misapplied.** The windmill needs none of these lessons, but gets all 12.
  It dropped in every run (4.50 → 3.83–4.25), and the judge now calls its spin "strobey".
- **Next:** give each drawing only the lessons whose `applies_to` matches it, and track each lesson's effect on later
  cases so lessons that hurt are pruned. Also more train/test drawings: 5 + 5 is small.

Reproduce: `uv run ksa learn --split train --cases pendulum,ball_ramp,stick_wave,rocket,sun_logo`, then
`uv run ksa run --method oneshot --split test --playbook playbooks/train-v1.json`, `ksa judge` each run, and
`uv run ksa report <runs...> --split test`.

## Run

```bash
uv sync
uv run playwright install chromium-headless-shell
export OPENAI_API_KEY=...            # or put it in .env
uv run python benchmark/make_cases.py   # regenerate the benchmark SVGs (already committed)
uv run ksa run --method oneshot         # one-shot baseline
uv run ksa run --method bestof --k 6    # equal-compute baseline: sample 6, keep the critic's best
uv run ksa run --method loop            # k=2 samples, then 2 rounds of revising the best into 2 children
uv run ksa run --method loop --cases fish,pendulum --rounds 3   # subset, more rounds
uv run ksa judge runs/<run-dir> --model gpt-5.4 --repeats 3     # held-out judge, repeated
uv run ksa compare runs/<one_shot> runs/<best_of_6> runs/<loop>   # side-by-side page -> runs/compare.html
uv run ksa learn --split train --out-playbook playbooks/train-v2.json   # learn lessons, case by case
uv run ksa run --method oneshot --split test --playbook playbooks/train-v1.json   # use them on held-out drawings
uv run ksa report runs/<run> runs/<run> ... --split test     # judged runs grouped by method
uv run pytest
```

Each run writes `runs/<stamp>-<method>/`, which holds:
- for each case: `input.png`, `tree.json` (every node: parent, round, score, critique, compute), and
  `nodes/<id>/` with `program.html`, `render/` (frames, `anim.gif`, `sheet.png`, `strip.png`) and `critique.json`;
- `results.json`, `summary.md`, and a gallery `index.html` (best node per case, score by round);
- `llm_calls.jsonl`, which logs every model call with its prompt, response, tokens and latency (the decision trace).

Models are set with the env vars `KSA_GEN_MODEL`, `KSA_CRITIC_MODEL`, `KSA_GEN_EFFORT` and `KSA_CRITIC_EFFORT`.

## Animation contract

A program is one self-contained HTML document with a 512x512 stage that defines
`window.ksaRender(t)`, a **pure function of time**. Each benchmark case names an anchor frame (the first, or the last for build-up intros) that must reproduce the drawing. The renderer steps `t` itself (default 4 s at
12 fps), so renders are deterministic and reproducible. A program that breaks the contract or throws
scores zero, and its errors are fed back.

## Findings so far

- **Contact sheets alias.** With only 8 evenly spaced frames, a correctly spinning 4-blade windmill
  looked to the critic like it was "jumping between repeated poses" and "deforming" (scored 3.25).
  Adding a strip of consecutive frames, and telling the critic about aliasing, fixed the verdict (4.25).
- **The judge is noisy.** The same spring–mass render scored 4.00 and then 2.50 on a re-judge. Benchmark
  numbers need repeated judging and a held-out judge model, and the loop must not overfit its own critic.
- **The baseline makes real semantic mistakes.** For example, the pendulum swings away from the side the
  diagram's arrow indicates, and never passes through the vertical. These are the failures the loop should fix.
- **Vision critics hallucinate fidelity errors, and a reviser chases them.** The critic kept reporting that
  the fish or pendulum in frame 0 was "smaller and shifted"; the ink bounding boxes were pixel-identical to the
  input. Revising against those phantom issues made programs *worse* (pendulum 2.25 → 1.75). Now fidelity
  is measured (ink-overlap F1 between the input and frame 0), the vision model judges only motion, and the
  reviser is told the reviewer can be wrong. With that hybrid critic, the loop fixes real errors: the pendulum went
  3.00 → 3.75 → 4.25 and now swings toward the arrow through the vertical with decaying amplitude.
- **A measurement can fight the intent.** Requiring frame 0 to match the drawing is wrong for logo intros
  ("the sun scales up from nothing"). Generators showed the full logo at t=0 and then reset it, and the judge
  scored that as jarring; the loop lost on both intro logos. Each case now declares an *anchor* frame (the first
  frame, or the last for build-up intros). Sun went 2.75 → 4.25 and bolt 2.92 → 4.25 under the judge.

Design, metrics and team roles: [docs/design.md](docs/design.md). Shareable result pages and demo material: [docs/demos.md](docs/demos.md).

## Provenance

All code, benchmark data and docs in this repository were written during the event (from Nov 14,
10:00 PT), as the git history shows. Before the event there were only planning notes, kept in a
separate repository: an ideation chat and a summary of the event rules. No code or assets from earlier
projects are used here. The concept builds on the author's prior research on sketch-based animation:
KineticSketch, DrawTalk, and the MotionLang motion DSL.

## Credits

[Playwright](https://playwright.dev) (headless rendering), [Pillow](https://python-pillow.org)
(GIFs and contact sheets), and the [OpenAI API](https://platform.openai.com) (generator and critic).

## License

[Apache-2.0](LICENSE)
