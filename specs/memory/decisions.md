# Decision Log

Append-only log of significant technical and methodological decisions across specs. Each entry
records what was decided, why, the alternatives considered, and which spec or task it came from.

<!-- New entries go at the top, most recent first -->

## 2026-10-17: Round 2 adjudicated; "I need/want to leave" is L0 (Spec 001 / WP-01)
Decision: Sandy adjudicated all 30 round 2 rows under rubric v2. Q1 is reading (a): "I need / I want
to + travel verb" is an `L0` need/want statement, recorded as rubric rule R8, and R6's example is
replaced. 13 first labels were kept, 16 changed to the suggestion, and 1 (r2-23) was kept at `INF`
against the suggested `NR`. Round 1 and 3 gold is **not** re-adjudicated to match R8: its
"need to leave/arrive" items stay `L2`: the 3 known `auto-v1` misses (r3-04 among them) and r3-24
(R6's old example, which `auto-v1` already labels `L2`).
Why: (a) follows the decision procedure, needs no new rule, and matches `auto-v1`. Editing round 3
gold toward the rules after their predictions are known would raise the reported 79% / κ 0.74 after
the fact. Adjudicated round 2 is the fresh check for `auto-v2`: per-item `auto-v1` errors on round 2
should not be read while writing `auto-v2`.
Alternatives considered: re-adjudicate round 3 to L0 and report both numbers (post hoc, toward the
rules); reading (b) `L2` (consistent with round 3, but needs a v3 rule that `auto-v1` breaks).

## 2026-10-14: D-06 context budget and separate genuine / mismatch sets (Spec 004)
Decision: every model sees inputs from one renderer, `render-v1` (`src/data/contexts.py`). Under
`full` and `mismatched`, context plus target is at most **350 whitespace tokens** (speaker tags
count), in training and evaluation alike. The oldest whole turns are dropped first; the target is
never cut. The budget is a renderer constant, not a run setting. Stage 1 scores none / one / full
on the *genuine* set (every turn with prior context) and the mismatch conditions on the *mismatch*
set (genuine turns with a donor). Donors that mention a target act value are disclosed, with one
sensitivity line per mismatch contrast. The test manifest (`data/manifests/contexts_test.csv`,
IDs and hashes only) is committed as the freeze object; dev is regenerated.
Why: D-06 asks for a common input budget. Without one, the encoder silently left-truncated at 512
subwords while an LLM would see the full history. 350 words truncates 104 of 11,195 test examples
(0.9%) and 71 dev examples (0.6%). The old "comparable" filter dropped 72 test examples (44 items)
without a donor from *every* condition, violating spec 001 AC-06.
Alternatives considered: no budget (models see different windows); an evaluation-only budget
(train and test inputs differ); a last-K-turns cap (long turns can still overflow the encoder);
removing cue donors (shrinks the control); committing only manifest summaries (the freeze would
depend on regeneration). Pending: `src.stage1.length_check` on the chosen encoders, run by Sandy
in WSL before the freeze; if any input exceeds 512 subwords, the budget is lowered for all models
under `render-v2`.

## 2026-10-13: Option A, rule-assigned levels and MultiWOZ acts instead of new labeling (Spec 001 v1.2)
Decision: no new hand labeling. Directness levels come from the frozen wording rules `auto-v1`, a
transcription of rubric v2 (`src/data/auto_levels.py`). Intents come from MultiWOZ user acts,
mapped onto the proposal's categories by `cat-v1` (`src/data/intent_categories.py`). The test set
is DIRECT's test split. This is a scoped exception to the constitution's "human annotators decide
every label": rule levels are mechanical, versioned, validated against human labels, and never
called gold.
Why: Sandy does not want to keep labeling. The remaining plan needed about 200–280 turns through
three passes (roughly 10–13 hours). The rules were written from the rubric's text and its invented
examples only, frozen, then scored once: 31/39 (79%), κ = 0.74 on the adjudicated rounds 1 and 3,
above the plan's κ ≥ 0.6 bar for two humans. They give hundreds to thousands of test examples per
level, against the plan's 25–40.
Known rule errors on that check: answers with no detail labeled L3 where humans said INF (4), and
"I need to leave/arrive …" labeled L0 where humans said L2 (3). Rubric v2 is itself inconsistent
on the second case (R6's example vs. step 3). Fixes go in a new version (`auto-v2`) checked on
labels the rules have not been tuned on (adjudicated round 2), never by editing `auto-v1`.
Alternatives considered: (B) a form pass only on about 200 test turns (about an hour); keeps human
gold levels. (C) LLM-assigned levels checked against human labels; circular when LLMs are also
evaluated, and the constitution bars Claude as an annotator.

## 2026-10-12: Re-scope to the December class paper under the course professor (Spec 001 v1.1)
Decision:
- The research is conducted through Sandy's Machine & Deep Learning course professor. The
  original proposal is the governing design. "Professor" (P) in every spec means this professor.
- The only target is the December class paper, written as a computer-science paper. WDSI, the
  2027 timeline and the 2015–2025 hallucination review are removed. FR-13, FR-14, WP-12, AC-14
  and D-08 are withdrawn (IDs kept, so cross-references stay stable). FR-11 is ordinary related work.
- Screened literary exchanges become an optional add-on: reported separately, cut first. The spec
  002/003 literary tooling stays as built.
- IndirectRequests returns as a separate transfer test (new FR-15, AC-15), as in proposal week 2:
  Stage 1 recall and Stage 2 slot-value recovery under `none` context, with GPT-family models
  flagged. Nothing new is generated, and the main benchmark stays human-written.
Why: the course professor said not to change the plan or proposal, to add some of the newer data
methods, and to optimize for the December deadline. All four choices were Sandy's (2026-10-12).
Alternatives considered:
- Keeping the literary quota (20–40 test items, ≥10 families): rejected. It is the largest
  human-labour item that the proposal never promised.
- Dropping literary work entirely: rejected. The professor allowed adding the methods, and the
  tooling is already built.
- Keeping the no-synthetic rule: rejected. It removed a proposal deliverable, and IndirectRequests
  is an already-pinned, cheap way to test L2-style hints, which are rare in MultiWOZ.
- Restoring new LLM-assisted examples as well: rejected. It adds labeling work before December.

## 2026-10-11: `validate` names a rule per finding; `coverage` reads only validated data (Spec 003 / T12, T13)
Decision:
- `validate` is read-only and checks the whole workspace (every batch and annotator). Each
  finding names one of 13 rules (`registry`, `group-split`, `target-hash`, `screening-log`,
  `taxonomy`, `labels`, `evidence`, `prior-chain`, `corrections`, `row-hash`, `local-text`,
  `duplicate-id`, `foreign-id`) and its item, and one run lists all of them.
- A label edited after export is caught through the local text file. Each text record already
  carries its committed row's key, so an edited row matches no record (`row-hash`). An edited
  form label with a context row built on it also breaks `prior-chain`.
- `n_segments` and stratum are recomputed from the sources, closing the T9 note that a tampered
  local snapshot could slip an out-of-range evidence index or a wrong-stratum intent past export.
- Group/split consistency is checked against the sources (`items.jsonl` for dialogues, the
  spec 002 families file for literary items), not just within the registry.
- `coverage --batch B` runs `validate` first and refuses on any finding. It prints both
  form × function (AC-003-12) and form × request type (FR13), plus intents, slots
  (stated / `?` / absent), confidence, future dependence, `needs_adjudication`, `prior_exposure`
  and `built_on_superseded`. Every cell is printed, one section per annotator. Titles are ASCII so
  the report survives redirection on Windows code pages.
Why: one run that lists every named problem is what makes a weekly "validate, then back up"
habit cheap. Recomputing from sources is the only check a stale or edited local file can't pass.
Refusing coverage on bad data keeps D-03/D-04 decisions off corrupted counts.
Alternatives considered:
- Committing a per-row label digest so edits are caught without local text: rejected. The
  committed row already is the labels, so a digest beside it is edited just as easily. The local
  text record is the independent copy.
- Coverage on unvalidated data with a warning: rejected, because counts from a broken chain look
  just as plausible as real ones.
Known limits: an annotator who edits both the committed row and its text record consistently
is not caught (integrity against accidents, not adversaries). `built_on_superseded` can't see a
paraphrase-only context correction, because FR10's chain hash excludes `text_sha256` by design.
`later_passes_sealed` is checked only for contradiction (a later row built on the corrected
row), since the sheets that existed at the time aren't recorded.

## 2026-10-11: Corrections are two-step, and "seen later evidence" includes built sheets (Spec 003 / T11)
Decision:
- `correct --prepare` writes a one-row correction sheet (`correct_<pass>_<A>.csv`), prefilled with
  the live row's labels and its local free text. `correct --reason R` applies it. The snapshot
  records the corrected row's identity, so a row changed in between is refused.
- `later_passes_sealed` is true when a later pass has an exported row **or a built sheet** for
  that item and annotator.
- A corrected row's `prior_sha256` points at the *current* live prior row.
- The log stores FR10 chain hashes, so a correction that changes only slot values or a paraphrase
  logs `old_sha256 == new_sha256`. The text change shows in the row's `text_sha256` and in the
  separate text record kept for each version.
Why:
- One command with hidden state ("first run writes, second run applies") is easy to misuse.
- A built sheet has already shown the evidence, even before anything was exported.
Alternatives considered: correcting by editing a full pass sheet (invites multi-row edits);
logging a full-row hash that includes free text (departs from FR10, which chains on labels only).

## 2026-10-11: Context and reveal pass shapes (Spec 003 / T9, T10)
Decision:
- Context and reveal sheets also use opaque, shuffled row IDs (`c-`, `r-`). The snapshot keeps
  each item's stratum and `n_segments`.
- Committed context rows hold `slot_names` and `unstated_slots` (names only), `request_status`
  (it depends only on `function`), the taxonomy version and hash, and `segmenter_version`.
  `request_type` is not committed. It needs the form row too, so it is derived at analysis time
  and can't go stale after a form correction.
- Reveal rows commit the derived `confirmatory_eligible` and `needs_adjudication`, which depend
  only on the row's own value.
- `function = uncertain` may record a candidate intent. A `request` needs a paraphrase.
- The reveal sheet shows the target and the annotator's own sealed reading (display only) beside
  the continuation. This departs from FR7's literal "only the continuation".
- The context sheet defaults to the newest taxonomy version. Export refuses if that version was
  edited in place after the sheet was built.
- Local text records are keyed by `(item_id, row_sha256)`, and `merge_export` compares that
  full-row key. Without it, a re-export that changed only a paraphrase would pass as identical,
  because FR10 excludes `text_sha256`.
Why:
- Item IDs name a dialogue that can be looked up, so opaque IDs keep every pass blind.
- `future_dependence` is defined relative to the context reading. Making the annotator recall 60
  readings from memory adds noise, and the reading was sealed in the previous pass.
- A candidate intent under `uncertain` is the most useful input for adjudication.
Alternatives considered: item IDs on context sheets (lookup risk); committing `request_type`
(staleness); a blank reveal sheet with no reading (recall burden, no extra blinding).

## 2026-10-11: Draft taxonomy `ctx-tax-v0` (Spec 003 / T7)
Decision: 11 dialogue intents (`find_`/`book_` per MultiWOZ domain, plus `ask_attribute` with a
required `attribute`), 5 literary intents with no required slots, and `joint_action` for both
strata. Bookings require the slots needed to act (people/day/time, people/day/stay, people,
departure/destination). Searches require none. Slot names are lowercase readable versions of
MultiWOZ's `*-Inform`/`*-Request` names (`leave_at`, `arrive_by`, `train_id`).
Why: required slots mean "can't be executed without it", so `name=?` marks a genuinely missing
detail rather than an unconstrained search. There is no catch-all literary intent such as
`do_action`: `out_of_taxonomy` plus coverage shows what v0 misses, which is the evidence D-03 needs.
Alternatives considered: one intent per MultiWOZ act (too fine, tied to the corpus); a generic
literary `act` intent (would hide every gap).

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
