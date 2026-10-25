# Verification: Spec 008

_2026-10-22. This covers the spec 008 tooling on `feature/option-a-auto-levels`, uncommitted. No
freeze was written: the real repository is not ready (see "Real repository"), and the freeze date
belongs to Sandy._

## Test suite

| Environment | Result |
|---|---|
| Native Windows, Python 3.12, without git on PATH | 888 ran, OK (10 skipped: the git tests and the git-dependent provenance tests) |
| Native Windows, Python 3.12, GitHub Desktop's git on PATH | 888 ran, OK (0 skipped) |
| WSL Ubuntu 22.04, `~/Pragmatic-Intent/.venv` Python 3.12.15, same working tree via `/mnt/c` | 888 ran, OK (5 skipped) |

The spec 008 tests are 157 tests in seven files, all with invented fixtures (`tests/freeze_fixtures.py`):

| File | Tests |
|---|---|
| `test_freeze_inputs.py` | 26 |
| `test_freeze_recipe.py` | 13 |
| `test_freeze_pins.py` | 23 |
| `test_freeze_check.py` | 21 |
| `test_freeze_record.py` | 33 |
| `test_freeze_amend.py` | 17 |
| `test_freeze_gates.py` | 24 |

Four existing test files now stub the new gate where they test spec 006/007 behavior on test:
- `test_test_audit` (Stage 1 and Stage 2 scoring);
- `test_freeze_recipe` (eval split);
- `test_analysis_cli` and `test_analysis_report`;
- `test_analysis_error_audit` (setup).

## Acceptance criteria

| AC | Evidence | Status |
|---|---|---|
| AC-008-01 `check` on fixtures | `test_freeze_check` and `test_freeze_pins` cover each finding code. The fixture tests include `analysis_draft`, `revision_unpinned` (`main`, a tag, a short hash), `recipe_missing`, `llm_model_floating`/`_missing` and `glob_empty`. A ready fixture exits 0. | pass |
| AC-008-02 existing readers | `WriteTest.test_existing_readers_accept_the_record_unchanged`: `src.analysis.freeze.freeze_date`, `require_frozen_config` and `split_audit.resolve_freeze_date` all accept the record. After an amendment, `require_frozen_config` accepts the new hash (`test_an_analysis_config_amendment_moves_the_top_level_hash`). | pass |
| AC-008-03 write refusals | `PreconditionTest` has one test per code: `freeze_exists`, `analysis_draft`, `test_audit_failed`, `git_unavailable` (three unknown shapes), `tree_dirty`, `date_in_future`, and `date_not_after_inspection` for the same day and the day before. `RealGitTest` covers a clean tree, ignored `results/` and `outputs/`, a tracked edit and an untracked file. A refused write leaves no file and no `.tmp`; a second write is refused and the record is kept. | pass |
| AC-008-04 no IDs | `NoTestIdsTest`: an unregistered fixture sheet gives `scan_unregistered` as a count plus the path. The ID is absent from stdout, stderr and the captured logs. Invalid registry rows are never echoed. Every printed line goes through `mask_ids`. | pass |
| AC-008-05 what `verify` detects | `VerifyDetectsTest`: items, registry `pre_freeze` rows, manifest, code, a new file under a code glob, analysis config content, prompt, Stage 1 semantic field, `uv.lock`, missing data, record edits (pin, date, original pin, inputs path), a rehashed pin edit, malformed records and fields, oversize, no record, an unsafe `inputs_path`. `VerifyToleratesTest`: `post_scoring` rows plus disclosure growth, CRLF code, comment-only config and recipe edits, run outputs. | pass |
| AC-008-06 amendments | `AmendTest` and `RefusalTest`: a chained, dated, reasoned entry with its commit. Added and removed pins. Two amendments chain, and tampering with the first (reason, chain, date order, a missing field) breaks `verify`. Refusals: no record, a tampered record, nothing changed, `frozen_set_immutable` (membership, data), bad reasons (empty, blank, 501 characters, newline, non-ASCII, IDs in either case), dates, write preconditions, size cap. A refused amendment leaves the record byte-identical. | pass |
| AC-008-07 gates | `test_freeze_gates`: the Stage 1 runner, the Stage 2, transfer and Stage 1 re-scorers, the legacy `evaluation.run`, and the test analysis. Each refuses with no record and with a failing record, and passes with a verifying one. The runner and the analysis also refuse `recipe_not_frozen`, `seed_not_frozen` and `condition_not_frozen`. Also covered: `--smoke` on test is refused; dev ignores an absent or broken record; `--eval-split test` without `--allow-test` is refused; `freeze_content_sha256` reaches `metrics.json` and the results line. | pass |
| AC-008-08 determinism | `test_the_bytes_are_deterministic_across_repositories`: two fixture repositories give byte-identical records, LF, with no absolute paths. `StabilityTest`: CRLF and LF checkouts pin identically. | pass |
| AC-008-09 real-repo timing | `check` took 1.9 s on Windows and 3.4 s on WSL (bound: 30 s). Over the same tree, the pin digest is identical on Windows and WSL (`e65d8529d8fb781f`, 74 pins). | pass |
| AC-008-10 docs | `docs/freeze.md`: procedure, amendments, codes, limits. `docs/stage1_baselines.md` documents the test-run flags. The roadmap WP-08 row and next actions point to it. | pass |

## Real repository (2026-10-22)

`python -m src.data.freeze check` exits 1 on both platforms with the same 8 items. These are the
work that must be done before the freeze:

| Item | Owner |
|---|---|
| `analysis_draft`: name the primary system, set `draft = false` (and settle the spec 007 fallback question) | Sandy |
| `revision_unpinned` × 3: `deberta-v3-large`, `roberta-base`, `roberta-large` | Sandy |
| `recipe_missing` for `llm` and `hybrid`, and `llm_model_floating` for `llm` | Sandy (D-05) |
| `tree_dirty`: the uncommitted spec 007 T14 and spec 008 work | Sandy commits |

These pass on the real data already:
- the split audit (`require_test_audit`);
- the sheet scan;
- the manifest agreement;
- the `auto-v1` rules version.

The data and membership pins equal the hashes committed in `split_audit_test_summary.json`.

## Resume verification, 2026-10-23

The existing Oct 22 working-tree implementation was preserved. Native Windows Python 3.12,
with GitHub Desktop's git on PATH: **888 tests passed in 71.271 s, no skips**. Existing
`GateTestCase.test_args` deprecation warnings remain; they did not fail the suite.
The read-only real-repository `freeze check` again found 74 ready pins and the same 8 open
items listed above. No freeze was written and no model run was launched. WSL was not rerun.

Later that day, Sandy requested WSL execution. The isolated `~/pi-wsl-20261023` snapshot passed
the same 888 tests in 12.809 s (5 skipped) with Python 3.12.15, and its read-only `freeze check`
again reported 74 ready pins and the same 8 items. No freeze was written. Subsequent dev-only
GPU smoke tests and the launched encoder grid are documented in the
[WSL run record](../../docs/wsl_development_2026-10-23.md); they are separate from freeze verification.

## Deviations from the reviewed spec and plan

- `uv.lock` is pinned as `env.uv_lock`, not `data.uv_lock`, so that a dependency fix can be amended
  (FR3 updated).
- `check` prints findings plus a count, with ready pin keys behind `--verbose`. FR10 asked for one
  line per pin (decisions.md, T4).
- Review R3 missed two test entry points, `src.evaluation.stage1 --split test` and the legacy
  `src.evaluation.run --split test`. Both are now gated, and FR16 is updated. They import the gate
  lazily, because `src.evaluation.stage1` sits in the freeze module's import chain.
- The existing test-analysis tests stub the gate instead of building a real freeze. The real-freeze
  analysis gate is covered in `test_freeze_gates.AnalysisGateTest`.
- The `security-review` skill could not run, because it needs git on PATH in the Claude shell.
  Each security-sensitive task (T1, T4, T5, T6) had a manual pass instead, recorded in
  `tasks.md`.

## Seen, not fixed

- `src.evaluation.transfer.main` doesn't catch `ManifestError` from a malformed `sources.toml`, so
  it raises instead of printing a failure. The real `sources.toml` is valid, so this is out of
  scope here.
