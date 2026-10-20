# Learnings

Concepts, patterns and AI-native practices picked up while building this project. This is a
running curriculum, so review it periodically.

<!-- New entries go at the top, most recent first -->

## Measure spec baselines with the shipped matcher (from Spec 006)
A spec's expected count is only as good as the code that produced it. Spec 006 said "exactly 49"
inspected dialogues from an ad-hoc word-boundary regex. The tool's boundary-safe pattern found 51,
so a correct result read as a deviation. When a spec quotes a measured number that the
implementation will reproduce, either measure it with the function that will ship, or write the
criterion as "re-measured by the tool; any difference explained".

## Put validity gates at the first expensive step (from Spec 006)
A fail-closed check guards the output only if it runs before the cost. Spec 006's plan gated the
test *scorers*, but the expensive, irreversible step is training (GPU hours) and the Stage 2 export.
The audit check moved into the trainer's `prepare` and into `inputs`. When planning a gate, list
every entry point that consumes the guarded input, and place the check before the first one that
costs time or exposes data.

## Provenance flags must ignore the tool's own outputs (from Spec 006 retro)
A `git_dirty` check built on bare `git status --porcelain` counts the results log it is about to
append to. With the log tracked, every run after the first in a checkout reports dirty code, and
the flag stops meaning anything. Exclude the tool's own output paths from provenance checks, or
write outputs outside the worktree.

## 2026-10-19: An AI assistant's session logs are an inspection record (006)
- **Pattern choice changes the count.** A word-boundary regex (`\bMUL1234\b`) silently misses IDs
  embedded in compound keys (`MUL1234_t02`), because `_` is a word character. The session-log
  count moved from 2 to 4 hits with a boundary-safe pattern.
- **Check real data, not only fixtures.** Real sheets break assumptions that fixtures never test:
  one ragged row in a hand-made CSV, and another spec's key-file convention.
- **Audit the auditor's own leaks.** A real test ID typed into a unit-test fixture is itself an
  exposure. Every real-data command in this session piped its output through an ID mask, so the
  transcript gained no new test IDs. Use invented IDs (`PMUL9xxx`) in fixtures.
- **Choose what is hashed.** Leaving a timestamp out of a deterministic summary keeps `--verify`
  meaningful. Putting disclosure-only counts outside the content hash keeps post-scoring
  inspection from moving a frozen set.

## 2026-10-18: Sync the active branch before resuming spec work (004/005)
The local research branch was behind the user's actual branch, `feature/option-a-auto-levels`.
Fetch found the missing remote ref; the prior session's uncommitted closeout notes were stashed,
then switch/pull recovered the option-A decision and completed renderer. The historical form
pilot/taxonomy tasks were not revived. The renderer's Windows suite and manifest check now pass.

Keep weak-label validity separate from tooling correctness. V2 was frozen before round-2 scoring,
but its 29/30 agreement equals v1 and the check has no gold L3 rows. Fresh L3 precision is still
human work. Separate oracle inputs from the routed stream, or route misses erase their own oracle
denominator. Act references also contain a few conflicting slot values: flag interpretation
exclusions while keeping detection, rather than silently selecting one. Explicit invalid-output
records preserve denominators. A Windows regression test caught CRLF output; new scorer exports
use explicit LF. Full evidence: [verification](../005-scoring/verification.md).

## 2026-10-10: Check parsers against independent ground truth
The KJV segmenter's output (66 books, 1,189 chapters, 31,102 verses) matches the canonical counts
exactly. A smoke check against real files caught two bugs that invented fixtures missed: a verse
marker at the end of a line, and a `***` separator line leaking into Malachi 4:6. Fixtures prove
the rules; real data shows whether the rules are the right ones.

## 2026-10-10: Match process weight to what can be verified
A spec lifecycle earns its cost when acceptance criteria can be checked by tests. A research
protocol mixes testable components (parsers, renderers, scorers) with human judgments
(labels, adjudication, writing). Split them: child specs for the code, and a tracked checklist
for the judgments.
