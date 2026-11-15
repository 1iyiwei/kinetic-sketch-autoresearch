# Design

## Research question

Can an autonomous loop that **generates, renders, critiques and revises** animation programs turn static
drawings (sketches, textbook diagrams, cartoons, logos) into better stylized animations than one-shot LLM
generation **with the same compute**? And does the system get better from its own results across drawings?

Hypotheses:
- **H1:** critique-and-revise beats both one-shot generation and best-of-K sampling at equal cost. Seeing the
  rendered motion catches errors that reading the code cannot: wrong direction, wrong pivot, parts flying off.
- **H2:** lessons distilled from earlier cases (the *playbook*) raise first-try quality on new, held-out cases.
- **H3:** how the critic sees the motion matters. Evenly spaced contact sheets alias; adding consecutive frames
  removes false "jumpy" verdicts. (We already saw this on the windmill.)

## How it maps to judging (5 × 20%)

| Criterion | What we show |
| --- | --- |
| Research rigour | Train/test split, equal-compute baselines, ablations, judge noise measured |
| Novelty | Autoresearch for *stylized animation*: a visual domain, a critic that watches motion, and a playbook that grows |
| Results | Held-out judge score and win rate vs. baselines; live demo on a new drawing |
| Autonomy & self-improvement | The loop picks what to fix, revises and keeps the best with no human; the playbook learns across cases |
| Interpretability | Every model call logged; the per-case search tree with renders, critiques and decisions |

## System

```
drawing (SVG) + intent
        │
        ▼
 ┌─ generate K variants ──► render (headless, deterministic) ──► critic (vision, rubric) ─┐
 │        ▲                                                                              │
 │        └──── revise best candidates using issues + fixes + render errors ◄────────────┘
 │                                    (until budget or plateau)
 ▼
best program ──► held-out judge (different model, repeated) ──► results
        │
        └──► distill lessons into the playbook (train cases only) ──► used by the generator on later cases
```

- **Program contract:** self-contained HTML defining `window.ksaRender(t)` as a pure function of time
  (see the README). Determinism makes every candidate reproducible and comparable.
- **Inner loop (per case):** beam search. Each round, revise the top B candidates, each into M children,
  steered by the critic's issues and fixes, and keep the best by critic score. Budget: R rounds, or stop
  once there's no gain. Log the tree: each node's program, render, critique, parent and score.
- **Outer loop (self-improvement):** after each train case, an analyst call turns what fixed failures into
  short, general lessons or helper snippets for the playbook. Examples: "rotate rigid assemblies about the hub
  center"; "a released pendulum swings toward the vertical first"; a damped-oscillation helper. The generator
  receives the playbook. Measure on the test cases only.
- **Critic vs. judge:** the critic's score is the loop's *objective*, maximized by search, not by training. The loop
  keeps the candidates the critic scores highest, returns the highest-scoring one, and steers each revision with the
  critic's issues and fixes; no weights or parameters change. Because the search targets this critic, it can find
  programs that exploit its blind spots without being better animations. So we report scores from a separate
  *judge* the loop never sees (a different model, repeated 3×). Evidence that the split matters: best-of-6, which
  only selects by critic score, raised the critic's mean (3.75 → 4.03) but not the judge's (3.58 → 3.60).

### Components: model calls vs. plain code

The roles below are not separate autonomous agents. One deterministic Python program (`search.py`, driven by
`cli.py`) runs the search and decides what happens next. It calls a model at fixed points, each with its own
system prompt and output format. Only the model calls use an LLM.

| Component | What it is | Model (as run on Sat) | Code |
| --- | --- | --- | --- |
| Orchestrator | Plain code: beam search, keep the best, stop rules, logging | none | `search.py` |
| Generator | Writes an animation program from the drawing (SVG + image) and intent | `gpt-5.5` | `generate.one_shot` |
| Reviser | The same generator model with a different prompt: its program, its own rendered frames, the critique | `gpt-5.5` | `generate.revise` |
| Renderer | Plain code: headless Chromium steps `ksaRender(t)`, saves frames, GIF, contact sheets | none | `render.py` |
| Critic | Hybrid: fidelity measured in code (ink-overlap F1); a vision model scores intent, motion, integrity and lists issues and fixes | `gpt-5.5` | `critic.py` |
| Judge | The same critic code with a different model, run 3× on final results only; never seen by the loop | `gpt-5.4` | `ksa judge` |
| Analyst | After a training drawing, rewrites the playbook from that drawing's search tree | `gpt-5.5` | `playbook.update` |
| Selector | Picks the playbook lessons that apply to a drawing | `gpt-5.4-mini` | `playbook.select` |

### What "learning" and "train" mean here

- **No model weights are updated.** All models are used as-is through their APIs.
- **Inner loop:** search over programs for one drawing. Nothing persists except the best program.
- **Outer loop:** the *playbook*, a JSON list of text lessons that the analyst rewrites after each training drawing
  and the generator reads in its prompt. This is learning in the prompt (in-context), not in the weights.
- **"Train", "val" and "test"** are splits of the benchmark drawings. *Train* drawings are the ones the playbook
  learns from; *val* drawings are used to prune lessons; *test* drawings are only used to measure.
- **Result:** prompt lessons did not reliably help (see `playbooks/README.md`); the inner loop did.
- **Proposed next step, not done yet:** real weight training. Fine-tune an open model (`Qwen/Qwen3.6-35B-A3B`)
  with LoRA on Tinker, using the best programs the loop found on the train drawings, and compare one-shot before
  and after on the test drawings.

## Experiments

| Method | Purpose |
| --- | --- |
| One-shot | Baseline (done: mean 3.23 / 5 under the critic) |
| Best-of-K one-shot | Equal-compute baseline: is revision better than just sampling more? |
| Loop (critique → revise) | H1 |
| Loop + playbook | H2, on held-out cases |
| Ablations: overview sheet only (no strip); blind revise (render errors only, no vision critique) | H3; is it the eyes that help? |

Measure judge noise first: re-judge the same renders n times, so differences smaller than the noise are not
claimed. Track cost (tokens, seconds) for every method. Plot score vs. compute.

**Benchmark:** grow from 10 to about 20 cases, spread across the four categories, then split into train and
test. Optionally add a few drawings from teammates or passers-by, made on the spot, as truly unseen tests.

## Infrastructure

- **Modal:** run the render + critique of each candidate in parallel sandboxes (a Playwright image), so a
  beam round of B×M candidates takes about as long as one candidate. This is our entry for *Best use of Modal*.
- **Models:** OpenAI (event credits). Generator `gpt-5.5`; critic and judge set by env vars, with the judge
  being a different model from the critic.
- **Trace viewer:** a static HTML page per run showing the search tree (thumbnails, scores, critic notes,
  diffs between parent and child). It is both the demo and the interpretability evidence.
- **Originator challenge:** develop with Claude Code / Codex and upload the agent sessions.

## Team roles (people, team of 3–5)

| Role | Owns |
| --- | --- |
| Lead / loop (Li-Yi) | Loop and playbook design, generator and critic prompts, benchmark, pitch |
| Infra | Modal app: Playwright image, parallel render and critique, the fan-out API the loop calls |
| Eval | Judge protocol, noise estimate, baselines and ablations runner, statistics and plots |
| Demo (optional) | Trace viewer / gallery, drawing input for the live demo, the 2-minute video |

The interfaces are already in the code: `Renderer.render(html) -> RenderResult`,
`critic.critique(...) -> {scores, issues, fixes, overall}`, and runs as `results.json` + `llm_calls.jsonl`.
So each role can work in parallel against these.

## Timeline (PT)

| When | Milestone |
| --- | --- |
| Sat 14:00 | Team formed; roles assigned; everyone runs `ksa baseline` locally |
| Sat 18:00 | Inner loop working on 3 cases; Modal fan-out prototype; judge noise measured |
| Sat 23:00 | Full benchmark with train/test split; loop vs. one-shot vs. best-of-K results |
| Sun 08:00 | Playbook (outer loop) run on train → test; ablations |
| Sun 11:00 | Freeze results; trace viewer polished; live-demo drawing path rehearsed |
| Sun 12:00 | Team registered on the platform (hard deadline) |
| Sun 13:30 | Demo video recorded; README results table final |
| Sun 14:00 | Submit (repo link, 2-minute video, description, track = Open, challenges = Modal, Originator) |

## Risks

- **Critic noise or bias drives the loop the wrong way.** Use structured output, repeated judging, a separate
  judge, and keep the critic and judge prompts apart.
- **Cost and latency.** Low reasoning effort in the inner loop, cheaper critic models, a small beam, and
  Modal parallelism.
- **Overfitting to the benchmark.** Keep the test cases untouched; add drawings made on the spot.
- **Live-demo failure.** Have pre-computed runs ready to replay from the trace viewer.
