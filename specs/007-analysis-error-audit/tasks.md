# Tasks: Spec 007

_Decomposed 2026-10-20 from the READY spec and plan (after review R1–R11, R6 = option a)._

**Dependency order:**
- **Foundation.** T1 (config) and T2 (bootstrap engine) depend on nothing.
- **Outcome table.** T3 → T4 → T5 build it.
- **Estimands.** T6–T8 compute them.
- **Run command and outputs.** T9–T11 build them.
- **Error audit.** T12–T13 need T9's frozen report.
- **Close-out.** T14 is the dev smoke run and the docs.

Dev evidence for D-07 arrives after T9: you can run `analysis run --split dev` on Sandy's TF-IDF
and encoder grids before the figures and the error audit exist.

**Conventions for every task:**
- stdlib Python 3.12 and `unittest`, except T11, which uses matplotlib from the `figures` uv group;
- invented fixtures only (`PMUL9xxx`-style IDs, tiny text);
- no command prints a test ID or utterance text;
- Claude runs dev only.

## T1: Analysis config, panel and canonical hash
- Description:
  - **New code:** `src/analysis/config.py` loads `configs/analysis/analysis-v1.toml` with
    `tomllib`. The config holds:
    - the rules version;
    - the **panel** (system name, family, design, required streams);
    - the primary system, endpoint, contrast and levels;
    - the exploratory levels;
    - the Holm family members;
    - the bootstrap samples, seed and confidence;
    - alpha;
    - the minimum dialogues per cell and the unstable-replicate threshold;
    - the error-audit design;
    - a `draft` flag.
  - **Validation:** strict, with every FR2 error named.
  - **Canonical hash:** the SHA-256 of sorted-key, compact JSON of the parsed content.
  - **Default config:** the committed `analysis-v1.toml` encodes the 2026-10-20 decisions:
    - the primary contrast is `full − none`, linear weights (−1, 0, +1) over L0–L2, endpoint
      `request_interpretation`;
    - L3 and INF are exploratory;
    - the Holm family is H1 trend, detection-only H2 trend, H4, full − mismatched, and H3
      test-time differences against the primary;
    - the panel holds today's Stage 1 systems (`tfidf-utterance`, `tfidf-context`, the
      DeBERTa/RoBERTa encoders) plus `llm` and `hybrid` placeholders;
    - `draft = true` until the freeze.

    The primary system stays a named placeholder until D-05.
- Files likely touched: `src/analysis/__init__.py` (new), `src/analysis/config.py` (new),
  `configs/analysis/analysis-v1.toml` (new), `tests/test_analysis_config.py` (new)
- Depends on: none
- Security-sensitive: yes. It parses a hand-edited file whose hash becomes a freeze input. A loose
  validator would let an invalid plan be frozen.
- Acceptance criteria:
  - Each of these fails with a named error (AC-007-1):
    - an unknown key, level, endpoint or contrast;
    - a family member or primary system outside the panel;
    - a primary system lacking the streams its endpoint needs (`request_interpretation` needs
      `routed` + `oracle`);
    - an empty or duplicate family member;
    - the primary test inside the family;
    - a non-positive bootstrap count or minimum-cell size.
  - Reordering keys, adding comments or reformatting leaves the hash unchanged. Changing any value
    (including `draft`) changes it.
  - The committed default loads, validates and has `draft = true`.
- Status: done (2026-10-20). 15 tests in `tests/test_analysis_config.py`; full suite 616 OK on
  native Windows, with and without git on PATH. Decisions are in `specs/memory/decisions.md`
  (T1 entry).

## T2: Shared dialogue bootstrap engine and Holm
- Description:
  - **`DialogueIndex`:** sorted dialogue IDs.
  - **`StatVector`:** dense `num`/`den` lists aligned to the index.
  - **`shared_bootstrap(stats, samples, seed)`:** each replicate is one `rng.choices` draw over the
    sorted dialogues, as in `metrics.py`, turned into a multiplicity vector. Each statistic's
    estimate is `sum(map(mul, w, num)) / sum(map(mul, w, den))`. A replicate with a zero
    denominator is skipped for that statistic and counted.
  - **Derived statistics:** linear combinations of base statistics (contrasts), evaluated on the
    replicates where every input is defined.
  - **Interval and p:** the percentile interval from `metrics._percentile_interval`'s order
    statistics; the bootstrap p from FR10 (floored at 1/B').
  - **`unstable` flag:** more than the configured share of replicates excluded.
  - **`holm(pvalues)`:** pure function, ties handled, monotone adjusted p.
- Files likely touched: `src/analysis/bootstrap.py` (new), `tests/test_analysis_bootstrap.py`
  (new)
- Depends on: none
- Security-sensitive: no. Pure numerical code on already-validated in-memory data.
- Acceptance criteria:
  - With one statistic over all dialogues, the interval equals
    `metrics.paired_bootstrap_difference` for the same seed and B, within 1e-12 (AC-007-6).
  - A hand-built 3-dialogue example gives the expected point estimate, percentile interval and
    bootstrap p.
  - A statistic present in 1 of 3 dialogues reports its excluded replicates and is `unstable`
    above the threshold. Its derived contrasts use only replicates where all inputs are defined.
  - Holm matches hand-computed adjusted p-values for 4 values, including a tie, and p = 1
    members.
  - The same inputs and seed give identical replicate lists. The statistic order is fixed.
- Status: done (2026-10-21). 20 tests in `tests/test_analysis_bootstrap.py`; full suite 636 OK. A
  synthetic timing run (944 dialogues, 1,440 statistics) projects about 4 minutes at B = 10,000.

## T3: Inputs file, panel mapping and run-directory checks
- Description:
  - **`src/analysis/inputs.py`:** loads `configs/analysis/inputs-<split>.toml`, which maps panel
    systems to:
    - Stage 1 run directories, by train condition and seed;
    - Stage 2 routed and oracle files, by seed;
    - transfer report files.
  - **Panel rules:** a system not in the panel is an error. A panel system with no files is
    `not_run`.
  - **Stage 1 run directories:** `config.resolved.json` must give the declared train condition and
    `eval_split == --split`, and `predictions.jsonl` and `metrics.json` must exist.
  - **Design rules (FR6):**
    - a `matched` system needs train-c runs for each genuine condition c;
    - every system needs train-`full` runs for its test-time and mismatch lines.
  - **Paths and hashes:** paths are resolved, must exist, must be regular files or directories,
    and are bounded in size. Every file is SHA-256 hashed into a provenance map.
- Files likely touched: `src/analysis/inputs.py` (new), `tests/test_analysis_inputs.py` (new)
- Depends on: T1
- Security-sensitive: yes. It resolves file paths from a hand-written file, and a split mismatch
  here is how a test-gate bypass would start.
- Acceptance criteria:
  - An extra system fails. A missing panel system is `not_run` (FR5).
  - A `matched` system whose `none` run is train-`full` fails. A Stage 1 run whose `eval_split`
    differs from `--split` fails (AC-007-3).
  - A missing `predictions.jsonl`, a nonexistent path or an oversized file fails with a named
    error. Hashes are recorded for every file read.
  - The test-time line resolves to the train-`full` runs for every condition.
- Status: done (2026-10-21). 17 tests in `tests/test_analysis_inputs.py`. Shared bounded and
  hashed reads are in `src/analysis/files.py`. Each run is checked against what it recorded:
  - run name;
  - train condition;
  - `eval_split`;
  - seed;
  - smoke flag.

## T4: Stage 1 outcome table, component check and seed averaging
- Description:
  - **Scorer change:** make `stage1._check_predictions` public as `check_predictions`. The old
    name stays as an alias.
  - **`src/analysis/outcomes.py`:** builds per-example Stage 1 outcomes (`stage1_correct`,
    `request_detected`) for every (system, line, condition, seed) from validated predictions. It
    uses spec 004's genuine/mismatch sets (`scoring_sets`) and, on test, spec 006 primary
    examples.
  - **Component check:** compares accuracy and request counts against `stage1.build_report` (run
    with `bootstrap_samples=1`) and against the run's saved `metrics.json`. Integer counts are
    compared exactly, rates to 1e-12.
  - **Seed averaging and seed variation (FR9):** averaging is done within (system, line,
    condition, example), and seed variation is summarised per headline metric. A contrast whose
    conditions have different seed sets is an error (FR7).
- Files likely touched: `src/evaluation/stage1.py`, `src/analysis/outcomes.py` (new),
  `tests/test_analysis_outcomes.py` (new)
- Depends on: T3
- Security-sensitive: yes. It parses untrusted prediction and metrics files. Validation goes
  through the scorer's checks, and nothing is coerced.
- Acceptance criteria:
  - 3 fixture seeds average to values in {0, 1/3, 2/3, 1}. Seed variation lists each seed's
    estimate, mean, SD, min and max. Removing one seed under one condition of a contrast fails
    (AC-007-2).
  - Each of these fails the run with a named error (AC-007-4, Stage 1 part):
    - an injected disagreement with `build_report` (a patched outcome function);
    - a predictions file that no longer matches its `metrics.json`.
  - A missing, extra or duplicate prediction fails (FR7).
  - Existing `test_stage1.py` tests still pass with the alias.
- Status: done (2026-10-21). 16 tests in `tests/test_analysis_outcomes.py`. Predictions are stored
  as tuples aligned to the evaluation set. Scorer errors that name an example are replaced with
  ID-free messages.

## T5: Stage 2 outcomes and the four endpoints
- Description:
  - **Outcomes:** extend the outcome table with routed and oracle rows validated by
    `interpretation.validate_predictions`, and `exact` from `interpretation.outcome`. The
    population is the same as spec 005's `end_to_end` (gold requests with a mapped category), and
    the oracle population is gold `indirect` with a mapped category.
  - **Endpoints by formula (FR3):** `request_interpretation`, `type_exact`, `stage1_correct`,
    `request_detected`. An invalid row is never correct.
  - **Component check against `stage2.build_report`:** request true/false positives, oracle exact,
    routed exact, and `end_to_end` (which equals `type_exact`).
- Files likely touched: `src/analysis/outcomes.py`, `tests/test_analysis_outcomes.py`
- Depends on: T4
- Security-sensitive: yes. It parses untrusted model-output JSONL (free-text paraphrase fields),
  and only validated fields are used.
- Acceptance criteria:
  - A gold-indirect, rule-L0 fixture predicted `direct` with an exact interpretation is a success
    for `request_interpretation` and a failure for `type_exact` (AC-007-5, first case).
  - An invalid row fails every endpoint. A `no_request` prediction on a gold request fails
    `request_interpretation`.
  - `type_exact` totals equal `stage2.build_report`'s `end_to_end` successes on a fixture. An
    injected disagreement fails (AC-007-4, Stage 2 part).
  - Each oracle-population example has exactly one oracle row per condition, or validation fails.
- Status: done (2026-10-21). 10 more tests in `tests/test_analysis_outcomes.py` (26 in the file).
  Full suite 679 OK, with and without git on PATH. FR3 populations are clarified in the spec.

## T6: H2 estimands, primary contrast, and the cell rules
- Description:
  - **`src/analysis/estimands.py` (H2 part):** builds statistic vectors from the seed-averaged
    outcome table for each system, line, endpoint, condition contrast (full − none, one − none,
    full − one) and level. It derives:
    - the linear (−1, 0, +1) and quadratic (+1, −2, +1) contrasts over L0–L2;
    - each level minus L0.
  - **Cell rules:**
    - a cell is `sparse` below the minimum dialogues;
    - a `sparse` or `unstable` statistic never gets a p-value;
    - the primary contrast on a sparse or unstable cell fails the run;
    - a `not_run` primary system fails a test run and is reported as `not_run` on dev.
  - **Labels:** "main effect, no interaction" is applied when the overall benefit's interval
    excludes 0 and the linear contrast's doesn't.
  - **Dev precision report:** the primary half-width, cell sizes, and the primary interval under a
    second bootstrap seed.
- Files likely touched: `src/analysis/estimands.py` (new), `tests/test_analysis_estimands.py`
  (new)
- Depends on: T2, T5
- Security-sensitive: no
- Acceptance criteria:
  - Context-helps-only-at-L2 fixture: the linear contrast is positive and its interval excludes 0.
  - Equal-benefit fixture: the main effect is positive, the linear contrast and every
    level-minus-L0 interval include 0, and the label is applied (AC-007-5).
  - A primary cell below the minimum fails the run. A sparse L3 cell is `sparse` with no p-value
    (AC-007-8).
  - The matched line uses the train-c outcomes. The test-time line uses train-`full` for every
    condition.
  - The dev precision report contains the half-width, cell sizes and the two-seed endpoints.
- Status: done (2026-10-21). See `src/analysis/estimands.py` and `tests/test_analysis_estimands.py`.
  - The dev precision report covers every run system: the primary design on its main endpoint,
    falling back to `stage1_correct` for Stage 1-only systems. So D-07 gets dev evidence before
    the LLM or hybrid exists.
  - Only the prespecified tests (the primary and the Holm members) carry a p-value.

## T7: H1, H3, H4 and H5 estimands
- Description:
  - **H1:** per condition and level success, with the L0–L2 linear contrast.
  - **H3:**
    - tested differences on **test-time** lines against the primary system (overall);
    - descriptive primary-line differences (overall and per level), with the "design differs
      across families" caption.
  - **H4:** on the oracle population, `request_detected`, oracle `exact` and routed
    `request_interpretation` per condition and level, on identical examples. The H4 contrast is
    drop(detection) − drop(oracle) under `full`, with drop = rate_L0 − rate_L2.
  - **H5:**
    - per `cat-v1` category, success and full − none;
    - an intent-standardized H2 line over the categories present at every level, with the
      excluded categories and their share reported.
  - **Stage 1-only systems** appear in `stage1_correct` tables only.
- Files likely touched: `src/analysis/estimands.py`, `tests/test_analysis_estimands.py`
- Depends on: T6
- Security-sensitive: no
- Acceptance criteria:
  - The H4 detection, oracle and routed rates use identical example sets per condition and level.
    A fixture where detection is flat and oracle success falls gives a negative H4 contrast
    (AC-007-10).
  - The H3 tested statistics use test-time lines for every system. The primary-line versions
    appear only as descriptive, with the caption (AC-007-11).
  - A system without Stage 2 output is absent from the end-to-end, H4 and `request_interpretation`
    tables.
  - Intent standardization with one category missing at L2 excludes it and reports its share. On
    a fixture with a single category, the standardized line equals the unstandardized one.
- Status: done (2026-10-21). 7 tests.
  - H4 is formed on the oracle population, which is gold *indirect* only. Its L0 cell therefore
    holds rule-L0 indirect rewrites (about 27% of them).
  - An empty cell is reported as `empty`, never imputed.

## T8: Holm family assembly and sensitivity lines
- Description:
  - **Holm family:** members are built from the config's list, never from the inputs. A member
    whose system is `not_run`, or whose statistic is sparse or unstable, keeps its place with
    p = 1 and status `not_run` or `untestable`. The output has raw p, adjusted p and interval per
    member.
  - **Sensitivity lines (FR18),** for the headline contrasts and the primary contrast:
    - `primary_minus_dup` on test, from the spec 006 audit's `dup_ids`;
    - `without_cue_donors` on mismatch contrasts, from `scoring_sets`.

    Each is its own statistic on the shared bootstrap, never crossed with the other.
- Files likely touched: `src/analysis/estimands.py`, `tests/test_analysis_estimands.py`
- Depends on: T7
- Security-sensitive: no
- Acceptance criteria:
  - Deleting a panel system from the inputs makes its members `not_run` with p = 1. The family
    size and the other members' adjusted p are unchanged (AC-007-7).
  - Each headline contrast on a test fixture carries one `primary_minus_dup` line. Mismatch
    contrasts also carry `without_cue_donors`. No crossed line exists.
  - The primary contrast never appears in the Holm family.
- Status: done (2026-10-21). 5 tests; the estimand suite has 20.
  - A member is `not_run` when its system did not run, and `untestable` when the system ran but
    the statistic cannot form or is sparse/unstable.
  - Both keep their place with p = 1.

## T9: `analysis run` CLI, split and freeze gates, report and provenance
- Description: `python -m src.analysis run --split {dev,test} --config ... --inputs ...`.
  - **Gate order on test:** the gates run before any prediction is read:
    1. `--allow-test`;
    2. a config with `draft = false`;
    3. a current spec 006 audit (`require_test_audit`);
    4. `data/manifests/freeze.json` with `analysis_config_sha256` equal to the config hash.
  - **Stamps:** `frozen_test` or `dev_diagnostic_not_a_finding`.
  - **Full JSON report** under `outputs/analysis/<split>/`, with a provenance block:
    - input hashes and the config hash;
    - the audit content hash (test);
    - the rules, category, scorer and renderer versions;
    - `git_state(ignore=(out_dir,))`;
    - the reproduction command.
  - **Output safety:** outputs never overwrite an input.
  - **Console output:** logs counts only.
- Files likely touched: `src/analysis/__main__.py` (new), `src/analysis/report.py` (new),
  `tests/test_analysis_cli.py` (new)
- Depends on: T8
- Security-sensitive: yes. This is the freeze/test gate (the core validity control), and it
  writes outputs that may be committed.
- Acceptance criteria:
  - On test, each of these fails before any prediction file is opened (AC-007-9):
    - no `--allow-test`;
    - a draft config;
    - a missing or stale audit;
    - a missing `freeze.json`;
    - a hash mismatch.
  - A dev run needs neither audit nor freeze, stamps `dev_diagnostic_not_a_finding`, and writes
    only under `outputs/analysis/dev/`.
  - Two runs give byte-identical JSON. Captured stdout/stderr hold no fixture text or fixture test
    IDs (AC-007-13, report part).
  - An output path equal to an input path fails.
- Status: done (2026-10-21). Code: `src/analysis/__main__.py`, `report.py`, `freeze.py`. 6 tests in
  `tests/test_analysis_cli.py`.
  - The fixtures use real items, so levels come from the real `auto-v1` rules.
  - The gate tests use the real `require_test_audit`. The success path supplies a constructed
    `SplitAudit`, which spec 006's own tests cover.
  - `KeyError` is reported without its key, because a key could be an ID.

## T10: Paper tables, figure data and the transfer table
- Description:
  - **`report.py` tables:** Markdown and CSV for the primary test, H1–H5, the Holm family, seed
    variation, cell sizes, and the not-run/sparse/unstable lists. Every row has its denominator
    (examples and dialogues) and a provenance reference.
  - **Figure data CSV:** benefit by level with intervals, per system and line.
  - **Transfer table:** built from spec 005 transfer reports, validating
    `scorer_version == "transfer-v1"`. It carries the LLM-generated label and the GPT flag, and is
    written to its own file.
  - **Destinations:** test tables go to committed `results/analysis/test/`; dev tables go to
    `outputs/analysis/dev/`.
  - **CSV safety:** formula-leading cells are escaped.
- Files likely touched: `src/analysis/report.py`, `tests/test_analysis_report.py` (new)
- Depends on: T9
- Security-sensitive: yes. It writes committed files that spreadsheets open (formula injection),
  and it must never carry IDs or text.
- Acceptance criteria:
  - The primary contrast row is labeled "L2 − L0 benefit difference (linear contrast)" and shows
    the quadratic contrast beside it.
  - The transfer table is its own file with the label and the GPT flag. A main-benchmark report
    given as transfer input fails (AC-007-12).
  - Committed-table fixtures contain no fixture utterance text and no example or dialogue IDs
    (asserted). Two runs are byte-identical (AC-007-13).
  - A formula-leading value is escaped in the CSV output.
- Status: done (2026-10-21). 8 tests in `tests/test_analysis_report.py`. Tables are CSV and
  Markdown per estimand.
  - Committed tables are refused if a dialogue-ID pattern appears in them.
  - Number lists (contrast weights) are never formula-escaped.
  - The transfer report is validated (`transfer-v1`, `llm_generated_transfer`) and kept in its own
    file.

## T11: Context-by-level figure script
- Description:
  - **Script:** `src/analysis/figures.py` reads the T10 figure data CSV and renders the
    context-by-level figure (benefit ± interval per level, one panel per system or line) to SVG
    and PDF.
  - **Determinism:** fixed `svg.hashsalt`, no metadata dates.
  - **Dependency:** matplotlib in a new `figures` uv dependency group in `pyproject.toml`. Sandy
    runs `uv lock` in WSL.
- Files likely touched: `src/analysis/figures.py` (new), `pyproject.toml`,
  `tests/test_analysis_figures.py` (new)
- Depends on: T10
- Security-sensitive: no
- Acceptance criteria:
  - On a fixture CSV, two renders give byte-identical SVG.
  - The test is skipped cleanly when matplotlib is absent, so the native-Windows suite still
    passes.
  - A malformed figure CSV (missing column, non-numeric interval) fails with a named error.
- Status: done (2026-10-21). 8 tests; they render for real on native Windows, where matplotlib 3.10.9
  is installed globally.
  - `pyproject.toml` gains the `figures` group pinned to matplotlib 3.10.9. **Sandy runs `uv lock`
    in WSL.**
  - Endpoints use reference-palette categorical slots 1–3, each with its own marker shape.
  - The dataviz validator could not run (no Node on this machine). The slots are the reference
    palette's validated ones, and shape gives secondary encoding.
  - A preview render was inspected; the dodge offsets are centred per panel.

## T12: `error-audit sample`: gate, stratified draw, registration and sheet
- Description: `python -m src.analysis error-audit sample --on YYYY-MM-DD --inspector A1 --report <frozen test report> ...`.
  - **Gate:** it fails, changing nothing, unless:
    - `data/manifests/freeze.json` exists (no CLI date override);
    - `--on` is on or after the freeze date and no later than today;
    - `--inspector` matches spec 006's pattern;
    - the report is a `frozen_test` report whose config hash matches.
  - **Errors:** recomputes the primary system's primary-line `request_interpretation` outcomes
    under `full` on test (T5). Errors are examples with a seed-averaged value below 0.5.
  - **Draw:** stratified by rule level L0–L3 with the config quota (default 15). It is a seeded
    uniform draw over sorted IDs. A short stratum is taken whole and the shortfall reported, with
    no backfill. For multi-seed systems, the shown output comes from the lowest wrong seed.
  - **Registration:** rows are built (`manual`/`error_audit`/`post_scoring`) and validated with
    spec 006's registry validator. If needed, a `register_rows` function is factored out of
    `split_audit` for this.
  - **Atomic write:** write the sheet (rendered input, prediction, gold acts, blank `code` and
    `gold_questionable`) to a temporary file under `data/interim/error_audit/`, append the
    registry rows, then rename. On failure, delete the temporary file and leave the registry
    untouched.
- Files likely touched: `src/analysis/error_audit.py` (new), `src/data/split_audit.py`,
  `tests/test_analysis_error_audit.py` (new)
- Depends on: T9
- Security-sensitive: yes. It writes the committed registry (a freeze input), handles test text,
  and is the control that keeps post-scoring inspection from moving the frozen set.
- Acceptance criteria (AC-007-14):
  - Each of these fails and registers nothing:
    - no `freeze.json`;
    - `--on` before the freeze date or after today;
    - a bad inspector;
    - a missing report, a non-`frozen_test` report, or a report with a config-hash mismatch.
  - The same seed gives the same 15-per-level sample. A short stratum is taken whole with the
    shortfall reported.
  - Every sampled dialogue gets a `post_scoring` row. The spec 006 audit content hash and every
    `primary` flag are unchanged.
  - An injected sheet-write failure leaves the registry byte-identical and no sheet behind.
  - Console output holds counts only, with no IDs or text.
- Status: done (2026-10-21). See `src/analysis/error_audit.py` and the `error-audit sample` command;
  tests are in `tests/test_analysis_error_audit.py`.
  - **No `register_rows` refactor was needed.** Spec 006's `merge_rows`, `validate_registry` and
    `write_registry` already form the validated append path.
  - **All-or-nothing.** Any failure after the registry write restores the registry's original bytes.
  - **Inspector.** It must be `A<n>`: `claude` is refused, because Claude never inspects test output.
  - **No re-sampling.** A second draw is refused while a sheet exists.

## T13: `error-audit export` and `report`, and the post-scoring scan location
- Description:
  - **`export`:** validates the filled sheet:
    - every row coded;
    - codes from the 7-code enum (`over_inference` is not allowed);
    - `gold_questionable` empty or `yes`;
    - the row set equal to the sample;
    - locked columns unchanged (checked against hashes recorded at sampling);
    - bounded fields and no formula-leading cells.

    It writes the committed, text-free `results/error_audit/codes.csv` (example ID, level, code,
    flag).
  - **`report`:** writes counts by level × code, with the sample design, quotas and shortfalls.
  - **Spec 006 change:** add `results/error_audit` to `POST_SCORING_SCAN_DIRS` in
    `src/data/split_audit.py`.
- Files likely touched: `src/analysis/error_audit.py`, `src/data/split_audit.py`,
  `tests/test_analysis_error_audit.py`, `tests/test_split_audit.py`
- Depends on: T12
- Security-sensitive: yes. It parses a hand-edited spreadsheet and writes a committed file
  containing test example IDs.
- Acceptance criteria (AC-007-15):
  - Each of these is rejected with a named error:
    - an uncoded row;
    - an unknown code, including `over_inference`;
    - an added or removed row;
    - an edited locked column;
    - a formula-leading cell.
  - A valid sheet yields a codes file with no text columns. `split_audit scan` passes with the
    file present and its dialogues registered `post_scoring`.
  - `report` counts by level × code on a fixture.
- Status: done (2026-10-21). `error-audit export` and `report` are added, and
  `POST_SCORING_SCAN_DIRS` gains `results/error_audit`.
  - Tests cover each rejection: uncoded row, unknown code (including `over_inference`), an added,
    removed or duplicated row, an edited locked column, a formula cell, a bad flag.
  - `split_audit scan` passes with the codes file present and fails without its `post_scoring`
    rows.

## T14: Dev smoke run, docs and close-out evidence
- Description:
  - **Dev smoke run:** on Sandy's dev predictions (TF-IDF from the clean WSL worktree, plus at
    least one encoder grid), write `configs/analysis/inputs-dev.toml` and run
    `analysis run --split dev`. Record:
    - the runtime against the 15-minute bound;
    - the component-check result;
    - the two-seed Monte Carlo agreement (±0.002 on the primary endpoints; otherwise raise B);
    - the dev precision report.
  - **Where the results go:**
    - the D-07 entry in `specs/memory/decisions.md` (the numbers);
    - `verification.md` (masked, dev only).
  - **Docs:**
    - `docs/analysis_plan.md`: the D-07 decisions and endpoint, with the GLMM text marked replaced;
    - `docs/stage1_baselines.md`/`docs/stage2_scoring.md`: pointers to the analysis;
    - the roadmap.
  - **Test suites:** the full native-Windows suite; WSL if Sandy runs it.
- Files likely touched: `configs/analysis/inputs-dev.toml` (new),
  `specs/007-analysis-error-audit/verification.md` (new), `docs/analysis_plan.md`,
  `docs/stage1_baselines.md`, `docs/stage2_scoring.md`, `specs/memory/decisions.md`,
  `specs/001-pragmatic-intent-study/roadmap.md`
- Depends on: T10 (T11–T13 are needed for AC-007-17's suite and docs, but not for the smoke run)
- Security-sensitive: no (dev data only; no test outputs are read)
- Acceptance criteria:
  - The dev run completes within the bound, the component check passes, and the Monte Carlo check
    passes or B is raised (AC-007-16).
  - The dev precision report is recorded with D-07. `analysis-v1.toml` is complete apart from
    the freeze-time primary system and `draft` flag.
  - The full suite passes on native Windows Python 3.12. `docs/analysis_plan.md` and spec 001's
    v1.3 note agree (AC-007-17).
- Status: blocked: needs Sandy's dev predictions. They are in WSL, not in this checkout.
  - **Done 2026-10-21:**
    - docs (`analysis_plan.md`, `stage1_baselines.md`, `stage2_scoring.md`, roadmap);
    - `verification.md`;
    - full suite, 731 OK;
    - runtime on the real dev set with a synthetic 47-run grid: 314 s at B = 10,000, two-seed
      agreement ≤ 0.0008.
  - **Remaining:** Sandy writes `inputs-dev.toml`, runs `analysis run --split dev` in WSL, and
    records the precision report with D-07.
