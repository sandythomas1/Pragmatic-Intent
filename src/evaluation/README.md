# Directness evaluation harness

Requires Python 3.11+ and the standard library. Labels come from exported human
annotations; source metadata comes from the existing DIRECT + MultiWOZ join.
Original/direct/indirect variants are dataset provenance, not level labels.

Run the development majority-class pilot from the repository root:

```bash
python3 -m src.evaluation.run \
  --annotations data/annotations/levels_round2.csv \
  --out-dir outputs/round2-pilot
```

The pilot uses leave-one-dialogue-out validation on the labeled dev sample. Every
variant and turn from a held-out dialogue is excluded from training. Ties follow
the fixed label order `L0`, `L1`, `L2`, `L3`, `INF`, `NR`. It uses no text/context
features, so predictions are identical under `none`, `one`, `full`, `mismatched`,
and `mismatched_one`. No GPU or additional download is needed.

Outputs are `predictions.jsonl` and `metrics.json`, in the ignored `outputs/`
folder. Re-running the same command replaces these outputs. Use a new output
folder to keep a run. Artifacts contain IDs, labels and aggregate metrics, without
source utterance text. Reports include input/source hashes, seed, Python version,
and the current Git commit; uncommitted changes are indicated explicitly.

## Score model predictions

For a single model/run, supply JSONL with these fields:

```json
{"item_id": "r2-01", "condition": "none", "prediction": "L0"}
```

```bash
python3 -m src.evaluation.run \
  --annotations data/annotations/levels_round2.csv \
  --predictions outputs/my-model/predictions.jsonl \
  --out-dir outputs/my-model-scored
```

Each supplied condition must cover every scorable labeled item exactly once.
Missing, duplicate, unknown IDs and invalid predictions fail rather than produce
partial scores. `?` gold labels are excluded and counted; `?` predictions are
invalid. With undecidable gold items, omit their predictions from the scoring
file. Mixed-case labels normalize. Select one annotator with `--annotator A1`.
The default split is `dev`; all annotations must belong to that split. Use
`--split test` only for externally generated predictions on a separate frozen
test sample. The automatic majority pilot refuses train/test runs.

Metrics include accuracy, macro-F1 over the fixed six labels (absent classes have
F1 zero), confusion matrices, and slices by gold level, provenance variant and
target-turn domain. The domain slice is metadata from MultiWOZ, not a validated
Stage 2 intent label; multi-domain turns form a combined slice. Accuracy has a
95% percentile bootstrap interval, resampling entire dialogues to preserve
correlation between variants. Defaults: 1,000 draws and seed 20261006. These are
descriptive intervals; they do not replace the planned mixed-effects analysis,
and on the tiny cross-validated pilot they do not model training variability.

Round 2 labels are provisional calibration annotations. This command implements
scoring and a development sanity check; it does not establish inter-annotator
agreement, freeze the rubric/test set, evaluate Stage 2, or define the final
direct/indirect/no-request mapping for Stage 1.

```bash
python3 -m unittest tests.test_evaluation
```
