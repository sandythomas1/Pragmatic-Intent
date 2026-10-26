#!/usr/bin/env bash
# Run the Stage 1 context ablation for one encoder config: every training condition x seed.
# Each run is scored under all five eval conditions and appended to results/stage1.jsonl.
#
#   scripts/stage1_grid.sh configs/stage1/encoder_deberta_v3_large.toml lab-5090
#   scripts/stage1_grid.sh configs/stage1/encoder_deberta_v3_large.toml lab-5090 --dry-run
#   MICRO_BATCH=8 SEEDS="13" scripts/stage1_grid.sh configs/stage1/encoder_roberta_base.toml rtx5060-wsl
#
# Five seeds by default, so seed variation can be reported (spec 001 §13); the first three
# match the original three-seed grid. Completed runs are verified before being skipped, and an
# interrupted run resumes from its last checkpoint (every CHECKPOINT_EVERY optimizer steps,
# default 250; 0 turns checkpoints off), so an interrupted grid can be restarted.
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 || ( $# -eq 3 && "$3" != --dry-run ) ]]; then
  echo "usage: stage1_grid.sh CONFIG MACHINE [--dry-run]" >&2
  exit 2
fi
dry_run=${3:-}
config=$(realpath "${1:?usage: stage1_grid.sh CONFIG MACHINE}")
machine=${2:?usage: stage1_grid.sh CONFIG MACHINE}
seeds=${SEEDS:-"13 42 2026 314 2718"}
conditions=${CONDITIONS:-"none one full"}
checkpoint_every=${CHECKPOINT_EVERY:-250}
if [[ ! "$checkpoint_every" =~ ^[0-9]+$ || ! "${GRAD_CKPT:-0}" =~ ^[01]$ ]]; then
  echo "CHECKPOINT_EVERY must be non-negative; GRAD_CKPT must be 0 or 1" >&2
  exit 2
fi
extra=()
[[ -n "${MICRO_BATCH:-}" ]] && extra+=(--micro-batch-size "$MICRO_BATCH")
[[ "${GRAD_CKPT:-0}" == 1 ]] && extra+=(--gradient-checkpointing)
[[ "$checkpoint_every" != 0 ]] && extra+=(--checkpoint-every "$checkpoint_every")

cd "$(dirname "$0")/.."
# Planning is stdlib-only; use the project's Python, even on Ubuntu 22.04.
# --no-sync keeps a dry run from installing GPU dependencies; --locked forbids lock drift.
# Validate the entire grid before starting its first run. Checkpoint frequency affects
# persistence only, so it is excluded from the recipe overrides used for validation.
plan_extra=()
[[ -n "${MICRO_BATCH:-}" ]] && plan_extra+=(--micro-batch-size "$MICRO_BATCH")
[[ "${GRAD_CKPT:-0}" == 1 ]] && plan_extra+=(--gradient-checkpointing)
plan=$(uv run --locked --no-sync python -m src.stage1.grid_check --config "$config" \
  --seeds "$seeds" --conditions "$conditions" "${plan_extra[@]}")
[[ -n "$dry_run" ]] || mkdir -p outputs/stage1/logs

while IFS=$'\t' read -r name condition seed status; do
    if [[ "$status" == skip ]]; then
      echo "skip $name train-$condition seed $seed (done)"
      continue
    fi
    command=(uv run --locked --group gpu python -m src.stage1.encoder --config "$config" --seed "$seed"
      --train-condition "$condition" --machine "$machine" "${extra[@]}")
    if [[ -n "$dry_run" ]]; then
      printf '%q ' "${command[@]}"
      printf '\n'
    else
      echo "=== $name train-$condition seed $seed ==="
      "${command[@]}" 2>&1 | tee "outputs/stage1/logs/$name-train-$condition-seed$seed.log"
    fi
done <<< "$plan"
