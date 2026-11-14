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
- **Critic vs. judge:** the loop optimizes the *critic*. We report scores from a separate *judge* (a
  different model, repeated 3×, mean ± sd), plus pairwise preference against the baseline, so we don't just
  report how well the loop overfits its own critic.

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

## Roles (team of 3–5)

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
