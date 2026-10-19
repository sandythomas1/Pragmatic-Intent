# Tasks: Spec 006

_Decomposed 2026-10-19 from the READY spec and plan (after review R1–R9). Order follows real
dependencies: T1 is the shared foundation; T2–T5 build on it in any order (T4 needs T2); T6 needs
T2 and T5; T7–T8 integrate scoring; T9 runs the real data and the docs. All code is stdlib
Python 3.12 with `unittest`, invented fixtures only, and no command prints utterance text._

## T1: Canonical dialogue IDs and the registry schema
- Description: `canonical_dialogue_id` (one validator/normalizer used everywhere); the registry
  row type (`dialogue_id, source, reason, inspector, inspected_on, phase, registry_version`) with
  closed enums for source, reason and phase; strict load (regex, enums, ISO dates, bounded field
  size, duplicate (dialogue, source) rejected, IDs must be test split given a split map); and a
  deterministic write (sorted, UTF-8, LF, formula-leading cells escaped). Also a hash over
  `pre_freeze` rows only, and the fixed reason precedence.
- Files likely touched: `src/data/split_audit.py` (new), `tests/test_split_audit.py` (new)
- Depends on: none
- Security-sensitive: yes. It parses an untrusted, hand-editable committed CSV and writes a file
  that is opened in spreadsheets (formula injection).
- Acceptance criteria:
  - `PMUL1762` and `PMUL1762.json` both canonicalize to `PMUL1762.json`. Malformed IDs
    (`../x`, `PMUL1762.json;`, `=cmd`, empty, overlong) raise a named error (AC-006-15).
  - Loading rejects, with a named error, a dev ID, an unknown ID, a bad enum, a bad date and a
    duplicate (dialogue, source) row (AC-006-2).
  - A formula-leading cell is escaped on write, and write → load → write is byte-identical.
  - The `pre_freeze` hash ignores `post_scoring` rows and changes when any `pre_freeze` field changes.
  - Precedence picks `levels_round1` over `fact_drift_review` for a dialogue with both.
- Status: done (2026-10-19). Formula prefixes are rejected by validation rather than escaped
  (decisions.md). 23 new tests; the full suite passes (508) with git on PATH. The security review
  was done manually because the skill needs git on PATH.

## T2: Source table and `register` with the phase gate
- Description: the fixed `SOURCES` table (explicit filenames, inspection dates, inspectors,
  expected SHA-256 for local files; the real dates and hashes are filled in T9 from the files and
  the history). `register` derives rows from committed level files and pinned local files, keeps
  manual and `claude_session` rows, keeps committed rows with a warning when a local source is
  missing, refuses a local source whose hash differs, and applies the phase gate (a freeze date
  from the freeze record or `--freeze-date`; after it, new rows are `post_scoring` and new
  `pre_freeze` rows are refused). No field comes from the clock.
- Files likely touched: `src/data/split_audit.py`, `tests/test_split_audit.py`
- Depends on: T1
- Security-sensitive: yes. It reads local files whose integrity matters and persists a committed
  freeze input.
- Acceptance criteria:
  - Fixture level files, an obsolete sheet and fact-drift rows yield the expected rows. Only test
    dialogues are registered, and the fact-drift reason is `fact_drift_review_unrecorded` (FR3).
  - A local source with a changed hash is refused with "changed since inspection". A missing one
    keeps its committed rows and logs a warning (AC-006-16).
  - Running `register` twice, with the clock mocked to different days, gives byte-identical files
    (AC-006-8, registry part).
  - With a freeze date set, a new `pre_freeze` row is refused, and a new `post_scoring` row is
    accepted and leaves the `pre_freeze` hash unchanged (AC-006-14, registry part).
  - Manual rows without a valid reason enum are rejected. Existing rows are never dropped silently.
- Status: done (2026-10-19). The real `DERIVED_SOURCES` dates and hashes were filled here, not in
  T9 (round 1: 2026-09-25, round 3: 2026-09-26, obsolete sheet and fact-drift: 2026-10-01, with
  both local files pinned). The freeze date is read from `data/manifests/freeze.json`, or from
  `--freeze-date` until that file exists. Rows dated on the freeze day are `post_scoring`. Manual
  rows are added with `register --add`.

## T3: Sheet `scan`
- Description: scan CSVs under the five human-facing locations. Resolve IDs through a
  `dialogue_id`-like column, an `item_id` via `items.jsonl`, or a sibling `key.csv`. Fail on
  unregistered test dialogues (pre-freeze locations), on unparseable CSVs, on sheets with no
  resolvable ID, and on an `.xlsx` with no sibling `*_items.csv`. Post-scoring sheets
  (`data/interim/error_audit/`) are checked against `post_scoring` rows. Output is file paths, IDs
  and counts only.
- Files likely touched: `src/data/split_audit.py`, `tests/test_split_audit.py`
- Depends on: T1
- Security-sensitive: yes. It reads arbitrary human-edited CSVs (untrusted input, bounded sizes,
  no text echoed).
- Acceptance criteria:
  - An unregistered test dialogue fails the scan, and the failure names the file and ID. A
    registered one passes. A dev-only sheet passes (AC-006-3).
  - A blind `sheet.csv` resolved through its `key.csv` is scanned. A sheet with no resolvable ID
    fails.
  - An unparseable CSV fails. An `.xlsx` without a sibling items CSV fails. With a sibling, it is
    skipped and the skip is logged.
  - A sentinel utterance in a fixture sheet never appears in the scan's output or logs.
- Status: done (2026-10-19). IDs are found by one boundary-safe pattern over every CSV cell and
  JSON/JSONL/TXT file, not per column (DIRECT `item_id`s and `d:<stem>:tNN` values embed the
  stem). "No resolvable ID fails" became "a blind `row_id` sheet without a sibling `key.csv`
  fails", because literary sheets legitimately hold no dialogue IDs. The registry file is not
  scanned. A sheet modified on or after the freeze date counts as post-scoring.

## T4: Transcript scan (local, one-time, IDs only)
- Description: `scan --transcripts <dir>...` reads JSONL logs line by line with a bounded line
  length, regex-matches dialogue IDs, keeps the test-split ones in canonical form, prints sorted
  IDs and counts only, and hands them to `register` as `claude_session` /
  `session_output_unverified` rows. The run date is written once and preserved. It reads only the
  paths given and follows no symlinks out of them.
- Files likely touched: `src/data/split_audit.py`, `tests/test_split_audit.py`
- Depends on: T1, T2
- Security-sensitive: yes. Session logs may hold secrets and unrelated work, and they are an
  untrusted external input.
- Acceptance criteria:
  - A fixture transcript holding a test ID, a dev ID, a bare-form test ID and a secret-looking
    string reports only the two test IDs (canonical, deduplicated). The secret and any log text
    are absent from stdout, logs and written files (AC-006-13).
  - An overlong line and invalid UTF-8 are handled without crashing or echoing.
  - Re-running `register` after the scan doesn't change the stored run date. After a freeze date,
    new hits are `post_scoring`.
- Status: done (2026-10-19). The usage is `scan --transcripts DIR... [--register --on DATE]`. Logs
  are read as raw bytes in 1 MiB windows with a 32-byte overlap; cut-off and context-less matches
  at window edges are handled and tested at every boundary offset. Only `.jsonl` files are read.
  54 tests cover T2–T4; the full suite passes (547) on native Windows with git on PATH.

## T5: `check`, split integrity and cross-split duplicate dialogues
- Description: the independent split checks (one split per dialogue; empty pairwise
  intersections; DIRECT test ⊆ `testListFile`, dev ⊆ `valListFile`, train disjoint from both;
  donor in the target's split). Exit 1 naming the rule and the first ID per rule while counting
  all failures. Also the `dup-v1` normalizer (NFKC, casefold, non-alphanumeric runs → space,
  strip) and the cross-split duplicate-dialogue finder (at least 2 user turns; test↔train/dev
  duplicates are non-primary; dev↔train reported only; `needs_decision` above 1%).
- Files likely touched: `src/data/split_audit.py`, `tests/test_split_audit.py`
- Depends on: T1
- Security-sensitive: no. It reads pinned, hash-verified inputs read-only and writes nothing
  committed. (Input validation still applies through T1's ID canonicalization.)
- Acceptance criteria:
  - Named-rule failures for a dialogue in two splits, a test dialogue absent from `testListFile`,
    a train dialogue in `valListFile` and a cross-split donor (AC-006-4).
  - A duplicated test dialogue is found below and above the threshold, with `needs_decision`
    only above 1%. A single-user-turn collision is ignored. Dev↔train is reported only (AC-006-5,
    detection part).
  - `dup-v1` maps strings differing only in case, punctuation, whitespace or compatibility forms
    to the same key, and keeps a one-word difference distinct.
- Status: done (2026-10-19). `check` reads `items.jsonl` itself (`split_records`, which counts rather
  than stops at a split conflict) and refuses list files that differ from their `data/sources.toml`
  pins. The underscore counts as a separator in `dup-v1` (`[\W_]+`). Duplicate keys hash the
  normalized user turns joined by `\n`. Inspection outranks duplication as an exclusion reason.

## T6: `audit`, the test audit file and summary
- Description: build one row per spec 004 genuine-set test example (reusing `src.data.contexts`
  set builders, asserting the IDs equal the committed `contexts_test.csv`, refusing on its input
  hash mismatch) with `primary`, exclusion reason (`inspected:<reason>` /
  `cross_split_duplicate_dialogue`), `dup_exact` against all train variants, and `donor_inspected`.
  The summary carries provenance hashes (items, dialogues, list files, `pre_freeze` registry rows,
  004 manifest), versions, counts by reason, primary sizes (genuine, mismatch), `dup_exact` rates
  overall / by variant / by `auto-v1` level, `donor_inspected`, the `post_scoring` count,
  `needs_decision` and its own content hash. `--verify` rebuilds and byte-compares.
- Files likely touched: `src/data/split_audit.py`, `tests/test_split_audit.py`
- Depends on: T2, T5
- Security-sensitive: yes. It writes the committed freeze object, which must stay text-free and
  tamper-evident.
- Acceptance criteria:
  - Every example of a dialogue with one registered `pre_freeze` turn is non-primary, in all
    conditions and both sets (AC-006-1). `post_scoring` rows don't affect `primary` or the content
    hash (AC-006-14, audit part).
  - `dup_exact` follows `dup-v1` and never changes `primary` (AC-006-6). An inspected donor leaves
    the example primary and is counted (AC-006-7).
  - The build is byte-identical twice. One changed `pre_freeze` row or one byte of `items.jsonl`
    changes the content hash, and `--verify` fails (AC-006-8).
  - A sentinel planted in fixture utterances, context turns and slot values is absent from the
    CSV, the summary and the logs (AC-006-10).
  - An ID mismatch against a fixture 004 manifest fails loudly.
- Status: done (2026-10-19). The summary has no build timestamp, so both files are fully
  deterministic and `--verify` byte-compares both. The `post_scoring` count sits under
  `disclosure`, outside the content hash (AC-006-14). `audit` refuses to build when `check`
  fails. `dup_exact` rates are over the primary genuine set. The audit CSV also carries `variant`
  and `mismatch_set` (IDs and flags only).

## T7: `load_test_audit` and Stage 1 test scoring
- Description: a small shared loader that validates the audit file and summary (schema,
  booleans, IDs, own content hash) and compares the recorded items, dialogues and `pre_freeze`
  registry hashes with the current ones, raising on any mismatch. Stage 1 test scoring requires
  it, drops non-primary examples from every contrast and set, states denominators, and adds one
  uncrossed `primary_minus_dup` line per contrast next to the existing minus-cue-donor line. Dev
  scoring is unchanged.
- Files likely touched: `src/evaluation/test_audit.py` (new), `src/evaluation/stage1.py`,
  `tests/test_test_audit.py` (new), `tests/test_stage1.py`, `docs/stage1_baselines.md`
- Depends on: T6
- Security-sensitive: yes. It parses a committed file that gates reported results, so a
  malformed or stale file must fail closed.
- Acceptance criteria:
  - Stage 1 test scoring fails without the audit and when it is stale against items, dialogues or
    `pre_freeze` rows, and a tampered row breaks the content hash (AC-006-9, Stage 1 part).
  - With a valid audit, every contrast's denominator excludes non-primary examples. Each contrast
    has exactly one `primary_minus_dup` line, and mismatch contrasts keep their minus-cue-donor
    line, uncrossed.
  - Dev Stage 1 reports are byte-identical to before (FR16).
- Status: done (2026-10-19). `require_test_audit` recomputes the current hashes and returns a
  `SplitAudit` (primary IDs, excluded reasons, `dup_exact` IDs, content hash). Rows are validated
  even when both hashes are resealed. The trainer checks the audit in `prepare`, before training.
  Predictions for excluded examples are ignored, so a model may predict the whole genuine set.

## T8: Stage 2 test scoring
- Description: Stage 2 routed and oracle test scoring use `load_test_audit` in the same way:
  primary filter, denominators, an uncrossed `primary_minus_dup` line. The transfer scorer is
  untouched. Document the test-scoring precondition and FR17 (the LLM-judge sample comes from dev)
  in `docs/stage2_scoring.md`.
- Files likely touched: `src/evaluation/stage2.py`, `tests/test_stage2.py`,
  `tests/test_stage2_cli.py`, `docs/stage2_scoring.md`
- Depends on: T7
- Security-sensitive: no. It reuses T7's validated loader and adds no new parsing surface.
- Acceptance criteria:
  - Stage 2 test scoring fails without the audit or with a stale one. With it, routed and oracle
    denominators exclude non-primary examples, and each contrast has one `primary_minus_dup` line
    (AC-006-9, Stage 2 part).
  - Dev Stage 2 output is unchanged. `transfer.py` behavior is unchanged.
- Status: done (2026-10-19). `inputs` on test also requires the audit and exports primary examples
  only, so test predictions align with the scored set.

## T9: Real-data run, smoke checks and documentation
- Description: confirm the `DERIVED_SOURCES` dates and hashes (filled in T2) still match. Run the
  transcript scan over this project's Claude Code transcripts and the Codex logs (IDs only), then
  `register`, `scan`, `check` and `audit` on real data. Write the committable registry, test
  audit and summary (no commit until Sandy asks). Record the smoke results in `verification.md`.
  Update `docs/analysis_plan.md` (exclusion, near-duplicate, phase and FR17 policies),
  `specs/memory/decisions.md`, `specs/memory/learnings.md`, the roadmap and the module docstring.
  Give Sandy the WSL `audit --verify` command. The full suite runs on native Windows.
- Files likely touched: `src/data/split_audit.py` (`SOURCES`),
  `data/annotations/inspected_test_dialogues.csv`, `data/manifests/split_audit_test.csv`,
  `data/manifests/split_audit_test_summary.json`, `specs/006-split-audit/verification.md`, docs
  and spec memory listed above
- Depends on: T1–T8
- Security-sensitive: yes. It handles real restricted DIRECT/MultiWOZ data and real session logs.
  Committed outputs must be verified text-free, and no test text may be printed during the run.
- Acceptance criteria:
  - `check` and `scan` pass on real data. The registry holds exactly the re-measured `pre_freeze`
    set (expected 49 distinct: 23 + 24 + 2; any difference is explained) (AC-006-11).
  - The summary reports example-level exclusions by reason, the primary genuine and mismatch
    sizes, `dup_exact` (overall, variant, level), `donor_inspected` and `needs_decision`.
    `audit --verify` passes on Windows. The WSL command is handed to Sandy.
  - A grep of the committed outputs for text from a sample of real utterances finds nothing. The
    run's console output contains no test utterance text.
  - The full suite passes on native Windows Python 3.12. The docs, decisions and roadmap record
    the policies (AC-006-12).
- Status: done (2026-10-19), except Sandy's WSL `audit --verify` (command in
  [verification.md](verification.md)).
  - The registry holds **51** `pre_freeze` dialogues, not 49. Two session-log dialogues appear only
    inside item IDs, which the earlier count's pattern missed. Both are explained in
    verification.md.
  - The primary set is 10,585 genuine and 10,513 mismatch examples; `needs_decision` is false.
  - Two real sheets led to scan changes: every CSV cell is read, and spec 003's
    `_sheet_info.json` keys are accepted.
  - A real test ID used as a T1 fixture was replaced with an invented one.
