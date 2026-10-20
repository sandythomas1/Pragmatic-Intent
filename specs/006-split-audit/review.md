# Review: Spec 006

Verdict: NEEDS REVISION → **READY** after revision (2026-10-19)

**Resolution.** Sandy approved all nine fixes. They are applied to spec.md and plan.md: R1 →
FR4/FR11/FR12/FR14/FR17, AC-006-14; R2 → FR6, AC-006-13 (Codex logs were also scanned: none);
R3 → FR2/FR3, AC-006-8/16; R4 → FR5, AC-006-15; R5 → FR8, AC-006-5; R6 → FR12/FR15, AC-006-9/11;
R7 → FR15; R8 → FR1/FR10, AC-006-11 (exact counts); R9 → FR4 and the plan's source table. The
re-measured session-log hits are 2 dialogues (11 items). The second hit came from this session
printing list-file IDs, which is why the spec adds a working rule.

_Reviewed 2026-10-19 against `specs/constitution.md`, `spec.md` and `plan.md`. Before the review,
Sandy settled the fact-drift question (exclude all 24 dialogues). Three findings block; the rest
don't. Each finding gives a concrete failure and a fix._

## Findings

### R1. Post-freeze test inspection would break the freeze (blocking: correctness)

**What's wrong.** FR4 makes `scan` fail on *any* unregistered test dialogue in a human-facing
sheet, and FR13 makes scoring fail on a stale audit. Spec 001, though, *plans* human
inspection of test after scoring: the WP-10 error audit, and possibly the ~50 Stage 2 outputs
rated to validate an LLM judge (spec 001 v1.2).

**Failure.** On Nov 15, Sandy draws an error-audit sheet from test predictions. `scan` fails. The
fix that looks obvious is to register those dialogues. That changes the registry hash, so the
audit file goes stale and every test score is refused or, if regenerated, changes after the
freeze. The primary set would then depend on model errors, which breaks "selection is independent
of model behavior".

**Fix.** Give the registry a `phase` column (`pre_freeze` / `post_scoring`). Only `pre_freeze`
rows define `primary`. After the WP-08 freeze record exists, new rows must be `post_scoring`. They
are logged for disclosure and don't change the audit's primary set or its content hash. `scan`
reports post-scoring sheets, but only a `pre_freeze` gap fails it. Add an AC. Also state in the
spec that the LLM-judge calibration sample is drawn from **dev** unless Sandy decides otherwise.
If it isn't, it is a pre-freeze test inspection.

### R2. The inspection record misses Claude's own session output (blocking: completeness)

**What's wrong.** The spec treats "complete to the researchers' knowledge" as the end of
discovery. But Claude has no memory of what earlier sessions printed. Debugging and smoke checks
can surface test utterances (spec 005's 8 conflicting test examples, spec 004's donor and cue
work), and nothing records it.

**Evidence (measured 2026-10-19).** A read-only regex scan of this project's 9 local Claude Code
transcripts found 16 distinct test dialogue IDs. 15 are already in the planned registry. **1 is
not (6 test items).** The registry as specified would have missed it.

**Fix.** Add FR4b: a one-time, local-only `scan --transcripts <dir>` that matches dialogue IDs
against the test split and outputs **IDs and counts only**, never lines. The transcripts may hold
secrets or unrelated content, so nothing from them is written beyond IDs, and the command is never
run in CI. Hits are registered as `source = claude_session`, `reason = session_output_unverified`,
the same conservative rule Sandy chose for fact-drift. Sandy is asked once whether Codex or other
assistant session logs exist locally to scan the same way. Add AC-006-13 with a fixture
transcript that holds a test ID, a dev ID and a secret-looking string: only the test ID is
reported, and the secret never appears in output.

### R3. Derived rows aren't deterministic or pinned to what was inspected (blocking: correctness)

**What's wrong.** Two separate problems:
- FR1 requires a `date` per row, but derived rows have no stated date. If `register` stamps "today",
  the registry, and with it the audit hash, changes on every run, which breaks NFR determinism and
  AC-006-8.
- The `fact_drift_review` rows derive from `fact_drift.jsonl`, which is regenerated whenever
  `audit_fact_drift` runs. If its rules change, the flagged set changes. New dialogues would be
  registered as "inspected" (they weren't), and removed ones would fail FR2's never-delete rule.

**Failure.** A future rule tweak to the fact-drift audit silently moves the primary test set.

**Fix.** Keep a fixed source table in code: source code, inspection date, inspector, and for
local sources the **expected SHA-256** of the file as it was at inspection time. `register`
refuses a local source whose hash differs ("source changed since inspection; register manually
with a reason"). Dates come from this table, never from the clock.

### R4. Dialogue ID form isn't specified (non-blocking, fix in spec)

The sources disagree on the ID form. Committed level files, `items.jsonl` and the MultiWOZ list
files use `PMUL1762.json` (checked), but docs, transcripts and future sheets use bare `PMUL1762`.
If the forms aren't canonicalized, `scan` or `check` misses matches, for example by reporting a
listed dialogue as absent. **Fix:** define the canonical form (with `.json`, matching
`items.jsonl`) and one normalizer used at every boundary. Test both forms.

### R5. The cross-split duplicate rule is ambiguous above the threshold (non-blocking)

FR7 doesn't say whether duplicates are `primary` when the rate exceeds 1% and the summary says
"needs decision". It also doesn't say whether dev↔train duplicates count. Two engineers would
diverge. **Fix:** test dialogues duplicating train *or* dev are always non-primary. Dev↔train
duplicates are reported only. "Needs decision" is a freeze blocker recorded in the summary and
doesn't change membership. Also define the "user-turn sequence" (all user turns, `dup-v1`
normalized, in order) and require at least two user turns, so single-turn templated dialogues
don't collide.

### R6. The staleness check omits the registry and runs into cross-OS hashing (non-blocking)

- FR13 checks input hashes but not the registry's hash. If the registry is edited without
  regenerating the audit, scoring still passes. **Fix:** the loader compares the audit's recorded
  registry SHA-256 with the committed registry.
- Scoring on the lab 4090 or WSL compares `items.jsonl` hashes built on another OS. Spec 004's
  byte-reproduction was verified on Windows only. **Fix:** add to AC-006-11 that Sandy runs
  `audit --verify` once in WSL before the freeze. If the hashes differ, the gap is fixed in the
  build, not by loosening the check.

### R7. Sensitivity lines can multiply (non-blocking)

Mismatch contrasts already carry spec 004's minus-cue-donor line. FR13 adds minus-`dup_exact`. The
spec doesn't say whether they are crossed. **Fix:** each sensitivity is applied once on its own,
against primary, and they are never crossed. That gives at most three lines per mismatch contrast.

### R8. Testability gaps in ACs (non-blocking)

- AC-006-11 says "the 23 label-round test dialogues plus the fact-drift dialogues". It should state
  exact expected numbers (23 + 24 + transcript hits, distinct total) so the smoke check passes or
  fails, not "looks right".
- FR9 reports by rule level but doesn't name the rule version. **Fix:** `auto-v1` (the default),
  with auto-v2 as a second column if available.
- The plan's "fixed precedence order" for reasons isn't listed. **Fix:** `levels_round1` >
  `levels_round3` > `obsolete_round3_sheet` > `fact_drift_review` > `claude_session` > `manual`.
  All sources stay in the registry. Only the summary reason uses precedence.

### R9. The xlsx skip contradicts the plan's own risk mitigation (non-blocking)

The plan skips `.xlsx` "because each has a sibling `_items.csv`", but its Risks section says
unparseable files fail. A future xlsx-only sheet would be skipped silently. **Fix:** an xlsx with
no sibling `*_items.csv` of the same round prefix fails `scan`. Also note the renumbering trap: the
local `round2_items.csv` holds committed **round 3** data and the local `round3_items.csv` is the
obsolete sheet. The source table (R3) must name files explicitly and never derive round numbers
from filenames.

## Non-Issues Considered

- **MultiWOZ list files are pinned.** `data/sources.toml` pins `valListFile.txt` and
  `testListFile.txt` by size and SHA-256 inside the MultiWOZ 2.1 archive. The plan's corresponding
  risk is resolved. Keep the hashes in provenance anyway.
- **Example IDs line up with spec 004.** Stage 1 and Stage 2 key examples as `<item_id>:<variant>`,
  and Stage 2 inputs equal spec 004's genuine-set size (dev 11,394 per condition). Reusing 004's set
  builders is sound, and the planned assertion against the committed manifest catches drift.
- **turn_index = 0 items.** They are outside the genuine set and never scored, so the audit
  covering only the genuine set loses nothing.
- **Scope.** Scoring integration (FR13) belongs here: an exclusion list that scorers don't enforce
  is the status quo that failed. Fuzzy dups, donor re-pairing and IndirectRequests are correctly
  non-goals.
- **Constitution.** Stdlib only, text-free committed files, untrusted input validated at the
  boundary, determinism and provenance are all present. Conservative exclusion fits "inspected data
  never enters untouched test". No conflict found.
- **Alternatives.** These are real comparisons. The "column in 004's manifest" alternative was
  plausible, and rejecting it for freeze-object stability is the right call.
- **Security.** Formula escaping, ID regexes and no text in logs are specified. The one new surface
  is transcript reading (R2), covered by the IDs-only, local-only rule.
