# Plan 007: Analysis and error audit

_Draft 2026-10-20 for [spec 007](spec.md); revised the same day after [review](review.md). It
describes how; the spec governs what._

## Approach

The analysis is a new stdlib package, `src/analysis/`, that sits **downstream of the per-run
scorers and reimplements none of their validation or outcome logic**. It works in four steps:

1. Load the frozen plan (the analysis config, which also fixes the model panel) and an inputs file
   that maps those panel systems to prediction files.
2. Rebuild a long **outcome table**, one row per (system, line, condition, seed, example), by
   calling the existing scorer validators and `interpretation.outcome`. From those components,
   derive the four endpoints (`request_interpretation`, `type_exact`, `stage1_correct`,
   `request_detected`). Check the component counts against each scorer's `build_report` and the
   run's saved `metrics.json`, then average seeds.
3. Compress the table to **dense per-dialogue numerator/denominator vectors** for every statistic
   an output needs. Run one bootstrap whose replicates are dialogue multiplicity vectors, so every
   statistic is a ratio of weighted sums on the same replicates.
4. Derive estimands (H1–H5, the primary contrast, the Holm family) from those replicate vectors and
   write the report, tables and figure data.

Steps 2 and 3 carry the method:

- **Reusing the scorers' functions** means "valid row" and "exact interpretation" mean exactly what
  specs 004–006 already verified. Only the *combination* changes for the primary endpoint
  (detection instead of type match, spec 001 §5). The component check makes any drift a loud
  failure. Comparing against the saved `metrics.json` also catches a predictions file replaced
  after its run.
- **Per-dialogue aggregation** is what makes a shared bootstrap affordable in pure Python:
  - the test set has about 944 dialogues, so a replicate is a multiplicity vector of length 944
    built from one `rng.choices` draw over the sorted dialogue list (the same draw `metrics.py`
    makes);
  - each statistic is `sum(map(operator.mul, w, num)) / sum(map(operator.mul, w, den))` over dense
    lists aligned to the dialogue index, so the multiply-adds run in C;
  - levels, conditions, lines and systems all see the same replicate, which gives H2's
    difference-in-differences, H3's cross-system and H4's cross-endpoint contrasts honest joint
    intervals;
  - a replicate whose denominator is 0 for a statistic is skipped for that statistic and counted.

**Why dialogue resampling covers the dependence the GLMM was for.** Every item, variant and
condition of an example is nested in one dialogue. Resampling dialogues therefore carries both
item-level and dialogue-level correlation into the interval. The GLMM's random intercepts were
meant for exactly those, and its intent covariate becomes the intent-standardized sensitivity line
(spec FR15). This is the substance of the spec 001 v1.3 amendment.

**The test gate** follows the pattern specs 005 and 006 already use, placed before any outcome is
read. It requires `--allow-test`, `require_test_audit` and `freeze.json` with the config hash.

**The error audit** is a separate subcommand that runs only after the frozen test analysis. It:
- reads that report (checking its hash and config hash);
- recomputes the primary system's outcome table, to find errors without trusting the report for
  IDs;
- registers the sample through `split_audit`'s registry functions as `post_scoring` before the
  sheet exists;
- takes its freeze date only from `data/manifests/freeze.json`.

**Build order**, so dev evidence arrives early:

1. Config (with panel), inputs, outcome table, endpoints and the component check.
2. The bootstrap engine and H2. This is enough to run on Sandy's TF-IDF and encoder dev grids for
   the D-07 precision report.
3. H1/H3/H4/H5, Holm and tables.
4. Transfer and figures.
5. The error audit, which is needed only after test scoring.

## Architecture

```
configs/analysis/analysis-v1.toml          frozen plan (D-07) + panel; hashed; pinned by freeze.json
configs/analysis/inputs-<split>.toml       panel system -> files (written after runs; hashed into report)
        │
src/analysis/config.py      load + validate plan and panel; canonical hash (sorted-key JSON of parsed TOML)
src/analysis/inputs.py      validate inputs against the panel (extra = error, absent = not_run);
                            Stage 1 run dirs via config.resolved.json (train_condition, eval_split);
                            Stage 2 routed/oracle files; sha256 every file
src/analysis/outcomes.py    OutcomeTable per (system, line, condition, seed, example_id):
                            valid, predicted_type, exact, stage1_correct -> endpoints;
                            component check vs build_report(bootstrap_samples=1) and metrics.json;
                            seed averaging; seed-variation summaries
src/analysis/bootstrap.py   DialogueIndex; StatVector (dense num/den lists);
                            shared_bootstrap(stats, seed, B) -> per-stat replicate lists + excluded counts;
                            percentile CI (metrics._percentile_interval order statistics); bootstrap p; holm()
src/analysis/estimands.py   endpoint and line selection; H1–H5; linear/quadratic contrasts; level-minus-L0;
                            intent-standardized line; sparse/unstable rules; Holm family assembly
                            (config-defined members; not_run/untestable -> p = 1)
src/analysis/report.py      JSON report + provenance; Markdown/CSV tables; figure data CSV;
                            output routing (dev -> outputs/analysis/dev, test tables -> results/analysis/test)
src/analysis/error_audit.py sample (freeze.json only, --on, --inspector, frozen-report check;
                            stratified seeded draw; register post_scoring; atomic sheet write),
                            export (validated codes -> results/error_audit/codes.csv), report
src/analysis/__main__.py    python -m src.analysis run | error-audit {sample,export,report}
src/analysis/figures.py     matplotlib (uv group `figures`): context-by-level figure from figure data
```

Data flow for one statistic. "`full − none` benefit at L1, system S, primary line,
`request_interpretation`":

1. The outcome table gives seed-averaged values for each eligible example under `full` and under
   `none`. For a `matched` S, these come from the train-`full` and train-`none` runs.
2. The statistic's vectors are num[d] = Σ(c_full − c_none) and den[d] = example count, over
   dialogue d's L1 examples, with zeros elsewhere.
3. Each replicate's estimate is Σ w·num / Σ w·den. The contrasts are combinations of these
   per-replicate estimates, computed on the replicates where all their inputs are defined.

Touch points in existing code. All are additive, and no scorer output changes.

- `src/evaluation/stage1.py`: `_check_predictions` becomes public as `check_predictions`. The
  private name stays as an alias.
- `src/data/split_audit.py`:
  - `POST_SCORING_SCAN_DIRS` gains `results/error_audit` (a tested one-line change), so the
    committed codes file needs only `post_scoring` rows;
  - a small `register_rows(rows, ...)` is factored out of the `register --add` path if needed, so
    the error audit can validate the rows first and then append them in-process.
- `src/stage1/provenance.py`: `git_state(ignore=...)`, fixed 2026-10-20, ignoring the analysis
  output dir.
- `pyproject.toml`/`uv.lock`: a new `figures` dependency group with matplotlib. Sandy runs
  `uv lock` in WSL. Native-Windows tests skip the figure test when matplotlib is absent.

## Alternatives Considered

- **Aggregate existing `metrics.json` files instead of re-reading predictions.** Rejected because
  per-run reports have already resampled independently. Neither seed averaging before resampling
  nor joint intervals for differences can be recovered from them.
- **Reuse spec 005's `end_to_end` as the primary endpoint.** Rejected (review R1). It requires the
  direct/indirect type to match DIRECT's variant label, which is not spec 001's endpoint, and it
  penalizes reading rule-L0 "indirect" rewrites as direct, inside the L2 − L0 contrast. It stays
  as the `type_exact` line.
- **Re-implement validation and exactness inside the analysis.** Rejected because it creates a
  second definition that could drift. Only the endpoint combination is new, and it is built from
  checked components.
- **A separate bootstrap per contrast (the current scorer pattern).** Rejected: H2 is a difference
  of level benefits that share dialogues, and separate bootstraps give no valid interval for it.
- **Resample only each slice's own dialogues (as `by_rule_level` does).** Rejected for the
  analysis. Per-slice draws can't be combined into joint contrasts. The cost is intervals that
  differ from the per-run slices, which the tables state.
- **Dialogue-weighted means instead of example-weighted ratios.** Rejected. Ratio-of-sums
  matches every existing scorer's point estimate and the paper's "accuracy" meaning.
- **Expand resampled examples per replicate (as `metrics.py` does), or use dict-based sums.**
  Rejected for performance. Dense lists with `map(operator.mul)` keep the inner loop in C.
  AC-007-6 checks equality against `metrics.py` where both apply.
- **numpy for the bootstrap.** Rejected, because the constitution keeps scorers stdlib-only, and
  the dense-vector design makes it unnecessary.
- **Sign-flip permutation p-values for the Holm family.** These are valid for simple paired
  contrasts, but not straightforward for difference-in-differences with unequal level composition
  per dialogue. Bootstrap p-values keep one method for every member.
- **H3 on primary lines (review R6b) or on same-design pairs only (R6c).** Rejected by Sandy.
  Primary lines mix matched and test-time designs, so a difference would confound family with
  design. Test-time lines are the only design every family has.
- **A panel derived from the inputs file.** Rejected (review R2). The inputs are written after the
  test runs, so a panel derived from them would let the Holm family and the H3 tables depend on
  test results.
- **Stdlib SVG figures.** This is possible and fully deterministic, but it means a hand-built plot
  layer. matplotlib in an isolated group is the paper-standard tool, and only the figure script
  depends on it.
- **Writing `freeze.json` here.** Deferred to a WP-08 spec (008), so the freeze record pins
  everything (audit, manifest, config, recipes, prompts) in one reviewed place.

## Tradeoffs

- **No mixed model.** The bootstrap DiD gives an interval and a test for the interaction and
  respects the nesting, but it does not adjust for intent. The intent-standardized line partially
  addresses the level × intent confound. The rest is a stated limitation: H2 is associational,
  because levels are observed, not randomized.
- **A confirmatory test on rule levels.** The level variable is noisy (κ 0.74). Misclassification
  between adjacent levels usually *attenuates* a trend, which biases toward a null result, not a
  false positive. That direction is stated in the paper.
- **The (−1, 0, +1) contrast ignores L1.** It is the standard linear contrast for three equally
  spaced levels and is simple to prespecify. A non-monotone L1 is visible only in the quadratic
  contrast, which is descriptive.
- **Matched training as primary.** It compares different trained models. Run-to-run variance
  enters the contrast, which is why seed averaging matters.
- **H3 on test-time lines.** For trained systems this includes a train/test shift that the matched
  line avoids, so the H3 benefits are not the same numbers as the primary H2 benefits. The tables
  show both lines.
- **Bootstrap p-values** are coarse at 1/B and assume the percentile bootstrap is adequate. With
  about 944 dialogues and L0–L2 cells in the hundreds of dialogues, that is reasonable. Sparse and
  unstable statistics are excluded from testing by rule.
- **Holm `not_run`/`untestable` members keep p = 1 and the family size.** This is slightly
  conservative if a system is never run, but it prevents a test-dependent shrinkage of the
  family.
- **Error-audit registration needs the committed freeze record and the frozen test report.** The
  audit cannot be piloted on test before the freeze. A dev dry-run with the same code (with a
  fixture freeze file) covers that.
- **Maintenance:** a fifth evaluation module that depends on three scorers' internals
  (`check_predictions`, `validate_predictions`, `outcome`). A scorer change now also needs an
  analysis-test run. The component check makes a mismatch fail loudly rather than silently.

## Risks

- **No `routed`/`oracle` system by the freeze** (LLM/hybrid late; D-05 open). Mitigation: config
  validation refuses a primary system without the streams its endpoint needs. The fallback
  endpoint (`stage1_correct`) must be chosen before test (spec Open Questions). The tool never
  switches endpoints by itself.
- **Performance overrun.** Estimate: a few thousand statistics × 944 dialogues × 10k replicates.
  Mitigation:
  - dense vectors with C-level `map`/`sum`;
  - bootstrapping only statistics shown with intervals;
  - limiting the sensitivity lines to the headline contrasts (spec FR18);
  - measuring on dev in AC-007-16, and lowering B only on dev evidence, before the freeze.
- **Seed sets differ across training conditions** (an interrupted grid). Mitigation: a hard error
  (FR7). The grid script is resumable.
- **False alarms in the component check** from floating-point summation order. Mitigation: compare
  integer counts. The rates from `metrics.json` are compared to 1e-12.
- **Stage 2 provenance for hybrids can't be verified** (whether the router was trained matched is
  only declared). Mitigation: record the declaration and file hashes. Stage 1 runs do verify,
  through `config.resolved.json`.
- **Printing test IDs** during the smoke or test run. Mitigation: CLI output is counts only, and
  tests assert it. Claude runs only dev, and Sandy runs test and the error audit (the spec 006
  working rule).
- **Error-audit registration half-applied** if the sheet write fails. Mitigation: build the rows
  and the sheet in memory, validate the rows with the registry validator, write the sheet to a
  temporary file, append the registry rows, then rename the sheet. On a registry failure the
  temporary file is deleted. AC-007-14 covers it.
- **The freeze writer slips** (spec 008 not built by about Nov 1). Test analysis and the error audit
  both block on it. Mitigation: a roadmap item now; fixtures cover this spec's gate logic
  independently.
- **Config edited after the freeze.** Mitigation: the hash check against `freeze.json` (FR21). Any
  change is a new config version plus a dated amendment.
