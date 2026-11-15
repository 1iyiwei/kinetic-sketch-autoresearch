# Tinker self-training results (held-out, 10 benchmark cases)

Teacher: gpt-5.5 critique→revise loop (`loop_k2_b1_c2_r2`) on 120 generated training drawings
(the 150-case split stopped at 120 when OpenAI credits ran out). Batch means 3.95 / 3.96 / 3.88 / 3.90.
Export: 185 SFT examples from 101 drawings (19 dropped as low-score, 0 held-out leaks).
Student: LoRA SFT of `Qwen/Qwen3.6-35B-A3B` (3B active) on Tinker. The 10 benchmark cases are never trained on.

Judged with two open vision models on Tinker (2 repeats per case). The Qwen3.6-35B judge is the same
model as the open-loop critic, so **Qwen3.5-397B is the independent judge and the headline column**.
Students: 3 samples per case (mean ± sd across runs).

| generator (one-shot unless noted) | runs | judge Qwen3.5-397B | judge Qwen3.6-35B | valid renders | anchor F1 | moving |
|---|---|---|---|---|---|---|
| Qwen3.6-35B-A3B, untrained | 3 | 1.92 ± 0.27 | 2.10 ± 0.20 | 77% | 0.47 | 57% |
| student, 90 drawings, 1 epoch | 3 | 2.49 ± 0.24 | 2.76 ± 0.41 | 73% | 0.64 | 67% |
| student, 90 drawings, 3 epochs | 3 | 3.05 ± 0.27 | 3.39 ± 0.22 | 90% | 0.89 | 77% |
| **student, 120 drawings, 1 epoch (`r1-e0`)** | 3 | **3.27 ± 0.38** | 3.84 ± 0.27 | 100% | 0.97 | 90% |
| **round 2**: teacher data + 131 open-loop programs (Qwen3.6-critic ≥ 4.25), 1 epoch (`r2-e0`) | 3 | 3.23 ± 0.30 | - | 100% | 0.97 | 93% |
| round 2b: teacher data + 19 open-loop programs selected by Qwen3.5-397B (≥ 3.75), 1 epoch (`r2b-e0`) | 3 | 2.68 ± 0.31 | 3.08 ± 0.21 | 87% | 0.81 | 83% |
| student, 120 drawings, 2 epochs | 3 | 3.06 ± 0.29 | 3.59 ± 0.36 | 93% | 0.86 | 83% |
| student, 120 drawings, 3 epochs | 3 | 3.19 ± 0.41 | 3.51 ± 0.43 | 97% | 0.90 | 97% |
| **open loop**: student `r1-e2` + Qwen3.6 critic | 2 | 3.51 ± 0.03 | 4.27 ± 0.11 | 100% | 1.00 | 100% |
| **open loop**: student `r1-e0` + Qwen3.6 critic | 1 | 3.69 | 4.16 | 100% | 1.00 | 100% |
| gpt-5.5 one-shot | 1 | 4.01 | 3.96 | 100% | 1.00 | 100% |

Findings
- Distillation works: one-shot quality 1.92 → 3.27 (independent judge), valid programs 77% → 100%,
  closing ~65% of the gap to gpt-5.5 one-shot at ~7K tokens/case on a 3B-active open model.
- Teacher data volume matters more than epochs: 90 → 120 drawings helps; extra epochs do not.
- A fully open loop (student generator + open critic, no OpenAI) reaches 3.5–3.7, ~85% of the gap.
- Round 2 (expert iteration with the open loop as teacher on 150 unused drawings) did not help:
  3.23 vs 3.27. Its data was selected by the Qwen3.6 critic, which overrates its own family (round-2
  loop means 4.0–4.7 by that critic), so the selection signal was weak. Self-training needs a reliable selector.
- Round 2b re-selected that data with the independent Qwen3.5-397B judge: it rates the round-2 loop programs
  only 2.7–3.1 (vs 4.0–4.7 from the Qwen3.6 critic), so just 19 of 150 passed, and the retrained student did not
  improve either. Conclusion: the open loop is not yet a good enough teacher; gains came only from gpt-5.5 data.
  Caveat: each student is a single training run, so training seed variance is unmeasured.
- Judge self-preference is real: the critic's own model scores the open loop 4.2–4.3, but the
  independent judge gives 3.5–3.7 and still prefers gpt-5.5 one-shot. Report the independent column.

Not yet done: more gpt-5.5 teacher data, a finished and evaluated RL run (see the RL section below),
gpt-5.5 loop re-judged with the same open judges (needs the held-out loop run directory).

Reproduce
```bash
uv run python -m ksa.distill export runs/teacher150/<run> ... --out data/sft_r1.jsonl
uv run python -m ksa.distill train data/sft_r1.jsonl --name r1
scripts/eval_students.sh base=tinker:Qwen/Qwen3.6-35B-A3B r1-e0=tinker://<run>/sampler_weights/r1-e0
KSA_GEN_MODEL=tinker://<run>/sampler_weights/r1-e0 KSA_CRITIC_MODEL=tinker:Qwen/Qwen3.6-35B-A3B uv run ksa run --method loop
uv run ksa judge runs/<run> --model tinker:Qwen/Qwen3.5-397B-A17B --repeats 2
```

## Expanded benchmark: all 23 drawings (Qwen3.5-397B judge)

Same protocol on the teammate's 23-drawing benchmark (8 train, 3 val, 7 test, 5 complex). None of these drawings is
in the Tinker training data. 3 one-shot samples per generator unless noted; `runs/eval23/`.

| Generator | All 23 | Test (7) | Complex (5) | Valid | First-frame F1 | Moves |
| --- | --- | --- | --- | --- | --- | --- |
| Qwen3.6-35B-A3B, untrained | 1.67 ± 0.36 | 1.90 | 1.17 | 77% | 0.45 | 51% |
| student `r1-e0` (seed 0, 1 epoch of a 3-epoch schedule) | 2.95 ± 0.33 | 2.97 | 2.91 | 93% | 0.88 | 80% |
| student `r1s1-e0` (seed 1, 1-epoch schedule) | 2.80 ± 0.08 | 2.67 | 2.48 | 87% | 0.83 | 72% |
| student `r1s2-e0` (seed 2, 1-epoch schedule) | 2.63 ± 0.18 | 2.76 | 2.16 | 91% | 0.88 | 81% |
| **student, mean of 3 training seeds** | **2.79 ± 0.16** | 2.80 | 2.52 | 90% | 0.86 | 78% |
| open loop: `r1-e0` + Qwen3.6 critic (1 run) | 3.30 | 3.38 | 3.07 | 100% | 0.97 | 91% |

- The distillation gain holds on the larger benchmark: +1.1 over the untrained model.
- Training-seed spread (±0.16) is about half the sample-to-sample spread. Differences between students under about
  0.3 are not meaningful; round 2 (3.23 vs 3.27) is within it, while round 2b (2.68) is borderline.
- Seeds 1 and 2 used a learning rate that decays to 0 within the single epoch; `r1-e0` is the first epoch of a
  3-epoch schedule (higher learning rate at its end). That difference is confounded with the seed.

## RL on Tinker (`ksa.rl`), incomplete: stopped by Tinker billing

GRPO-style RL on the distilled student, no OpenAI: warm-start with one epoch of SFT on `data/sft_r1.jsonl`, then
each step samples 4 programs for each of 8 training drawings (held-out drawings excluded). Reward is 0 if a sample
has no program or fails to render, else the Qwen3.6-35B critic's overall score / 5. Advantage is reward minus the
group mean, and the update uses Tinker's `importance_sampling` loss (LoRA rank 32, lr 2e-5). Both runs stopped when
the Tinker account hit a billing block (HTTP 402), before the planned 23-drawing evaluation.
Per-step logs: `runs/rl-*/steps.jsonl`.

| Run | Sampling temperature | Steps done | Mean reward per step | Valid renders per step | Groups with no signal |
| --- | --- | --- | --- | --- | --- |
| `rl1` | 1.0 | 6 / 12 | 0.25, 0.26, 0.10, 0.20, 0.19, 0.20 | 34%, 41%, 16%, 34%, 28%, 25% | 3, 2, 5, 0, 3, 5 of 8 |
| `rl2t08` | 0.8 | 3 / 16 | 0.57, 0.38, 0.47 | 88%, 59%, 66% | 0, 0, 0 of 8 |

- At temperature 1.0 the student breaks most programs: undefined variables, stray non-ASCII tokens inside
  identifiers, and duplicate declarations, so only 16–41% render (vs about 90% at the eval temperature of 0.7). Many
  groups get identical (zero) rewards and carry no signal, and the mean reward did not rise over 6 steps.
- At temperature 0.8, 59–88% render and every group has a usable reward spread. That is the setting to continue with.
  The sampler's logprobs then come from the temperature-scaled distribution, which importance sampling only partly
  corrects for.
- No RL checkpoint has been evaluated, so there is no claim yet that RL improves the student. Saved checkpoints:
  `rl1-sft` and `rl1-rl4` (run `179b1700-…`), and `rl2t08-sft` (run `2e889a50-…`).

Resume once Tinker billing is restored:
```bash
uv run python -m ksa.rl --name rl2t08 --steps 16 --cases 8 --group 4 --save-every 4 --temperature 0.8
OUT=runs/eval23 JUDGE=tinker:Qwen/Qwen3.5-397B-A17B scripts/eval_students.sh \
  e23-rl-sft=tinker://<run>/sampler_weights/rl2t08-sft e23-rl-rl16=tinker://<run>/sampler_weights/rl2t08-rl16
```
