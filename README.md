# Kinetic Sketch Autoresearch

Built at the [SF AI Research Hackathon](https://iterate.inc/ai-research) (Iterate, Nov 14–15, 2026), Open Track.

**Question:** can an autonomous research loop (generate an animation program → render it → have a
vision critic review it → revise) turn static drawings into better *stylized* animations than one-shot
LLM generation? Inputs are rough sketches, textbook diagrams, cartoons and flat logos. The target is
cartoon, whiteboard and motion-graphics motion, not photorealism.

## Outcome

<table>
<tr>
<td align="center" width="100%">
<a href="https://youtu.be/q5HoxP6mZOM">
<img src="https://img.youtube.com/vi/q5HoxP6mZOM/hqdefault.jpg" width="360" alt="Video">
<br>Video</br>
</a>
</td>
</tr>
<tr>
<td align="center" width="100%">
<a href="docs/demos.md">
<img src="demos/screenshot.png" width="360" alt="Slides">
<br>Demos</br>
</a>
</a>
</td>
</tr>
</table>

## Status

| Piece | State |
| --- | --- |
| Benchmark: 23 drawings (sketch, diagram, cartoon, logo), with train, val, test and complex splits | done: `benchmark/` |
| Deterministic headless renderer (frames, GIF, contact sheets) | done: `src/ksa/render.py` |
| One-shot baseline generator | done: `src/ksa/generate.py` |
| Hybrid critic: measured fidelity + vision rubric, structured output | done: `src/ksa/critic.py` |
| Research loop: beam search with critique → revise | done: `src/ksa/search.py` |
| Equal-compute baselines (one-shot, best-of-K), held-out repeated judge | done: `src/ksa/cli.py` |
| Playbook: lessons distilled from search trees, train/test split | done: `src/ksa/playbook.py`, `playbooks/` |
| Report across runs (grouped by method, paired wins) | done: `src/ksa/report.py` |
| Per-drawing lesson selection; per-lesson credit (`ksa lessons`) | done: `src/ksa/playbook.py`, `src/ksa/lessons.py` |
| Playbook v2 on 8 train / 3 val / 7 test drawings | done: no reliable gain (see below) |
| Open models on Tinker: Qwen generator and critic, Nemotron-VL judge (`tinker:` models in `llm.py`) | done: mixed result (see below) |
| Distill the loop into an open model (Qwen on Tinker) | next |
| Exa: web references for the reviser inside the loop (`--exa`), and finding a drawing on the web | done: `src/ksa/exa.py` |
| Sketch pad with an Animate button, live progress and the program's code (`ksa serve`) | done: `src/ksa/serve.py`, `tools/draw.html` |
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

## Expanded benchmark: 23 drawings (Sat 15:20)

The benchmark grew to 23 drawings in four splits: **train** (8, the playbook learns from these), **val** (3, for
pruning lessons), **test** (7, held-out numbers), and **complex** (5: Newton's cradle, meshing gears, a domino chain,
a cat jumping onto a box, and a three-beat story). The complex tier is never learned from and is reported separately.
One-shot ran 3 times per split; the loop ran once. Held-out judge `gpt-5.4`, 3× each.

| Split | One-shot (3 runs) | Loop (1 run) | Loop vs. one-shot | Wins / losses / ties |
| --- | --- | --- | --- | --- |
| Test (7) | 3.78 | **3.99** | +0.21 | 6 / 1 / 0 |
| Complex (5) | 3.60 | 3.52 | −0.08 | 1 / 3 / 1 |

- **On single-subject drawings the loop's gain holds up on the bigger test set.** It wins on 6 of 7 drawings, the
  largest gain again on the spring–mass (3.47 → 4.08).
- **On complex drawings it doesn't help yet.** Multi-object interactions are hard for both methods: Newton's cradle
  scores 2.39 one-shot and 2.33 with the loop. The critic can name what's wrong ("the right ball should swing out
  as the left one hits"), but two rounds of revision don't fix coordinated physics across several bodies. Possible
  next steps: more rounds on complex drawings, a physics helper in the generator's toolbox, or splitting the
  animation into beats that are revised separately.

Run directories: `runs/v2/oneshot-{val,test,complex}-{1,2,3}`, `runs/v2/loop-{test,complex}`.

## Playbook: does learning carry over to new drawings? (Sat 14:50)

See [`playbooks/README.md`](playbooks/README.md) for the file format and how the playbook files relate.

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
| One-shot + all 12 lessons | 3 | 3.68 | +0.08 | 4 / 1 / 0 |
| **One-shot + selected lessons** | 3 | **3.74** | **+0.14** | 4 / 1 / 0 |
| Loop | 1 | 3.90 | +0.30 | 3 / 1 / 1 |
| Loop + all 12 lessons | 1 | 3.87 | +0.27 | 3 / 2 / 0 |
| Loop + selected lessons | 1 | 3.92 | +0.32 | 3 / 1 / 1 |

**Giving every lesson to every drawing transfers in both directions:**
- **Positive transfer where a lesson fits.** The spring–mass is an oscillator the playbook never saw, but its
  lessons came from the pendulum. It improved in every run: 3.17–3.50 without, 3.67–4.25 with.
- **Negative transfer where a lesson is misapplied.** The windmill needs none of these lessons, but gets all 12.
  It dropped in every run (4.50 → 3.83–4.25), and the judge now calls its spin "strobey".

**Per-drawing lesson selection.** Before generating, a small model (`gpt-5.4-mini`) looks at the drawing and its
intent and picks only the lessons for the motion and physics the animation needs, matching on the kind of motion
rather than the object's name. Selecting none is allowed. The selection and its reasons are saved per case
(`playbook_selected.json`). On the training drawings it recovers each drawing's own lessons. On the test drawings it
gives the spring–mass the oscillator and diagram lessons, the windmill only the pivot-rigging lesson, and the logos
the build-up-intro and settle lessons.
- One-shot with selected lessons scores 3.74, against 3.68 with all lessons and 3.60 with none. The windmill
  recovers (4.00 with all lessons → 4.42 selected, 4.50 with none).
- Per-lesson credit (`ksa lessons`): every lesson that was selected on a test drawing has a non-negative mean
  effect. Lessons 6 and 8 (oscillator, diagram guides) gained +0.22 on the spring–mass; lesson 7 (pivot rigging)
  gained +0.42 on the fish and lost 0.08 on the windmill.
- **How strong is this?** It's a trend, not yet significant. Per-run means with selection are 3.72 / 3.63 / 3.88
  against 3.52 / 3.70 / 3.58 without, about 1.5 standard errors apart, from 3 runs on 5 drawings.
- **Disclosure:** the selector's wording was revised once after seeing its picks on the test drawings (the first
  version matched object names and gave the spring–mass no lessons). The revised wording is generic and names no
  test drawing. `ksa lessons --prune-to` can drop lessons that hurt, but pruning on test results and then reporting
  test scores would be circular, so it is not used for any number here. It needs a separate validation split.
- **Next:** more drawings (a validation split for pruning, and enough cases for significance), and per-lesson
  credit computed during learning.

Reproduce: `uv run ksa learn --split train --cases pendulum,ball_ramp,stick_wave,rocket,sun_logo --lessons all`,
then `uv run ksa run --method oneshot --split test --playbook playbooks/train-v1.json --lessons {all,select}`,
`ksa judge` each run, `uv run ksa report <runs...> --split test`, and
`uv run ksa lessons --playbook playbooks/train-v1.json --baseline <no-playbook runs> --with <selected runs>`.

### Playbook v2 on the larger benchmark: no reliable gain (Sat 15:50)

Learned with selection on all 8 train drawings ([`playbooks/train-v2.json`](playbooks/train-v2.json), 12 lessons),
pruned on the 3 val drawings, and tested on the 7 test drawings (one-shot, 3 runs each, held-out judge):

| One-shot with… | Judge (7 test drawings) | vs. no playbook | Wins / losses / ties |
| --- | --- | --- | --- |
| no playbook | 3.78 | — | — |
| v2, selected lessons | 3.63 | −0.15 | 2 / 5 / 0 |
| v2 after pruning on val, selected lessons | 3.74 | −0.04 | 3 / 2 / 2 |
| *(for contrast)* the loop, no playbook | 3.99 | +0.21 | 6 / 1 / 0 |

- **Pruning on val dropped nothing.** No selected lesson had a negative mean effect over ≥ 2 val drawings, so the
  pruned playbook is *identical* to v2. The two rows differ by 0.11 from run-to-run noise alone. That is as large as
  every playbook effect we measured, including v1's +0.14.
- **Selection is shaky on new kinds of drawings.** On val it gave the flower a pendulum lesson and the clock a
  rigid-rod lesson; both cost 0.11.
- **Conclusion:** lessons in the prompt don't reliably improve generation at this scale, while the render → critique
  → revise loop does: +0.33 on the first 10 drawings, +0.30 on the 5-drawing test, +0.21 on the 7-drawing test,
  winning on 6 of 7. To make improvements stick, the next step is to put them in the model's weights rather than
  its prompt: fine-tune an open model on the programs the loop found (see "Next: distill the loop into the model").

### Open models on Tinker (Sun 10:45)

The same pipeline now runs entirely on open models hosted on [Tinker](https://thinkingmachines.ai/tinker/), with no
OpenAI calls: any model named `tinker:<base model>` goes through Tinker's sampler, with images spliced in as image
chunks where the chat template puts them. We used `Qwen/Qwen3.6-35B-A3B` (thinking off) as the generator and the
in-loop critic, and `nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-BF16`, a different model family, as the held-out
judge (3 repeats). To compare like with like, the earlier GPT runs on the same 7 test drawings were re-judged by
Nemotron too.

| Generator (critic) | One-shot (3 runs) | Loop (1 run) | Loop vs. one-shot, wins / losses | Tokens per case, one-shot / loop |
| --- | --- | --- | --- | --- |
| gpt-5.5 (gpt-5.5) | 4.33 | 4.31 | 4 / 3 | 9K / 74K |
| Qwen3.6-35B-A3B (Qwen3.6-35B-A3B) | 3.28 | 3.41 | 3 / 4 | 8K / 50K |

Held-out judge: Nemotron-3.5-Super-VL, mean of 3. Browse it at [`results/tinker-test/`](results/tinker-test/index.html).

What this shows:

- **The loop rescues broken programs.** Qwen's one-shot windmill crashed on its first frame (it called `.find` on a
  DOM NodeList) and its spring–mass barely moved; the loop rendered, saw and fixed both (windmill 3.11 → 4.83,
  spring–mass 1.87 → 3.53, one-shot averaged over 3 runs).
- **A weak critic misleads it elsewhere.** The Qwen critic can be lenient (it rated one one-shot run 3.98 where the
  judge gave 3.30), so the search often stopped early at a candidate the judge liked less (bolt logo 4.44 → 2.93).
  The loop is only as good as its critic.
- **The GPT loop's gain does not survive a second judge.** Under gpt-5.4 the GPT loop beat one-shot by +0.21 on these
  7 drawings (6 of 7 wins); under Nemotron it ties (−0.02, 4 of 7). The two judges correlate only weakly per case
  (Pearson 0.43 over 28 judged animations), and Nemotron is more lenient (mean 4.32 vs. 3.83) and noisier
  (within-case sd 0.15–0.45 vs. 0.08–0.18). With 7 drawings, a +0.2 difference is within what the choice of judge
  changes; the large, consistent effect is repairing failures, not polishing good programs.

### Next: distill the loop into the model (Tinker)

Every loop run leaves training data: (drawing, intent) → the best program found, plus critic scores for every
candidate. Plan: fine-tune `Qwen/Qwen3.6-35B-A3B` with LoRA on [Tinker](https://thinkingmachines.ai/tinker/) on the
loop's best programs for the train drawings, then compare one-shot before and after on the held-out test drawings.
Smoke test: base Qwen3.6-35B-A3B on Tinker wrote a valid windmill program in one shot (about 4.3K tokens, 76 s),
which the held-out judge scored 4.50, against 4.42 for `gpt-5.5` one-shot on that drawing (one sample).

## Run

```bash
uv sync
uv run playwright install chromium-headless-shell
export OPENAI_API_KEY=...            # or put it in .env
uv run python benchmark/make_cases.py   # regenerate the benchmark SVGs (already committed)
uv run ksa serve                        # drawing page with an Animate button: http://127.0.0.1:8765
uv run ksa run --method loop --exa      # the loop, with web references (Exa) before each revision
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
A model named `tinker:<base model>` runs on Tinker (needs `TINKER_API_KEY`); for example, entirely on open models:

```bash
export KSA_GEN_MODEL=tinker:Qwen/Qwen3.6-35B-A3B KSA_CRITIC_MODEL=tinker:Qwen/Qwen3.6-35B-A3B
uv run ksa run --method loop --split test --out runs/qwen/loop-test
uv run ksa judge runs/qwen/loop-test/<run> --model tinker:nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-BF16 --repeats 3
uv run ksa report runs/qwen/*/*/ --split test --judge tinker:nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-BF16
```

### Exa: what the loop doesn't know

The critic can say *that* a motion is wrong ("the flag does not wave", "the pendulum swings the wrong way"), but
neither it nor the generator can look up how the thing really moves. With `--exa` (needs `EXA_API_KEY`), before
revising a program the loop searches the web with [Exa](https://exa.ai) for the drawing's intent, steered by the
critic's top motion issue, and gives the reviser short excerpts with their sources, for example that a flag's
flutter is "a travelling wave growing in amplitude as it progresses towards the trailing edge". There is one search
per revised program, shared by its children; every search (query, sources, excerpts) is saved to the run's
`exa.jsonl`, and each revised node in `tree.json` records which search it was given. A failed search is logged and
the loop goes on without it.

The sketch pad uses Exa a second way: "Find a drawing" searches SVG Repo, Wikimedia Commons and Openclipart for a
description. The server downloads each file, strips scripts, event handlers and external references, names
unnamed shapes (`p1`, `p2`, …) so the generator can refer to parts, and fits it into a 512 × 512 drawing. You can
draw on top of it before animating. Licences vary by file; the page links each source.

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

Slides: [`slides/`](slides/README.md) (`open slides/index.html`). Replayable results: [`results/`](results/README.md). Design, metrics and team roles: [docs/design.md](docs/design.md). Shareable result pages and demo material: [docs/demos.md](docs/demos.md).

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
