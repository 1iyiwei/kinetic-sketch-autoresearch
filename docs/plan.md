# Hackathon Plan — Kinetic Sketch Autoresearch

Target: **Track 5 (Open Track)**, SF AI Research Hackathon. Submission deadline: **Sun 14:00 PT** (slides say 14:00; event page says 14:30 — plan for 14:00).

Judging: five equal criteria — Research rigour, Novelty, Results, Autonomy & self-improvement, Interpretability & reproducibility.

## Where we are

Generator (LLM → `window.ksaRender(t)` HTML) → deterministic Chromium renderer → hybrid critic (measured anchor-frame fidelity + vision for motion/intent/integrity) → beam critique→revise loop → separate held-out judge (repeated scoring).

| Method | Held-out judge (/5) | Tokens |
|---|---|---|
| One-shot | 3.58 | 91K |
| Best-of-6 | 3.60 | 540K |
| **Loop** | **3.91** | 721K |

Loop wins 7 / loses 2 / ties 1 vs one-shot (pendulum 3.08→4.25, spring-mass 3.17→4.17).

**Gaps:** nothing learns across drawings yet (weak "self-improvement"); small sample (10 cases, 1 seed, no CIs); clean procedural SVGs only.

## Expansion: self-training an open model with Tinker (expert iteration)

The expensive loop is the **teacher**; we distill its best programs into a small open model, then put that model back into the loop as the generator and repeat.

```
~300 training drawings (procedural + LLM scene specs, same sketch style)
        ↓
Teacher: gpt-5.5 critique→revise loop   (Modal fan-out)
        ↓  best program per case (+ ranked siblings as preference pairs)
Tinker LoRA SFT on an open model  (SVG + intent → HTML program)
        ↓
Student model ──► generator inside the loop ──► round 2 data ──► retrain
        ↓
Held-out eval on the 10 benchmark cases (+ hand-drawn) — never in training
```

**Headline to aim for:** a small open model, one-shot, approaches the gpt-5.5 loop at a fraction of the cost and latency. Report honestly even if partial.

## Steps & timeline (PT)

| # | Step | Owner | When |
|---|---|---|---|
| 1 | Critique→revise loop + held-out judge | Li-Yi | ✅ done |
| 2 | Training-drawing generator (LLM scene specs rendered with `make_cases.py` sketch helpers), train/test split | Andrewe/Devin | Sat ~20:00 |
| 3 | Run teacher loop over training cases (Modal parallel); export SFT JSONL from `runs/*/` best nodes | Andrewe/Devin | Overnight |
| 4 | Tinker SFT (LoRA); student served via Tinker OpenAI-compatible endpoint so `ksa run` can use it as the generator | Andrewe/Devin | Sun 02:00–06:00 |
| 5 | Round 2: student generates inside the loop, retrain. Stretch: RL with renderer checks + critic as reward | Andrewe/Devin | Sun 06:00–10:00 |
| 6 | Held-out eval: base open model vs SFT r1 vs SFT r2 vs gpt-5.5 one-shot vs full loop — same judge; quality, $ cost, latency, validity | all | Sun by 11:00 |
| 7 | Trace viewer, figures, README, demo video | all | Sun 11:00–13:30 |

## Rigour checklist

- Equal-compute comparison (score vs tokens/$), not just best-vs-best.
- Held-out judge is a different model, ≥3 repeats; report variance / bootstrap CIs; pairwise A/B with swapped positions.
- Objective metrics alongside LLM scores: anchor-frame fidelity, render validity, clipping, motion energy.
- No test leakage: benchmark + hand-drawn cases excluded from training data.
- Every run keeps `tree.json`, `results.json`, `llm_calls.jsonl` for replay.

## Sponsor challenges (optional, stack on top)

- **Modal:** parallel render+critique for teacher data generation; show wall-clock speedup.
- **past.dev:** shared lesson memory — critic/analyst write, generator/reviser read (≥2 writers, ≥2 readers, cross-agent read).
- **Exa:** reviser searches physics/animation references when critic flags a physics issue, cites sources (only if ablated).
- **Originator:** upload agent sessions.

## 3-minute pitch

1. Problem in one GIF → 2. Loop diagram → 3. Tree replay (pendulum swing fixed) → 4. Score vs compute with CIs → 5. Tinker student vs teacher on held-out cases (quality / cost / latency) → 6. Live drawing (precomputed replay as backup).

## Open decisions

- Who owns Tinker work alongside Li-Yi's loop work.
- Which sponsor challenges to enter.
- Live drawing on stage vs precomputed replay.
- Base model choice for the student (check Tinker model list; must write valid HTML/JS reliably).

## Status & commands (Tinker pipeline)

Built and smoke-tested end to end:

```bash
uv run python benchmark/make_train_cases.py              # 300 train drawings -> benchmark/train/ (75 per category)
uv run ksa run --method loop --cases-file benchmark/train/cases.json   # teacher data
uv run python -m ksa.distill export runs/<train-run> --out data/sft_r1.jsonl   # held-out cases always excluded
uv run python -m ksa.distill train data/sft_r1.jsonl --name r1                 # Tinker LoRA SFT, prints tinker:// path
KSA_GEN_MODEL=tinker:Qwen/Qwen3.6-35B-A3B uv run ksa run --method oneshot      # base student
KSA_GEN_MODEL=tinker://.../sampler_weights/r1-e2 uv run ksa run --method oneshot   # fine-tuned student
```

Smoke results (not headline numbers): teacher loop on 8 train cases = 3.56 mean, ~150K tokens/case;
base Qwen3.6-35B-A3B one-shot: windmill 4.50, pendulum 2.25 (text-only, ~12K tokens/case);
SFT on 12 examples trained and sampled through `tinker://` successfully.
Note: base model's SFT loss starts low (~0.15), so round-1 SFT gains may be modest; RL with the
renderer + critic as reward is the likely bigger lever.
