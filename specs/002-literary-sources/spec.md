# Spec 002: Literary source registration and screening inventory

Status: Reviewed, READY (Claude adversarial review 2026-10-10, R1–R5 applied). Open questions await Sandy.

Parent: [spec 001](../001-pragmatic-intent-study/spec.md) WP-02, FR-02, FR-03. Acceptance scenarios AC-01, AC-02.

## Problem

Spec 001 adds addressed literary exchanges (Aesop, and the John 2 water-to-wine exchange) as a
human-authored transfer stratum. Today nothing registers those editions, nothing locates an
utterance inside them reproducibly, and nothing records which candidates were screened in or
out and why. Without this, a literary item can't be reconstructed from a pinned source (AC-01).
A narrator's moral could slip in as a "request" (AC-02). And hand-picked examples would make
selection depend on what the researcher noticed, which violates the constitution's
selection-independence rule.

## Goals

- Pin the two candidate editions (Aesop, V. S. Vernon Jones 1912, PG #11339; King James Bible,
  PG #10) by URL, size and SHA-256 in the existing manifest/downloader.
- Segment each pinned text deterministically into located units: fables → title, narrative and
  moral paragraphs; Bible → book/chapter/verse. Every unit carries offsets into the pinned file.
- Assign literary *families* (split groups) to the dev pilot before anyone screens them, either
  by seeded random draw or by explicit, reasoned assignment.
- Propose screening candidates mechanically and exhaustively within each dev family. A human then
  screens each one (speaker, addressee, include/exclude and reason) in a spreadsheet.
- Export a committed, text-free screening log that reconstructs every target verbatim from the
  pinned source, and validate it.

## Non-Goals

- Contextual function, request presence, intent, slots, paraphrase, form level (spec 003).
- Rendering none/one/full/mismatched model inputs (spec 004).
- Drawing untouched *test* families (WP-04). The family tooling accepts `dev` only for now.
- Sources beyond the two pinned editions. Jokes and other works are added later via the same
  manifest and segmenter interface, with their own spec amendment.
- Any LLM-assisted discovery or filtering of candidates.
- The dialogue (MultiWOZ) half of the pilot. That draw is folded into spec 003.

## Requirements

### Functional

1. **FR1 Source pins.** `data/sources.toml` gains `aesop_jones1912` and `kjv_pg10`, with
   `www.gutenberg.org` added to `allowed_hosts`. `python -m src.data.download_sources --only
   aesop_jones1912 kjv_pg10` fetches and verifies both files.
2. **FR2 Segmentation.** `src/literary/sources.py` parses each pinned file into `Unit` records:
   `source`, `unit_id`, `episode_id`, `kind` (`title`/`narrative`/`moral`/`verse`), human
   `locator`, and `start`/`end` code-point offsets into the file decoded as UTF-8 *without*
   newline translation. `text[start:end]` is the unit's exact text, with surrounding whitespace
   trimmed. Before parsing, the loader verifies the file's SHA-256 against the manifest.
   - Aesop: the fable region runs from the last standalone `ÆSOP'S FABLES` heading to the trailing
     `ILLUSTRATIONS` heading. A title is an all-caps line preceded by ≥3 blank lines and followed
     by a blank line. A paragraph whose lines are all indented is a `moral`. Episode = fable,
     with ID `aesop:<title-slug>`. Duplicate titles are a parse error.
   - KJV: book headings are matched in table-of-contents order, so alias headings such as
     "Otherwise Called: The First Book of the Kings" are ignored. A verse starts at `C:V `
     (at line start or after whitespace) and runs to the next verse marker or structural heading.
     Episode = chapter, with ID `kjv:<book>:<chapter>` (66 fixed book slugs). Within a book,
     verse numbers must be strictly sequential (next verse, or next chapter at verse 1).
     Otherwise it's a parse error.
3. **FR3 Families.** Committed `data/annotations/literary_families.csv` maps
   `family_id` → `source`, the `episode_ids` it groups, `split`, `assignment`
   (`drawn`/`assigned`), `seed`, `reason`, `assigned_on` and `protocol_version`.
   - `families draw --source S --count N --seed K` samples N episodes of S uniformly and
     deterministically, and records each as its own dev family. The pool is the episodes that are
     not yet assigned and have ≥1 mechanical proposal (FR4). The pool size is recorded (review R3).
   - `families assign --source S --family-id F --episodes E1 [E2…] --reason TEXT` records an
     explicit dev family, used for meeting candidates and multi-chapter/parallel accounts.
   - An episode belongs to at most one family. Unknown episodes and non-dev splits are rejected.
4. **FR4 Proposal.** `propose` enumerates candidates in every dev family not yet proposed.
   It writes them to the local sheet `data/interim/literary/screening_sheet.csv` and a
   machine-owned sidecar `proposals.jsonl`. It appends only, never overwriting human edits.
   - Aesop: every double-quoted span in `narrative` units. Interrupted speech (a quote ending in
     a comma, then a ≤80-character tag with no `"` or `.!?`, then another quote) merges into one
     candidate. An unclosed quote runs to the end of its paragraph and is flagged.
   - KJV: every verse containing a speech verb (`saith|said|say|saying|spake|spoken|answered|
     asked|cried|besought|commanded|told|prayed`). The whole verse is proposed and flagged
     `needs_trim` (review R4).
   - Candidate IDs are stable: `lit-` + the first 10 hex characters of
     SHA-256(`source:start:end` of the proposal).
5. **FR5 Screening sheet.** The sheet columns are `candidate_id, family_id, locator, flags,
   unit_text, target_text, speaker, addressee, status, exclusion_reason, notes`.
   `target_text` is pre-filled with the proposal. The screener may shorten it or extend it
   across adjacent units in the same episode. `status` ∈ {blank/pending, include, exclude}.
   **`include` means eligible**: an addressed exchange with source-grounded prior context, carried
   into annotation *whether or not it is a request*. Request/function is judged in spec 003, not
   here (review R1). **Manual additions** (review R2): a row with a blank `candidate_id`, a dev
   `family_id` and a `target_text` adds an utterance the proposers missed.
   `exclusion_reason` ∈ {`no_addressed_speech`, `no_context`, `uncertain_reading`,
   `out_of_scope`, `duplicate_story`, `rights_pending`, `future_evidence_dependence`,
   `narrator_moral`}.
6. **FR6 Export.** `export --screener ID` resolves each row's `target_text` to offsets. Matching
   ignores whitespace differences, and the text must occur exactly once in the episode.
   The command writes committed `data/annotations/literary_screening.csv`: `candidate_id, source,
   family_id, episode_id, split, locator, target_start, target_end, target_sha256,
   source_sha256, origin, speaker, addressee, status, exclusion_reason, screener, protocol_version`.
   `origin` ∈ {`proposed`, `manual`}. Manual rows get IDs from their resolved span with the same
   hash rule. Every proposed candidate appears, including pending ones. No source text or notes
   appear. Rows are sorted by source, then episode order, then `target_start` (review R5).
7. **FR7 Validation.** `validate` recomputes everything from the pinned raw files and committed
   CSVs. It exits non-zero and lists every problem found. Rules: source hash matches the manifest;
   offsets fall within their episode; target hash matches; family and split are consistent;
   candidate IDs are unique; enums are valid; `include` has speaker and addressee; `exclude` has
   a reason. An included target overlapping a `title`/`moral` unit is an error (AC-02).

### Non-Functional

- Security: the sheet is human-edited, untrusted input. Validate IDs against the sidecar,
  enums, field lengths (speaker/addressee ≤60 printable characters, no newlines) and offsets.
  Spreadsheet cells that start with `= + - @` are written with a leading `'` and read back
  without it, so source text can't run as an Excel formula. Paths are resolved only under the
  configured directories. No new network code: downloads reuse the existing allowlisted, pinned
  downloader.
- Data handling: committed CSVs contain IDs, offsets, hashes, short role names and enums only.
  Source text stays in git-ignored `data/raw/` and `data/interim/`.
- Determinism: the same pinned files, seed and sheet give byte-identical committed CSVs, apart
  from `assigned_on`, which is injectable for tests.
- Performance: segmenting the 4.4 MB KJV file takes a few seconds or less on a laptop. No
  caching layer.
- Observability: each command logs counts (units, families, proposed, included/excluded/pending).
  Errors name the candidate ID and the rule that failed.
- Stdlib only (Python 3.12), consistent with `src/data` and `src/annotation`.

## Acceptance Criteria

- AC-002-1: With both raw files present, `download_sources --verify-only --only aesop_jones1912
  kjv_pg10` passes. Corrupting one byte makes the segmenter refuse to parse.
- AC-002-2: Segmenting the pinned Aesop file yields 284 fables. Segmenting the pinned KJV file
  yields 66 books in canonical order with sequential verses. `text[start:end]` of "John 2:3"
  begins "And when they wanted wine". (Smoke check against real files.)
- AC-002-3: Unit tests on invented Gutenberg-format fixtures cover title/narrative/moral
  classification, KJV alias headings, mid-line verse markers, and parse errors for duplicate
  titles and non-sequential verses.
- AC-002-4: `families draw` with the same seed and pool gives the same episodes. It never
  returns an already-assigned episode, and it rejects a count larger than the remaining pool.
- AC-002-5: `propose` run twice adds no duplicate rows and preserves a screener's edits. An
  interrupted quote (`"Oh, but," said the Bat, "I'm a mouse."`) is one candidate.
- AC-002-5b: A manual row in a dev family exports with `origin=manual` and a span-derived ID.
  A manual row in an unassigned family, or one duplicating an existing span, is rejected.
- AC-002-6: Export rejects an unknown candidate ID, an invalid enum, `include` without an
  addressee, `exclude` without a reason, and `target_text` that occurs zero or several times.
  Each error names the candidate.
- AC-002-7: An included target inside a `moral` unit fails validation. The same target excluded
  as `narrator_moral` passes (AC-02).
- AC-002-8: `validate` on a freshly exported log passes. Editing one committed offset or the
  family split makes it fail with a named rule (AC-01).
- AC-002-9: The committed CSVs contain no unit or target text. Locators and episode IDs may carry
  bibliographic identifiers (fable titles, book/verse references), but never utterance or
  narrative text. A test asserts that no fixture sentence appears in exported files.
- AC-002-10: The full test suite passes on native Windows Python 3.12.

## Open Questions

- ~~John 2 in the dev pilot~~ **Resolved 2026-10-10:** Sandy confirmed. `kjv:cana-wedding` is an
  assigned dev family, so John 2 can never be a test item.
- Gutenberg occasionally regenerates files. A changed upstream hash means re-pinning, and all
  committed offsets for that source would need a migration. Default: keep the pinned local copy
  (back up `data/raw/`). A migration tool is out of scope until it's needed.
- The screener has read the whole fable, including its moral, before the later wording-only
  pass. With a solo rater this contamination is unavoidable. Spec 003 must record it as a limitation.
