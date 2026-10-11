# Decision Log

Append-only log of significant technical and methodological decisions across specs. Each entry
records what was decided, why, the alternatives considered, and which spec or task it came from.

<!-- New entries go at the top, most recent first -->

## 2026-10-11: Taxonomy rules and a per-version content hash (Spec 003 / T6)
Decision:
- `out_of_taxonomy` takes no slots, and its details go in local notes.
- Slot values may contain `=` but not `;`. Empty segments are ignored, and an empty value is an
  error that suggests `name=?`.
- `canonical_slots` sorts the pairs by name, for hashing.
- Each version gets a canonical content hash (`version_sha256`) covering stratum and the sorted
  required/optional slots per intent, excluding descriptions. Context rows will record it as
  `taxonomy_sha256` (T9, spec FR8 amended).
Why:
- "Append-only by version" stops deletion but not redefinition. Editing `ctx-tax-v0`'s required
  slots after labels exist would silently change what every earlier label means.
- Descriptions are excluded so that fixing a typo isn't treated as a redefinition.
- An `out_of_taxonomy` intent has no slot schema, so any slot on it is unverifiable.
Alternatives considered: trusting git history for in-place edits (invisible to `validate`);
hashing the raw CSV lines (sensitive to row order and typo fixes); allowing free-form slots on
`out_of_taxonomy` (can't be validated or scored).


## 2026-10-11: Sealed-pass machinery in its own module; the snapshot is the form key (Spec 003 / T3, T4)
Decision:
- Pass logic lives in `src/annotation/context_passes.py`. `context.py` is CLI orchestration plus
  source reconstruction.
- The per-sheet snapshot (`<pass>_<A>_sheet_info.json`) is also the form pass's row-ID → item key,
  and it stores each item's prior hash. Export refuses a row whose prior row changed after the sheet
  was built.
- Form utterances are shown whitespace-collapsed.
- `sheet` refuses to overwrite a sheet with unexported items.
- Spec 002 gains a public `load_log`.
- `Dirs.literary_work_dir` is configurable.
Why:
- Keeping pass logic out of `context.py` stops that file from collecting every pass's logic by T12,
  and the machinery can be tested without argparse.
- A separate key file would duplicate the snapshot and could drift from it.
- Storing prior hashes per item proves which version of the prior row a label was made on.
- Literary targets span CRLF line breaks, so the sheet collapses whitespace for display.
- Overwriting an unexported sheet would destroy an annotator's work.
- With the literary work dir hard-coded, tests would have written into Sandy's real
  `data/interim/literary/screening_sheet.csv`. This was caught before any test ran.
Alternatives considered: everything in `context.py` (as plan.md first sketched); a separate
key CSV; showing raw text with line breaks; a `--force` overwrite flag (deleting the sheet is an
explicit, visible equivalent).
Limitation: a committed row edited by hand before its next-pass row exists has no successor hash
to catch it. Git history is the audit trail for that window.


## 2026-10-11: Registry and draw details (Spec 003 / T2)
Decision:
- A dialogue `target_sha256` hashes the turn text from `dialogues.jsonl` (original MultiWOZ),
  not DIRECT's `target_utterance`.
- `draw` refuses a batch that already holds drawn items.
- The draw ignores `mismatch_status`, unlike `levels.eligible_items`.
- The registry is written sorted by `item_id`.
- A literary `source_ref` is the source key, and `seed`/`pool_size`/`inputs_sha256` stay blank.
- Dialogue stems must start with an alphanumeric character.
Why:
- DIRECT stripped outer whitespace on 4,024 rows, and `validate` (T12) recomputes from
  `dialogues.jsonl`. Hashing a different string would fail every whitespace-stripped item.
- Re-running `draw` wouldn't be idempotent: the pool excludes registered dialogues, so a second
  run would quietly add 40 *different* dialogues.
- Donor availability is spec 004's concern (spec 001 AC-06), never a selection criterion.
- A sorted registry gives the stable order that the form-sheet shuffle starts from (AC-003-3).
- Strict field shapes keep the committed file text-free and free of formula prefixes.
Alternatives considered: hashing `items.jsonl` text (breaks validation for stripped rows); making
`draw` append and trusting the operator (silent over-sampling); an `--append` flag (YAGNI, since
a new batch name does the same job and is visible in the registry).


## 2026-10-11: Schema core choices (Spec 003 / T1)
Decision:
- `request_type` gains an `uncertain` value for `function = uncertain`. FR11 had left that case
  undefined.
- `canonical_hash` accepts **string values only**. Rows are hashed exactly as they're written to
  and read back from CSV.
- Annotator free text rejects Unicode categories Cc/Cf/Zl/Zp/Cs (controls, invisible format and
  bidi characters, line separators). It does not use `str.isprintable()`.
- Batch names also exclude Windows device names (`con`, `nul`, `com1`…).
Why:
- Without the `uncertain` type, an uncertain-presence item would be forced into `none` or
  `form_unknown`, which would silently move it into or out of the detection denominators.
- Coercing an int at export but hashing a string at validation would break the hash chain
  without any visible cause.
- `isprintable()` rejects non-breaking spaces, which Excel and pasted text often contain.
- A batch becomes a directory name on native Windows.
Alternatives considered: mapping uncertain to `none` (hides ambiguity); `str()`-coercing values
before hashing (silent mismatches); reusing spec 002's `_single_line` (false rejections of NBSP).


## 2026-10-11: Contextual annotation uses sealed passes and request precedence (Spec 003 review)
Decision: labels are collected in three sealed passes per annotator: form (target only), context
(prior segments only) and reveal (later evidence). Each sheet is built per item from the previous
pass's committed export, and rows are hash-chained.
- `function = request` whenever a turn contains any request of the addressee, including
  proposals of joint action. Otherwise decline > inform > social > other.
- Unstated required slots are `name=?`, never invented.
- Evidence is recorded as `seg-v1` sentence/turn indices.
- Mistakes are fixed with a logged `correct` command that supersedes and never rewrites.
Why: the order of evidence exposure is the validity threat in a solo-rater pilot, so the tool
enforces it rather than relying on discipline. Precedence removes disagreement that comes from a
missing rule rather than real ambiguity. `?` slots stop gold from containing invented inference.
Alternatives considered: one sheet with hidden columns (a spreadsheet can't enforce hiding);
multi-select function (messier agreement); exact-span evidence (slower); immutable labels with
no correction path (invites hand-edits that break the chain).


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
