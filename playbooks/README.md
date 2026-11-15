# Playbooks

A playbook is the system's **outer loop**: lessons it carries from one drawing to the next.

- **Inner loop** (one drawing): generate an animation program → render it → a vision critic reviews the frames →
  revise. This is `ksa run --method loop`.
- **Outer loop** (across drawings): after the inner loop finishes a training drawing, an *analyst* model reads that
  drawing's search tree. It sees the first attempts' issues, the code diff of the fix that won, and what is still
  wrong. It then rewrites the playbook as at most 12 short, general lessons. Later drawings get the lessons in the
  generator's prompt. This is `ksa learn`; the code is in [`src/ksa/playbook.py`](../src/ksa/playbook.py).

Lessons must transfer, so the analyst never names the drawing. "The pendulum swings the wrong way" becomes
"for a released pendulum or other suspended oscillator drawn at an extreme, use the drawing as the maximum-
displacement pose with zero initial velocity", and "rotate the rod and bob together about one fixed pivot" is meant
to carry over to anything hinged.

## File format

```json
{
  "lessons": [{"text": "...", "applies_to": "...", "evidence": "..."}],
  "history": [{"ts": "...", "case": "pendulum", "change_note": "...", "n_lessons": 10, "best_score_by_round": [3.0, 4.25, 4.75]}]
}
```

- `lessons`: what the generator gets. `applies_to` says which drawings or motions a lesson is for; `evidence` says
  which observation in the search tree supported it.
- `history`: one entry per update, in learning order. It records which drawing triggered the update, what changed
  and why, and that drawing's best score after each round of its inner loop.

## How the training cases and their order were chosen

- **Which drawings:** the benchmark's `train` split (see `SPLIT` in
  [`benchmark/make_cases.py`](../benchmark/make_cases.py)). Each category (sketch, diagram, cartoon, logo) and a
  build-up logo intro appear in both train and test, so lessons have a chance to transfer.
- **Order:** the order the drawings are listed in `benchmark/cases/cases.json`. For v1 I passed a different order
  on the command line, but a bug at the time ignored it (since fixed: `--cases` now sets the learning order). The
  `history` field always records the real order.
- **Lesson numbering:** roughly the order lessons first appeared, but not strictly. The analyst rewrites the whole
  list after every drawing and may merge, reword or reorder earlier lessons to stay within 12. Use `evidence` and
  `history` to trace where a lesson came from. In v1, lessons 1–5 came from ball_ramp (rolling, bounce, settling),
  6–8 from pendulum, 9–10 from stick_wave, 11 from rocket and 12 from sun_logo.

## The files

| File | What it is | Learned on (in order) | Used for |
| --- | --- | --- | --- |
| `train-v1.json` | First learning run. During learning, the generator got **all** lessons. | ball_ramp → pendulum → stick_wave → rocket → sun_logo (5) | The first held-out test on 5 drawings: one-shot +0.08 with all lessons, +0.14 with per-drawing selection (a trend within noise) |
| `train.json` | Default output of `ksa learn`, kept as the working copy. Currently byte-identical to `train-v1.json`. | — | Nothing on its own; use the versioned files |
| `train-v2.json` | Second learning run, on the larger benchmark. During learning, each drawing got only its **selected** lessons. | the same 5, then bouncing_ball → bird → star_logo (8) | Test on 7 drawings: one-shot −0.15 (no reliable gain) |
| `train-v2-pruned.json` | v2 after pruning on the 3 `val` drawings (`ksa lessons --prune-to`). No lesson met the pruning rule, so its lessons are **identical** to v2; it only adds a "pruned nothing" entry to `history`. | — | Test on 7 drawings: one-shot −0.04. The 0.11 gap to v2 with identical lessons measures run-to-run noise |

## What we learned

- Lessons transfer when they fit and hurt when they don't. With v1 and all lessons, the spring–mass gained in every
  run (oscillator lessons from the pendulum), while the windmill lost in every run (it got launch and bounce advice
  it didn't need).
- Per-drawing selection (a small model picks the lessons that match the drawing's motion) removes most of the harm,
  but on the larger test set the playbook's overall effect is within run-to-run noise.
- Conclusion: prompt lessons are not a reliable way to improve at this scale; the inner loop is (+0.21 to +0.33 on
  every test set). The next step is to put the loop's improvements into model weights: fine-tune an open model on
  the programs the loop found. See the main [README](../README.md).

## Commands

```bash
uv run ksa learn --split train --out-playbook playbooks/train-v3.json            # learn (default: selection on)
uv run ksa run --method oneshot --split test --playbook playbooks/train-v1.json --lessons select   # use it
uv run ksa lessons --playbook playbooks/train-v2.json --baseline <runs without> --with <runs with>  # per-lesson effect
```
