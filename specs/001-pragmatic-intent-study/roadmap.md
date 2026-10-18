# Roadmap: Spec 001 execution tracker

_Started 2026-10-10. This tracks how [spec 001](spec.md) gets done. It does not restate the protocol.
Status reflects real evidence in the repo only. The [interactive guide](spec-guide.html) is not a tracker._

**How work flows.** Spec 001 is the umbrella protocol (see `specs/memory/decisions.md`, 2026-10-10).
Code work packages become child specs that run spec → review → tasks → implement. Human
research work stays here as checklist items. Owner key: **S** = Sandy, **P** = course professor
(Sandy's Machine & Deep Learning professor, through whom this research is conducted),
**C** = Claude (tooling only; Claude is never a gold annotator).

**Direction, 2026-10-13 (spec 001 v1.2, option A).** No new hand labeling. Levels come from the
frozen `auto-v1` wording rules (79%, κ = 0.74 against adjudicated rounds 1 and 3), intents from
MultiWOZ acts (`cat-v1`), and the test set is DIRECT's test split. The form/context/reveal passes
are dropped. See `specs/memory/decisions.md`, 2026-10-13.

**Direction, 2026-10-12 (spec 001 v1.1).** The proposal is the governing design; the only target
is the December class paper, written as a computer-science paper. The literary stratum is an
optional add-on that is cut first. IndirectRequests is back as a separate transfer test (FR-15).
WDSI, the 2027 timeline and the hallucination review are gone (D-08, WP-12 withdrawn).

**Schedule pressure.** D-01: Sandy's working estimate is a **Dec 3** due date (unconfirmed). The
schedule below compresses spec §14's windows by about 8 days, mostly out of the run, analysis and
writing windows. The first things to cut are the literary add-on, the second encoder and
mismatched_one, then the IndirectRequests transfer test.
Freeze, leakage checks, scorer verification and honest limits are never cut.

| Window | Work | Exit evidence |
|---|---|---|
| Oct 12–18 | Round 2 and original L3 check done. Renderer/manifest verified on Windows; spec 005 scoring tooling and provisional v2 rules implemented. Related-work reading can proceed. | Verified tooling; v2 frozen before held-out check. |
| Oct 19–25 | Fresh v2 L3 precision check; WSL encoder length checks; weak baselines and Stage 2 outputs on dev (S). | Rule audit, input-length evidence and dev predictions. |
| Oct 26–Nov 1 | Audit official test groups and prior inspection. **Freeze** references, splits, contexts and the analysis plan. | Freeze record (WP-08 data side). |
| Nov 2–8 | Models on dev (S, WSL 5060 / lab 4090). LLM prompt chosen on dev. Pin recipes. Draft related work and methods sections. | Pinned recipes and dev predictions. |
| Nov 9–13 | Run the frozen test grid, hybrid and IndirectRequests transfer (S). | Validated predictions and provenance. |
| Nov 14–19 | Paired contrasts, intervals, error audit. | Tables, figures, limits. |
| Nov 20–26 | Write the paper; send the draft to the course professor (Thanksgiving is Nov 26). | Full draft. |
| Nov 27–Dec 3 | Apply professor feedback, reproduce key results, finish, submit. | Submitted paper and results package. |

## Decisions (spec §16)

| ID | Status | Note |
|---|---|---|
| D-01 due date | **Estimated Dec 3** (Sandy, 2026-10-10) | Unconfirmed; replan if the syllabus says otherwise. |
| D-02 second rater | Not required for option A's mechanical labels | Any later human/LLM-judge agreement still needs its own raters and limitations. |
| D-03 intents/slots | `cat-v1` / MultiWOZ acts under option A | Spec 005 scores observed Inform values and Request names; no contextual-taxonomy approval gate. |
| D-04 test size/power | Official DIRECT test split; inferential status open | Audit prior inspection and coverage before the study freeze; sparse/noisy rule levels can remain exploratory. |
| D-05 models/budget | Open | Before model development. Sandy owns the model code. |
| D-06 context windows | **Decided** (Sandy, 2026-10-14) | 350-word budget on `full`/`mismatched`, train and eval, `render-v1`. Truncates 0.9% of test examples. Encoder length check pending (S, WSL). |
| D-07 statistics | Open | On dev, before the analysis freeze. |
| D-08 WDSI | **Withdrawn** (2026-10-12) | The course professor: research goes through the class, December only. |

## Work packages

| WP | Kind | Owner | Child spec | Status |
|---|---|---|---|---|
| WP-01 Deadline, resources, round 2 adjudication | Human | S | none | Round 2 adjudicated 2026-10-17; due date/resources remain open. |
| WP-02 Register sources, screen dev pilot | Code + human | C tooling, S screening | **002** literary sources and screening | Tooling done. 9 dev families and 22 candidates proposed (2026-10-10). Screening is **optional** since 2026-10-12. |
| WP-02b Dialogue pilot draw (40 dev dialogues × 1 turn) | Code (small) + human | C, S | Folded into **003** | Done 2026-10-11: `pilot1` drawn (seed 20261011) by spec 003 T5. |
| WP-03 Contextual annotation supplement and pilot labels | Historical tooling | C | **003** | Tooling retained; form/context/reveal passes and taxonomy approval dropped under option A on 2026-10-13. No form-A1 work remains. |
| WP-04 Audit official groups, prior inspection and splits | Code + human | C audit, S review | Own spec (split audit), needed before freeze | Pending; option A uses the official test split rather than a new sample. |
| WP-05 Context renderer and invariants | Code | C | **004** context conditions | Tooling done 2026-10-14 (T1–T16). `check` passes on dev and test; test manifest committed. |
| WP-06 Act references, Stage 2/routing scorers, IndirectRequests transfer (FR-15) | Code | C | **005** scoring | Tooling implemented 2026-10-18; dev inputs prepared. Model outputs and later adequacy/LLM-judge calibration pending. |
| WP-07 Models on dev | Code | **S**, C reviews | none (Sandy's code) | Existing weak Stage 1 trainers only. |
| WP-08 Feasibility and freeze record | Human + code | S, C manifest | 004/005 freeze tooling | Not started. |
| WP-09 Held-out grid and hybrid | Code run | S | none | Blocked on WP-08. |
| WP-10 Analysis and error audit | Code + human | C analysis tooling, S audit | **006** analysis | Not started. |
| WP-11 Paper and demo | Human | S, P guides the CS-paper form | none | Related work (FR-11) can start now. |
| WP-12 Publication extension | none | none | none | **Withdrawn** 2026-10-12. |

## Next actions

- [x] C: Fix the native-Windows TOML fixture so the full test suite passes on Windows (2026-10-10).
- [x] C: Spec 002, literary source registration and screening inventory (2026-10-10). Both editions
  are pinned. A real-file smoke check gives 284 fables and 31,102 verses. A scratch-dir
  draw/propose/export/validate flow passes. 172 tests pass on Windows.
- [x] S: Estimate the class due date (D-01): Dec 3. Confirm against the syllabus.
- [x] S: John 2 goes to the dev pilot as an explicitly assigned, inspected family, so it can never be test (2026-10-10).
- [x] C (approved by S): Literary pilot draw, 2026-10-10. There were 8 Aesop fables, plus
  `kjv:cana-wedding` (John 2), giving 22 candidates. **Seed provenance:** 6 fables come from seed 99. That seed was first used
  in the tooling smoke test, where Claude saw those fables' quoted speech, so the same seeded
  draw was reused to keep the inspected fables in dev. 2 more come from seed 20261010. Both
  draws were uniform over fables with quoted speech; pool sizes are in `literary_families.csv`.
- [~] Dropped 2026-10-13 (option A). S: Label the dialogue form pass: `data/interim/context/pilot1/form_A1.csv`, then `export --pass form --batch pilot1 --annotator A1 --rubric v2` (usage in `docs/source_collection_plan.md#contextual-annotation-tooling`). Back up `data/interim/context/` to Google Drive.
- [ ] S (optional add-on, only if time allows): Screen `data/interim/literary/screening_sheet.csv`,
  then run `export --screener A1` and `validate` (usage in `docs/source_collection_plan.md#screening-tooling`).
- [x] S: Adjudicate round 2 using `docs/round2_review.md` and rubric v2 (done 2026-10-17; Q1 = (a) `L0`, rubric R8). `label_initial` stays untouched.
  Under option A this is the fresh check for any later rule version (about 15 minutes). Rubric-v2
  sheet: `data/interim/labeling/round2/adjudication_A1.csv`; decide Q1 in `docs/option_a_checks.md` first.
- [x] C: Option A tooling (2026-10-13): `src/data/auto_levels.py` (`auto-v1` rules, `validate`,
  `distribution`), `src/data/intent_categories.py` (`cat-v1`), Cohen's κ in `src/evaluation/metrics.py`.
  24 new tests; 422 pass.
- [ ] S/P: Tell the course professor about option A: send `docs/option_a_change_summary.pdf`.
- [x] S: Spot-check 40 rule-L3 turns (OK/wrong). Done 2026-10-17: precision 12/40 (30%); see `docs/option_a_checks.md#2-spot-check-the-rules-l3-turns`. Sheet drawn 2026-10-13 (dev, seed 20261013):
  `data/interim/auto_levels/spotcheck_L3/sheet.csv`. Instructions: `docs/option_a_checks.md`.
- [x] C: Wire rule levels and `cat-v1` categories into Stage 1 scoring as slices, replacing the
  human-level slice (2026-10-14). `by_rule_level` and `by_category` on every condition and paired
  contrast; `--levels` and the config `levels` key are gone. Usage: `docs/stage1_baselines.md#slices-option-a`.
- [x] C: Spec 003 drafted (2026-10-11): sealed form → context → reveal passes, 40×1 dev dialogue draw, taxonomy v0 mechanism. Sandy chose: 40 dialogues × 1 turn; Claude drafts taxonomy v0 for S/P approval; split audit and condition judgments out of scope; free text local-only with hashes committed.
- [x] C: `/spec-review 003` (2026-10-11): READY after R1–R14 (Sandy decided R1/R2/R5/R7/R8/R14).
- [x] C: `/spec-decompose 003` (2026-10-11): 13 tasks; T1–T5 deliver the form sheet first (~Oct 14), T7 is the taxonomy/rubric approval gate.
- [x] C: Implement spec 003 T1–T13 (target: tooling ready by Oct 18; done 2026-10-11).
  - 2026-10-11: T1–T5 done. `pilot1` drawn (seed 20261011, 40 of 990 dev dialogues; only 1 social-only
    target, a ~1-in-1,000 outcome of an unbiased sampler, so the seed is kept and this is disclosed). Form sheet
    `data/interim/context/pilot1/form_A1.csv` is ready. Literary items are registered after screening export. Sandy pre-approved the T5 pilot draw (seed 20261011) and the T7 gate; the T7 taxonomy/rubric content is still shown to Sandy before the context sheet goes out.
  - 2026-10-11: T6–T11 done: taxonomy mechanism; drafts of `ctx-tax-v0` (17 intents) and the `ctx-v0` rubric
    (`docs/context_supplement.md`); `seg-v1` views; context and reveal passes; logged `correct`. 351 tests pass.
    Remaining: T12 `validate`, T13 `coverage`.
  - 2026-10-11: T12–T13 done: `validate` (13 named rules, read-only, recomputes from sources) and
    `coverage --batch` (per-annotator tables, every cell, `prior_exposure`, `built_on_superseded`).
    397 tests pass. Real data: `validate` OK on the 40-item registry. Next: `/spec-retro 003`.
- [~] Not needed under option A (2026-10-13). S/P: Approve taxonomy v0 (`data/annotations/intent_taxonomy.csv`) and the `ctx-v0` rubric
  (`docs/context_supplement.md`) before the context pass. Record the approval date here; edits
  before approval change v0 in place, edits after the first context export need `ctx-tax-v1`.
- [x] S: Course professor's direction (2026-10-12): keep the proposal and plan, optionally add the
  new data methods, December class paper only, research through the course. Spec 001 v1.1.
- [ ] S/P: Ask the course professor to confirm the due date (D-01), second-rater availability
  (D-02), and the expected paper format/length.
- [ ] S: Start the FR-11 related-work reading from the proposal's five references; log any
  extra search strings and dates.
- [x] C: IndirectRequests transfer adapter and slot-value scorer (FR-15), inside [spec 005](../005-scoring/spec.md), 2026-10-18.
- [x] C: Spec 004, context conditions (2026-10-14): shared renderer `render-v1` with the D-06 budget,
  genuine and mismatch sets in Stage 1 scoring, donor cue flags with a sensitivity line, `check`
  and `manifest` (`python -m src.data.context_manifest`). Real data: all seven rules pass on dev
  (11,394 examples) and test (11,195); 72 test examples (44 items) have no donor; the budget drops
  turns from 104 test / 71 dev examples; donor cue flags 574 test / 534 dev. 452 tests pass.
- [ ] S (before the freeze): run `uv run --group gpu python -m src.stage1.length_check --config
  configs/stage1/<encoder>.toml` in WSL for each chosen encoder. Exit 1 means some input exceeds
  512 subwords; tell Claude, and the budget drops for all models under `render-v2`.
- [x] C: Native-Windows verification (2026-10-18): 452 tests before spec 005; all seven context
  checks pass on dev/test; the 11,195-row test manifest reproduces byte-for-byte. WSL was not rerun.
- [x] C: Spec 005 deterministic Stage 2/oracle/routed scorer, slot normalization and separate
  IndirectRequests adapter/scorer implemented. Real adapter schemas: 123/136/194 pinned records.
  Dev routed/oracle inputs and transfer validation inputs are in `data/interim/stage2/`.
  Conflicting act values exclude 2 dev and 8 test examples from interpretation only.
- [x] C: Add and freeze `auto-v2` before checking adjudicated round 2 (2026-10-18): 29/30,
  κ = 0.9286, the same round-2 agreement as v1. There are no gold L3 rows in round 2.
  Full-corpus v1 predictions are unchanged; v1 remains the default. [Verification](../005-scoring/verification.md).
- [ ] S: Complete the fresh, small v2 L3 precision check at
  `data/interim/auto_levels/auto-v2/spotcheck_L3/sheet.csv` (40 rows, seed 20261018;
  63 historical/original-check turns excluded), then `python -m src.data.auto_levels_v2 spotcheck-report`.
  This does not resume the dropped three-pass annotation pipeline. V2 L3 remains provisional.
- [ ] S: Supply dev model outputs using [the Stage 2 contract](../../docs/stage2_scoring.md).
  The tooling runs no models and does not yet evaluate free-paraphrase adequacy.
