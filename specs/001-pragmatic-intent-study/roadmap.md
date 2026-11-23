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
| Nov 2–8 | Models on dev (S, WSL 5060 / lab 5090). LLM prompt chosen on dev. Pin recipes. Draft related work and methods sections. | Pinned recipes and dev predictions. |
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
| D-05 models/budget | **Primary decided 2026-11-01:** routed hybrid (DeBERTa-v3-large router + Qwen2.5-7B-Instruct interpreter); frontier Claude/OpenAI members if feasible. API data use, scope and cap are still open ([spec 009](../009-llm-routed-hybrid/spec.md)). Compute settled (2026-10-19) | Lab RTX 5090s are available. Configs for `deberta-v3-large` (planned primary encoder) and `roberta-large` were added, and the grid now runs 5 seeds. Panel, LLM and spending cap are still open. Sandy owns the model code. |
| D-06 context windows | **Decided** (Sandy, 2026-10-14) | 350-word budget on `full`/`mismatched`, train and eval, `render-v1`. Truncates 0.9% of test examples. Encoder length check pending (S, WSL). |
| D-07 statistics | **Method decided** (Sandy, 2026-10-20; spec 001 v1.3 note) | Bootstrap DiD on seed-averaged outcomes; confirmatory L0–L2 linear contrast for one prespecified system on `request_interpretation`; L3/INF exploratory; Holm secondary family with the panel fixed in the config; matched training primary; H3 tested on test-time lines. The `analysis-v1.toml` values are frozen at WP-08 after the dev precision report ([spec 007](../007-analysis-error-audit/spec.md)). Dev precision report done 2026-10-25 (TF-IDF and DeBERTa-v3-base): B = 10,000 kept; L0–L2 half-width 0.0069. |
| D-08 WDSI | **Withdrawn** (2026-10-12) | The course professor: research goes through the class, December only. |

## Work packages

| WP | Kind | Owner | Child spec | Status |
|---|---|---|---|---|
| WP-01 Deadline, resources, round 2 adjudication | Human | S | none | Round 2 adjudicated 2026-10-17; due date/resources remain open. |
| WP-02 Register sources, screen dev pilot | Code + human | C tooling, S screening | **002** literary sources and screening | Tooling done. 9 dev families and 22 candidates proposed (2026-10-10). Screening is **optional** since 2026-10-12. |
| WP-02b Dialogue pilot draw (40 dev dialogues × 1 turn) | Code (small) + human | C, S | Folded into **003** | Done 2026-10-11: `pilot1` drawn (seed 20261011) by spec 003 T5. |
| WP-03 Contextual annotation supplement and pilot labels | Historical tooling | C | **003** | Tooling retained; form/context/reveal passes and taxonomy approval dropped under option A on 2026-10-13. No form-A1 work remains. |
| WP-04 Audit official groups, prior inspection and splits | Code + human | C audit, S review | **006** split audit | Closed 2026-10-19 ([retro](../006-split-audit/retro.md)). Registry: 51 inspected test dialogues (13 label-round, 10 obsolete sheet, 24 fact-drift, 4 session logs), plus 5 cross-split duplicates excluded. Primary set: 10,585 genuine / 10,513 mismatch examples. WSL `audit --verify` passed. |
| WP-05 Context renderer and invariants | Code | C | **004** context conditions | Tooling done 2026-10-14 (T1–T16). `check` passes on dev and test; test manifest committed. |
| WP-06 Act references, Stage 2/routing scorers, IndirectRequests transfer (FR-15) | Code | C | **005** scoring | Tooling implemented 2026-10-18; dev inputs prepared. Model outputs and later adequacy/LLM-judge calibration pending. |
| WP-07 Models on dev | Code | **S**, C reviews | none (Sandy's code) | DeBERTa-v3-base dev grid done 2026-10-25 in WSL (`none`/`one`/`full` × five seeds, 15 runs) and analyzed. Matched dev accuracy: none 0.906, one 0.907, full 0.908 (dev diagnostics, not findings). [Run record](../../docs/wsl_development_2026-10-23.md). The large encoders, LLM and hybrid are not yet run. |
| WP-08 Feasibility and freeze record | Human + code | S, C manifest | 004/005 freeze tooling; **008** [freeze record](../008-freeze-record/spec.md) | Tooling done 2026-10-22 (spec 008 T1–T9; [procedure](../../docs/freeze.md)). `python -m src.data.freeze check` lists what Sandy must settle before `write`: the draft config, 3 unpinned encoder revisions, the LLM/hybrid recipes. There is one freeze, just before the Nov 9 grid. Every test entry point is gated on `verify`. |
| WP-09 Held-out grid and hybrid | Code run | S | none | Test grid run 2026-11-19 to 11-22: TF-IDF, Qwen, DeBERTa-large and the hybrid are scored; DeBERTa-base finished 2026-11-22 (job 468). All 32 Stage 1 test rows are recorded. Test analysis run 2026-11-23 (job 469): primary H2 interval includes 0. |
| WP-10 Analysis and error audit | Code + human | C analysis tooling, S audit | **007** [analysis and error audit](../007-analysis-error-audit/spec.md) (renumbered from 006 on 2026-10-19) | Drafted, reviewed (R1–R11 applied) and decomposed into 14 tasks on 2026-10-20 ([tasks](../007-analysis-error-audit/tasks.md)). T1 (config `configs/analysis/analysis-v1.toml`, draft) done 2026-10-20; T2 (shared bootstrap engine, Holm) done 2026-10-21; T3–T13 done 2026-10-21: the full `python -m src.analysis run` and `error-audit` tooling, 731 tests. T14 done 2026-10-25, pending Sandy's review: the real dev analysis of the TF-IDF runs and the DeBERTa-v3-base grid passed (91 s, component check, Monte Carlo 0.00016); the precision numbers are in the D-07 entry of `specs/memory/decisions.md`. Next: `/spec-retro 007`. Sandy runs `uv lock` for the new `figures` group. |
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
  - 2026-10-23: C prepared a [primary-source evidence map and related-work draft](../../docs/related_work.md),
    covering all five starting references and eight related works, with a dated search log and
    explicit reading depth. DIRECT, DRInQ, READI, INDIR-IT and ISA schemas are the closest
    comparisons. Sandy's reading/review and the final manuscript section remain open.
- [x] C: IndirectRequests transfer adapter and slot-value scorer (FR-15), inside [spec 005](../005-scoring/spec.md), 2026-10-18.
- [x] C: Spec 004, context conditions (2026-10-14): shared renderer `render-v1` with the D-06 budget,
  genuine and mismatch sets in Stage 1 scoring, donor cue flags with a sensitivity line, `check`
  and `manifest` (`python -m src.data.context_manifest`). Real data: all seven rules pass on dev
  (11,394 examples) and test (11,195); 72 test examples (44 items) have no donor; the budget drops
  turns from 104 test / 71 dev examples; donor cue flags 574 test / 534 dev. 452 tests pass.
- [ ] S (before the freeze): run `uv run --group gpu python -m src.stage1.length_check --config
  configs/stage1/<encoder>.toml` in WSL for each chosen encoder. Exit 1 means some input exceeds
  512 subwords; tell Claude, and the budget drops for all models under `render-v2`.
  - 2026-10-23: DeBERTa-v3-base passed in WSL on all five train/dev conditions: maximum 482/472
    tokens, zero over 512. Other chosen tokenizers and the later test preflight remain open.
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
- [x] C: Spec 006 split / prior-inspection audit drafted (2026-10-19). Sandy decided: exclude
  inspected dialogues as targets only (donors kept, count disclosed); near-duplicates are flagged
  with a sensitivity line, not excluded; no other inspections known. Open: confirm the
  conservative fact-drift exclusion (24 dialogues, about 170 items).
- [x] C/S: `/spec-review 006` (2026-10-19): R1–R9 applied; READY. Fact-drift exclusion confirmed;
  the session-log scan found 2 more test dialogues (Codex logs: none). About 49 test dialogues
  are excluded.
- [x] C: `/spec-decompose 006` (2026-10-19): 9 tasks in [tasks.md](../006-split-audit/tasks.md).
- [x] C: Implement spec 006 T1–T9 (2026-10-19).
  - Registry, scans, `check` and `audit` are built, and the committed freeze object is
    `data/manifests/split_audit_test{.csv,_summary.json}` (content hash `432e402c841b…`).
  - Stage 1 and Stage 2 test scoring now require it.
  - The registry has 51 dialogues, not 49; why is in [verification](../006-split-audit/verification.md).
  - `dup_exact` is 15.0% of primary examples, mostly NR thanks/bye lines; `needs_decision` is false.
- [x] WSL `audit --verify` passed 2026-10-19: same input hashes as Windows, byte-identical audit.
- [x] C: Transcript rescan 2026-10-19: no new test dialogues. Rerun just before the freeze only if a
  session works with test data in the meantime.
- [x] C: `/spec-retro 006` (2026-10-19): spec closed; [retro](../006-split-audit/retro.md). Before
  the 5090 grid: `git_dirty` counts the tracked results log, so later runs in one checkout log
  dirty (retro "What To Improve").
- [x] TF-IDF dev baselines rerun under the current code (2026-10-19), run from a clean WSL worktree
  at `b13ac75` and logged in `results/stage1.jsonl`.
  - `tfidf-utterance`: 0.877 dev accuracy.
  - `tfidf-context`: full-trained 0.877 under `full` vs 0.866 under `none`.
  - The old pre-spec-004 lines stay local only.
- [x] C: Retro follow-up (2026-10-20): `git_state(ignore=...)` in `src/stage1/provenance.py`
  excludes the run's own results log and output directory from `git_dirty`. Ignore paths outside
  the worktree are dropped, so an external log path still works. `src/evaluation/run.py` now uses
  the same helper. 8 new tests (hermetic temp repos); 600 pass on Windows. Unblocks the 5090 grid.
- [x] C: Spec 008 freeze record (2026-10-22): drafted, reviewed (R1–R14), decomposed (T1–T9)
  and implemented. Sandy chose one freeze before Nov 9, dated amendments, and gates on the runner,
  scorers and analysis. See [docs/freeze.md](../../docs/freeze.md) and
  [verification](../008-freeze-record/verification.md).
- [ ] S: Before the freeze, clear `python -m src.data.freeze check`:
  - encoder revisions pinned 2026-10-25; remaining findings are listed in the
    [lab readiness handoff](../../docs/lab_readiness_2026-10-25.md);
  - name the primary system and set `draft = false`;
  - give the LLM/hybrid recipes and `llm_model`, or drop them from the panel;
  - decide `auto-v1` vs `auto-v2`.

  Then follow the [procedure](../../docs/freeze.md#procedure-sandy-before-the-nov-9-grid). Claude
  reruns the transcript scan at least one day before.
- [ ] S: Supply dev model outputs using [the Stage 2 contract](../../docs/stage2_scoring.md).
  The tooling runs no models and does not yet evaluate free-paraphrase adequacy.

- [x] C: Lab readiness checks (2026-10-25): updated the figures lock, pinned the three remaining
  encoder revisions, repaired the WSL grid launcher and dry-ran both lab profiles. DeBERTa-large
  train/dev token lengths pass. Both RoBERTa tokenizers have two 514-token mismatched-training
  inputs; Sandy chose DeBERTa-large preparation and holding RoBERTa, retaining `render-v1`.
  No renderer or test data changed.
- [x] C: Lab resume safeguards (2026-10-25): the whole dev grid validates completed artifacts
  before training. New runs/checkpoints pin dialogue and source hashes; changed inputs during
  a run are refused. Legacy outputs are preserved and cannot be silently skipped. 918 tests
  pass on each platform (expected skips); see the lab handoff for evidence and compatibility.
- [x] C: Package the DeBERTa-large lab handoff (2026-10-26): private archive with Git history,
  working-tree overlay, pinned local data, checksums and both GPU profiles. WSL and restored
  checkout suites pass 918 tests (5 skipped); all train/dev tokenizer conditions fit 512.
  [Preparation evidence](../../docs/lab_preparation_2026-10-26.md).
- [x] C: `/spec-review 009` (2026-11-02): 14 findings, 6 blocking. All were applied and the spec
  is READY ([review](../009-llm-routed-hybrid/review.md)). Sandy chose prompt selection on the
  hybrid's dev `request_interpretation`. Next: `/spec-decompose 009`.
- [x] C: `/spec-decompose 009` (2026-11-02): 15 tasks
  ([tasks](../009-llm-routed-hybrid/tasks.md)). Critical path to the Nov 5 lab smoke:
  T1 → T2 → T4 → T5 → T6 → T8 → T12 → T15 runbook. Next: `/spec-implement 009 T1`.
- [x] C: Implement 009 T1–T12 and T14, then draft the T15 runbook. Done 2026-11-05 except the T14
  `inputs-dev.toml` entries, which wait on step 5. T7 and T13 are off the critical path (OQ1).
- [x] S/C: 009 lab work on the 5090, steps 1–4 (2026-11-05). P2 selected (mean 0.1774, 0.61%
  invalid) after a dev-time prompt fix; the full dev run is 0.79% invalid. Results are in
  [verification](../009-llm-routed-hybrid/verification.md), the reasons in the decisions log.
- [x] S: DeBERTa-large lab dev grid: 15 runs done 2026-10-27, in the dev analysis through PR #6.
- [x] S: Freeze choices (2026-11-05): hybrid primary, `auto-v1`, RoBERTa dropped (OQ4), `llm_model` is
  the Hugging Face commit.

**Next, in order (as of 2026-11-05):**

- [x] S: Merge the spec 009 PR into `main` (PR #8, 2026-11-05).
- [x] S: Review and merge the composer interpreter gate before the freeze. It changes pinned code
  (PR #9, merged 2026-11-09 as a3bff5c after C's review; 1185 tests OK on Windows).
- [x] C: 009 step 5: `compose` and `stage2 score` on the lab (CPU), then bring the evidence back,
  add the `inputs-dev.toml` entries and run `analysis run --split dev` (AC-009-9, T14, T15).
  Done 2026-11-09 on Windows, not the lab. The compose counts match the lab's, and AC-009-9 and
  AC-009-10 are met. The hybrid's dev half-width is 0.019
  ([verification](../009-llm-routed-hybrid/verification.md)).
- [x] S: Run the transcript scan on the Windows/WSL logs. Only the Mac's logs were scanned on
  2026-11-05 (53 logs, 0 unregistered). A new row moves the earliest freeze date to the day after it.
  Done by C on 2026-11-09, count-only with the IDs kept out of the session:
  - the Pragmatic-Intent Claude Code logs plus `~/.codex/sessions`: 65 logs, 13 test dialogues
    mentioned, 0 unregistered;
  - the other 16 Claude Code project folders: 359 logs, 0 mentioned;
  - WSL has no Claude or Codex logs.

  Nothing was registered, so the earliest freeze date is still 2026-11-06. Rescan only if a
  session works with test data before the freeze.
- [ ] S: Tell the lab admins about the 4.8 GB held on `cbu-5090-right` with no listed process.
- [ ] C: Look into why P1's mean fell (0.1399 to 0.1275) while its invalid rate improved, before
  the paper's methods section.
- [ ] S/C: Set `draft = false`, then `freeze check`, `write`, commit and `verify` on the lab. The
  earliest date is 2026-11-06, because the latest inspection is 2026-11-05. Render P2 on the lab
  first: `freeze verify` needs that git-ignored file.
  - C, 2026-11-09 on Windows: Sandy kept the hybrid as primary, so `draft = false`. `write --on
    2026-11-09` gave 98 pins, content `64454bed0ecc`, and `verify` passes locally.
  - C, 2026-11-11: amendment 1 fixes the rendered P2 pin. The write had hashed a stale local
    `p2.txt` from before the aea7d53 prompt fix (`5c7d9b82`); the selected P2 is `b736f5e4`, as in
    the selection run's provenance. Content is now `5c5759f767c9`, and `verify` passes on a fresh
    render. No test run had used the freeze. The paper discloses the amendment.
  - Left for S: merge the freeze PR, then on the lab pull `main`, regenerate `data/interim/`,
    render P2 and run `freeze verify`. It must print "verified" before the grid.
- [ ] S: WP-09 test grid on the 5090 after the freeze (planned around Nov 9). The recipe's test
  input files need generating first.
  - C, 2026-11-18: Sandy can use only one 5090, and the grid is about 17 h of GPU time, so it now
    runs in resumable sessions on one card.
    - **What was added.** `scripts/stage1_test_grid.sh` (pins `GPU=` as the only visible device,
      caps runs with `MAX_RUNS`, stops on a STOP file, writes to `outputs/stage1-test/`) and
      `scripts/plan_test_grid.py` (checks the freeze and every run before any GPU time).
    - **Order.** TF-IDF, then the Qwen test run, then DeBERTa-large one seed per session
      (2.3 h each, 11.7 h measured), then compose, then DeBERTa-base last. Base is the cut if time
      runs out.
    - **Checks.** The planner verifies against the real freeze locally: 32 runs, all in the
      frozen grid. No pinned code changed.
    - [Runbook](../../docs/wp09_single_gpu_runbook.md).
    - **Schedule.** Sandy chose two overnight blocks. Night 1 runs TF-IDF, Qwen and all of
      DeBERTa-large; compose follows the next morning. Night 2 runs DeBERTa-base, which is still
      run last and cut if needed.
    - **Handoff, 2026-11-18 evening (for the MacBook session).** Sandy plans to start night 1
      tonight from the MacBook, on whichever lab computer with a 5090 is free.
      1. Merge the WP-09 launcher PR into `main` first. The lab clones `main`, and the launcher
         is not on `main` until the merge.
      2. On the lab, follow the [runbook](../../docs/wp09_single_gpu_runbook.md):
         - "Session 0", then "Session 1", while Sandy watches;
         - then, in tmux, `GPU=<the 5090's index> SYSTEMS="deberta-v3-large"
           scripts/stage1_test_grid.sh lab-5090` (about 11.7 h).
      3. Stop and report, rather than work around, if any of these happen:
         - `freeze verify` doesn't print `verified`;
         - `git status --short` isn't empty;
         - the dry run doesn't end with `32 run(s) planned`;
         - any test-gate refusal appears.
      4. Don't print test dialogue IDs or text in the chat. Logs, `metrics.json` and checksums are
         fine.
      5. Afterwards, record here how far it got: the commit, the machine, the runs finished, and
         the three test-input checksums.
      - PR #12 (the P1 diagnosis) isn't needed for tonight.
    - **Night 1, 2026-11-19 to 11-20 (lab, cbu-5090-left, commit `37c71c0`).** Three Slurm jobs
      chained with `afterok`, all exited 0: 454 setup, 455 TF-IDF plus Qwen test, 456 all 15
      DeBERTa-large runs (11.3 h, ended 01:38 on 11-20).
      - Gates: `freeze verify` printed verified (content `5c5759f767c9`), `git status` was clean,
        and the dry run planned 32 runs. The test-input checksums match 2026-11-11: routed
        `dfd9d469…` (52,181 rows), oracle `f1c5c627…` (20,205), IndirectRequests `76959478…` (194).
      - `results/stage1-test.jsonl`: 17 rows (2 TF-IDF, 15 DeBERTa-large), all clean and non-smoke
        on the 10,465 primary test examples.
      - Qwen test: 51,148 calls, 0 retries, 378 invalid; transfer 194/194, 0 invalid.
      - DeBERTa-large, train-full: on `none`, seeds 13 and 42 drop to 0.769 and 0.741 accuracy, against
        about 0.90 for the other three. Dev showed the same thing on seed 2026 (0.718). Report this per seed.
    - **Session 7, 2026-11-22 (job 467, CPU on cbu-5090-left).** Composed 15 hybrid runs and
      scored Qwen (main and transfer) and every hybrid run on test. Compose wrote 782,715 rows, 5,604
      of them invalid, and all 17 `score` calls exited 0.
      - End-to-end success on `full`: Qwen alone 0.272. Hybrid (5-seed mean) with a train-none router
        0.111, train-one 0.191, train-full 0.333; with a train-full router it is 0.282 on `mismatched`.
      - Request-detection precision on `full`: Qwen 0.972, hybrid train-full 0.993. Category accuracy
        is about 0.76 for both. Oracle success is 0.181.
      - IndirectRequests transfer (Qwen, `none`): 4 of 194 end-to-end; 6 requests detected.
      [`configs/analysis/inputs-test.toml`](../../configs/analysis/inputs-test.toml) lists these
      runs, and DeBERTa-base since night 2.
    - **Night 2, queued 2026-11-22 (job 468, `afterok:467`).** All 15 DeBERTa-base runs with
      `CHECKPOINT_EVERY=0`, because `/lab/home` was 98% full (11 GB free). `checkpoint_every` is not
      part of the run config, so results don't change; an interrupted run restarts from step 0.
      Scripts are in `~/wp09-night2/` on the lab.
      - Job 468 exited 0 at 21:24 on 11-22 (2.3 h). `results/stage1-test.jsonl` now has 32 rows. All 15
        base rows are at commit `37c71c0`, clean, freeze `5c5759f767c9`, non-smoke, 10,465 test examples.
      - DeBERTa-base, 5-seed mean accuracy: train-full 0.926 on `full` and 0.911 on `mismatched` (gap
        +0.015). Train-one gets 0.750 on `full`; train-none gets 0.441. Train-full on `none` is 0.908
        and stable on every seed (0.90–0.91), unlike large.
    - Private evidence archives (test predictions, never in git) are at `~/wp09-test-evidence.tar.gz`
      on the lab, with a verified copy on Sandy's Mac (sha256 `1e25b96d…`). The base archive is
      `~/wp09-test-evidence-base.tar.gz` (sha256 `e352d4a2…`), also copied and verified on the Mac.
    - **Test analysis, 2026-11-23 (job 469, CPU on cbu-5090-left, commit `60b7af6`).**
      `python -m src.analysis run --split test --inputs configs/analysis/inputs-test.toml --allow-test`
      exited 0 in 4 min. Every FR21 gate passed: 6 systems and 48 runs, 0 not run, 0 sparse or unstable statistics.
      The tables are in [`results/analysis/test/`](../../results/analysis/test/). `report.json`
      stays private, in `outputs/` and the archive `~/wp09-analysis/wp09-test-analysis.tar.gz` (sha256 `5396dbb5…`,
      copied and verified on the Mac).
      - **Primary (confirmatory H2, hybrid, matched):** the L2 − L0 benefit difference is −0.005 [−0.027, 0.018],
        p 0.686: `interval_includes_0`. The test set doesn't support it.
      - Secondary (Holm): H1 trend +0.033 [0.012, 0.054], p_holm 0.008. Full − mismatched (hybrid) +0.057,
        p_holm 0.001. H2 detection trend 0.000, p_holm 0.940. H4 detection vs. oracle +0.024, p_holm 0.213.
        H3: TF-IDF and DeBERTa-base are 0.07–0.09 below the hybrid's context benefit, DeBERTa-large 0.004 below,
        all p_holm 0.001.

- [x] 2026-10-23 to 10-25, at Sandy's request: WSL DeBERTa-base dev grid in
  `~/pi-wsl-20261023` (`none`/`one`/`full` × five seeds), followed by the real dev analysis.
  Micro-batch 4, gradient checkpointing, effective batch 32; successful smoke peak 3.48 GiB.
  [Run record](../../docs/wsl_development_2026-10-23.md).
  - 2026-10-25: all 15 runs and the analysis completed (05:55Z). This closes spec 007 T14,
    pending Sandy's review ([verification](../007-analysis-error-audit/verification.md)).
  - The first attempt was interrupted at step 5,000/6,342 of `none`/seed 13 when the host
    went to sleep (12:06 PDT; not a GPU fault). It was resumed 2026-10-24T01:49Z with the same
    code digest, and that run restarted from step 0.
  - 2026-10-24, at Sandy's request: C added encoder checkpoint/resume (`--checkpoint-every`;
    10 tests, bitwise-identical resume; GPU kill/resume smoke passed). The grid was restarted
    fresh at 03:42Z with checkpoints every 250 steps. No run had completed.
  - 2026-10-24 05:41Z, at Sandy's request: `CUDA_LAUNCH_BLOCKING` was turned off, with a
    retry-once fallback to on. The run resumed at step 4,750 with losses identical to the first
    attempt, and throughput went from 21 to about 37 ex/s.
