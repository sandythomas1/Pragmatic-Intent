# Verification and handoff — spec 005

2026-10-18, native Windows Python 3.12. Base: `feature/option-a-auto-levels`, commit `d402f56`.
Git fetch discovered this branch; switch and `pull --ff-only` completed. Earlier spec-003 closeout
notes from the stale branch are preserved in a named stash and were not applied here.

## Implemented and verified

| Task / criteria | Evidence |
|---|---|
| T1 / A1 | Invented v2 wording tests and explicit dispatch; existing v1 callers/defaults retained. Full-corpus v1 prediction digest is unchanged. |
| T2 / A2–A3 | V2 frozen before the round-2 check; fresh dev L3 sample excludes historical labels and the original seeded v1 sample's turns. Duplicate/missing spot-check IDs and OK rows with contradictory better labels fail. |
| T3 / A4–A6 | `tests/test_interpretation.py`: observed/reference slots, conservative normalization, extra/missing slots, unknown schema fields, complete condition/ID sets and invalid records. |
| T4 / A4–A7 | `tests/test_stage2.py`, `tests/test_stage2_cli.py`: route miss versus oracle, direct-route interpretation, non-request abstention/unsupported claims, mismatch pairing, cue sensitivity, no-text reports, safe inputs, source-overwrite rejection and LF output. |
| T5 / A8 | `tests/test_transfer.py`: literal-list safety, aliases/collisions, ambiguous targets, invalid/out-of-candidate results, full denominators, generation/family flags and explicit test opt-in. |
| T6 / A9 | Full native-Windows suite: 485 tests passed. Log: git-ignored `outputs/verification/spec005-tests.txt`. Real-data adapter/input checks below are separate from fixture tests. |

Development followed red/green tests; initial tests failed for missing behavior, then passed.
Review additionally caught non-request abstention incorrectly requiring a category and CRLF output
on Windows; regression tests now cover both. No model, GPU or paid/API jobs were run. WSL was not
rerun. No new test-model predictions or research model results are claimed.

## Frozen rule evidence

- `auto-v2` normalized-source hash (both rule modules):
  `5fe07e5f875e4ebeb5c80435a852312f53456a4a87830ec88c01017864c7689f`.
  See [auto_v2_freeze.json](auto_v2_freeze.json). New rules were fixed using the rubric,
  disclosed failure classes and invented tests before adjudicated round 2 was evaluated.
- Held-out round 2: 29/30 (96.67%), κ = 0.9286 against final labels. V1 on the same round also
  scores 29/30, κ = 0.9286. This is validation evidence, **not an accuracy improvement claim**.
  No per-item held-out errors were inspected for rule development or used to revise v2.
- Round 2 contains no gold L1 or L3 examples. It cannot validate L3 precision. V2 remains
  provisional pending the fresh check; no default was switched and historical 79% / κ 0.74
  round-1/3 agreement was not rewritten.
- Full-corpus v1 `(item_id, variant, level, rule)` prediction digest, before and after:
  `33cd6b6acc617fca3c10cd33e3f01dec144a52da6c277ee5c658e674d8150a89`.
- Round-2 reference file SHA-256 in this native-Windows checkout:
  `bfb39cb3bec1b1a2639ca8ebcd05d90c10113ec643170c869e5daedaca371ba6`.
  This is a local byte hash; CSV line endings may differ in other checkouts.
- Fresh L3 sample: 40 rows, seed 20261018, 63 historical/original-check turns excluded,
  0 verdicts filled. The original v1 draw is reconstructed read-only from seed 20261013 and
  the same pinned items, so missing git-ignored old sheets do not allow resampling inspected turns.
  Snapshot contains rule/source hashes, seed, excluded-turn digest and row mapping. No v1 sheet
  was overwritten and no human verdict was generated.

Local files: `outputs/auto_levels/auto-v2/{freeze,validate}.json` and
`data/interim/auto_levels/auto-v2/spotcheck_L3/{sheet.csv,key.csv,snapshot.json}`.

## Real-data smoke checks

- All pinned IndirectRequests files pass byte/hash and schema validation: train 123 (22
  ambiguous), validation 136 (21), test 194 (38). Reading the test schema/counts is not a model
  evaluation. No transfer records were added to training or committed.
- Main act-reference coverage: dev 11,394 weak examples, with 2 conflicting-value interpretation
  exclusions and 4,516 oracle-eligible examples; test 11,195, with 8 such exclusions and 4,332
  oracle-eligible examples. Detection retains conflicting-reference examples. No quota or model
  output was used to select or remove an example.
- Prepared `data/interim/stage2/dev_routed_inputs.jsonl`: 56,862 records; 11,394 under each of
  none/one/full, 11,340 under each mismatch condition.
- Prepared `data/interim/stage2/dev_oracle_inputs.jsonl`: 22,560 records; 4,516 under each of
  none/one/full, 4,506 under each mismatch condition. The oracle selection is independent of routes.
- Prepared `data/interim/stage2/indirect_requests_validation_inputs.jsonl`: 136 none-only records.
  Export fields were checked for forbidden gold/act/situation/rating columns and input hashes.
  Text inputs remain git-ignored. No test model-input exports were prepared.
- Spec 004 Windows checks: the original 452-test suite passed before these changes; all seven
  context invariant rules have zero failures for dev and test; committed test manifest reproduces
  all 11,195 rows byte-for-byte. Manifest SHA-256:
  `3dd59868379a94c83d298e6f7f3d3a765b3bb7f96d1d7b7ab5592d899413a977`.

## Remaining human/model work

1. Sandy: the fresh, small L3 precision audit, then
   `python -m src.data.auto_levels_v2 spotcheck-report`. This is not form-A1 labeling or the
   retired three-pass pilot. V2 does not become a validated L3 slice merely because the code passes.
2. Sandy: spec 004 T17 tokenizer length checks in WSL for the selected encoders. Commands are
   in [the baseline guide](../../docs/stage1_baselines.md). The agent did not launch them.
3. Sandy: model outputs using [the input/prediction contracts](../../docs/stage2_scoring.md).
   Free-paraphrase adequacy and an LLM judge remain unimplemented until outputs exist and the
   planned human ratings can calibrate the judge. Deterministic act recovery is reported separately.
4. Split/prior-inspection audit, model/prompt selection and WP-08 freeze before reported test runs.
   `--allow-test` records explicit user intent; it does not establish an approved freeze.

Verification was completed before publication. Commits and PR publication are tracked in Git;
no deployment or model/API/GPU run was performed.
