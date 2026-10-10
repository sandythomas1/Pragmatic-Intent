# Analysis Plan: Draft for the December 2026 Study

_Draft 2026-10-09. Not preregistered or frozen. No new experiment was run by this revision._

## Question and estimands

Retain the proposal's context/linguistic-ambiguity question. Operationalize indirectness with
independent wording labels; measure ambiguity separately. Follow the
[research plan](research_plan.md) and [collection protocol](source_collection_plan.md).

Assistant dialogue is the primary December stratum; literature is separate transfer/pilot analysis.
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
- Literary transfer: separate genre, canonical familiarity, function and exploratory depth reporting.
  Do not pool source-confounded cells into the primary interaction.

Bootstrap complete dialogue/episode groups, preserving every item's conditions/model outputs.
Average seeds within model/item/condition first and report across-seed variability separately.
Seeds are not additional independent test items. Literary work/collection sensitivity analysis
needs enough independent works; a handful cannot support population-level literary claims.

Proposed binary correctness model for assistant dialogue:

~~~text
correct ~ context * form_level * model + intent + (1 | dialogue_group) + (1 | item_id)
~~~

Repeated conditions need item dependence as well as dialogue dependence. Consider context random
slopes only with sufficient groups. Select package, contrast coding, estimation, seed handling
and convergence/separation fallback on dev; freeze before test. The primary endpoint differs from
the legacy six-way form scorer. If the pilot cannot support this model, prespecify paired descriptive
contrasts and label H2 exploratory instead of fitting an unstable model.

Propose one primary context-by-level test, 95% intervals and alpha 0.05 for confirmatory testing;
Holm correction for the frozen secondary comparison family. Report effect sizes and contradictory
or null findings. Use pilot-based simulation before claiming power. These settings remain proposed
until the freeze checklist is complete.

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

## Freeze checklist before reported test runs

- [ ] Exact class due date, minimum deliverable and model budget recorded.
- [ ] Taxonomy, form/function supplement, required slots and gold policy settled.
- [ ] Pilot agreement, coverage and sample/power decision recorded; single-rater limits explicit.
- [ ] IDs, source/group splits, exclusions, context/donor mappings and hashes frozen.
- [ ] Model revisions, training-label policies, prompts, token budgets, seeds and retry rules pinned.
- [ ] Contextual adapter, Stage 2 scorer and routing tested on dev.
- [ ] Endpoint/test, bootstrap settings, secondary comparison family, statistical implementation
      and fallback fixed; underpowered analyses labeled exploratory in advance.
- [ ] Human baseline assignment and output audit sample/agreement procedures fixed.
- [ ] Freeze date and Git commit recorded; later amendments dated with rationale.

**Freeze record: pending.** Existing round-2 and DIRECT dev diagnostics cannot fulfill these
conditions retroactively.
