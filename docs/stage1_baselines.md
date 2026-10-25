# Stage 1 baselines: weak supervision, context ablation, how to run

**2026-10-18:** standalone Stage 1 rescoring accepts `--rules-version auto-v2` for explicit
provisional v2 slices; the default and existing model-run configs retain v1. The v2 source is
frozen, its held-out round-2 agreement is 29/30 (the same as v1), and fresh L3 precision is pending.
See [the rule check handoff](option_a_checks.md) and [Stage 2/transfer scoring](stage2_scoring.md).

_Added 2026-10-07. Development code: it has been unit-tested and checked against the real DIRECT +
MultiWOZ join (data loading only). No model has been trained yet._

This is the "TF-IDF baseline with a distinct training source and dialogue-separated dev evaluation"
from the [round 2 review](round2_review.md), plus the cross-encoder runs that come after it. It does
not settle the open annotation decisions. Rule-assigned levels and intent categories appear only as
evaluation slices (see [Slices](#slices-option-a)).

## Revised-study scope (2026-10-09)

These trainers remain weak-label development tools under the [revised plan](research_plan.md). They do not yet ingest literary data or contextual gold function and Stage 2 interpretation. The new [analysis plan](analysis_plan.md) is an unfrozen draft; its existence does not authorize reported test runs. Complete its freeze checklist and the contextual adapter/scorers first. The existing supervision policy, code and configs are unchanged.

## Supervision policy `direct_variants_v1`

Training labels come from DIRECT's **train** split and evaluation from its **dev** split
(MultiWOZ's official validation dialogues), so no dialogue appears on both sides. DIRECT's variant
names are weak Stage 1 labels, not human L0–L3 levels. Implementation:
[`src/stage1/data.py`](../src/stage1/data.py).

| DIRECT row | Examples |
|---|---|
| Target turn's user acts are only thanks / bye / greeting | both paraphrases → `no_request` |
| Any other user acts | `direct` paraphrase → `direct`, `indirect` paraphrase → `indirect` |
| No user acts (a MultiWOZ annotation gap) | excluded: request status unknown |
| Direct and indirect text identical | excluded: contradictory labels |
| Original `target` utterance | not used: DIRECT gives it no directness label |
| Test row whose paraphrase DIRECT's raters marked unacceptable | that paraphrase excluded |

Context always comes from the original dialogue; only the target utterance is replaced by its
paraphrase.

Counts on the real join:

| | Examples | direct | indirect | no_request | Excluded |
|---|---|---|---|---|---|
| Train (every condition) | 101,460 | 41,450 | 41,450 | 18,560 | 5,939 rows with no acts, 1 identical pair, 85 rows with no mismatch donor (170 examples) |
| Dev, genuine set (none / one / full) | 11,394 | 4,517 | 4,517 | 2,360 | 998 rows at turn 0, 676 rows with no acts |
| Dev, mismatch set (mismatched, mismatched_one) | 11,340 | | | | the genuine set minus 54 examples (27 rows) with no donor |

The training set is identical under every training condition. Since spec 004 (2026-10-14) dev is
scored on two sets ([spec 004](../specs/004-context-conditions/spec.md)):

- the **genuine** set, every turn with prior context, for `none`, `one` and `full`;
- the **mismatch** set, the genuine turns that have a mismatch donor, for `mismatched` and
  `mismatched_one`.

A contrast uses one set on both sides, so its difference is paired; `metrics.json` records each
contrast's `set` and `n`. Before spec 004 every condition used the mismatch set, so turns without a
donor (mostly long dialogues) silently left the genuine-context results too.

**Context budget (D-06).** All inputs, training and evaluation, come from the shared renderer
`src.data.contexts` (`render-v1`): under `full` and `mismatched`, context plus utterance is at most
350 whitespace tokens, oldest whole turns dropped first, the utterance never cut. On dev this drops
turns from 71 `full` examples (0.6%); on test from 104 (0.9%). The budget is a renderer constant,
the same for every model, never a config key.

**Known noise.** About 15% of DIRECT's indirect paraphrases still use an L1 formula ("could you…"),
and some crowd paraphrases change the meaning. A model trained on these labels learns "which of
DIRECT's two rewrites is this". That approximates indirectness, but it is not the CCSARP scale.

## Design

- **Train under one condition, score under all five.** Each run trains with `train_condition` and
  predicts dev under `none`, `one`, `full`, `mismatched` and `mismatched_one`.
  - Training under each of `none` / `one` / `full` / `mismatched` gives the context ablation.
  - Scoring a `full`-trained model under `mismatched` is the relevant-context control at test time.
- **Paired contrasts.** `metrics.json` reports `one-none`, `full-none`, `full-one`,
  `full-mismatched` and `one-mismatched_one`, each as an accuracy difference with a 95% paired
  bootstrap interval over dialogues, overall and **by variant**. The two mismatch contrasts also
  have a `without_cue_donors` line: the same contrast without examples whose donor context names a
  value from the target turn's user acts (a sensitivity check, see spec 004 FR9). A larger context benefit on
  `indirect` than on `direct` paraphrases is the descriptive H2 signal. The mixed-effects test
  belongs in the analysis plan, not here.
- **Artifact probe.** `tfidf-utterance` sees no context. If it already separates the variants well,
  most of the signal is surface wording (research plan, Phase 3).
- **Fixed recipe.** There is no early stopping or selection on dev: epochs and the learning rate are
  in the config. Test runs use the same recipe file with `--eval-split test --allow-test`, and need
  a verifying WP-08 freeze record ([docs/freeze.md](freeze.md)). The run must be in the frozen
  grid: pinned recipe, frozen seed, and a training condition its design uses. `--smoke` is refused
  on test.
- **Test audit (spec 006).** With `eval_split = "test"`, the trainer checks the committed split audit
  in `prepare`, before any training: a missing or stale audit stops the run. Only primary examples
  are predicted and scored. Every contrast gains a `primary_minus_dup` line, and `metrics.json`
  and `results/stage1.jsonl` record a `test_audit` block. `python -m src.evaluation.stage1
  --split test` applies the same gate. Dev runs are unchanged.

## Setup (once per machine: WSL2 on the 5060, Linux on the lab 5090 or 4090)

Keep the repo under `~/`, not `/mnt/c`. On WSL, install only the Windows NVIDIA driver; CUDA 12.8
wheels need driver 570 or newer. The 5090 is sm_120, like the 5060, so the same `uv.lock` torch
build covers it; `env_check` confirms this.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh          # uv, if not installed
git clone https://github.com/sandythomas1/Pragmatic-Intent.git ~/Pragmatic-Intent
cd ~/Pragmatic-Intent && git switch feature/stage1-baselines
uv sync --group gpu                                       # Python 3.12, torch 2.11 + CUDA 12.8, pinned by uv.lock
uv run python -m src.data.download_sources                # ~420 MB, checksummed
uv run python -m src.data.build_direct_dataset            # deterministic: same bytes on both machines
uv run --group gpu python -m src.stage1.env_check --tokenizer microsoft/deberta-v3-base
```

`env_check` fails if the torch build has no kernels for the GPU (the usual RTX 50-series problem),
if bf16 does not work, or if the data files are missing. Each result records `items_sha256`.
Compare it across machines to confirm both built the same dataset.

## Run order

Always pass `--machine` (e.g. `rtx5060-wsl`, `lab-5090`). It is the machine label written to the
committed results log; the hostname stays in the run's local `metrics.json`.

```bash
# 1. CPU baselines (either machine, minutes)
uv run --group classical python -m src.stage1.tfidf --config configs/stage1/tfidf_utterance.toml --seed 13 --machine rtx5060-wsl
for c in one full mismatched; do
  uv run --group classical python -m src.stage1.tfidf --config configs/stage1/tfidf_context.toml \
    --seed 13 --train-condition $c --machine rtx5060-wsl
done

# 2. Encoder smoke test (1,000 train / 300 dev examples; not logged to results)
uv run --group gpu python -m src.stage1.encoder --config configs/stage1/encoder_deberta_v3_base.toml \
  --seed 13 --train-condition full --machine rtx5060-wsl --micro-batch-size 8 --smoke

# 3. Large-encoder smoke test on the 5090: check the loss falls and read peak_memory_gib
uv run --group gpu python -m src.stage1.encoder --config configs/stage1/encoder_deberta_v3_large.toml \
  --seed 13 --train-condition full --machine lab-5090 --smoke

# 4. Full grids: 4 training conditions x 5 seeds, resumable (on the 5090 for reported numbers)
scripts/stage1_grid.sh configs/stage1/encoder_deberta_v3_large.toml lab-5090
scripts/stage1_grid.sh configs/stage1/encoder_roberta_large.toml lab-5090
```

**Encoders (2026-10-19).** With the lab RTX 5090 the planned encoders are the large models:
`deberta-v3-large` first, then `roberta-large` as the second encoder (the first model cut under
schedule pressure). The base configs stay for quick development runs on the 5060. The large
configs use learning rate 1e-5 and 10% warmup, the usual settings for these models, because large
DeBERTa can collapse to a single class at 2e-5. A collapsed smoke run is a recipe failure: report
it before the grid, so any change is made once, on dev, before recipes are pinned.

**Machine settings.** `batch_size = 32` is the effective batch and stays fixed. On a smaller GPU,
lower only `--micro-batch-size`; gradient accumulation keeps the optimization the same, and the
resolved value is logged.
- RTX 5060 (8 GB): base models only, `--micro-batch-size 8`. Use 4 plus `--gradient-checkpointing` if you run out of memory.
- RTX 4090 (24 GB): base models at the default 16, or 32; large models at 8.
- RTX 5090 (32 GB): base models at 32; large models at the config default (8 for DeBERTa, 16 for
  RoBERTa). Raise it only if the smoke run's `peak_memory_gib` leaves room. Long `full` inputs
  set the peak.

With the grid script, set `MICRO_BATCH=8`, `GRAD_CKPT=1`, `SEEDS="13"` or `CONDITIONS="full"`.
The default is five seeds (`13 42 2026 314 2718`).

**Checkpoints.** `--checkpoint-every N` saves the full training state every N optimizer steps,
and once more when training ends, to `<run dir>/checkpoint.pt`. The state covers the weights,
optimizer, scheduler, data order and RNG states. Rerunning the same command resumes from it,
with the same batches and dropout stream as an uninterrupted run. The checkpoint is deleted
after the run's outputs are written. A crash or sleep therefore costs at most N steps, not the
whole run. A checkpoint from a different recipe, seed, condition, data file or batch layout is
refused; delete it to restart that run.
- The grid script checkpoints every 250 steps by default (`CHECKPOINT_EVERY=0` turns this off).
- A checkpoint is about 3× the model's fp32 size: roughly 2 GB for base models and 5 GB for large.
- After a resume, `model.resumed_at_steps` lists the steps each resume started from.
  `peak_memory_gib` then covers only the last process.

**Runtime.** Each encoder run processes 101,460 × 2 epochs of training examples, plus 5 × 11,340
dev predictions. The smoke test logs examples per second; use it to estimate a full run before
starting a grid. Following the research plan's compute rule, report each model's numbers from a
single machine.

**Pin the model revision before reported runs.** The first run logs `model.resolved_revision`.
Copy that hash into the config's `revision` so later runs cannot pick up a changed checkpoint.

## Outputs

| Path | Content | In git? |
|---|---|---|
| `outputs/stage1/<run>/train-<condition>/seed<N>/predictions.jsonl` | `example_id`, `condition`, `prediction`, class `probs` (no text) | no |
| `…/metrics.json` | full report: per-condition metrics, slices, contrasts, counts, provenance, hostname | no |
| `…/config.resolved.json` | the exact config after overrides | no |
| `results/stage1.jsonl` | one line per completed run: headline metrics and contrasts, config/data hashes, git commit and dirty flag, GPU, package versions, machine label | **yes**: commit it after runs |

`git_dirty` ignores the run's own outputs (the `--results` log and the run's output directory), so a
seed grid can append to the tracked log in one checkout and each run still records `false` when
the code is clean. Any other change, tracked or untracked, still marks the run dirty.

To re-score a predictions file, for example after a new rule version (`--dialogues` defaults to
`data/interim/direct/dialogues.jsonl` and is needed for the donor cue flags):

```bash
python -m src.evaluation.stage1 --predictions outputs/stage1/<run>/train-full/seed13/predictions.jsonl \
  --out /tmp/rescored.json
```

**Cross-run analysis (spec 007).** A run's `metrics.json` has bootstrapped each contrast on its
own. The paper's numbers come from `python -m src.analysis run` instead (see
[analysis plan](analysis_plan.md), D-07):
- it re-validates every run's predictions against its saved `metrics.json`;
- it averages seeds;
- it puts every statistic on one shared dialogue bootstrap.

List the run directories in `configs/analysis/inputs-<split>.toml` (format in
`src/analysis/inputs.py`). Each run must match what it recorded: name, train condition,
`eval_split`, seed, and not a smoke run. A `test_time` system needs a `full`-trained run, so train
`tfidf-utterance` with `--train-condition full` as well.

```bash
python -m src.analysis run --split dev --inputs configs/analysis/inputs-dev.toml   # dev diagnostics only
```

## Context checks and the manifest (spec 004)

```bash
python -m src.data.context_manifest check --split dev      # seven invariant rules; exit 1 on any failure
python -m src.data.context_manifest manifest --split test  # data/manifests/contexts_test.csv + summary
python -m src.data.context_manifest manifest --split test --verify   # rebuild and compare bytes
```

`check` slices the expected context straight from `dialogues.jsonl` (it never trusts the renderer)
and verifies: identical target under every condition, no turn at or after the target, the budget,
and the donor rules (same split, other dialogue, window `0..t` ending on a system turn, no shared
act domain). The manifest holds IDs, set membership, budget drops, cue flags and SHA-256 hashes of
every condition's input, no text. The test manifest and both summaries are committed (the test
manifest is the freeze object; `.gitattributes` keeps it LF-only); the dev manifest is git-ignored
and regenerated. Both splits take about 1–3 seconds.

**Encoder length check (Sandy, WSL, before the freeze).** The budget is counted in words, so confirm
that no budgeted input exceeds the encoder's 512 subword tokens:

```bash
uv run --group gpu python -m src.stage1.length_check --config configs/stage1/encoder_deberta_v3_base.toml
uv run --group gpu python -m src.stage1.length_check --config configs/stage1/encoder_roberta_base.toml
```

It exits 1 if any input would be truncated; then the budget is lowered for every model under a new
renderer version. Each large model uses the same tokenizer as its base model, so these two checks
also cover `deberta-v3-large` and `roberta-large`. Encoder runs also record `eval_inputs_at_max_length` per condition.

## Slices (option A)

_Since 2026-10-14 ([spec 001 v1.2](../specs/001-pragmatic-intent-study/spec.md)); these replace the
human-level slice._ Every condition and every paired context contrast is also broken down by:

| Key | Value | Source |
|---|---|---|
| `by_rule_level` | `auto-v1` level (L0–L3, INF, NR) of the example's own paraphrase | [`src/data/auto_levels.py`](../src/data/auto_levels.py) |
| `by_category` | `cat-v1` primary intent category of the target turn | [`src/data/intent_categories.py`](../src/data/intent_categories.py) |

`metrics.json` and `results/stage1.jsonl` record each slice's version under `slices`. Gold labels
stay the weak `direct_variants_v1` labels; the rule levels are the indirectness variable for the
context × indirectness breakdown, and are never called gold. Report them with their agreement
against the human calibration rounds (`python -m src.data.auto_levels validate`).

On dev (the 11,340-example mismatch set) the rules put 1,695 of 5,670 "indirect" paraphrases (30%) at
L0, so `by_rule_level` and `by_variant` differ substantially.

## What these numbers can and cannot support

- They are **development** results on dev, against weak labels. They support debugging, the
  artifact probe and choosing what to run. They are not the paper's H2 test.
- `by_human_level` uses the round 2 labels, which are unadjudicated. Only 18 of them fall on scored
  examples: direct/indirect paraphrases of turns with user acts. That slice is a sanity check. On
  those 18, the weak label and the submitted level often disagree. Two `indirect` paraphrases were
  labeled L0, and `direct` paraphrases were labeled L1–L3 or INF. This is expected, given the noise
  noted above, and it is why weak labels must not stand in for levels.
- Before reported experiments: adjudicate round 2, freeze the rubric, settle the six-way → Stage 1
  mapping, label a frozen test sample, and freeze `docs/analysis_plan.md` under the revised collection protocol.
