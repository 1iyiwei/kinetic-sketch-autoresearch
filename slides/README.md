# Slides

Twelve HTML slides for the pitch and the demo video. Open the first one:

```bash
open slides/index.html
```

Move with **← / →** (or Page Up / Page Down, or space), or with the previous/next links at the bottom of each slide.
The stage is 1280 × 720 and scales to the window; use the browser's full screen for recording.

Input drawings are the committed SVGs, and animations play live from the committed programs in
[`results/`](../results/README.md), so the slides show the exact animations the judge scored. They work offline,
except the web fonts (which fall back to system fonts).

| # | Slide | Shows |
| --- | --- | --- |
| 1 | Title | The one-sentence story; a drawing and the loop's animation |
| 2 | The problem | The pendulum and the one-shot first attempt swinging the wrong way, with the critic's note |
| 3 | The system | Diagram of the inner loop (generator, renderer, critic, reviser), the judge, and the outer loop (analyst, playbook) |
| 4 | The loop fixing it | r0n0 → r1n0 → r2n1 playing, with the critic's suggested fix |
| 5 | Results | One-shot vs. best-of-6 vs. loop on 10 drawings (held-out judge) |
| 6 | Side by side | Pendulum and spring–mass under all three methods |
| 7 | Held-out test | 7 test drawings: one-shot vs. loop; spring–mass and fish playing |
| 8 | Critics | Aliasing (overview sheet vs. consecutive strip), hallucinated fidelity errors, judge noise |
| 9 | Anchor fix | Sun and bolt logo intros before and after the anchor-frame fix |
| 10 | Playbook | The outer loop and its honest result |
| 11 | Limits | Complex drawings: Newton's cradle and gears, one-shot vs. loop |
| 12 | Next | Tinker distillation, Modal, try it yourself |

## Edit

The slides are generated; edit [`build.py`](build.py), then rebuild:

```bash
uv run python slides/build.py
```

Per-case scores come from the `results/*/manifest.json` files; averages over several runs are in `NUMBERS` at the
top of `build.py` (copied from the README tables). The two windmill images in `assets/` are copied from `runs/` when
present.
