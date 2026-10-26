# Lab readiness, 2026-10-25

For the packaged 2026-10-26 handoff, follow the
[DeBERTa-large lab runbook](deberta_large_lab_runbook.md).

**Move to a lab GPU for DeBERTa-v3-large development, starting with a smoke test.** Prefer the
5090; the 4090 is an alternative with a smaller micro-batch and gradient checkpointing. Large-model
training has not been verified on either lab machine. The local 5060 completed the base grid;
repeating it is unnecessary while `render-v1` remains unchanged.

Sandy chose DeBERTa-large preparation with RoBERTa on hold on 2026-10-25, retaining `render-v1`.
Reported test runs remain gated by
the WP-08 freeze. Nothing in this handoff writes a freeze, changes the primary system, or chooses
an LLM/hybrid recipe.

## Starting state and changes

- Fetched `origin`; PR #4 is merged at `1016c258eeb1070542b07899812d87f1a92ab89b`.
  PRs #1–#4 were retrieved; #4 has no discussion comments. Its remaining work includes model
  recipes, the freeze, and the spec 007/008 retrospectives.
- Created local branch `chore/lab-dev-readiness` from `origin/main`. No commit or push was made.
  Existing WSL checkouts, completed runs, source data and byte-pinned manifests were preserved.
- Updated `uv.lock` for the already-declared `figures` group. Existing locked packages retain
  their versions. No dependency sync or model-weight download was performed.
- Pinned the remaining encoder revisions from the Hugging Face model API on this date:

| Model | Revision |
|---|---|
| `microsoft/deberta-v3-large` | `64a8c8eab3e352a784c658aef62be1662607476f` |
| `FacebookAI/roberta-base` | `e2da8e2f811d1448a5b465c236feacd80ffbac7b` |
| `FacebookAI/roberta-large` | `722cf37b1afa9454edce342e7895e588b6ff1d59` |

The grid launcher now uses project Python rather than Ubuntu's system Python, refuses lockfile
drift, accepts `--dry-run`, defaults to `none one full` × five seeds (15 dev runs), and treats
`GRAD_CKPT=0` as disabled. Mismatch evaluation still runs with the full-trained model. Shell
files use LF, including when checked out on Windows. Existing checkpoint/resume and failure
propagation remain in place. Completed runs are verified against their recipe, seed, data,
source and prediction hashes before being skipped; keep output directories separate when
changing a recipe or source.

## Verification

| Check | Result |
|---|---|
| Windows Python 3.12.9 suite | 918 tests, OK, 16 skipped; 41.994 s |
| WSL Python 3.12.15 suite | 918 tests, OK, 5 skipped; 30.252 s |
| Launcher regressions | 8 pass in WSL; old launcher reproduced `ModuleNotFoundError: tomllib` and silently skipped stale outputs |
| Completed-run validation | 11 tests cover matching outputs, stale recipes/data/source, edited/missing artifacts and invalid grids |
| `uv lock --check` | passes on Windows and offline in WSL |
| Real launcher dry runs | 15 DeBERTa-large/5090 and 15 RoBERTa-large/4090 commands; no training |
| WSL environment check | RTX 5060, driver 610.88, torch 2.11.0+cu128, sm_120, bf16 matmul passes |
| DeBERTa-large tokenizer | 10 train/dev condition groups pass; train max 482, dev max 472 |
| RoBERTa-base and large tokenizers | each fails on 2 mismatched-training inputs at 514 tokens |
| `freeze check` | 75 ready pins; 5 findings remain, down from 8 |

Windows skips include unavailable torch/checkpoint tests and the eight Linux launcher tests;
the WSL environment has torch. CPU tokenizer checks used all 101,460 training examples and
11,394 genuine / 11,340 mismatch dev examples across the five conditions. No held-out test
utterance, prediction or metric was inspected. The environment matmul is a short preflight;
no training was launched in this session.

Local evidence is under `outputs/verification/readiness-20261025/` in the Windows workspace.
The isolated Linux source snapshot is `/home/sandy/pi-lab-readiness-20261025`; it reuses the
existing Python environment only for checks, leaving the completed grid snapshot untouched.
The final transfer patch is validated in `/home/sandy/pi-lab-patchcheck-20261025`.

## Resume safeguards

The follow-up review reproduced two silent reuse defects: the grid accepted `metrics.json`
without checking the run, and a checkpoint's identity omitted the dialogue-context bytes.
`src.stage1.grid_check` now validates the entire requested grid with stdlib-only code before
its first training process starts. A later stale result therefore prevents earlier pending
runs from consuming GPU time.

New Stage 1 metrics and result lines include `dialogues_sha256`, `source_sha256` and
`predictions_sha256`. Source hashing covers all Python files under `src/`, including dirty
edits, with CRLF normalized to LF. The hash is identical on Windows and WSL. `prepare` captures
data/source hashes; `finish` refuses changed inputs before writing outputs. Checkpoints use
the same items/dialogues/source identity, together with their existing recipe and batch fields.

Historical artifacts are not rewritten or given invented provenance. The real completed
base-grid `none`/seed-13 artifacts were checked: automatic reuse is refused for missing
dialogues/source hashes, and all three output hashes remain unchanged. The completed base
results and their recorded analysis remain available. Use the original source for historical
checkpoints, or a separate output tree for a fresh run with the current source.

The new checks were exercised with tiny CPU training models and invented data, followed by
the full suites above. No full model training or lab GPU job was launched. Detailed logs use
the `resume-` prefix in the evidence directory. Fresh 5090 and 4090 DeBERTa-large dry runs each
produce 15 commands.

## DeBERTa-large lab commands

These require this session's uncommitted changes. Until they are committed and pushed, use
`outputs/verification/readiness-20261025/lab-readiness.patch` with a clean checkout at the base
commit above. Transfer the patch to the lab and run `git apply --check` before `git apply`:

```bash
git switch -c chore/lab-dev-readiness 1016c258eeb1070542b07899812d87f1a92ab89b
git apply --check /path/to/lab-readiness.patch
git apply /path/to/lab-readiness.patch
```

Keep the lab checkout on its Linux filesystem. From its root:

```bash
uv sync --locked --group gpu
uv run --locked python -m src.data.download_sources
uv run --locked python -m src.data.build_direct_dataset
uv run --locked --group gpu python -m src.stage1.env_check
uv run --locked --group gpu python -m src.stage1.length_check \
  --config configs/stage1/encoder_deberta_v3_large.toml \
  --out outputs/verification/length-deberta-large.json

# 5090: smoke first; inspect loss, predicted classes and peak_memory_gib before the grid.
uv run --locked --group gpu python -m src.stage1.encoder \
  --config configs/stage1/encoder_deberta_v3_large.toml \
  --seed 13 --train-condition full --machine lab-5090 --smoke
bash scripts/stage1_grid.sh configs/stage1/encoder_deberta_v3_large.toml lab-5090 --dry-run
# Run this only after the smoke succeeds; five seeds × three training conditions.
bash scripts/stage1_grid.sh configs/stage1/encoder_deberta_v3_large.toml lab-5090
```

For a 4090, start conservatively, preserving effective batch 32:

```bash
uv run --locked --group gpu python -m src.stage1.encoder \
  --config configs/stage1/encoder_deberta_v3_large.toml \
  --seed 13 --train-condition full --machine lab-4090 \
  --micro-batch-size 4 --gradient-checkpointing --smoke
MICRO_BATCH=4 GRAD_CKPT=1 bash scripts/stage1_grid.sh \
  configs/stage1/encoder_deberta_v3_large.toml lab-4090 --dry-run
# After the smoke succeeds:
MICRO_BATCH=4 GRAD_CKPT=1 bash scripts/stage1_grid.sh \
  configs/stage1/encoder_deberta_v3_large.toml lab-4090
```

Use a persistent terminal/session, keep the machine awake, and keep this checkout's source and
data fixed throughout the grid. Checkpoints are saved every 250
optimizer steps; repeat the same command to resume. Stop on OOM, nonfinite losses or class
collapse and record the failure before changing a recipe. These are dev commands; the reported
test grid needs the separate [freeze procedure](freeze.md).

## RoBERTa budget finding

Both pinned RoBERTa tokenizers give the same result under `render-v1` at 350 words:
all dev conditions fit (maximum 500 tokens); training `none`, `one` and `full` fit (maximum
512); training `mismatched` has two 514-token inputs. These two inputs are outside the default
three-condition training grid, but the current all-condition preflight still fails.

The protocol says to lower the common budget under `render-v2` when a preflight exceeds 512,
never to truncate one model silently. That would require regenerated manifests/audits and
comparable baseline reruns. The renderer and existing results were left unchanged. Sandy chose
DeBERTa-large preparation with RoBERTa on hold on 2026-10-25. This does not remove RoBERTa from
the planned panel or change the all-condition preflight requirement. A later shared-renderer
revision would also require reconsidering DeBERTa runs made now.

## Remaining freeze decisions

`freeze check` still reports `analysis_draft`, missing LLM and hybrid recipes, a floating/missing
LLM model identifier, and `tree_dirty`. Sandy still needs to name the primary system, supply or
remove the LLM/hybrid panel entries, decide the rules version, and authorize commits before the
freeze. `auto-v1` remains the default; no human labels or research decisions were invented.
