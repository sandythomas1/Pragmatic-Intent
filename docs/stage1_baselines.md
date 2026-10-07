# Stage 1 baselines: weak supervision, context ablation, how to run

_Added 2026-10-07. Development code: it has been unit-tested and checked against the real DIRECT +
MultiWOZ join (data loading only). No model has been trained yet._

This is the "TF-IDF baseline with a distinct training source and dialogue-separated dev evaluation"
from the [round 2 review](round2_review.md), plus the cross-encoder runs that come after it. It does
not settle the open annotation decisions. Human levels appear only as an evaluation slice.

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
| Dev, comparable | 11,340 | 4,507 | 4,507 | 2,326 | 1,027 rows at turn 0 or with no donor, 674 rows with no acts |

The training set is identical under every training condition. The dev set keeps only
**comparable** turns: turn index > 0 with a mismatch donor. Every condition therefore scores the same
11,340 examples, and differences between conditions are paired.

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
  bootstrap interval over dialogues, overall and **by variant**. A larger context benefit on
  `indirect` than on `direct` paraphrases is the descriptive H2 signal. The mixed-effects test
  belongs in the analysis plan, not here.
- **Artifact probe.** `tfidf-utterance` sees no context. If it already separates the variants well,
  most of the signal is surface wording (research plan, Phase 3).
- **Fixed recipe.** There is no early stopping or selection on dev: epochs and the learning rate are
  in the config. `--allow-test` is required before anything is scored on test. Keep test for the
  frozen run, after `docs/analysis_plan.md` exists.

## Setup (once per machine: WSL2 on the 5060, Linux on the lab 4090)

Keep the repo under `~/`, not `/mnt/c`. On WSL, install only the Windows NVIDIA driver; CUDA 12.8
wheels need driver 570 or newer.

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

Always pass `--machine` (e.g. `rtx5060-wsl`, `lab-4090`). It is the machine label written to the
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

# 3. Full grids: 4 training conditions x 3 seeds, resumable (on the 4090 for reported numbers)
scripts/stage1_grid.sh configs/stage1/encoder_deberta_v3_base.toml lab-4090
scripts/stage1_grid.sh configs/stage1/encoder_roberta_base.toml lab-4090
```

**Machine settings.** `batch_size = 32` is the effective batch and stays fixed. On a smaller GPU,
lower only `--micro-batch-size`; gradient accumulation keeps the optimization the same, and the
resolved value is logged.
- RTX 5060 (8 GB): `--micro-batch-size 8`. Use 4 plus `--gradient-checkpointing` if you run out of memory.
- RTX 4090: the default 16, or 32.

With the grid script, set `MICRO_BATCH=8`, `GRAD_CKPT=1`, `SEEDS="13"` or `CONDITIONS="full"`.

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

To re-score a predictions file, for example with a later round's human levels:

```bash
python -m src.evaluation.stage1 --predictions outputs/stage1/<run>/train-full/seed13/predictions.jsonl \
  --out /tmp/rescored.json --levels data/annotations/levels_round2.csv
```

## What these numbers can and cannot support

- They are **development** results on dev, against weak labels. They support debugging, the
  artifact probe and choosing what to run. They are not the paper's H2 test.
- `by_human_level` uses the round 2 labels, which are unadjudicated. Only 18 of them fall on scored
  examples: direct/indirect paraphrases of turns with user acts. That slice is a sanity check. On
  those 18, the weak label and the submitted level often disagree. Two `indirect` paraphrases were
  labeled L0, and `direct` paraphrases were labeled L1–L3 or INF. This is expected, given the noise
  noted above, and it is why weak labels must not stand in for levels.
- Before reported experiments: adjudicate round 2, freeze the rubric, settle the six-way → Stage 1
  mapping, label a frozen test sample, and write `docs/analysis_plan.md`.
