# DeBERTa-large lab handoff

Prepared 2026-10-26 for Sandy. This is a **dev-only** handoff for the lab RTX 5090
or RTX 4090. The local RTX 5060 is used for validation, not large-model training.
The lab smoke and training runs have not been executed.

## Start from GitHub

Clone this PR branch on the lab's Linux filesystem. After the PR is merged, you
can clone `main` instead. Use Git rather than a source ZIP so run provenance can
record the commit.

```bash
set -euo pipefail
git clone --branch chore/lab-dev-readiness \
  https://github.com/sandythomas1/Pragmatic-Intent.git
cd Pragmatic-Intent
uv sync --locked --group gpu
uv run --locked --no-sync python -m src.data.download_sources --only direct multiwoz
mkdir -p data/interim
uv run --locked --no-sync python -m src.data.build_direct_dataset \
  > data/interim/direct-rebuild-summary.json
sha256sum -c <<'CHECKSUMS'
c7f56b41bde43598f04b867ad6a52189d632c53578cf49734d44b6034550fe83  data/interim/direct/items.jsonl
574ae000db5562521e3a767f4ee55e4e64abdf89e60d9038c47f4f7d25059949  data/interim/direct/dialogues.jsonl
CHECKSUMS
```

Both dataset checksums must pass before proceeding to
**Environment and preflight** below. Raw source data, rebuilt dataset files and
the private package are excluded from Git; downloading the repo supplies the
code and pinned source references. Keep the source terms in `docs/data_sources.md`.

## Alternative: transfer and restore the local package

The local package is
`outputs/lab/pi-deberta-large-20261026.tar.gz`, with a `.sha256` sidecar.
Copy both files to the lab machine using your usual private transfer method.
The archive contains source text in the two local dataset files; keep it in private
project storage and respect the source terms in `docs/data_sources.md`.

Use a new directory on the lab's Linux filesystem. With the archive and sidecar in
your current directory:

```bash
sha256sum -c pi-deberta-large-20261026.tar.gz.sha256
tar -xzf pi-deberta-large-20261026.tar.gz
cd pi-deberta-large-20261026
sha256sum -c PACKAGE_SHA256SUMS
git clone --branch chore/lab-dev-readiness source.bundle work
cp -a payload/. work/
cd work
git bundle verify ../source.bundle
sha256sum -c ../WORKTREE_SHA256SUMS > ../worktree-verification.log
git status --short --branch
```

The Git bundle supplies the existing commit history; the overlay supplies the
uncommitted lab-preparation changes. A dirty tree is expected and must be reported
truthfully. The package has no old model outputs, checkpoints, virtual environment,
credentials or downloaded model weights. `MANIFEST.json` records the base commit,
source digest, recipe hashes and data checksums. Do not pull or edit this restored
checkout during a grid. A changed recipe/source belongs in another checkout.

## Environment and preflight

Make `uv`, Git and an appropriate NVIDIA driver available on the lab machine.
The lockfile pins Python dependencies; the first sync and model load need network
access. Do not install a Linux NVIDIA display driver inside WSL.

```bash
set -euo pipefail
export TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=4
unset CUDA_LAUNCH_BLOCKING
uv sync --locked --group gpu
mkdir -p outputs/verification
uv run --locked --group gpu python -m src.stage1.env_check \
  2>&1 | tee outputs/verification/lab-env.log
uv run --locked --group gpu python -m src.stage1.length_check \
  --config configs/stage1/encoder_deberta_v3_large.toml \
  --out outputs/verification/deberta-large-lengths.json \
  2>&1 | tee outputs/verification/deberta-large-lengths.log
```

Both commands must exit zero. The length check covers all five train and dev
conditions without silently truncating inputs. Stop if any input exceeds 512
tokens; the common renderer budget then needs a separate protocol revision.
No test scoring or freeze is part of this handoff.

## Smoke test: choose one lab profile

Use the 5090 profile on a 32 GB RTX 5090:

```bash
uv run --locked --group gpu python -m src.stage1.encoder \
  --config configs/stage1/encoder_deberta_v3_large.toml \
  --seed 13 --train-condition full --machine lab-5090 --smoke \
  --checkpoint-every 16 \
  2>&1 | tee outputs/verification/deberta-large-smoke-5090.log
```

Use the conservative 4090 profile on a 24 GB RTX 4090:

```bash
uv run --locked --group gpu python -m src.stage1.encoder \
  --config configs/stage1/encoder_deberta_v3_large.toml \
  --seed 13 --train-condition full --machine lab-4090 --smoke \
  --micro-batch-size 4 --gradient-checkpointing --checkpoint-every 16 \
  2>&1 | tee outputs/verification/deberta-large-smoke-4090.log
```

The effective batch stays 32 in both profiles. Keep the selected profile unchanged
throughout the grid. The smoke uses 1,000 training and 300 genuine dev examples;
it writes `outputs/stage1/deberta-v3-large/train-full/seed13-smoke/`, separately
from the real grid, and does not append a results record.

After a zero exit, inspect the smoke log for finite losses and review its metrics
and predicted-class counts:

```bash
uv run --locked --no-sync python - <<'PY'
import collections
import json
from pathlib import Path
p = Path('outputs/stage1/deberta-v3-large/train-full/seed13-smoke')
m = json.loads((p / 'metrics.json').read_text())
print(json.dumps(m['run']['model'], indent=2))
counts = collections.defaultdict(collections.Counter)
for line in (p / 'predictions.jsonl').read_text().splitlines():
    row = json.loads(line)
    counts[row['condition']][row['prediction']] += 1
for condition, labels in sorted(counts.items()):
    print(condition, dict(labels))
PY
```

Check `resolved_revision` against
`64a8c8eab3e352a784c658aef62be1662607476f`, `peak_memory_gib` against the
device's available memory, and prediction counts for class collapse. Smoke scores
only check the pipeline. A single-class prediction pattern needs investigation;
do not automatically tune the learning rate from a short smoke. Stop on OOM,
nonfinite loss or other failures, preserve logs, and resolve them before training.

## Plan and run the dev grid

Use a persistent terminal (for example `tmux` if available) and keep the lab machine
awake. First review the dry run for your selected profile:

```bash
# RTX 5090
bash scripts/stage1_grid.sh configs/stage1/encoder_deberta_v3_large.toml \
  lab-5090 --dry-run

# RTX 4090
MICRO_BATCH=4 GRAD_CKPT=1 bash scripts/stage1_grid.sh \
  configs/stage1/encoder_deberta_v3_large.toml lab-4090 --dry-run
```

Each plan must contain 15 runs: `none`, `one`, `full` training crossed with
seeds `13 42 2026 314 2718`. Every run evaluates all five dev conditions;
mismatch controls use the full-trained model in the analysis. After reviewing a
successful smoke, run **one** of the following in the same environment:

```bash
# RTX 5090
bash scripts/stage1_grid.sh configs/stage1/encoder_deberta_v3_large.toml \
  lab-5090 2>&1 | tee -a outputs/verification/deberta-large-grid-5090.log

# RTX 4090
MICRO_BATCH=4 GRAD_CKPT=1 bash scripts/stage1_grid.sh \
  configs/stage1/encoder_deberta_v3_large.toml lab-4090 \
  2>&1 | tee -a outputs/verification/deberta-large-grid-4090.log
```

Checkpoints are saved every 250 optimizer steps, then removed after a successful
run. If interrupted, inspect the failure and repeat the identical command. The
launcher verifies completed runs before skipping them and refuses stale or
incomplete provenance. Resume with the same micro-batch and checkpointing profile;
switching GPU profiles requires a separate checkout. Keep only one grid process
active in this checkout. The launcher stops at the first failed run; it does not
automatically retry CUDA failures.

## Bring back the evidence

After completion, save the following locally for private transfer back to the
research workspace:

```bash
tar -czf ../deberta-large-dev-evidence.tar.gz \
  outputs/stage1/deberta-v3-large outputs/stage1/logs \
  outputs/verification results/stage1.jsonl
sha256sum ../deberta-large-dev-evidence.tar.gz \
  > ../deberta-large-dev-evidence.tar.gz.sha256
```

Keep the original package and `MANIFEST.json` alongside these outputs. Do not merge
results from different source/config snapshots into the same run directories.
Review the 15 completed runs and add them to the dev analysis inputs before making
any model choice. Reported test runs remain blocked on the separate WP-08 freeze.

## Preparation evidence (2026-10-26)

- Remote pull: already up to date at `1016c258eeb1070542b07899812d87f1a92ab89b`.
- WSL Python 3.12.15: 918 tests passed, 5 skipped, 16.242 seconds.
- `uv lock --check --offline`: passed; no dependency versions changed.
- Both real launcher dry runs: 15 planned runs, no training.
- Local environment check: RTX 5060, torch 2.11.0+cu128, bf16 matmul passed.
- Freeze check: 75 ready pins; five open items (`tree_dirty`,
  `llm_model_floating`, `analysis_draft`, and missing LLM/hybrid recipes).
- Lab GPU smoke/training and model-weight download: pending on the lab machine.

Archive round-trip and tokenizer-preflight evidence are recorded in the dated
`docs/lab_preparation_2026-10-26.md` closeout.
