# Review: Spec 007

Verdict: NEEDS REVISION (original); **READY after revision, 2026-10-20**

## Resolution (2026-10-20)

Sandy chose R6 option (a) and asked for every fix to be applied. Where each fix landed in the
revised `spec.md` and `plan.md`:

| Finding | Where it was applied |
|---|---|
| **R1** | FR3 defines four endpoints by formula; `request_interpretation` is primary, `type_exact` secondary; AC-007-5's first case. |
| **R2** | FR1/FR2 put the panel in the config; FR5 says an extra system is an error and an absent one is `not_run`; FR17 and AC-007-7. |
| **R3** | FR10 sets the joint draw, example-weighted ratios, zero-denominator exclusion, `unstable`, the CI-vs-p rule and the note on per-run differences; AC-007-6 gets a tolerance and an `unstable` case. |
| **R4** | FR23 takes the freeze date from `freeze.json` only, and requires `--on`, `--inspector` and the frozen report; AC-007-14. |
| **R5** | FR26 adds `results/error_audit/codes.csv` and spec 006's post-scoring scan directory; AC-007-15. |
| **R6** | Option (a): FR4 and FR12; AC-007-11. |
| **R7** | The "Amends spec 001" header, the spec 001 v1.3 note, and the plan's "why dialogue resampling covers the dependence". |
| **R8** | `over_inference` is removed from the enum; FR25 says over-inference comes from the false-positive rate. |
| **R9** | FR4 names the contrast and adds the quadratic; FR10 sets the CI-vs-p rule; FR14 fixes the H4 sign; FR15 sets H5 coverage; FR24 picks the sheet seed; FR22 sets output paths; FR18 scopes the sensitivity lines; FR5 adds the `eval_split` check; FR8 runs `bootstrap_samples=1` and compares `metrics.json`. |
| **R10** | The plan's dense vectors and `map(operator.mul)`, and the NFR's "only statistics with intervals". |
| **R11** | Roadmap WP-08 row and the spec's Open Questions (proposed spec 008). |

The open questions that remain (primary system and endpoint fallback, the rules version, the
freeze writer and B) are freeze-time decisions. They don't block decomposition or implementation.

_Reviewed 2026-10-20 against `specs/constitution.md`, spec 001 v1.2, specs 004–006 and the current
code (`src/evaluation/stage1.py`, `stage2.py`, `interpretation.py`, `metrics.py`,
`src/data/split_audit.py`)._

## Findings

### R1. The primary endpoint is not the one spec 001 defines, and the mismatch is confounded with level (blocking)

**What's wrong.** FR3 names `end_to_end` "as scored by spec 005" and describes it as "detection
AND `cat-v1` category AND act recovery". The code is stricter than that description.
`stage2.build_report` (lines 114–116) counts an example correct only when
`prediction == e.label`: the three-way **type** (direct vs indirect) must match DIRECT's variant
label, and the interpretation must be `exact`. Spec 001 §5 defines the primary H2 endpoint as
"request **detection** AND intended-category recovery".

**Why it matters.** The study's level variable is the rule level, but the type gold is the DIRECT
variant name, and the two disagree systematically:
- About 27% of DIRECT's "indirect" rewrites are rule-L0 (spec 001 v1.2 block).
- In the L0 cell, a model that reads plain wording as direct is scored *wrong* for doing so.

This depresses L0 success by a wording-dependent amount, and that amount can differ between
`full` and `none`. It bites in exactly the cell the primary trend subtracts (L2 − L0), so it can
create or hide an H2 effect. It is also a silent departure from the parent spec.

**Fix.**
- Define the primary endpoint as `request_interpretation`: predicted ≠ `no_request`, not
  invalid, and `outcome(...).exact`. It is computed from the same validated rows and outcome
  function, so FR7's reuse rule still holds.
- Keep spec 005's type-exact `end_to_end` as a named secondary line.
- The marginal check (FR7) compares the components (detection count, exact count, type-correct
  count), since `build_report` doesn't emit the new combination.
- State the definition in FR3 by its formula, not by "as scored by spec 005".

### R2. The system panel and the Holm family are fixed by a file written after test runs (blocking)

**What's wrong.** FR4 puts the systems in an inputs file that is "written after runs". FR3/FR16
put "each other system's H3 benefit difference against the primary system" in the Holm family.
So the family's size and members come from the inputs, which aren't covered by the frozen
config hash. FR16's `not_run` rule only covers members the config already names.

**Why it matters.** After seeing test scores, someone could leave out a system (or one design
line) from the inputs file:
- The family shrinks, and the Holm-adjusted p-values of the remaining members fall.
- A poorly performing model disappears from the H3 tables.

Either way the analysis passes the FR20 gate. This breaks "selection is independent of model
behavior" and "freeze before reporting".

**Fix.**
- The frozen config enumerates the panel: system name, family, context design, and which
  streams it must supply (Stage 1, routed, oracle, transfer).
- The inputs file only maps those names to files. An extra system is an error.
- A configured system with no files is `not_run`: disclosed in every table, kept in the family
  size, and given p = 1 for the adjustment (say so in FR16).
- Add an AC: deleting a system from the inputs file leaves the family size and the other
  members' adjusted p-values unchanged.

### R3. The shared-bootstrap estimator is underspecified in three ways (blocking)

Two engineers would build different estimators from FR9 as written.

**(a) Resampling scope.** The plan resamples *all* dialogues and evaluates a slice statistic
(L3, a small category) on whichever drawn dialogues contain it. The per-run scorer
(`by_rule_level`) resamples only the slice's own dialogues, with k = the slice's dialogue
count. These are different estimators with different interval widths. AC-007-6 only covers the
all-dialogue case, so it would not notice.

**(b) Weighting.** The statistic could be a ratio of sums (example-weighted, as the plan
implies) or a mean of per-dialogue means (dialogue-weighted). The two give different estimates
whenever dialogues contribute unequal numbers of examples to a level.

**(c) Zero denominators.** A replicate can draw no dialogue containing a sparse slice (INF, L3,
a small H5 category, or any slice in a dev fixture). The estimate is then 0/0, and nothing says
whether that replicate is dropped, counted, or makes the statistic undefined.

**Fix.** State in FR9:
- one joint resample of all eligible dialogues per replicate;
- each statistic is Σ w·num / Σ w·den (example-weighted);
- a replicate with a zero denominator is excluded *for that statistic only*, and the count of
  excluded replicates is reported;
- a statistic with more than 1% excluded replicates is marked `unstable` and never tested.

Note in the plan that the slice intervals will differ from the per-run `by_rule_level` intervals
by design. Give AC-007-6 an explicit tolerance (≤ 1e-12, or exact `fractions`), because
example-expansion and weighted sums add floats in different orders.

### R4. The error audit can bypass the freeze, and its date rule is inconsistent (blocking)

**What's wrong.**
- FR23 says the sampler requires "a freeze date". Spec 006's `register` also accepts
  `--freeze-date` until `freeze.json` exists (decision log, 2026-10-19). If the sampler accepts
  a CLI date, anyone can pass a past date before the real freeze. The rows are then classed
  `post_scoring`, so they don't move the primary set, even though test was inspected before
  the freeze. That is exactly what spec 006 FR14 exists to prevent.
- FR23 dates rows "the sampling day", but the NFR says the date comes from `--on`. `phase_for`
  treats rows dated on or after the freeze date as `post_scoring`, so a backdated `--on` would
  make the rows `pre_freeze` and move the set.
- The inspector is hard-coded to `A1`.

**Fix.**
- The sampler reads the freeze date only from `data/manifests/freeze.json` (no CLI override).
- It requires `--on` ≥ that date and ≤ today.
- It requires the frozen test analysis to exist: its report hash is recorded in the sample
  summary, which proves the sample came from frozen scores.
- It takes `--inspector`, validated by spec 006's pattern.
- Add each of these to AC-007-13.

### R5. The committed codes file has no path, and the obvious one breaks spec 006's scan (blocking, small)

**What's wrong.** FR25 commits a codes file with test example IDs but names no location. The
natural home, `data/annotations/`, is in spec 006's `PRE_FREEZE_SCAN_DIRS`
(`split_audit.py:102`). There, every test dialogue in the file needs a `pre_freeze` row. Sampled
dialogues only have `post_scoring` rows, so `scan` would fail. Making it pass would mean adding
`pre_freeze` rows, which moves the primary set.

**Fix.**
- Fix the path, for example `results/error_audit/codes.csv`.
- Either add that directory to spec 006's `POST_SCORING_SCAN_DIRS` (a one-line additive change,
  tested), or state that `scan` ignores it and why.
- Add an AC that `split_audit scan` passes after `export`.

### R6. H3 compares contrasts with different designs (blocking: needs Sandy's decision)

**What's wrong.** FR12 compares each system's *primary-line* full − none benefit:
- for trained systems this is **matched** (two different models);
- for the LLM it is **test-time** (one model, two inputs).

A difference between an encoder and the LLM therefore mixes "model family" with "how the
context effect was measured". H3 is "context benefit differs by model family", so with mixed
designs the Holm-tested H3 members can't tell the two apart.

**Options.**
- **(a) Recommended:** the H3 family members compare the *test-time* lines for every system
  (the only design all families share). The primary-line comparison is descriptive, and the
  design caveat is stated.
- **(b)** Keep primary lines and state in the tables that H3 confounds design with family.
- **(c)** Restrict H3's family to same-design pairs, so encoder-vs-encoder and TF-IDF-vs-encoder
  are tested and cross-design pairs are descriptive.

### R7. Spec 007 amends spec 001 without saying so (blocking, documentation only)

**What's wrong.**
- Spec 001 §13 and FR-10 tie a confirmatory H2 to the mixed-effects endpoint plus pilot
  simulation: "If unsupported, prerecord descriptive paired contrasts and **exploratory H2**."
- D-07's default reads "mixed-effects interaction only if supported".
- Spec 007 drops the GLMM, replaces the simulation with a dev precision report, *and* keeps H2
  confirmatory.

These are legitimate D-07 choices, but they contradict the parent's text as written. The
constitution says spec 001 wins conflicts, so a reviewer (or the professor) reading spec 001
would conclude the confirmatory claim is unsupported.

**Fix.**
- Add an "Amends spec 001" line to spec 007's header naming §13, FR-10 and D-07.
- Add a dated v1.3 note to spec 001: bootstrap DiD on dialogue clusters is the D-07 dependence
  model; the dev precision report replaces the pilot simulation for L0–L2; L3/INF stay
  exploratory.
- Say in the plan why dialogue clustering covers the dependence the GLMM was for: items and
  variants are nested in dialogues, so dialogue resampling carries item dependence too.

### R8. Over-inference can never be sampled by the error audit (non-blocking; decide cheaply)

**What's wrong.** FR22 samples end-to-end errors, and those exist only on mapped request
examples. Over-inference is a false positive on a gold non-request (`NR`), which is outside that
population. So the `over_inference` code can never be used.

**Fix (zero labour).** Remove `over_inference` from the audit enum, and say that over-inference
is reported quantitatively as the non-request false-positive rate. Adding an NR stratum would
cost about 15 more items of labeling and is optional.

### R9. Smaller clarity gaps (non-blocking)

- **Primary trend naming.** The weights (−1, 0, +1) give L2 − L0; L1 carries no weight. That is
  the standard orthogonal linear contrast for three equally spaced levels, but call it what it
  computes in tables ("L2 − L0 benefit difference, linear contrast"), and report L1's deviation
  (the quadratic contrast) descriptively, so readers don't assume L1 informs the test.
- **CI vs p-value.** The primary test is decided by "the CI excludes 0", and the Holm family uses
  bootstrap p. With integer-indexed percentiles the two can disagree by one replicate. Say that
  the CI rule governs the primary test and p governs Holm, or derive both from the same order
  statistic.
- **H4 sign.** Define "drop" = rate(L0) − rate(L2). H4 predicts a *negative* contrast (detection
  drops less).
- **H5 standardization** is undefined when a category is absent from some level. Restrict it to
  categories present at every level in the analysis, and report the coverage.
- **Which seed's output goes on the error-audit sheet** when several seeds exist. Pick a rule,
  e.g. the lowest seed among the wrong ones.
- **Output paths.** Specify which outputs are committed (test tables under `results/analysis/`)
  and which are git-ignored (dev diagnostics, the full JSON under `outputs/analysis/`). Dev
  numbers shouldn't sit in committed results.
- **Sensitivity-line scope (FR17).** "Every reported contrast" multiplies the bootstrap work by
  2–3×. Name the contrasts that carry `primary_minus_dup` and `without_cue_donors`: the headline
  contrasts and the primary trend.
- **Split cross-check.** Verify each Stage 1 run's `config.resolved.json` `eval_split` against
  `--split`. FR6's coverage check already rejects test IDs in a dev run, but an explicit check
  gives a clearer error and closes a gate bypass by mislabeling.
- **Marginal-check cost.** Call `build_report` with `bootstrap_samples=1`; otherwise about 160
  scorer calls each run 1,000-sample bootstraps per slice. Optionally also compare against each
  run's saved `metrics.json`. That catches a predictions file swapped after scoring, which the
  recomputation alone cannot detect.

### R10. Performance bound is unverified and could be tight (non-blocking)

**Estimate.** Roughly 8 systems × 2 lines × 2–3 endpoints × 5 contrasts × (1 + 6 levels + about 5
categories), plus the sensitivity lines, gives a few thousand statistics. At about 300 dialogues
each over 10,000 replicates, that is around 10¹⁰ multiply-adds. Pure-Python dict lookups would
take well over 15 minutes.

**Fix.** The plan should state the inner loop:
- statistics stored as dense lists aligned to a dialogue index;
- `sum(map(operator.mul, weights, values))` per statistic per replicate;
- bootstrapping only statistics that get an interval in a table.

AC-007-15 measures the result on dev before B is frozen.

### R11. Schedule dependency on the freeze writer (non-blocking)

Test analysis (FR20) and the error audit (FR23) both need `freeze.json`, which nothing writes
yet. Spec 007 can be built and tested with fixture freeze files, but the WP-08 writer (the
proposed spec 008) is on the critical path for Nov 9. Put it on the roadmap now.

## Non-Issues Considered

- **Constitution, stdlib rule.** The analysis is stdlib-only. matplotlib sits in its own pinned uv
  group and only the figure script imports it, which the constitution allows ("ML dependencies
  stay in the pinned uv dependency groups"). Native-Windows tests skip when it's absent.
- **Selection independence and the error audit.** Sampling *errors* depends on model output by
  design, and that is the audit's purpose. It doesn't select benchmark items, and strata plus a
  seeded uniform draw keep it from being hand-picked.
- **Seeds inflating n.** Averaging seeds before resampling, with dialogues as the unit, satisfies
  NFR-02 and §13.
- **Item and variant dependence.** Every item and variant is nested in one dialogue, so dialogue
  resampling covers it (this belongs in R7's note too).
- **Transfer separation.** FR18 and AC-007-11 keep IndirectRequests in its own table, consistent
  with AC-15.
- **Text and ID exposure.** Committed outputs are aggregates. The sheet with text is git-ignored
  and in spec 006's post-scoring location. CLI output is counts only. Test runs are Sandy's. This
  meets the constitution and the no-test-output working rule (apart from R5's path).
- **Matched design for the LLM.** It is untrained, so `test_time` is its only line. The matched
  decision doesn't touch a confirmatory LLM/hybrid-interpreter test, apart from a hybrid's router.
- **Mismatch control design.** It is test-time for the full-trained model, as in
  `docs/stage1_baselines.md`. It's not contradicted by matched training.
- **Determinism.** The fixed statistic order, `random.Random(seed)` and no clock fields (once R4
  pins the date) are consistent with specs 004–006's byte-identical outputs.
- **Gate placement.** The test gate runs before any outcome is read, which follows the spec 006
  learning: put the gate at the first expensive or exposing step.
- **Scope.** The GLMM, the LLM judge, the freeze writer and power simulation are rightly
  non-goals. Nothing in the requirements exceeds the Problem.
- **AC testability.** All ACs are pass/fail on fixtures, apart from AC-007-15 (a real-data smoke
  check, reported separately, which is the house convention). AC-007-5's "helps equally" fixture
  is constructible with identical per-level benefits.
