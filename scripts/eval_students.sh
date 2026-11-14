#!/usr/bin/env bash
# Held-out eval of Tinker students without OpenAI: generate with each model (SEEDS samples per case,
# measured-only critic), then judge every run with the open Qwen vision judge.
#   scripts/eval_students.sh name=generator [name=generator ...]
set -u
cd "$(dirname "$0")/.."
SEEDS=${SEEDS:-3}
JUDGE=${JUDGE:-tinker:Qwen/Qwen3.6-35B-A3B}
REPEATS=${REPEATS:-2}
mkdir -p runs/eval/logs
for spec in "$@"; do
  name=${spec%%=*}; gen=${spec#*=}
  (
    for s in $(seq "$SEEDS"); do
      KSA_CRITIC_MODEL=none KSA_GEN_MODEL="$gen" uv run ksa run --method oneshot --out "runs/eval/$name" \
        > "runs/eval/logs/$name-$s.log" 2>&1
    done
    for rd in runs/eval/"$name"/*/; do
      uv run ksa judge "$rd" --model "$JUDGE" --repeats "$REPEATS" >> "runs/eval/logs/$name-judge.log" 2>&1
    done
    echo "done $name"
  ) &
done
wait
echo ALL_DONE
