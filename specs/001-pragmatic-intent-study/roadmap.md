# Roadmap: Spec 001 execution tracker

_Started 2026-10-10. This tracks how [spec 001](spec.md) gets done. It does not restate the protocol.
Status reflects real evidence in the repo only. The [interactive guide](spec-guide.html) is not a tracker._

**How work flows.** Spec 001 is the umbrella protocol (see `specs/memory/decisions.md`, 2026-10-10).
Code work packages become child specs that run spec → review → tasks → implement. Human
research work stays here as checklist items. Owner key: **S** = Sandy, **P** = professor,
**C** = Claude (tooling only; Claude is never a gold annotator).

**Schedule pressure.** D-01: Sandy's working estimate is a **Dec 3** due date (unconfirmed). The
schedule below compresses spec §14's windows by about 8 days, mostly out of the run, analysis and
writing windows. The first things to cut are the second encoder, extra genres and mismatched_one.
Freeze, leakage checks, scorer verification and honest limits are never cut.

| Window | Work | Exit evidence |
|---|---|---|
| Oct 12–18 | Adjudicate round 2. Screen the literary pilot. Spec 003 and the ≈40-turn dialogue pilot draw. | Screened literary log; dialogue pilot sheet. |
| Oct 19–25 | Pilot contextual labels. Coverage/feasibility check. Weak baselines on dev (S). Spec 004 renderer. | Feasibility note and taxonomy (D-03, D-04). |
| Oct 26–Nov 1 | Collect untouched test groups. Spec 005 scorers. **Freeze** gold, splits, contexts and the analysis plan. | Freeze record (WP-08 data side). |
| Nov 2–8 | Models on dev (S, WSL 5060 / lab 4090). LLM prompt chosen on dev. Pin recipes. | Pinned recipes and dev predictions. |
| Nov 9–13 | Run the frozen test grid and hybrid (S). | Validated predictions and provenance. |
| Nov 14–19 | Paired contrasts, intervals, error audit. | Tables, figures, limits. |
| Nov 20–26 | Write the paper (Thanksgiving is Nov 26). | Full draft. |
| Nov 27–Dec 3 | Reproduce key results, finish, submit. | Submitted paper and results package. |

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
| D-08 WDSI | Open | The advisor interview suggested submission Aug 2027; confirm with the professor. |

## Work packages

| WP | Kind | Owner | Child spec | Status |
|---|---|---|---|---|
| WP-01 Deadline, resources, round 2 adjudication | Human | S | none | Open. Adjudication needs Sandy's decisions on `docs/round2_review.md`. |
| WP-02 Register sources, screen dev pilot | Code + human | C tooling, S screening | **002** literary sources and screening | Tooling done. 9 dev families and 22 candidates proposed (2026-10-10). Screening is next (S). |
| WP-02b Dialogue pilot draw (≈40 original MultiWOZ dev turns) | Code (small) + human | C, S | Folded into 003 | Not started. |
| WP-03 Contextual annotation supplement and pilot labels | Code + human | C schema/tooling, S/P labels | **003** contextual annotation schema | Not started. |
| WP-04 Collect untouched groups, validate splits | Code + human | C audit, S collection | 003 (split audit) | Not started. |
| WP-05 Context renderer and invariants | Code | C | **004** context conditions | Not started. |
| WP-06 Contextual adapters, Stage 2/routing scorers | Code | C | **005** scoring | Not started. |
| WP-07 Models on dev | Code | **S**, C reviews | none (Sandy's code) | Existing weak Stage 1 trainers only. |
| WP-08 Feasibility and freeze record | Human + code | S, C manifest | 004/005 freeze tooling | Not started. |
| WP-09 Held-out grid and hybrid | Code run | S | none | Blocked on WP-08. |
| WP-10 Analysis and error audit | Code + human | C analysis tooling, S audit | **006** analysis | Not started. |
| WP-11 Paper and demo | Human | S | none | Literature review (FR-11) can start now. |
| WP-12 Publication extension | Mixed | S, P | later | After the class. |

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
- [ ] S: Screen `data/interim/literary/screening_sheet.csv`, then run `export --screener A1` and
  `validate` (usage in `docs/source_collection_plan.md#screening-tooling`).
- [ ] S: Adjudicate round 2 using `docs/round2_review.md` and rubric v2. `label_initial` stays untouched.
- [ ] C: Next child spec, 003: contextual annotation schema, plus the ≈40-turn dialogue pilot draw (WP-02b/03).
- [ ] S/P: Ask the professor about second-rater availability (D-02) and the WDSI call (D-08).
- [ ] S: Start the FR-11 literature search log (search strings and dates).
