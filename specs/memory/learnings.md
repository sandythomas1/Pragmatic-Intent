# Learnings

Concepts, patterns and AI-native practices picked up while building this project. This is a
running curriculum, so review it periodically.

<!-- New entries go at the top, most recent first -->

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
