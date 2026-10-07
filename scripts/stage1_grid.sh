#!/usr/bin/env bash
# Run the Stage 1 context ablation for one encoder config: every training condition x seed.
# Each run is scored under all five eval conditions and appended to results/stage1.jsonl.
#
#   scripts/stage1_grid.sh configs/stage1/encoder_deberta_v3_base.toml lab-4090
#   MICRO_BATCH=8 SEEDS="13" scripts/stage1_grid.sh configs/stage1/encoder_roberta_base.toml rtx5060-wsl
#
# Runs that already have metrics.json are skipped, so an interrupted grid can be restarted.
set -euo pipefail

config=$(realpath "${1:?usage: stage1_grid.sh CONFIG MACHINE}")
machine=${2:?usage: stage1_grid.sh CONFIG MACHINE}
seeds=${SEEDS:-"13 42 2026"}
conditions=${CONDITIONS:-"none one full mismatched"}
extra=()
[[ -n "${MICRO_BATCH:-}" ]] && extra+=(--micro-batch-size "$MICRO_BATCH")
[[ -n "${GRAD_CKPT:-}" ]] && extra+=(--gradient-checkpointing)

cd "$(dirname "$0")/.."
name=$(python3 -c "import sys, tomllib; print(tomllib.load(open(sys.argv[1], 'rb'))['run']['name'])" "$config")
mkdir -p outputs/stage1/logs

for condition in $conditions; do
  for seed in $seeds; do
    if [[ -f "outputs/stage1/$name/train-$condition/seed$seed/metrics.json" ]]; then
      echo "skip $name train-$condition seed $seed (done)"
      continue
    fi
    echo "=== $name train-$condition seed $seed ==="
    uv run --group gpu python -m src.stage1.encoder --config "$config" --seed "$seed" \
      --train-condition "$condition" --machine "$machine" "${extra[@]}" \
      2>&1 | tee "outputs/stage1/logs/$name-train-$condition-seed$seed.log"
  done
done
