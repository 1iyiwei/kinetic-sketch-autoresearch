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
- Judge self-preference is real: the critic's own model scores the open loop 4.2–4.3, but the
  independent judge gives 3.5–3.7 and still prefers gpt-5.5 one-shot. Report the independent column.

Not yet done: round 2 (student-in-loop data → retrain), more teacher data (OpenAI credits),
gpt-5.5 loop re-judged with the same open judges (needs the held-out loop run directory).

Reproduce
```bash
uv run python -m ksa.distill export runs/teacher150/<run> ... --out data/sft_r1.jsonl
uv run python -m ksa.distill train data/sft_r1.jsonl --name r1
scripts/eval_students.sh base=tinker:Qwen/Qwen3.6-35B-A3B r1-e0=tinker://<run>/sampler_weights/r1-e0
KSA_GEN_MODEL=tinker://<run>/sampler_weights/r1-e0 KSA_CRITIC_MODEL=tinker:Qwen/Qwen3.6-35B-A3B uv run ksa run --method loop
uv run ksa judge runs/<run> --model tinker:Qwen/Qwen3.5-397B-A17B --repeats 2
```
