# Tasks: Context conditions, invariants and the common-set manifest

> **Phase:** Tasks · **Status:** draft · **Date:** 2026-10-14
> Derived from [`plan.md`](plan.md). Each task is small, ordered, and independently verifiable.
> `/implement` works top to bottom, checking boxes and committing logical units.

Every code task ships its own `unittest` tests with invented fixtures only. Run the suite with
`python -m unittest discover -s tests -t .` from the repo root. Real-data runs are smoke checks,
reported separately (T13). Tasks 1–4 form the first end-to-end slice: budgeted rendering flows
through training, both example sets and the scorer. Cue flags, `check`, `manifest` and the length
check build on it.

## Legend
- `[ ]` todo · `[~]` in progress · `[x]` done
- **(dep: N)** = depends on task N · **[P]** = parallelizable with siblings (disjoint files only)
- **Owner:** `@implementer` (default) · `@qa` · `@S` = Sandy (a human step, never run by Claude)
- **plan: <sections>** = the `plan.md` sections the task needs

## Setup
- [ ] 1. **Rendering core.** Create `src/data/contexts.py` with `RENDERER_VERSION = "render-v1"`,
  `BUDGET_WORDS = 350`, the `Rendered` dataclass, `render_context` (moved verbatim from
  `src/stage1/data.py`), `render()` with the budget on `full`/`mismatched` only, `input_sha256`,
  `target_sha256`, `genuine()` and `in_mismatch_set()`. Add `tests/test_contexts.py`.
  Done when: the budget fits, drops the oldest whole turns, never shortens the target, empties the
  context when the target alone is over budget, and counts `dropped`; `one`/`mismatched_one` are
  never budgeted; a no-donor mismatch returns `None`; one pinned hash value matches; sentinels in the
  original target, a later turn, the other variant and an act value never appear in any context.
  @implementer · plan: Rendering rules, Common sets

## Core Implementation
- [ ] 2. **Stage 1 uses the shared renderer.** `src/stage1/data.py`: `model_inputs` calls
  `contexts.render` for train and eval, and `render_context` is re-exported from `contexts`.
  Done when: a golden fixture whose inputs are under budget gives byte-identical `(context, target)`
  pairs to the pre-change `model_inputs`; an over-budget fixture is truncated the same way in
  training and evaluation. (dep: 1) · plan: Rendering rules, API Contract
- [ ] 3. **Two example sets in Stage 1.** `build_examples(require_comparable=…)` becomes
  `require_context=…` (excludes `turn_index == 0` only, reason `no_prior_context`), and
  `comparable()` is deleted. `src/stage1/runner.py` gets `Prepared.eval_sets` (genuine for
  none/one/full, the mismatch subset for the mismatch conditions) with `eval_inputs` aligned to them.
  `src/stage1/tfidf.py` and `src/stage1/encoder.py` iterate `prepared.eval_sets[condition]`
  (one-line plumbing change each; flag it for Sandy's review). Done when: a no-donor eval item
  appears under none/one/full only, and the training set is unchanged. (dep: 2) · plan: Common sets
- [ ] 4. **Scorer on per-condition sets.** `src/evaluation/stage1.py`: a `ScoringSets` argument
  (`None` = every example in both sets), expected predictions per condition, metrics per condition
  with `set` and `n`, each contrast with `set` and `n`, mismatch contrasts on the mismatch set on
  both sides, report `sets` and `renderer_version`. The CLI uses `require_context` and builds the
  sets from the items. The runner passes the sets and carries `sets` and `renderer_version` into
  `results/stage1.jsonl`. Done when: `full-mismatched` reports `set: mismatch` with the mismatch
  `n`; `full-none` uses the genuine `n`; missing, extra and duplicate rows still fail.
  (dep: 3) · plan: Scorer
- [ ] 5. [P] **Cue flags.** In `contexts.py`: map the target's user-act `(slot, value)` pairs to
  the fact-drift slot types (`Day, Time, Price, Area, Food, Dest/Depart/Name`; skip
  `dontcare`/`none`/empty), and add `cue_flags(item, rendered, vocab) -> CueFlags(donor_cue,
  donor_cue_one, dropped_cue)`, where `rendered` holds the condition renderings. It uses
  `audit_fact_drift.extract_mentions` and `_values_match` (nested for food/place). `donor_cue`
  tests the budgeted `mismatched` window, `donor_cue_one` the single `mismatched_one` turn, and
  `dropped_cue` the turns the budget removed from `full`. Done when: a donor naming the target's
  day in its last turn sets both donor flags; the same value only in an earlier donor turn sets
  `donor_cue` but not `donor_cue_one`; no mention sets neither; a dropped `full` turn naming the
  target's place sets `dropped_cue`; `dontcare` never matches. (dep: 1) · plan: Cue flags
- [ ] 6. **Sensitivity line.** The scorer adds `without_cue_donors: {n, difference, ci95}` to
  every contrast that touches a mismatch condition. It drops the examples flagged for *that*
  condition (`donor_cue` for `mismatched`, `donor_cue_one` for `mismatched_one`), and
  `ScoringSets.cue_donor_ids` is keyed by condition. The scorer CLI gains `--dialogues` to compute
  flags; the runner computes them once in `prepare()`. Done when: a fixture with one example
  flagged only by `donor_cue` gives `full-mismatched` `without_cue_donors.n` = mismatch `n` − 1
  and `one-mismatched_one` `without_cue_donors.n` = mismatch `n`, and the headline contrasts are
  unchanged.
  (dep: 4, 5) · plan: Scorer, Cue flags
- [ ] 7. [P] **`check` command.** `python -m src.data.contexts check --split {dev,test}` with the
  seven rules (`target_identical`, `no_future`, `budget`, `donor_split`, `donor_distinct`,
  `donor_window`, `donor_domains` on act domains only). `no_future` compares each rendered context
  against slices taken directly from `dialogues.jsonl` (`dialogue[:t]` or `donor[:t]`) and never
  calls `build_context` or `render`, so it doesn't check the code against itself. It counts
  failures per rule, names the first example per rule, and exits 1 on any failure. It validates inputs at the boundary
  (unknown split, missing donor dialogue, duplicate `example_id`). Done when: one corrupted fixture
  per donor rule, plus a context containing the target turn, fail with the named rule, and a clean
  fixture passes. (dep: 1) · plan: Checks, Security & Privacy
- [ ] 8. **`manifest` command.** `python -m src.data.contexts manifest --split … [--verify]
  [--out-dir data/manifests]` writes `contexts_<split>.csv` (columns as in the plan, including
  `donor_cue_one`, sorted, no text) and `contexts_<split>_summary.json` (provenance, set counts,
  exclusions by reason, dropped counts, `target_over_budget`, cue counts per flag, per-condition
  word-length stats, `donor_domain_check: "acts_only"`, injectable `built_at`). Both files are
  UTF-8 without BOM, written with `newline="\n"`. The single `target_sha256` is computed from every
  defined condition's rendered target, and the build fails, naming the example, if they differ.
  `--verify` rebuilds and fails on any byte difference. Add `data/manifests/contexts_dev.csv` to
  `.gitignore` and `data/manifests/*.csv -text` to a new `.gitattributes`. Done when: two builds
  are byte-identical; the bytes contain no `\r` and no BOM; changing one character of one context
  turn changes that row's hash and `manifest_sha256`; a forced target mismatch between two
  conditions fails the build; a fixture whose target exceeds the budget is counted in
  `target_over_budget`; `--verify` passes on a fresh build and fails after an edit.
  (dep: 5, 7) · plan: Manifest
- [ ] 9. [P] **Encoder length check.** Add `src/stage1/length_check.py` (tokenizer only, CPU):
  it tokenizes every budgeted train and eval input as `encoder.encode` does, and reports per
  condition the maximum subword length and the count at or over `max_length`. In
  `src/stage1/encoder.py`, record `eval_inputs_at_max_length` per condition. Both are model-side
  files: flag them for Sandy's review. Done when: a unit test with a fake tokenizer gives the right
  counts; it imports `transformers` lazily, so the stdlib suite still runs without it.
  (dep: 2) · plan: Encoder length check

## Tests
- [ ] 10. **End-to-end Stage 1 fixture.** Extend `tests/test_stage1.py`'s runner test: invented
  items include one eval item without a donor and one donor with a cue. `prepare()` → fake
  predictions → `finish()` gives the right set sizes, `set`/`n` per contrast, a
  `without_cue_donors` line, and `renderer_version` in metrics and the results log.
  (dep: 6) @qa · plan: Testing Strategy
- [ ] 11. **No-text scan.** A test builds the manifest and summary from fixtures and asserts that
  no fixture utterance, context turn or slot value appears in either file. (dep: 8) @qa
- [ ] 12. **Full suite.** Run the full suite; fix any regressions in `test_stage1.py` callers of
  `require_comparable`/`comparable`. Native Windows Python 3.12 is confirmed by Sandy on the
  Windows machine. (dep: 10, 11) @qa
- [ ] 13. **Real-data smoke check (reported, not CI).** On `data/interim/direct/`: `check` passes
  on dev and test; `manifest` builds dev and test; the test summary shows 44 items / 72 examples
  excluded `no_donor`, the budget's dropped counts (about 104 test examples), and the cue-flag
  counts; `manifest --split test --verify` passes; timing under a minute per split. Record the
  numbers in the roadmap. (dep: 8) @qa

## Observability & Docs
- [ ] 14. **Logs and provenance pass.** Confirm each command logs examples, set sizes, exclusions
  by reason, dropped counts, cue flags and failures per rule; errors name the example and the rule;
  `renderer_version` and the budget appear in every summary and metrics file. (dep: 8, 10)
- [ ] 15. [P] **Docs.** `docs/stage1_baselines.md`: the two sets, the budget, updated dev counts,
  `--dialogues` in the re-score command. New usage section for `python -m src.data.contexts`
  (check, manifest, verify) and for `length_check.py` (WSL command, needs the `gpu` group).
  Update the `src/data/direct_dataset.py` and `src/stage1/data.py` docstrings where they mention
  "comparable". (dep: 13)
- [ ] 16. **Decision and roadmap.** Add a D-06 entry to `specs/memory/decisions.md` (350-word
  budget, train and eval, rejected options, the share of test examples truncated). In the roadmap:
  mark D-06 decided, set WP-05 to "tooling done", and add the `@S` step from task 17. Set this
  file's and `spec.md`'s status. (dep: 13)
- [ ] 17. **@S, before the freeze:** in WSL, run `length_check.py` for each chosen encoder config.
  If any input reaches 512 subwords, tell Claude; the budget is lowered for all models under
  `render-v2`. (dep: 9) @S

## Verification (maps 1:1 to spec Acceptance Criteria)
- [ ] V1. AC-004-1: the target is identical under all five conditions, and the manifest build fails if any condition's target hash differs (T1, T8).
- [ ] V2. AC-004-2: sentinels for the original target, later turns, the other variant and act values are absent from every context (T1, T7).
- [ ] V3. AC-004-3: a no-donor item is in the genuine set and the none/one/full scores, absent from both sides of mismatch contrasts, and listed as `no_donor` (T3, T4, T8, T10).
- [ ] V4. AC-004-4: the budget holds in training and evaluation, oldest whole turns go first, the target is untouched, counts are correct, and untouched inputs are byte-identical (T1, T2).
- [ ] V5. AC-004-5: `check` fails with the named rule for each donor corruption and for a context containing the target turn (T7).
- [ ] V6. AC-004-6: a donor mentioning a target value is flagged (per mismatch condition), and one that doesn't is not (T5).
- [ ] V7. AC-004-7: the manifest is byte-identical on rebuild, with LF line endings and no BOM; a one-character context change changes the row hash and `manifest_sha256` (T8).
- [ ] V8. AC-004-8: committed manifest and summary contain no fixture text (T11).
- [ ] V9. AC-004-9: the Stage 1 report states the set and `n` of every contrast; `full-mismatched` uses the mismatch set on both sides (T4, T10).
- [ ] V10. AC-004-10: real-data smoke: `check` passes on dev and test, 44 test items without a donor (T13).
- [ ] V11. AC-004-11: D-06 is recorded in `decisions.md` and the roadmap with the budget and the share truncated (T16).
- [ ] V12. AC-004-12: the full suite passes on native Windows Python 3.12 (T12; Windows run by Sandy).
- [ ] V13. AC-004-13: each mismatch contrast has a `without_cue_donors` line with its `n` (T6, T10).
- [ ] V14. AC-004-14: `manifest --split test --verify` regenerates the committed test manifest byte-identically, on macOS and on Sandy's Windows/WSL checkout (T8, T12, T13).
- [ ] V15. Capture a learning in `~/development/memory/lessons_learned.md` if anything was non-obvious.
