# Retro: Spec 006

_Closed 2026-10-19. Drafted, reviewed (R1–R9), decomposed, implemented (T1–T9), verified on
Windows and WSL, and opened as PR #3 in one day. Evidence: [verification.md](verification.md)._

## Outcome

`src/data/split_audit.py` (`register`, `scan`, `scan --transcripts`, `check`, `audit`) builds a
committed, text-free registry of 51 inspected test dialogues and a hashed test audit
(`data/manifests/split_audit_test{.csv,_summary.json}`, content `432e402c841b…`). That audit fixes
the primary test set at 10,585 genuine and 10,513 mismatch examples. Of the 1,000 test
dialogues, 56 are excluded: 51 inspected and 5 cross-split duplicates. `src/evaluation/test_audit.py`
makes Stage 1 (scorer and trainer) and Stage 2 (`inputs` and `score`) fail closed on test without
a current audit, and every contrast gains an uncrossed `primary_minus_dup` line. `check` passes,
`needs_decision` is false (0.50% duplicate dialogues), and the audit regenerates byte for byte on
Windows and WSL. Spec 004's manifest, the renderer and donor pairing are unchanged.

## Deviations from Plan

- **51 registered dialogues, not "exactly 49" (AC-006-11).** The spec's count came from an ad-hoc
  word-boundary regex that cannot see an ID inside an item ID (`<ID>_t02`). The tool's
  boundary-safe pattern found 2 more session-log dialogues. All are kept under the approved
  conservative policy, and the reason is in verification.md.
- **No timestamp in the audit summary.** The NFR allowed an injectable build timestamp. Removing
  it lets `--verify` byte-compare both files, so a stale or tampered summary can't pass.
- **IDs are found by pattern over every cell, not by column or `item_id` lookup (T3).** Real
  values embed the stem (`d:<stem>:tNN`, `<stem>.json#N`), so column lookup would have missed
  `context_items.csv` and every `key.csv`. "A sheet with no resolvable ID fails" narrowed to "a
  blind `row_id` sheet with no key fails", because literary sheets legitimately hold no dialogue
  IDs. Spec 003's `<sheet>_sheet_info.json` was accepted as a key after the real scan hit it.
- **Formula-leading values are rejected, not escaped (T1, AC-006-2).** Every registry field is a
  validated ID, enum, date or constant, so no legitimate value can start with `=`, `+`, `-` or `@`.
- **Transcripts are read as 1 MiB byte windows, not line by line (T4).** Some log lines are
  megabytes long. Window-edge matches are tested at every offset.
- **The gate reaches two places the plan didn't name.** `src/stage1/runner.py` checks the audit
  in `prepare`, before any GPU time, and Stage 2 `inputs` on test exports primary examples only.
  Both serve FR15, and neither is new scope.
- **Source dates and hashes were pinned in T2, not T9**, because `register` couldn't be tested
  honestly without them.
- **Claude ran WSL `audit --verify`, not Sandy**, at Sandy's request ("do 1 and 2"). It ran from a
  temporary detached worktree, and Sandy's checkout was untouched.
- **FR17 (the LLM-judge sample comes from dev) is policy only.** It is documented in
  `docs/analysis_plan.md` and `docs/stage2_scoring.md` but not enforced in code, because no judge
  tooling exists yet.

No non-goal crept in: no split, manifest or donor changes, no fuzzy matching, no model run. No
goal was dropped.

## What Went Well

- **The review found the design hole before any code existed.** R1 (no phase field, so
  post-scoring error-audit inspection would either go unrecorded or move the frozen set) became
  the `pre_freeze`/`post_scoring` split. The disclosure-outside-the-hash design followed from it.
- **The real-data smoke run earned its place.** It broke three assumptions the fixtures never
  tested: a ragged hand-made CSV row, another spec's key-file convention, and the 49-vs-51 count.
  Each was explained without printing a test ID.
- **The ID-mask working rule held.** After it was adopted, every real-data command was masked,
  and the post-PR transcript rescan found 0 new test dialogues.
- **Determinism held across operating systems on the first try.** Explicit LF output, no clock
  fields and pinned list files gave identical `items.jsonl`/`dialogues.jsonl` hashes and a
  byte-identical audit on WSL.
- **Failing closed where it is cheapest.** Checking the audit in the trainer's `prepare` means a
  stale audit costs seconds, not a 5090 run.

## What To Improve

- **Don't state expected counts from a different matcher than the tool's.** "Exactly 49" was
  measured with a regex the tool doesn't use, which turned a correct result into a deviation.
  Future specs should state counts as "measured by the tool in the smoke step, any difference
  explained", or measure with the shipped function.
- **A real test ID went into a unit-test fixture (T1)** and was printed in a `testListFile` slip.
  It cost one dialogue. Fixtures should draw IDs from an invented range (`PMUL9xxx`) from the
  first test. A guard test could reject fixture IDs found in the committed registry.
- **`git_dirty` provenance counts the results log itself.** `src/stage1/provenance.py` uses a bare
  `git status --porcelain`. Now that `results/stage1.jsonl` is tracked, every run after the first
  in a checkout sees it modified and logs `git_dirty: true`, even with clean code. Before Sandy's
  5-seed 5090 grid, exclude `results/` from that check (`git status --porcelain -- . ':!results'`)
  or log results outside the worktree, as the TF-IDF rerun did. `src/evaluation/run.py` has the
  same pattern.
- **Plan the gate at the earliest expensive step.** The plan listed only the scorers; the trainer
  and the Stage 2 export were found during implementation. Future plans should ask where the
  first costly or irreversible step starts and put validity checks there.
- **Enforce FR17 when LLM-judge tooling is built** (spec 007 or later): the judge-calibration
  sampler should refuse test IDs unless they are registered `pre_freeze`.
