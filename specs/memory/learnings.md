# Learnings

Concepts, patterns and AI-native practices picked up while building this project. This is a
running curriculum, so review it periodically.

<!-- New entries go at the top, most recent first -->

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
