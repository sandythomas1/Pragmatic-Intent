# Roadmap: Spec 001 execution tracker

_Started 2026-10-10. This tracks how [spec 001](spec.md) gets done. It does not restate the protocol.
Status reflects real evidence in the repo only. The [interactive guide](spec-guide.html) is not a tracker._

**How work flows.** Spec 001 is the umbrella protocol (see `specs/memory/decisions.md`, 2026-10-10).
Code work packages become child specs that run spec → review → tasks → implement. Human
research work stays here as checklist items. Owner key: **S** = Sandy, **P** = course professor
(Sandy's Machine & Deep Learning professor, through whom this research is conducted),
**C** = Claude (tooling only; Claude is never a gold annotator).

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
| Oct 12–18 | Adjudicate round 2. Label the 40-turn dialogue pilot (form pass). Start related-work reading. Literary screening only if time allows. | Dialogue form labels; adjudicated round 2. |
| Oct 19–25 | Pilot contextual labels. Coverage/feasibility check. Weak baselines on dev (S). Spec 004 renderer. | Feasibility note and taxonomy (D-03, D-04). |
| Oct 26–Nov 1 | Collect untouched test groups. Spec 005 scorers and IndirectRequests adapter. **Freeze** gold, splits, contexts and the analysis plan. | Freeze record (WP-08 data side). |
| Nov 2–8 | Models on dev (S, WSL 5060 / lab 4090). LLM prompt chosen on dev. Pin recipes. Draft related work and methods sections. | Pinned recipes and dev predictions. |
| Nov 9–13 | Run the frozen test grid, hybrid and IndirectRequests transfer (S). | Validated predictions and provenance. |
| Nov 14–19 | Paired contrasts, intervals, error audit. | Tables, figures, limits. |
| Nov 20–26 | Write the paper; send the draft to the course professor (Thanksgiving is Nov 26). | Full draft. |
| Nov 27–Dec 3 | Apply professor feedback, reproduce key results, finish, submit. | Submitted paper and results package. |

## Decisions (spec §16)

| ID | Status | Note |
|---|---|---|
| D-01 due date | **Estimated Dec 3** (Sandy, 2026-10-10) | Unconfirmed; replan if the syllabus says otherwise. |
| D-02 second rater | Open: unknown | Tooling is rater-agnostic (pseudonymous IDs, blinded sheets). Gold stays provisional until resolved. |
| D-03 intents/slots | Open | After the dev pilot (WP-03). |
| D-04 test size/power | Open | Late October, from pilot coverage. |
| D-05 models/budget | Open | Before model development. Sandy owns the model code. |
| D-06 context windows | Open | Spec 004 proposes; Sandy decides before freeze. |
| D-07 statistics | Open | On dev, before the analysis freeze. |
| D-08 WDSI | **Withdrawn** (2026-10-12) | The course professor: research goes through the class, December only. |

## Work packages

| WP | Kind | Owner | Child spec | Status |
|---|---|---|---|---|
| WP-01 Deadline, resources, round 2 adjudication | Human | S | none | Open. Adjudication needs Sandy's decisions on `docs/round2_review.md`. |
| WP-02 Register sources, screen dev pilot | Code + human | C tooling, S screening | **002** literary sources and screening | Tooling done. 9 dev families and 22 candidates proposed (2026-10-10). Screening is **optional** since 2026-10-12. |
| WP-02b Dialogue pilot draw (40 dev dialogues × 1 turn) | Code (small) + human | C, S | Folded into **003** | Done 2026-10-11: `pilot1` drawn (seed 20261011) by spec 003 T5. |
| WP-03 Contextual annotation supplement and pilot labels | Code + human | C schema/tooling, S/P labels | **003** contextual annotation (passes 1–3) | Tooling done 2026-10-11 (T1–T13). Labels (S) and taxonomy approval pending; condition judgments (pass 4) deferred to a later spec after D-02. |
| WP-04 Collect untouched groups, validate splits | Code + human | C audit, S collection | Own spec (split audit), needed by Oct 26 | Not started. Moved out of 003 (2026-10-11). |
| WP-05 Context renderer and invariants | Code | C | **004** context conditions | Not started. |
| WP-06 Contextual adapters, Stage 2/routing scorers, IndirectRequests transfer (FR-15) | Code | C | **005** scoring | Not started. IndirectRequests is already downloaded and pinned. |
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
- [ ] S: Label the dialogue form pass: `data/interim/context/pilot1/form_A1.csv`, then `export --pass form --batch pilot1 --annotator A1 --rubric v2` (usage in `docs/source_collection_plan.md#contextual-annotation-tooling`). Back up `data/interim/context/` to Google Drive.
- [ ] S (optional add-on, only if time allows): Screen `data/interim/literary/screening_sheet.csv`,
  then run `export --screener A1` and `validate` (usage in `docs/source_collection_plan.md#screening-tooling`).
- [ ] S: Adjudicate round 2 using `docs/round2_review.md` and rubric v2. `label_initial` stays untouched.
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
- [ ] S/P: Approve taxonomy v0 (`data/annotations/intent_taxonomy.csv`) and the `ctx-v0` rubric
  (`docs/context_supplement.md`) before the context pass. Record the approval date here; edits
  before approval change v0 in place, edits after the first context export need `ctx-tax-v1`.
- [x] S: Course professor's direction (2026-10-12): keep the proposal and plan, optionally add the
  new data methods, December class paper only, research through the course. Spec 001 v1.1.
- [ ] S/P: Ask the course professor to confirm the due date (D-01), second-rater availability
  (D-02), and the expected paper format/length.
- [ ] S: Start the FR-11 related-work reading from the proposal's five references; log any
  extra search strings and dates.
- [ ] C: IndirectRequests transfer adapter and slot-value scorer (FR-15), inside spec 005.
