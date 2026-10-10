# Decision Log

Append-only log of significant technical and methodological decisions across specs. Each entry
records what was decided, why, the alternatives considered, and which spec or task it came from.

<!-- New entries go at the top, most recent first -->

## 2026-10-10: Literary locators are raw decoded offsets, and screeners copy words, not offsets (Spec 002 / T2, T5)
Decision: unit and target offsets index the pinned file decoded as UTF-8 with CRLF intact. Screeners
edit `target_text`, and export resolves it to offsets: whitespace-insensitive, word-bounded, and
required to be unique in the episode.
Why: raw offsets reproduce source bytes exactly, with no normalization contract. Copying words is
far less error-prone than typing offsets, and the uniqueness rule makes resolution unambiguous.
Alternatives considered: offsets into LF-normalized text (adds a hidden contract); screener-entered
offsets (error-prone); committing the public-domain text (breaks the single "committed files are
text-free" rule).

## 2026-10-10: Exhaustive mechanical proposals inside pre-assigned dev families (Spec 002 / T3, T4)
Decision: families are assigned to dev, by seeded draw or by explicit logged reason, before anyone
reads them. Every quoted span (Aesop) or speech-verb verse (KJV) in them is proposed. Missed
utterances are added as `origin=manual` rows, so they stay visible in the log.
Why: it keeps selection independent of models and of the researcher's attention (constitution).
Pre-assignment also stops a fable that was read during the pilot from leaking into test.
Alternatives considered: keyword or LLM pre-filtering (selection on difficulty, and circular);
hand-picking (invisible selection).

## 2026-10-10: Security review of spec 002 (Spec 002 / T1, T4, T5)
Decision: the review found no findings at or above the reporting bar. One low finding was fixed:
committed `family_id` values are now regex-validated on every load, and the sheet escapes
`family_id`/`locator` against spreadsheet formula injection.
Why: the families CSV is committed, so it is untrusted, and it flows into a sheet that is opened
in Excel.
Alternatives considered: escaping only, which would leave malformed IDs flowing into the committed log.

## 2026-10-10: Spec 001 is an umbrella; code work goes through child specs (Spec 001)
Decision: Spec 001 does not go through `/spec-review` → `/spec-decompose` → `/spec-implement`.
It stays the protocol source of truth, and `roadmap.md` tracks it. Each code-bearing work package
gets a small child spec (002+) that does run the full lifecycle. Human research work (adjudication,
screening, labeling, freezes, writing) is tracked as roadmap checklist items.
Why: about half of spec 001's 12 work packages are human judgments or writing, which unit tests
can't verify. The lifecycle is valuable where a silent bug would corrupt results: source
locators, rendering invariants and scorers.
Alternatives considered: (a) Full lifecycle on 001. Its review and decomposition would duplicate
§11/§14/§15, which already exist, and yield untestable "tasks" like "adjudicate round 2".
(b) No specs at all, following the roadmap ad hoc. That loses adversarial review on exactly the
components where validity bugs hide.
