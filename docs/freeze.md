# The WP-08 freeze record

_Spec 008 ([spec](../specs/008-freeze-record/spec.md), [plan](../specs/008-freeze-record/plan.md)).
Stdlib only; run from the repository root._

The freeze record, `data/manifests/freeze.json`, pins everything that determines a reported test
number:

| Family | What is pinned | Can it be amended? |
|---|---|---|
| `data.*` | `data/sources.toml`, `items.jsonl`, `dialogues.jsonl` | **no** |
| `membership.*` | split audit (CSV and content hash), registry `pre_freeze` rows, context manifest, renderer version, budget | **no** |
| `env.uv_lock` | `uv.lock` | yes |
| `labels.*` | rules version, and the `auto-v2` seal if `auto-v2` is used | yes |
| `code.*` | every file matched by the code globs in `configs/freeze/freeze-v1.toml` | yes |
| `analysis.*` | the canonical hash of `configs/analysis/analysis-v1.toml` | yes |
| `recipe.<system>.*` | Stage 1 recipe hash, encoder revision, prompt files, `llm_model`, seeds | yes |

**What enforces it.** Every test-time entry point refuses to run unless `verify` passes:
- the Stage 1 trainers, with `--eval-split test --allow-test`;
- `src.evaluation.stage1`, `stage2`, `transfer` and `run`, each with `--split test`;
- `src.analysis run --split test`.

The trainers and the test analysis also refuse a Stage 1 run outside the frozen grid: a recipe
that isn't pinned, a seed that isn't listed, or a training condition the system's design doesn't
use. Dev runs never read the record.

## Commands

```bash
python -m src.data.freeze check [--on YYYY-MM-DD] [--verbose]   # read-only: what is still missing
python -m src.data.freeze write --on YYYY-MM-DD                  # once; refuses unless check is clean
python -m src.data.freeze verify                                 # recompute every pin
python -m src.data.freeze amend --on YYYY-MM-DD --reason "..."   # after the freeze, dated and chained
python -m src.data.freeze show                                   # pins and amendments, for the paper
```

`check` prints problems first, then a one-line count of ready pins. It never prints a pin value, a
dialogue or item ID, or any text. It exits 0 only when `write` would succeed.

## Procedure (Sandy, before the Nov 9 grid)

1. **Settle the open items.** Run `python -m src.data.freeze check` now and after each change. On
   2026-10-22 it lists:
   - **`analysis_draft`.** Name the primary system in `configs/analysis/analysis-v1.toml` and set
     `draft = false`. This includes the spec 007 fallback question if no LLM or hybrid is ready.
   - **`revision_unpinned`** for `deberta-v3-large`, `roberta-base` and `roberta-large`. Pin each one
     to a 40-hex Hugging Face commit, as `b13ac75` did for `deberta-v3-base`.
   - **`recipe_missing`** and **`llm_model_floating`** for `llm` and `hybrid`. Add their prompt and
     config files under `files`, and a dated snapshot as `llm_model`, in
     `configs/freeze/freeze-v1.toml`. If a placeholder system is dropped from the panel, drop it
     from both files.
   - **`tree_dirty`.** Commit everything except `results/` and `outputs/`.

   Also decide `auto-v1` vs `auto-v2` (`rules_version` in the analysis config).
2. **Transcript rescan, at least one day before the freeze.** Claude reruns the spec 006 transcript
   scan, with IDs masked. Any row it registers carries that day's date. The freeze date must be
   **strictly after** every `pre_freeze` inspection; otherwise `check` says
   `date_not_after_inspection`.
3. **Commit**, then run `check --on <date>` and confirm it says `ready to write`.
4. **Write:** `python -m src.data.freeze write --on <date>`.
5. **Commit `data/manifests/freeze.json`** (`git add data/manifests/freeze.json`). Git history is
   the outside witness that the freeze came before the grid.
6. **On the lab machine**, after cloning or pulling and regenerating `data/interim/`:
   `python -m src.data.freeze verify`. It must print `verified`. If `data.items` or
   `data.dialogues` differ, the regeneration differs from the frozen one; stop and investigate. Do
   not amend.
7. **Run the grid.** Use the frozen seeds and the conditions each design implies. For example:

   ```bash
   uv run --group gpu python -m src.stage1.encoder --config configs/stage1/encoder_deberta_v3_large.toml \
     --seed 13 --train-condition none --eval-split test --allow-test --machine lab-5090
   ```

   Each run's `metrics.json` and results line carry `freeze_content_sha256`.

## Amendments

The freeze is written once. After it, a bug fix in pinned code, a recipe correction or an analysis
config change is recorded like this:

```bash
python -m src.data.freeze amend --on 2026-11-10 --reason "Fix label order in encoder.prediction_rows"
```

- `amend` recomputes the pins and records the date, the reason, every changed key (old and new
  value) and the commit. It chains the amendment to the previous record by `content_sha256`.
- It refuses when:
  - nothing changed;
  - a `data.*` or `membership.*` pin moved. The test set never moves after the freeze; that would
    need a new freeze version, disclosed;
  - the date is before the freeze or the last amendment, or after today;
  - any `write` precondition fails (for example a dirty tree or a draft config).
- **Reasons** are one line of printable ASCII, up to 500 characters, with no dialogue or item IDs.
  **Never quote corpus text in a reason.** The record is committed.
- `freeze_date` never changes. Commit the amended record.
- **Disclosure.** `python -m src.data.freeze show` lists every amendment. Each one goes in the
  paper's methods or limitations section.

## Reason codes

| Code | Meaning |
|---|---|
| `freeze_missing` / `freeze_malformed` | no record, or not a `freeze-record-v1` object |
| `freeze_tampered` | content hash, amendment chain, or top-level hash inconsistent |
| `freeze_mismatch` | a pinned file or value differs from the freeze (the keys are listed) |
| `recipe_not_frozen` / `seed_not_frozen` / `condition_not_frozen` / `system_not_frozen` | a Stage 1 run outside the frozen grid |
| `not_ready` | `write` or `amend` with failing preconditions (codes listed) |
| `frozen_set_immutable` | an amendment would move the test set or its data |
| `git_unavailable` | git not on PATH (native Windows: put GitHub Desktop's git first) or not a repository; never treated as clean |
| `scan_unregistered` | a sheet holds unregistered test dialogues; run `python -m src.data.split_audit scan` to see which |

## Limits

- The record is tamper-evident, not tamper-proof. Someone who edits both a pinned file and the
  record, and recomputes the hashes, can defeat `verify` on its own. Committing the record before
  the grid is the defence.
- Stage 2 and transfer prediction files carry no run identity. Their recipes (prompts,
  `llm_model`) are pinned, but which file came from which recipe is declared, not enforced. The
  paper says so.
- `--smoke` is refused on test. Smoke-test on dev, then run `verify`.
