#!/usr/bin/env bash
# Run the frozen WP-09 Stage 1 test grid on ONE GPU, in sessions (docs/wp09_single_gpu_runbook.md).
#
#   GPU=0 scripts/stage1_test_grid.sh lab-5090 --dry-run
#   GPU=0 MAX_RUNS=3 scripts/stage1_test_grid.sh lab-5090
#   GPU=0 SYSTEMS="deberta-v3-large" scripts/stage1_test_grid.sh lab-5090
#
# - One GPU: GPU names exactly one device index, exported as CUDA_VISIBLE_DEVICES, so no run can
#   touch the other card. Required for a real run; a dry run does not need it.
# - Freeze first: scripts/plan_test_grid.py verifies the freeze and checks every run against the
#   frozen grid before the first model loads; one bad completed run refuses the whole plan.
# - Sessions: MAX_RUNS caps the runs started this session (default: all). Creating
#   outputs/stage1-test/STOP ends the session after the current run. Rerunning the same command
#   skips verified runs and resumes an interrupted encoder from its last checkpoint
#   (every CHECKPOINT_EVERY optimizer steps, default 250; 0 turns checkpoints off).
# - Separate outputs: test runs write to outputs/stage1-test/ and results/stage1-test.jsonl, never
#   over the dev grid in outputs/stage1/. A lock stops a second launcher in the same checkout.
# - Order: SYSTEMS (default: both TF-IDF baselines, then DeBERTa-v3-large, then base), then seed,
#   then condition, so a cut leaves complete seeds and the hybrid's routers come first.
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 || ( $# -eq 2 && "$2" != --dry-run ) ]]; then
  echo "usage: stage1_test_grid.sh MACHINE [--dry-run]" >&2
  exit 2
fi
machine=$1
dry_run=${2:-}
systems=${SYSTEMS:-"tfidf-utterance tfidf-context deberta-v3-large deberta-v3-base"}
checkpoint_every=${CHECKPOINT_EVERY:-250}
max_runs=${MAX_RUNS:-0}
if [[ ! "$machine" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]]; then
  echo "MACHINE must be a plain label such as lab-5090" >&2
  exit 2
fi
if [[ ! "$checkpoint_every" =~ ^[0-9]+$ || ! "$max_runs" =~ ^[0-9]+$ || ! "${GRAD_CKPT:-0}" =~ ^[01]$ \
      || ! "${MICRO_BATCH:-1}" =~ ^[1-9][0-9]*$ ]]; then
  echo "CHECKPOINT_EVERY and MAX_RUNS must be non-negative integers (0 = no limit for MAX_RUNS)," \
       "MICRO_BATCH a positive integer, GRAD_CKPT 0 or 1" >&2
  exit 2
fi
if [[ -z "$dry_run" ]]; then
  if [[ ! "${GPU:-}" =~ ^[0-9]+$ ]]; then
    echo "GPU must name exactly one device index (see nvidia-smi), e.g. GPU=0" >&2
    exit 2
  fi
  export CUDA_VISIBLE_DEVICES=$GPU
fi
# The vLLM environment (docs/llm_lab_runbook.md) conflicts with the gpu group; syncing the gpu
# group into it would break it, so the Stage 1 grid refuses to run with it selected.
if [[ -n "${UV_PROJECT_ENVIRONMENT:-}" ]]; then
  echo "unset UV_PROJECT_ENVIRONMENT first: the Stage 1 grid uses the project .venv, not the LLM environment" >&2
  exit 2
fi

cd "$(dirname "$0")/.."
out_root=outputs/stage1-test
plan_extra=()
[[ -n "${MICRO_BATCH:-}" ]] && plan_extra+=(--micro-batch-size "$MICRO_BATCH")
[[ "${GRAD_CKPT:-0}" == 1 ]] && plan_extra+=(--gradient-checkpointing)
encoder_extra=("${plan_extra[@]}")
[[ "$checkpoint_every" != 0 ]] && encoder_extra+=(--checkpoint-every "$checkpoint_every")

if [[ -z "$dry_run" ]]; then
  mkdir -p "$out_root/logs"
  exec 9>"$out_root/.lock"
  if ! flock -n 9; then
    echo "another stage1_test_grid.sh is running in this checkout" >&2
    exit 1
  fi
  if [[ -e "$out_root/STOP" ]]; then
    echo "$out_root/STOP exists; remove it to start a session" >&2
    exit 1
  fi
fi

# Planning is stdlib-only: --no-sync keeps it from installing GPU packages, --locked forbids drift.
plan=$(uv run --locked --no-sync python -E -s -m scripts.plan_test_grid --systems "$systems" "${plan_extra[@]}")

started=0
pending=0
while IFS=$'\t' read -r name module config condition seed status; do
  if [[ "$status" == skip ]]; then
    echo "skip $name train-$condition seed $seed (done under this freeze)"
    continue
  fi
  if (( max_runs > 0 && started >= max_runs )) || [[ -e "$out_root/STOP" ]]; then
    pending=$((pending + 1))
    continue
  fi
  extra=()
  [[ "$module" == src.stage1.encoder ]] && extra=("${encoder_extra[@]}")
  command=(uv run --locked --group gpu python -E -s -m "$module" --config "$config" --seed "$seed"
    --train-condition "$condition" --eval-split test --allow-test --machine "$machine"
    --out-root "$out_root" --results results/stage1-test.jsonl "${extra[@]}")
  started=$((started + 1))
  if [[ -n "$dry_run" ]]; then
    printf '%q ' "${command[@]}"
    printf '\n'
  else
    echo "=== $(date -u +%FT%TZ) $name train-$condition seed $seed ==="
    # stdin is the plan itself; a trainer must not be able to consume the remaining rows.
    "${command[@]}" < /dev/null 2>&1 | tee -a "$out_root/logs/$name-train-$condition-seed$seed.log"
  fi
done <<< "$plan"

verb=started
[[ -n "$dry_run" ]] && verb=planned
echo "session: $started run(s) $verb, $pending left for a later session"
