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
| Vision critic (4-criterion rubric, structured output) | done: `src/ksa/critic.py` |
| Research loop (critique → revise, search over variants) | next |
| Parallel rendering and critique on Modal | next |
| Held-out judge, judge-noise estimate, ablations | next |

First baseline (one-shot `gpt-5.5`, critic `gpt-5.5`, both at low effort): **mean 3.23 / 5** over 10 cases.

## Run

```bash
uv sync
uv run playwright install chromium-headless-shell
export OPENAI_API_KEY=...            # or put it in .env
uv run python benchmark/make_cases.py   # regenerate the benchmark SVGs (already committed)
uv run ksa baseline                     # all cases; or --cases fish,pendulum
uv run ksa judge runs/<run-dir> [--model gpt-5.4]   # re-score existing renders
uv run pytest
```

Each run writes `runs/<stamp>-baseline/`, which holds:
- for each case: `input.png`, `program.html`, `render/` (frames, `anim.gif`, `sheet.png`, `strip.png`) and `critique.json`;
- `results.json`, `summary.md`, and a gallery `index.html`;
- `llm_calls.jsonl`, which logs every model call with its prompt, response, tokens and latency (the decision trace).

Models are set with the env vars `KSA_GEN_MODEL`, `KSA_CRITIC_MODEL`, `KSA_GEN_EFFORT` and `KSA_CRITIC_EFFORT`.

## Animation contract

A program is one self-contained HTML document with a 512x512 stage that defines
`window.ksaRender(t)`, a **pure function of time**. The renderer steps `t` itself (default 4 s at
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

## Credits

[Playwright](https://playwright.dev) (headless rendering), [Pillow](https://python-pillow.org)
(GIFs and contact sheets), and the [OpenAI API](https://platform.openai.com) (generator and critic).
The concept builds on the author's prior research on sketch-based animation. All code in this repository
was written during the event.
