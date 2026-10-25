# Spec 007: Analysis and error audit

> **Phase:** Reviewed · **Status:** Revised 2026-10-20 after [review](review.md) (R1–R11 applied; R6 = option a) · **Owner:** Sandy (decisions, runs, error-audit labels), Claude (tooling) · **Date:** 2026-10-20
> The *what* and *why*. Implementation detail belongs in `plan.md`.

Parent: [spec 001](../001-pragmatic-intent-study/spec.md) WP-10, FR-10, FR-12 (tables and figures),
FR-15 (transfer table), §13, AC-09, AC-10, AC-12; D-07 (statistics). This spec was renumbered from 006 on 2026-10-19.

**Amends spec 001** (recorded as the v1.3 note there, 2026-10-20):
- **§13 / D-07:** the dependence model is a dialogue-cluster bootstrap difference-in-differences,
  not a GLMM.
- **FR-10:** a dev precision report replaces the pilot power simulation. H2 is confirmatory for
  the L0–L2 trend only, and L3/INF stay exploratory.
- **§5:** the primary endpoint is computed as defined there (request detection AND interpretation;
  FR3), not by spec 005's type-exact `end_to_end`.

Written under the v1.2 direction (option A): levels are `auto-v1` rule levels, intents are `cat-v1`,
and the test set is the spec 006 primary set of DIRECT's official test split.
Roadmap: the tooling is built and run on dev Oct 20–25. D-07 and the analysis config are frozen with
WP-08 (Oct 26–Nov 1). The test analysis runs Nov 14–19.

## Problem

Specs 004–006 score **one run at a time**. Each `metrics.json` holds one seed of one model, with
its own dialogue bootstrap per contrast. The paper needs more than that, and nothing builds it:

- **Seed aggregation.** The 5090 grid gives 5 seeds per training condition. Spec 001 §13 says
  to average seeds within model, item and condition before resampling, and to report seed
  variation separately. Today seeds are only separate result lines.
- **An H2 interaction estimate.** `by_rule_level` contrasts give each level's full − none benefit
  from its own bootstrap. No interval exists for the *difference* between levels, which is the
  thing H2 is about. Contrasts from separate bootstraps can't be subtracted with an honest
  interval, because the levels share dialogues. AC-09 forbids presenting a main effect as an
  interaction.
- **Comparisons across runs.** Matched training means comparing different runs (trained on
  `full` vs trained on `none`; Sandy, 2026-10-20). H3 compares model families on identical items.
  H4 compares detection with interpretation on identical gold items. None of this fits inside a
  single run's report.
- **The endpoint.** Spec 005's `end_to_end` requires the three-way type (direct vs indirect) to
  match DIRECT's variant label. Spec 001 §5 defines the primary endpoint as request *detection* AND
  interpretation. Under option A the two diverge by level: about 27% of DIRECT "indirect"
  rewrites are rule-L0, and reading them as direct counts as a failure.
- **Multiplicity and freeze.** D-07 is open. Nothing fixes, before test, which contrast is the
  primary test, which systems and comparisons form the Holm family, or the bootstrap settings.
  Nothing checks that the analysis run on test used the frozen plan.
- **The error audit.** It is post-scoring human inspection of test (spec 001 §13). Spec 006 can
  record it as `post_scoring`, but no tool draws the sample. An unrecorded, hand-picked or
  pre-freeze sample would break selection independence.

## Goals

- One deterministic analysis command turns a set of scored prediction files into the paper's
  numbers: seed-averaged metrics, paired context contrasts, the H2 interaction, and the
  H1/H3/H4/H5 comparisons. Every number has its denominator and an interval from **one shared
  dialogue bootstrap**.
- D-07 is pinned as a **versioned, hashed analysis config** that also fixes the model panel. It
  is validated on dev and frozen with WP-08. A test analysis refuses to run without that frozen
  hash.
- Every outcome is computed from the existing scorers' validation and outcome functions, and
  checked against them, so the analysis cannot silently disagree with specs 004–006.
- A seeded, stratified error-audit sampler, a sheet and a validated export. It runs only after
  the frozen test analysis, and the sample is registered `post_scoring` before any text is shown,
  so the frozen set never moves.
- Paper-ready, text-free tables (and figure data) traceable to inputs, hashes and the reproduction
  command (AC-12).

## Non-Goals

- Running, training or prompting any model, and choosing the model panel (D-05) or prompts. Sandy
  owns model code and runs. The config *records* the chosen panel at the freeze.
- A mixed-effects model, in any role (Sandy, 2026-10-20: bootstrap difference-in-differences only).
- Changing the per-run scorers' semantics (`src/evaluation/stage1.py`, `stage2.py`, `transfer.py`),
  the renderer, the manifests or the split audit's membership rules. The only additive touches
  are making `stage1.check_predictions` public and adding one post-scoring scan directory to
  spec 006 (FR25).
- The WP-08 freeze record itself (`data/manifests/freeze.json`). This spec defines the field it
  needs (`analysis_config_sha256`) and checks it. Writing the record is WP-08 (proposed spec 008).
- LLM-judge calibration and free-paraphrase adequacy scoring. These are a separate spec, if kept.
  FR17 of spec 006 (the judge sample comes from dev) is unchanged.
- The literary add-on's analysis (not collected), and pooling IndirectRequests with the main
  benchmark (never).
- Power simulation beyond the dev precision report (FR15).
- Writing the paper.

## User Stories

- As **Sandy writing the results section**, I want one command that turns the frozen test
  predictions into the H1–H5 tables, with intervals and denominators, so I copy numbers instead of
  assembling them by hand from 40 `metrics.json` files.
- As **the course professor**, I want the H2 claim to rest on one prespecified interaction test,
  with seeds averaged, dialogues as the resampling unit and a panel fixed before test, so it isn't
  seed-inflated or chosen after seeing test.
- As **the freeze step (WP-08)**, I want one hash that fixes the whole analysis plan, including
  the model panel, so a change after test scoring is detectable.
- As **Sandy doing the error audit**, I want a random, stratified sample that is registered before
  I read it, so inspecting test outputs cannot be cherry-picked and cannot move the frozen set.

## Functional Requirements

**Analysis config (D-07)**

1. The analysis plan MUST be one versioned TOML file (`configs/analysis/analysis-v1.toml`). It
   fixes:
   - the rules version;
   - the **panel**: each system's name, family (`majority`, `tfidf`, `encoder`, `llm` or
     `hybrid`), context design (`matched` or `test_time`) and required streams (`stage1`,
     `routed`, `oracle`, `transfer`);
   - the primary system, endpoint, contrast and levels;
   - the exploratory levels;
   - the secondary (Holm) family;
   - bootstrap samples, seed and confidence;
   - alpha;
   - the minimum-cell and replicate-stability rules;
   - the error-audit design;
   - a `draft` flag, true until the freeze names the primary system.

   Its canonical SHA-256 is computed over the parsed, normalized content, so comments and
   whitespace don't move it, and it is recorded in every output.
2. The config MUST be validated at load. Each of these is a named error:
   - an unknown key;
   - an unknown endpoint, contrast or level name;
   - a primary system or family member naming a system outside the panel;
   - a primary system without the streams its endpoint needs;
   - an empty or duplicate family member;
   - the primary test listed in the secondary family;
   - a non-positive bootstrap count.
3. **Endpoints.** Each endpoint is defined by its formula over validated rows, using
   `interpretation.outcome(...).exact`. An invalid row is never correct.
   - `request_interpretation` (**primary**, spec 001 §5): the routed prediction is not
     `no_request` AND `exact`.
   - `type_exact`: spec 005's `end_to_end` (prediction equals the variant label AND `exact`).
     This is a named secondary line.
   - `stage1_correct`: the three-way Stage 1 prediction equals the label. This is the
     detection-only endpoint, available for every system.
   - `request_detected`: the prediction is not `no_request`. It is used for H4.

   Population (clarified 2026-10-21, T5):
   - `type_exact` is scored on exactly spec 005's `end_to_end` population. That is every example
     whose gold category is mapped, non-requests included, so its totals equal the scorer's.
   - `request_interpretation` is scored on the gold *requests* in that population. Counting
     non-requests would score a request predicted on a non-request with empty slots as a
     success.
   - `request_detected` is scored on gold requests, `stage1_correct` on all scored examples, and
     the oracle's `exact` on the oracle population.
4. The default content MUST encode Sandy's 2026-10-20 decisions:
   - **Primary test (confirmatory):** the linear contrast of the full − none benefit across
     `L0`, `L1`, `L2`, with weights (−1, 0, +1). That is the L2 − L0 benefit difference, and L1
     carries no weight; tables label it so. It uses one named primary system and
     `request_interpretation`. It is two-sided at alpha 0.05, decided by whether the 95%
     percentile interval excludes 0. The quadratic contrast (+1, −2, +1) is reported
     descriptively.
   - **Exploratory:** `L3` (rule precision 12/40 under `auto-v1`; the `auto-v2` check is pending)
     and `INF`. They appear in the same tables, labeled exploratory, and never enter a test.
   - **Secondary family (Holm-corrected):**
     - the H1 trend of the primary system;
     - the detection-only (`stage1_correct`) H2 trend of the primary system;
     - the H4 contrast;
     - the full − mismatched corruption control;
     - for each other panel system, the H3 difference against the primary system on
       **test-time** lines (FR12).
   - **H5, the primary-line H3 differences and all other slices** are exploratory and
     uncorrected.

**Inputs**

5. An inputs file MUST map **only the configured panel's systems** to their prediction files by
   evaluation condition, train condition and seed. Trained systems use Stage 1 run directories;
   systems with Stage 2 output give routed and oracle files. A system not in the panel is an
   error. A panel system with no files is `not_run`. Every file is SHA-256 hashed into the
   output. For Stage 1 runs, `config.resolved.json` MUST give the declared train condition and an
   `eval_split` equal to `--split`.
6. The context design MUST follow Sandy's 2026-10-20 decision:
   - **Trained systems:** the genuine conditions (`none`, `one`, `full`) are *matched*. The
     condition-c outcome comes from the model trained on c. This is the **primary line**.
   - **Test-time line:** the full-trained model scored under every condition. It exists for
     every system, and it is the only line for untrained systems (LLM).
   - **Mismatch controls:** these always use the full-trained model at test time.

   A `matched` system whose condition-c file comes from a different train condition is a named
   error.
7. Every system MUST cover the same evaluation example set per condition (spec 004 genuine or
   mismatch set; on test, spec 006 primary examples). Within a system, the conditions of any one
   contrast MUST have the same seed set. Systems may differ in seed count. A missing, extra or
   duplicate prediction, or a seed present under one condition and not the other, is an error,
   never silently dropped.

**Outcomes**

8. Per-example outcomes MUST be computed with the existing scorers' functions:
   - Stage 1: `stage1.check_predictions` (made public; the old private name stays as an alias)
     and its label comparison.
   - Stage 2: `interpretation.validate_predictions` / `outcome`.

   For every system, seed and condition, the analysis MUST check its component counts against
   the scorer's `build_report` on the same inputs (run with `bootstrap_samples=1`) and fail on any
   difference. The components are: Stage 1 accuracy; request true/false positives; oracle exact
   successes; routed exact interpretations; `end_to_end` successes (which equal `type_exact`).
   Where the run's saved `metrics.json` is present, its accuracy and success values MUST also
   match. That catches a predictions file swapped after scoring.
9. Seeds MUST be averaged within (system, line, condition, example) before any resampling, giving
   a value in [0, 1]. Seed variation MUST be reported separately for each headline metric and the
   primary contrast: the per-seed estimates, their mean, SD, min and max. Seeds never count as
   extra independent items.

**Estimation**

10. All intervals and p-values of one analysis run MUST come from **one shared dialogue
    bootstrap**, defined as follows:
    - **One draw per replicate.** Each replicate draws, with replacement, as many dialogues as the
      evaluated set holds, from all of its dialogues (sorted by dialogue ID, `random.Random(seed)`,
      as in `metrics.py`). Every statistic is evaluated on that same draw.
    - **Estimator.** Each statistic is example-weighted: Σ_d w_d·num_d / Σ_d w_d·den_d, where w_d is
      the dialogue's multiplicity in the draw.
    - **Zero-denominator replicates.** A replicate that draws no dialogue containing a statistic's
      examples is excluded *for that statistic only*, and the count is reported. A statistic with
      more than 1% excluded replicates is `unstable`. It gets an interval but never a test.
    - **Interval.** The 95% percentile interval, using the order statistics of
      `metrics._percentile_interval`.
    - **p-value.** The two-sided bootstrap p is `min(1, 2 · min(#(d* ≤ 0), #(d* ≥ 0)) / B')`,
      floored at `1/B'`, where B' is the count of non-excluded replicates.
    - **Which rule decides.** The interval rule decides the primary test; p is used only for Holm.
    - **Expected difference from per-run reports.** Slice intervals differ from the per-run
      `by_rule_level` intervals (which resample only the slice's dialogues). The tables state
      this.
11. **H2:** for each system, line and endpoint, and each level, report the full − none, one − none
    and full − one benefits, the primary linear contrast, the quadratic contrast, and each level's
    benefit minus the `L0` benefit. A main effect without an interaction MUST be labeled as such
    (AC-09). The primary test's result is reported once, exactly as prespecified.
12. **H3:**
    - **Tested:** for every panel system, the difference between its **test-time** full − none
      benefit and the primary system's, overall. This is the design every family shares (Sandy,
      2026-10-20, review R6a). The pairs with the primary system form the Holm members.
    - **Descriptive:** the same difference on primary lines (matched for trained systems),
      overall and per level, captioned "design differs across families".
13. **H1:** per system, condition and level, report the success rate, with the L0–L2 linear
    contrast.
14. **H4:** on the spec 005 oracle population (gold `indirect` variants with a mapped category),
    for systems with Stage 2 output, report per condition and level: `request_detected`, oracle
    `exact` and routed `request_interpretation`, all on identical examples. Define drop(x) =
    rate_L0(x) − rate_L2(x). The H4 contrast is drop(detection) − drop(oracle) under `full`. H4
    predicts it is negative.
15. **H5 (exploratory):** per `cat-v1` category, report success and the full − none benefit. The
    sensitivity is an intent-standardized H2 line: each level's benefit reweighted to the pooled
    category mix, using only categories present at every level considered. The excluded
    categories and their share are reported.
16. **Cell rule and dev precision report:**
    - A level × condition cell with fewer than the config's minimum dialogues (default 30) is
      `sparse`. Sparse and `unstable` statistics never get a p-value. If the primary test touches
      one, the run fails.
    - On dev, the run MUST also report the primary contrast's interval half-width, every cell's
      size, and the Monte Carlo check: the primary interval endpoints under two bootstrap seeds.
      These are recorded with D-07 as the precision evidence that replaces a pilot power
      simulation.
17. **Holm:** the secondary family's p-values MUST be Holm-adjusted together. Each member is
    reported with its raw p, its adjusted p and its interval. A member that cannot be computed
    (its system is `not_run`, or the statistic is `sparse`/`unstable`) keeps its place in the
    family with p = 1 and is shown as `not_run` or `untestable`. The family size is fixed by the
    config, never by the inputs.
18. **Sensitivity lines** from specs 004/006 MUST carry through for the headline contrasts
    (overall full − none, one − none, full − one, the mismatch controls) and the primary
    contrast:
    - `primary_minus_dup`, on test;
    - `without_cue_donors`, for mismatch contrasts.

    Each line is applied alone and never crossed with the other.
19. **Transfer table:** spec 005 transfer reports (one per panel system with a `transfer` stream)
    MUST be gathered into a separate table, labeled LLM-generated, with GPT-family systems
    flagged. It is never pooled with, or placed in the same table as, the main benchmark. A report
    without `scorer_version: transfer-v1` is rejected.

**Split and freeze gates**

20. A dev run MUST stamp every output `dev_diagnostic_not_a_finding`.
21. A test run MUST require all of the following, and then stamp its outputs `frozen_test`:
    - `--allow-test`;
    - a config with `draft = false`;
    - a current spec 006 audit (as the scorers do);
    - `data/manifests/freeze.json`, with `analysis_config_sha256` equal to the config's hash.

    A missing or different hash fails before any outcome is read.

**Outputs**

22. Each run writes two groups of outputs:
    - **The full JSON report**, git-ignored, under `outputs/analysis/<split>/`.
    - **Tables and figure data.** These cover H1–H5, the primary test, the Holm family, seed
      variation, transfer and cell sizes, as Markdown and CSV, plus figure data (benefit by level
      with intervals, per system and line). A dev run writes them git-ignored under
      `outputs/analysis/dev/`. A test run writes them to committed `results/analysis/test/`.

    A figure script renders the context-by-level figure from the figure data. All outputs are
    aggregates with no IDs and no text. Every table row names its denominator (examples and
    dialogues) and points to the report's provenance block. That block holds:
    - the input hashes and the config hash;
    - on test, the audit content hash;
    - the rules, category, scorer and renderer versions;
    - the git commit and dirty flag;
    - the reproduction command.

**Error audit**

23. `error-audit sample` MUST require the following, and fail without changing anything if any is
    missing:
    - `data/manifests/freeze.json`. The freeze date is read only from it, with no CLI override.
    - `--on` (YYYY-MM-DD) on or after the freeze date and no later than today.
    - `--inspector`, validated by spec 006's pseudonymous-ID pattern.
    - The frozen test analysis report. Its hash and config hash are checked and recorded in the
      sample summary.
24. The sample MUST be drawn for the primary system on its primary line under `full` on test.
    It contains `request_interpretation` errors only, where an error has a seed-averaged value
    below 0.5. It is stratified by rule level `L0`–`L3`, with the per-level count from the config
    (default 15, 60 total).
    - **Draw.** A seeded uniform draw within each stratum, over example IDs sorted first. The
      draw never looks at predictions beyond the error flag.
    - **Short stratum.** A stratum with fewer errors than its quota is taken whole and the
      shortfall is reported. It is never backfilled from another stratum.
    - **Sheet output for multi-seed systems.** The sheet shows the lowest seed among those whose
      output is wrong.
25. **Registration and sheet.**
    - Before writing any sheet, `sample` MUST register every sampled dialogue in the spec 006
      registry as `manual`/`error_audit`, phase `post_scoring`, with the given inspector and
      date.
    - Registration and sheet writing are all-or-nothing.
    - The sheet goes to git-ignored `data/interim/error_audit/`, spec 006's post-scoring scan
      location. It holds the rendered input, the prediction, the gold acts, and blank columns for
      one error code and an optional `gold_questionable` flag.
    - The error codes are a closed enum from spec 001 §13: `literal_reading`,
      `wrong_intent_or_slot`, `missed_cue`, `unsupported_addition`, `source_mismatch`,
      `malformed_response`, `routing_failure`.
    - Over-inference is not audited: it is reported quantitatively as the non-request
      false-positive rate, because the error population holds no non-requests.
    - `gold_questionable` is recorded but never removes an error (spec 001 §13).
26. `error-audit export` MUST validate the filled sheet: every row coded, codes from the enum, the
    row set equal to the sample, no edits to locked columns, and no formula-leading cells. It
    writes the committed, text-free codes file `results/error_audit/codes.csv` (example ID,
    level, code, flag). `results/error_audit/` MUST be added to spec 006's
    `POST_SCORING_SCAN_DIRS`, so that `split_audit scan` requires only `post_scoring` rows there.
    `error-audit report` writes counts by level × code, with the sample design and shortfalls.

## Non-Functional Requirements

- **Security / data handling:**
  - Committed outputs hold aggregates, hashes and versions, and (the codes file only) example
    IDs with codes. They hold no utterance text and no free text.
  - The error-audit sheet with text lives only under git-ignored `data/interim/error_audit/`.
  - No command prints a test ID or text to the terminal. Logs carry counts, file names and rule
    names.
  - Config, inputs, prediction files, reports and the filled sheet are untrusted:
    - paths are resolved and must not overwrite an input;
    - IDs and enums are validated;
    - CSV field sizes are bounded;
    - formula-leading cells are rejected on read and escaped on write.
  - The freeze-date source for the error audit is the committed record only (FR23).
  - Corpus text is data, never instructions.
- **Determinism:** the same inputs, config and seed give byte-identical reports and tables
  (sorted keys, LF, no clock fields). The error-audit registration date comes from `--on`. The
  bootstrap uses `random.Random(seed)` in a fixed statistic order.
- **Performance:** a test run with B = 10,000, about 8 systems, 5 conditions and 6 levels finishes
  in under 15 minutes on a laptop CPU, using the standard library only. The bootstrap works on
  dense per-dialogue vectors, and only statistics that appear with an interval in some output are
  bootstrapped.
- **Compatibility:** Python 3.12, stdlib for everything except the figure script. The figure
  script uses matplotlib from a new pinned uv group (`figures`) and writes deterministic SVG/PDF.
  The code runs on native Windows and WSL. No per-run scorer output changes.
- **Observability:** each run logs per-system counts, seed sets, `not_run` systems, cell sizes,
  `sparse`/`unstable` statistics and the result of the component check.
- **Testability:** unit tests use invented fixtures (`PMUL9xxx`-style IDs, tiny text). The
  bootstrap engine is checked against hand-computed values and against
  `metrics.paired_bootstrap_difference`.

## Acceptance Criteria

- [ ] AC-007-1: The config loader rejects each of the following with a named error:
  - an unknown key or level;
  - a family member or primary system outside the panel;
  - a primary system without the streams its endpoint needs;
  - a duplicate family member;
  - the primary test inside the family.

  Reformatting the TOML leaves the hash unchanged; changing one value changes it.
- [ ] AC-007-2: A fixture with 3 seeds averages to per-example values in {0, 1/3, 2/3, 1}. Seed
  variation reports each seed's estimate. Removing one seed's file under one condition of a
  contrast fails with a named error.
- [ ] AC-007-3: Design checks:
  - a `matched` fixture system whose `none` file comes from a `full`-trained run fails;
  - a Stage 1 run whose `eval_split` differs from `--split` fails;
  - the test-time line uses the train-`full` run for every condition.
- [ ] AC-007-4: For every fixture system, seed and condition, the component counts equal the
  scorer's `build_report` values and the saved `metrics.json` values. Each of these fails the run:
  - an injected disagreement (a corrupted outcome function);
  - a predictions file that differs from the one its `metrics.json` was scored from.
- [ ] AC-007-5: Endpoint fixtures:
  - A gold-indirect, rule-L0 example predicted `direct` with an exact interpretation is a success
    under `request_interpretation` and a failure under `type_exact`.
  - In a fixture where context helps only at `L2`, the primary contrast is positive with an
    interval excluding 0.
  - In one where context helps equally at every level, the main effect is positive, the contrast
    and every level-minus-L0 interval include 0, and the report says "main effect, no
    interaction" (AC-09).
- [ ] AC-007-6: Bootstrap engine checks:
  - With one level and one contrast over all dialogues, the shared bootstrap's interval equals
    `metrics.paired_bootstrap_difference` with the same seed and B (difference ≤ 1e-12).
  - A hand-built 3-dialogue example gives the expected percentile interval and bootstrap p.
  - A slice present in one dialogue out of 3 reports its excluded replicates and is `unstable`
    above 1%.
- [ ] AC-007-7: Holm adjustment matches hand-computed values for 4 p-values, including ties.
  Deleting a panel system from the inputs makes its members `not_run` with p = 1, and leaves the
  family size and the other members' adjusted p-values unchanged. A system missing from the panel
  but present in the inputs fails.
- [ ] AC-007-8: A primary-test cell below the minimum dialogues fails the run. A sparse
  exploratory cell is `sparse` and has no p-value.
- [ ] AC-007-9: On test, the run fails without `--allow-test`, without a current audit, without
  `freeze.json`, or when `analysis_config_sha256` differs. With all of them present:
  - it stamps `frozen_test`;
  - it writes tables to `results/analysis/test/`;
  - each headline contrast carries `primary_minus_dup`.

  On dev it stamps `dev_diagnostic_not_a_finding`, writes only under `outputs/analysis/dev/`, and
  needs neither audit nor freeze.
- [ ] AC-007-10: H4 uses identical examples for detection, oracle and routed success under each
  condition and level, and the sign follows FR14. A system without Stage 2 output appears in
  detection (`stage1_correct`) tables only.
- [ ] AC-007-11: The H3 Holm members use test-time lines for every system. The primary-line
  comparison appears only as descriptive, with the design caption.
- [ ] AC-007-12: Transfer reports produce a separate table with the LLM-generated label and the
  GPT flag. A main-benchmark report given as transfer input fails.
- [ ] AC-007-13: Running the analysis twice gives byte-identical outputs. Committed tables and
  logs contain no fixture utterance text and no fixture test IDs (asserted).
- [ ] AC-007-14: `error-audit sample` fails and registers nothing in each of these cases:
  - without `freeze.json` (a `--freeze-date` style override is not accepted);
  - with `--on` before the freeze date or after today;
  - with a bad inspector;
  - without the frozen test analysis report, or with a report whose config hash differs.

  With valid inputs:
  - it draws 15 per level, deterministically for a seed;
  - it takes a short stratum whole and reports the shortfall;
  - it registers every sampled dialogue `post_scoring`, leaving the audit content hash and
    `primary` unchanged;
  - it registers nothing if writing the sheet fails.
- [ ] AC-007-15: `error-audit export` rejects an uncoded row, an unknown code (including
  `over_inference`), an added or removed row, an edited locked column and a formula-leading cell.
  A valid sheet yields a text-free `results/error_audit/codes.csv`, `split_audit scan` still
  passes, and `report` counts the codes by level × code.
- [ ] AC-007-16: Smoke check (reported separately), on Sandy's dev predictions (TF-IDF plus at
  least one encoder grid):
  - the run completes within the performance bound;
  - the component check passes;
  - the two-seed Monte Carlo check agrees to ±0.002 on the primary interval endpoints (or B is
    raised before the freeze);
  - the dev precision report is recorded with D-07 in `specs/memory/decisions.md`;
  - `analysis-v1.toml` is ready to freeze.
- [ ] AC-007-17: The full suite passes on native Windows Python 3.12. Two documents are updated:
  - `docs/analysis_plan.md`, to the D-07 decisions: bootstrap DiD, the `request_interpretation`
    endpoint, the confirmatory L0–L2 contrast, exploratory L3/INF, matched training, test-time
    H3, the Holm family and the error-audit design, with the GLMM text marked as replaced;
  - spec 001, with its v1.3 note.

## Open Questions

- **Primary system.** It is named in `analysis-v1.toml` at the freeze, chosen on dev evidence
  only. It needs `routed` and `oracle` streams (LLM or hybrid; D-05). *Fallback, to decide before
  the freeze:* if no such system is ready, does the confirmatory test move to `stage1_correct`
  for a named encoder (an endpoint change recorded before test), or does H2 become
  estimation-only?
- **Rules version at the freeze.** `auto-v1` is the default. If the `auto-v2` L3 check lands
  before the freeze, does the config switch to `auto-v2`? L3 stays exploratory either way.
- **Freeze record writer.** This is the proposed spec 008 (WP-08), on the critical path for the
  Nov 9 grid. It writes `freeze.json` with `freeze_date` and `analysis_config_sha256` and pins the
  audit, manifest, recipe and prompt hashes.
- **Bootstrap B on test.** The default is 10,000, kept unless the dev Monte Carlo check (FR16)
  fails.

Resolved with Sandy on 2026-10-20:

- **D-07 method:** dialogue-grouped bootstrap difference-in-differences on seed-averaged outcomes.
  No mixed model, in any role. Rejected: a GLMM sensitivity line; GLMM primary.
- **H2 status:** one confirmatory test, the L0–L2 linear contrast, for one prespecified system.
  L3 is exploratory with its precision caveat. Holm on the secondary family. Rejected: L3
  entering on a precision threshold; estimation-only H2.
- **Context contrast for trained models:** matched training is primary. Test-time ablation is a
  secondary line, and mismatch controls stay test-time. Rejected: test-time primary; both without
  a primary.
- **H3 design (review R6, option a):** the Holm-tested H3 differences use test-time lines for every
  system. The primary-line comparison is descriptive, with a design caption. Rejected: (b) primary
  lines with a caveat, which confounds design with family; (c) same-design pairs only.
- **Error audit:** 60 errors (15 per level L0–L3), about 1 hour of Sandy's labeling. Over-inference
  is reported by the false-positive rate, not audited (review R8).
- **Primary endpoint (review R1):** `request_interpretation`, following spec 001 §5. Spec 005's
  `type_exact` is secondary.

## References

- Constitution: [`specs/constitution.md`](../constitution.md): freeze before reporting;
  selection independent of model behavior; honest limits; text-free committed files; stdlib only;
  deterministic outputs.
- Parent: [spec 001](../001-pragmatic-intent-study/spec.md) §5 (H1–H5), §13, FR-10, FR-12, FR-15,
  AC-09/10/12/15, D-07; [roadmap](../001-pragmatic-intent-study/roadmap.md) WP-10;
  [analysis plan](../../docs/analysis_plan.md).
- Inputs come from: [spec 004](../004-context-conditions/spec.md) (genuine/mismatch sets, cue
  donors); [spec 005](../005-scoring/spec.md) (Stage 2 routed/oracle, transfer);
  [spec 006](../006-split-audit/spec.md) (primary set, `dup_exact`, registry phases, FR14 freeze
  date, FR17); `docs/stage1_baselines.md` (grid: 4 training conditions × 5 seeds).
- Code checked in review: `src/evaluation/stage2.py` (lines 114–116, type-exact `end_to_end`),
  `src/evaluation/metrics.py` (bootstrap), `src/data/split_audit.py` (lines 101–104, freeze file
  and scan directories).
- Measured (committed `split_audit_test_summary.json`, aggregate counts): primary genuine test
  examples by `auto-v1` level are L0 3,895, L1 1,782, L2 2,162, L3 324, INF 182, NR 2,240. Rule L3
  precision was 12/40 on dev (2026-10-17).
