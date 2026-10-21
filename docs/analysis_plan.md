# Analysis Plan: Draft for the December 2026 Study

_Draft 2026-10-09. Not preregistered or frozen. No new experiment was run by this revision._

## Question and estimands

Retain the proposal's context/linguistic-ambiguity question. Operationalize indirectness with
independent wording labels; measure ambiguity separately. Follow the
[research plan](research_plan.md) and [collection protocol](source_collection_plan.md).

Assistant dialogue is the primary December stratum. IndirectRequests (FR-15) and the optional
literary add-on are separate transfer analyses, never pooled into the primary interaction.
Original full preceding context establishes historical gold, held fixed across ablations.
Reduced-context scores measure recovery of that historical intent, not the sole reasonable reading
without context. Also report human uncertainty and supported alternative readings by condition.

For requests with settled form and in-scope intent, primary correctness means **correct request
detection AND intended category recovery**, adding required supported slots only where the frozen
taxonomy defines them. Missed routing fails end-to-end scoring. H2 asks how the paired full-minus-none
benefit changes across L0-L3. A context main effect alone does not support H2.

## Metrics and denominators

| Outcome | Metric | Population |
|---|---|---|
| Request detection | Request precision/recall/F1; three-way macro-F1/confusion matrix | Settled contextual status; separate informing/social slices. |
| Oracle Stage 2 | Intent accuracy; required-slot exact match where applicable | All settled in-scope gold indirect requests, irrespective of Stage 1 prediction. |
| End-to-end pipeline | Correct detection plus intent/required slots | Identical gold request sets by condition; direct routes also output intent. |
| Over-inference | False-positive request rate | Gold non-requests, by source and contextual function. |
| Unsupported interpretation | Human-audited unsupported/contradictory additions | Fixed stratified output sample; record size and selection. |
| Ambiguity | Independent agreement, uncertainty, supported alternatives | Human condition judgments; unavailable without independent raters. |
| Free-text quality | Human support/faithfulness review | Prespecified sample; supplementary to structured labels. |

Invalid output counts as error. If an uncertain/abstain option is adopted before freezing, report
coverage/selective accuracy separately and count abstention as a miss on the primary endpoint.
Log transport failures/retry rules separately. Unsupported intent additions are an operational
task error measure, not a worldwide hallucination estimate.

## Comparisons and inference

- H1/H2: categorical form level; paired one-minus-none, full-minus-none and full-minus-one differences
  per level. Full-minus-mismatched is a separate corruption control.
- H3: same items across TF-IDF, encoder and LLM. One model per family cannot establish all-family behavior.
- H4: detection and oracle interpretation on identical gold indirect items/conditions; show routing
  losses. Different denominators would make the comparison uninterpretable.
- H5: supported intent slices; small cells and clarification are exploratory.
- IndirectRequests transfer: utterance-only Stage 1 recall (every item is a request) and Stage 2
  slot-value accuracy over the closed candidate set, on the test split; `<ambiguous>` targets as a
  separate slice. Label the table LLM-generated and flag GPT-family models.
- Literary add-on (if collected): separate genre, canonical familiarity and function reporting.
  Do not pool source-confounded cells into the primary interaction.

Bootstrap complete dialogue/episode groups, preserving every item's conditions/model outputs.
Average seeds within model/item/condition first and report across-seed variability separately.
Seeds are not additional independent test items. Literary work/collection sensitivity analysis
needs enough independent works; a handful cannot support population-level literary claims.

> **Replaced (D-07, 2026-10-20; spec 001 v1.3, spec 007).** The mixed model below was the 2026-10-09
> proposal. It is **not** used, in any role. The decided method follows it ("D-07: decided
> method").

~~~text
correct ~ context * form_level * model + intent + (1 | dialogue_group) + (1 | item_id)   # replaced
~~~

### D-07: decided method (2026-10-20; implemented by spec 007)

Implemented by `python -m src.analysis run` and fixed by the hashed config
`configs/analysis/analysis-v1.toml`. The WP-08 freeze record pins that hash, and a test run
refuses any other.

- **Dependence model: dialogue-cluster bootstrap difference-in-differences.**
  - Seeds are averaged within (system, line, condition, example) before resampling.
  - One shared bootstrap per run resamples whole dialogues (B = 10,000). Every statistic is an
    example-weighted ratio on the same draw, so differences between levels, systems and
    endpoints have joint intervals.
  - Dialogue resampling carries the item and dialogue dependence the random intercepts were for.
  - Intent is handled by an intent-standardized sensitivity line, not a covariate.
- **Primary endpoint: `request_interpretation`** (spec 001 §5): a request is detected (the
  prediction is not `no_request`) AND its interpretation is exact. It is scored on gold requests
  with a mapped category. Spec 005's type-exact `end_to_end` is a secondary `type_exact` line.
- **Confirmatory test (H2).** One test: the linear contrast (−1, 0, +1) of the full − none benefit
  over rule levels L0, L1, L2 (the L2 − L0 benefit difference).
  - It uses one prespecified primary system on its primary line.
  - It is two-sided at α 0.05, decided by whether the 95% percentile interval excludes 0.
  - The quadratic contrast is descriptive.
  - L3 (rule precision 12/40) and INF are exploratory.
  - A main effect without an interaction is labelled "main effect, no interaction".
- **Context design.** Trained models use **matched** training as the primary line: condition c is
  scored by the model trained on c. The test-time line (the full-trained model under every
  condition) is secondary. Mismatch controls always use the full-trained model.
- **Secondary family (Holm), fixed in the config, never by the inputs:**
  - the H1 trend;
  - the detection-only H2 trend;
  - H4: drop(detection) − drop(oracle) under full;
  - full − mismatched;
  - H3: each other panel system's benefit minus the primary system's, on **test-time** lines.

  A system that did not run keeps its place with p = 1. H5 and the primary-line H3 comparison
  are exploratory.
- **Cells.**
  - Fewer than 30 dialogues makes a cell `sparse`.
  - More than 1% excluded replicates makes a statistic `unstable`.
  - Neither is tested.
  - The primary test touching either fails the run.
- **Precision instead of a power simulation (FR-10 amended).** The dev run reports the primary
  interval's half-width, every cell's size, and the interval under a second bootstrap seed (must
  agree to ±0.002, or B is raised before the freeze).
- **Error audit.** 15 `request_interpretation` errors per level L0–L3 from the primary system
  under full:
  - drawn after the frozen test analysis;
  - seeded and stratified;
  - registered `post_scoring` before the sheet exists;
  - coded with the closed spec 001 §13 code set.

  Over-inference is reported as the non-request false-positive rate.

Report effect sizes and contradictory or null findings. Dev numbers are diagnostics
(`dev_diagnostic_not_a_finding`); only a `frozen_test` run is a finding.

## Exclusions and leakage

Exclude unsettled full-context gold, unsupported intents/required slots, future-evidence-only
requests or undecidable form from the relevant confirmatory endpoint; retain counts/challenge
reporting. Missing context ambiguity alone cannot justify removing model errors. Missing donors
affect only paired controls, with explicit common-set denominators. Log truncation/cue visibility.

Use official dialogue splits and exclude entire previously inspected test dialogues from rounds
1/3. Group retellings/translations and near-duplicates. Calibration/dev, prompt construction,
fine-tuning and manually reviewed model outputs cannot use untouched test groups. Literary test
sources never become prompt examples. Audit shortcuts using utterance-only baselines, formatting
checks and source-separated results. Do not claim naturally occurring wording was randomized.

**Test audit (spec 006, 2026-10-19).** The policies below are implemented by
`python -m src.data.split_audit` and pinned in `data/manifests/split_audit_test{.csv,_summary.json}`.
- **Inspected dialogues are excluded as targets, whole.** The registry
  (`data/annotations/inspected_test_dialogues.csv`) lists 51 test dialogues:
  - 13 from calibration rounds 1/3;
  - 10 from the obsolete test-drawn round-3 sheet;
  - 24 more with fact-drift flags, whose reviewed sample was not recorded;
  - 4 named in assistant session logs.

  Every example of such a dialogue leaves the primary set, under every condition. Inspected
  dialogues stay in the mismatch donor pool; the count of primary examples with an inspected donor
  is disclosed (495).
- **Cross-split duplicate dialogues** are excluded as well. A duplicate is a test dialogue with at
  least 2 user turns whose `dup-v1`-normalized user turns equal a train or dev dialogue's. There
  are 5 (0.50%), below the 1% that would need a decision before the freeze.
- **Near-duplicate utterances are flagged, not excluded.** `dup_exact` marks a test paraphrase that
  equals a train utterance under `dup-v1` (NFKC, casefold, non-alphanumeric runs to one space). It
  covers 15.0% of primary examples. Each contrast reports one `primary_minus_dup` sensitivity line
  beside spec 004's `without_cue_donors` line, and the two are never crossed.
- **Primary set:** 10,585 genuine and 10,513 mismatch test examples (610 genuine examples excluded).
- **Phases.** Only `pre_freeze` registry rows define the primary set and the audit's content hash.
  After the WP-08 freeze date, new rows (for example the error audit) are `post_scoring`: they are
  disclosed and never move the frozen set.
- **LLM-judge calibration sample (FR17).** The ~50 Stage 2 outputs rated to validate the LLM judge
  come from **dev**. Drawing them from test needs Sandy's explicit decision before the freeze, and
  those dialogues are then registered `pre_freeze`.
- **Scoring gate.** Stage 1 and Stage 2 test scoring refuse to run without a valid audit that is
  current against `items.jsonl`, `dialogues.jsonl` and the `pre_freeze` registry rows.

## Freeze checklist before reported test runs

- [ ] Exact class due date, minimum deliverable and model budget recorded.
- [ ] Taxonomy, form/function supplement, required slots and gold policy settled.
- [ ] Pilot agreement, coverage and sample/power decision recorded; single-rater limits explicit.
- [ ] IDs, source/group splits, exclusions, context/donor mappings and hashes frozen. (Spec 006
      audit built 2026-10-19, content hash `432e402c841b…`; verified byte-identical on Windows
      and WSL. Rerun the transcript scan before the freeze if test data is touched again.)
- [ ] Model revisions, training-label policies, prompts, token budgets, seeds and retry rules pinned.
- [ ] Contextual adapter, Stage 2 scorer and routing tested on dev.
- [ ] Endpoint/test, bootstrap settings, secondary comparison family, statistical implementation
      and fallback fixed; underpowered analyses labeled exploratory in advance. (Method decided and
      implemented 2026-10-20/21, spec 007. Still open: the primary system (D-05), the endpoint
      fallback if no Stage 2 system is ready, the rules version, the dev precision evidence, and
      `draft = false`.)
- [ ] Human baseline assignment and output audit sample/agreement procedures fixed.
- [ ] Freeze date and Git commit recorded; later amendments dated with rationale.

**Freeze record: pending.** Existing round-2 and DIRECT dev diagnostics cannot fulfill these
conditions retroactively.
