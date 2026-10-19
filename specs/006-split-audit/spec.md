# Spec 006: Split and prior-inspection audit

> **Phase:** Implemented · **Status:** T1–T9 done 2026-10-19 ([verification](verification.md)); WSL `audit --verify` pending · **Owner:** Sandy (decisions), Claude (tooling) · **Date:** 2026-10-19
> The *what* and *why*. No implementation detail; that belongs in `plan.md`.

Parent: [spec 001](../001-pragmatic-intent-study/spec.md) WP-04, FR-06, AC-04; WP-08 (freeze).
Written under the v1.2 direction (option A, 2026-10-13): the test set is DIRECT's official test
split, so WP-04 audits that split rather than collecting new untouched groups.
Roadmap window: Oct 19–25, before the Oct 26–Nov 1 freeze. Review: [review.md](review.md).

## Problem

The constitution says anything a researcher has inspected never enters untouched test, and that
leakage is controlled by group. FR-06 and AC-04 turn this into a rule: exclude the *whole*
dialogue, not just the inspected turn. `docs/analysis_plan.md` already promises to exclude the
round 1/3 test dialogues, but nothing records or enforces it. A check on 2026-10-19 found more
inspected test dialogues than the plan names:

- **Calibration rounds 1 and 3** (committed `levels_round1.csv`, `levels_round3.csv`): 13 test
  dialogues. Sandy labeled them, and the rubric and `auto-v1` rules were shaped around them.
  PMUL1762, the fact-drift example, is one of them.
- **The obsolete test-drawn round-3 sheet** (local `round3_items.csv`, 2026-10-01): 10 more test
  dialogues. Sandy never labeled it, but Claude sealed labels on it, so Claude read it.
- **The fact-drift precision check** (2026-10-01): Claude hand-read samples of flagged rewrites
  from all splits, and the sample IDs were never recorded. 25 test dialogues have flagged
  rewrites (24 not already counted above).
- **Claude session output.** Claude doesn't remember what earlier sessions printed. A read-only
  scan of the local Claude Code transcripts found test dialogue IDs. All but 2 are already counted
  above; the 2 left cover 11 items, and one of them is a mention of IDs only. Codex session logs
  hold no test IDs.

Together these touch about 49 of 1,000 test dialogues (about 357 of 7,372 test items). Nothing
also checks today, independently of the builder, that split intersections are empty. Nothing
measures how many test utterances are already in train verbatim either: after simple
normalization, 1,154 test targets (15.7%) match a train utterance, mostly short templated lines.
Spec 001 also *plans* human inspection of test after scoring (the WP-10 error audit), and that
must not move the test set. The freeze record (WP-08) needs all of this pinned before any
reported test score.

## Goals

- A committed, text-free registry of every known inspected test dialogue, with its source,
  reason, inspection date and phase. It is rebuilt deterministically from pinned sources and
  stated as complete to the researchers' knowledge plus a mechanical scan of the session logs.
- Independent, fail-loud verification that splits are grouped by dialogue and that the split
  intersections are empty.
- A flagged near-duplicate audit of test against train that keeps the official splits
  (Sandy, 2026-10-19).
- One text-free, hashed test audit file that the freeze record pins, saying for every test example
  whether it is in the primary set, why not, and whether it is near-duplicate flagged.
- Stage 1 and Stage 2 test scoring honor the audit: exclusions are applied, denominators are
  stated and the near-duplicate sensitivity line is reported.
- Inspection after scoring is recorded for disclosure and never changes the primary set.

## Non-Goals

- Changing the official splits, `items.jsonl` or mismatch donor pairing. Inspected dialogues stay
  in the donor pool, and spec 004's committed test manifest is not changed (Sandy, 2026-10-19:
  targets only, donor overlap disclosed as a count).
- Excluding near-duplicates from the primary endpoint (Sandy, 2026-10-19: flag plus sensitivity).
- Fuzzy or delexicalized near-duplicate matching. It is an explicit later extension, not December
  scope.
- Excluding dev dialogues. Dev is where inspection is allowed.
- Collecting new untouched groups (replaced by the official split under option A), and the
  literary add-on's family grouping (spec 002 already pre-assigns families to dev).
- IndirectRequests separation. Spec 005 already keeps transfer records out of the main benchmark
  and training.
- The WP-08 freeze record itself. This spec produces one of its inputs and honors its date.
- Any model run or reported test score.

## User Stories

- As **Sandy writing the methods section**, I want one table saying which test dialogues were
  removed and why, so the "untouched test" claim is true and checkable.
- As **the course professor**, I want evidence that no calibration or rule-development turn was
  scored as held-out test, so the rule-level results aren't inflated by tuning on test.
- As **the freeze step (WP-08)**, I want one hashed, text-free file that fixes the primary test
  set, so a later change to exclusions is detectable.
- As **a future session (Claude or Sandy)** that opens a new sheet, I want the audit to fail if a
  pre-freeze human-facing sheet holds an unregistered test dialogue, so an inspection can't go
  unrecorded again.
- As **Sandy doing the error audit after scoring**, I want to inspect test outputs without
  invalidating the frozen test set.

## Functional Requirements

**Registry**

1. The system MUST maintain a committed registry of inspected test dialogues. Each row holds the
   dialogue ID (canonical form, FR5), a source code, a reason code, who inspected it (pseudonymous
   annotator ID or `claude`), the inspection date, the phase (`pre_freeze` or `post_scoring`) and
   the registry version. It holds no utterance text and no free-text notes. A dialogue may have
   several rows, one per source. All of them stay in the registry, and the summary reason uses the
   fixed precedence `levels_round1` > `levels_round3` > `obsolete_round3_sheet` >
   `fact_drift_review` > `claude_session` > `manual`.
2. Derived rows MUST come from a fixed source table in code. The table names each source's file
   explicitly (never inferred from a filename's round number), its inspection date and inspector,
   and, for git-ignored local files, the file's expected SHA-256 at inspection time. `register`
   MUST refuse a local source whose hash differs ("changed since inspection"); such a change is
   handled as a manual row with a reason. If a local source is missing (a fresh clone), the
   committed rows are kept and a warning is logged. Dates come from the table, never from the
   clock. Manual rows MUST carry a reason code from a closed enum, and they are preserved. Rows are
   never deleted silently; a removal is a new registry version with a logged reason.
3. Test dialogues with fact-drift flags MUST be registered with reason
   `fact_drift_review_unrecorded`, from the 2026-10-01 `fact_drift.jsonl` pinned by hash, because
   the sampled IDs were not recorded and any of them may have been read (Sandy, 2026-10-19).
4. A `scan` MUST search the human-facing sheet locations (labeling, auto-level spot checks,
   context annotation, literary screening, committed annotations) for test-split dialogue IDs,
   directly or through an `item_id`. It MUST fail, naming the file and the dialogue, when a test
   dialogue is unregistered. A CSV it can't parse, or an `.xlsx` with no sibling items CSV, also
   fails it. Sheets in the designated post-scoring locations, and any sheet dated after the freeze
   date (FR14), are reported and need `post_scoring` rows, but they never change the primary set.
   Model-input exports are not inspection and are not scanned.
5. Every dialogue ID read at any boundary (registry, sheets, list files, transcripts) MUST be
   normalized to one canonical form, the `items.jsonl` form with `.json` (for example,
   `PMUL1762.json`), by one shared function. Every registered ID MUST exist in the corpus and be
   in the test split; a dev, train or unknown ID, or a malformed one, is a validation error.
6. A one-time, local-only `scan --transcripts <dir>` MUST match MultiWOZ dialogue IDs in assistant
   session logs (Claude Code transcripts, and Codex logs if present) against the test split. It
   MUST output **IDs and counts only**, never a line of the log. Hits are registered as
   `source = claude_session`, `reason = session_output_unverified`, `phase = pre_freeze`, with the
   date of the scan run. Sessions don't record whether an ID came with its text, so every hit is
   treated conservatively. It never runs in CI and reads only paths given on the command line.

**Split checks**

7. A `check` MUST verify, from `items.jsonl` and independently of the builder, that: each dialogue
   is in exactly one split; the train, dev and test dialogue sets have empty pairwise
   intersections; DIRECT test dialogues are a subset of MultiWOZ 2.1's official `testListFile`,
   DIRECT dev is a subset of `valListFile`, and DIRECT train is disjoint from both lists; and every
   mismatch donor is from the target's split. It MUST exit non-zero, naming the rule and the first
   offending ID per rule, while still counting all failures.
8. The `check` MUST find cross-split duplicate dialogues: a test dialogue with at least two user
   turns whose full user-turn sequence (all user turns, in order, each `dup-v1` normalized)
   exactly equals that of a train or dev dialogue. Such test dialogues are always non-primary, with
   reason `cross_split_duplicate_dialogue`. Dev↔train duplicates are reported only. If test
   duplicates exceed 1% of test dialogues, the summary MUST carry `needs_decision: true`. That is a
   freeze blocker Sandy resolves; it does not change membership.

**Near-duplicate audit**

9. For each test example, the system MUST flag `dup_exact` when its model-visible text (the
   variant utterance) equals, after the versioned normalization `dup-v1`, any train utterance under
   any variant. The flag never excludes.
10. The summary MUST report the flag rate overall, by variant and by `auto-v1` rule level (the
    default rules), so the paper can show whether duplication is concentrated at one level.

**Audit file and scoring**

11. An `audit` command MUST write, for the test split, one row per example in spec 004's genuine
    set: example ID, item ID, dialogue ID, `primary` (true/false), exclusion reason (empty,
    `inspected:<reason>` or `cross_split_duplicate_dialogue`), `dup_exact`, and whether its donor is
    a registered dialogue (`donor_inspected`, a disclosure only). Only `pre_freeze` registry rows
    affect `primary`. It holds no text.
12. The audit summary MUST carry provenance: SHA-256 of `items.jsonl`, `dialogues.jsonl`, the
    MultiWOZ list files, the `pre_freeze` registry rows (a hash over those rows only, so that
    adding `post_scoring` rows doesn't change it) and spec 004's committed test manifest; the
    `dup-v1` and registry versions; and its own content hash. It MUST also carry counts: dialogues,
    items and examples excluded by reason; the primary set size for the genuine and mismatch sets;
    `dup_exact`; `donor_inspected`; the number of `post_scoring` dialogues; and `needs_decision`.
13. The test audit file and summary MUST be committed (the freeze object). They MUST regenerate
    byte-identically from the pinned inputs (`--verify`).
14. Once the WP-08 freeze record gives a freeze date, `register` MUST accept new rows only as
    `post_scoring`, and every new `pre_freeze` row MUST fail with "freeze recorded on <date>".
    Until the record exists, the freeze date is unset and new rows default to `pre_freeze`.
15. Stage 1 and Stage 2 scoring on test MUST require the audit file. They MUST drop non-primary
    examples from every contrast and state each contrast's denominator. Each sensitivity is
    applied once, on its own, against the primary set, and never crossed with another. Spec 004's
    minus-cue-donor line stays, and a new primary-minus-`dup_exact` line is added, each with its
    own denominator. Scoring on test MUST fail without a valid audit file, or when the audit's
    recorded hashes don't match the current `items.jsonl`, `dialogues.jsonl` or `pre_freeze`
    registry rows.
16. Dev scoring MUST be unchanged.
17. The ~50 Stage 2 outputs rated to calibrate the LLM judge (spec 001 v1.2) MUST be drawn from
    **dev**. Drawing them from test needs Sandy's explicit decision before the freeze, and the
    dialogues are then registered `pre_freeze`.

## Non-Functional Requirements

- **Security / data handling:** committed files hold IDs, codes, dates, counts and hashes only.
  Tests assert that no fixture text reaches them or the logs. The registry, sheets, list files and
  transcripts are untrusted input: IDs are regex-validated and canonicalized, enums are checked,
  CSV field sizes are bounded, and malformed rows are rejected loudly. Committed CSVs escape
  formula-leading cells. No command prints utterance text. Errors name IDs, files and rules only.
  The transcript scan never echoes log content, which may hold secrets or unrelated work, and
  nothing from it is written except matched IDs.
- **Determinism:** the same pinned inputs give byte-identical files (UTF-8, LF line endings on
  every OS), apart from an injectable build timestamp. No registry field comes from the clock,
  except the run date of the one-time transcript scan, which is written once and committed.
- **Performance:** `check`, `scan` and `audit` each finish in under a minute on a laptop CPU over
  the full corpus (about 71,500 items).
- **Compatibility:** Python 3.12 standard library only, passing on native Windows and WSL. Spec
  004's manifest, the renderer and donor pairing are not changed.
- **Observability:** each command logs counts (by split, by reason, by phase, flagged). Failures
  name the rule, file and ID.
- **Testability:** unit tests use invented fixtures only.

## Acceptance Criteria

- [ ] AC-006-1: A fixture test dialogue with one registered `pre_freeze` turn has *all* of its
  examples non-primary, in every condition and both common sets (AC-04).
- [ ] AC-006-2: A registry row with a dev ID, an unknown ID, a bad enum or a malformed ID is
  rejected with a named error. A formula-leading cell is escaped on write.
- [ ] AC-006-3: `scan` fails, naming file and ID, when a fixture sheet holds an unregistered test
  dialogue. It passes when the dialogue is registered or the sheet holds only dev IDs. It fails on
  an unparseable CSV and on an `.xlsx` without a sibling items CSV.
- [ ] AC-006-4: `check` fails with a named rule for: a dialogue in two splits, a DIRECT test
  dialogue absent from `testListFile`, a train dialogue present in `valListFile`, and a donor from
  another split.
- [ ] AC-006-5: A fixture test dialogue whose user turns duplicate a train dialogue's is
  non-primary with `cross_split_duplicate_dialogue`, both below and above the 1% threshold. Above
  it, the summary has `needs_decision: true`. A single-user-turn collision is not flagged. A
  dev↔train duplicate is reported but changes nothing.
- [ ] AC-006-6: `dup_exact` is set for a test utterance that differs from a train utterance only in
  case, punctuation and whitespace, and not for one that differs in a word. It never changes
  `primary`.
- [ ] AC-006-7: An example whose donor is a registered dialogue stays primary and is counted in
  `donor_inspected`.
- [ ] AC-006-8: Running `register` and `audit` twice gives byte-identical files on different days.
  Changing one `pre_freeze` registry row or one byte of `items.jsonl` changes the content hash,
  and `--verify` fails.
- [ ] AC-006-9: Stage 1 and Stage 2 test scoring fail without the audit file, or when the audit is
  stale against `items.jsonl`, `dialogues.jsonl` or the `pre_freeze` registry rows. With a valid
  audit, reported denominators exclude non-primary examples. Each contrast has one
  primary-minus-`dup_exact` line, and mismatch contrasts also keep their uncrossed minus-cue-donor line.
- [ ] AC-006-10: The committed registry, audit file and summary, and the captured logs, contain no
  fixture utterance text (asserted by a test).
- [ ] AC-006-11: Smoke check (reported separately): on the real data, `check` and `scan` pass. The
  registry holds exactly 49 distinct `pre_freeze` test dialogues: 23 label-round, 24 more from
  fact-drift and 2 more from session transcripts (re-measured at the time the scan runs). The
  summary reports example-level exclusion, `dup_exact`, `donor_inspected` and `needs_decision`.
  The committed test audit regenerates byte-identically on Windows, and Sandy runs
  `audit --verify` once in WSL before the freeze. If the hashes differ, the build is fixed; the
  check is never loosened.
- [ ] AC-006-12: The full suite passes on native Windows Python 3.12. `docs/analysis_plan.md`, the
  roadmap and `specs/memory/decisions.md` record the exclusion, near-duplicate, phase and
  LLM-judge-sample (FR17) policies.
- [ ] AC-006-13: Given a fixture transcript holding a test ID, a dev ID and a secret-looking
  string, `scan --transcripts` reports only the test ID, in canonical form. Neither the secret nor
  any log text appears in its output, logs or written files.
- [ ] AC-006-14: Once a freeze date is set, a new `pre_freeze` row is refused, and a new
  `post_scoring` row is accepted, appears in the summary count and leaves `primary` and the
  audit's content hash unchanged.
- [ ] AC-006-15: `PMUL1762` and `PMUL1762.json` resolve to the same registered dialogue in every
  command.
- [ ] AC-006-16: `register` refuses a local source file whose SHA-256 differs from the source
  table, and keeps committed rows with a warning when the file is missing.

## Open Questions

- **Example-level counts.** Item counts are measured; example counts (genuine and mismatch sets)
  are filled in by the smoke check.

Resolved with Sandy on 2026-10-19:

- **Fact-drift dialogues (FR3):** exclude all 24 extra test dialogues with flagged rewrites
  (about 170 items), because the reviewed sample wasn't recorded. Rejected: excluding none, with
  the risk disclosed (the "untouched" claim would then need a caveat).
- **Session-log hits (FR6):** treat them the same conservative way (Sandy approved review fix R2).
- **Donors:** exclude inspected dialogues as targets only; keep them as donors and disclose the
  count. Rejected: redrawing 147 items' donors, which would need a new render/manifest version
  just before the freeze.
- **Near-duplicates:** flag `dup_exact` plus a sensitivity line. Rejected: exclusion from primary
  (it removes mostly short direct requests, which confounds level); a disclosed count only.
- **Other inspections:** none known beyond the label rounds. The registry is stated as complete to
  the researchers' knowledge plus the session-log scan, and `scan` guards against future sheets.

**Working rule from now on.** Claude sessions print no test-split dialogue IDs or text except
through this spec's tools. Every printed ID costs a dialogue at the transcript scan.

## References

- Constitution: [`specs/constitution.md`](../constitution.md) (leakage by group; inspected data
  never in untouched test; selection independent of model behavior; freeze before reporting;
  text-free committed files; stdlib only).
- Parent: [spec 001](../001-pragmatic-intent-study/spec.md) FR-06, AC-04, WP-04, WP-08, WP-10;
  [roadmap](../001-pragmatic-intent-study/roadmap.md); [analysis plan](../../docs/analysis_plan.md)
  "Exclusions and leakage".
- Related: [spec 004](../004-context-conditions/spec.md) (genuine/mismatch sets, test manifest,
  minus-cue-donor line); [spec 005](../005-scoring/spec.md) (Stage 2 scoring, `--allow-test`);
  [data sources](../../docs/data_sources.md) "Fact drift in rewrites".
- Measured 2026-10-19 on the real join: 1,000 test dialogues and 7,372 test items; label-round
  test dialogues 23 (176 items); fact-drift test dialogues 25, 24 of them new (170 items); session
  logs: 9 Claude Code transcripts, 2 new test dialogues (11 items); 13 Codex logs, none. 147 other
  test items use a label-round dialogue as donor. 1,154 test targets (15.7%) match train after
  lowercasing and stripping punctuation. The MultiWOZ list files are pinned in `data/sources.toml`.
