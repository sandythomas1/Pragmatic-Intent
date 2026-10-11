# Plan 003: Contextual annotation supplement and dialogue pilot draw

## Approach

Add one stdlib CLI, `python -m src.annotation.context`, with these subcommands:

- `draw`, `register-literary`, `sheet`, `export`, `correct`, `validate`, `coverage`;
- `taxonomy-check`, which only validates the taxonomy file.

It follows the same shape as `src.annotation.levels` (sample → sheet → export) and
`src.literary.screening` (untrusted sheet → validated, text-free committed log). The new idea is
**sealed passes**:

- Each pass's sheet is generated, item by item, from the committed export of the previous pass.
- Every exported row stores `prior_sha256`, the canonical hash of the row it was built on.
- So the order "form before context before reveal" is enforced by the tool, and can be checked
  afterwards from committed files alone. It doesn't depend on annotator discipline.

Eligibility is decided per item and captured in a `sheet_info.json` snapshot when the sheet is
built. Literary items registered late therefore never block dialogue work.

All text shown to annotators is reconstructed at sheet-build time from sources:

- dialogue: `data/interim/direct/dialogues.jsonl`, which is original MultiWOZ text and the same
  join the Stage 1 code uses;
- literary: the pinned raw editions, through `src.literary.sources` and the offsets in
  `literary_screening.csv`.

Committed files hold IDs, enums, slot names, `?` flags and hashes. Free text goes to a
git-ignored JSONL keyed by item, with its hash committed and a Google Drive backup.

The function pass and the interpretation pass from spec 001 §7 share one sheet, called the
**context pass**. Both are judged under the same information state (prior context only), so
splitting them adds a sheet without adding any blinding. The blinding boundaries that matter are
these two:

- target only → prior context (form vs. function);
- prior → future (gold vs. future dependence).

Each of them gets its own sealed pass.

**Prior segments (`seg-v1`)** are the one shared view of prior context.

- Dialogue segments are turns `0..t-1`. That's the same window as the `full` condition in
  `direct_dataset.py`.
- Literary segments are sentences of the episode's `narrative`/`verse` units, clipped at
  `target_start`. They never cross a unit, and they never include `title` or `moral`.
- Evidence is recorded as segment indices. Spec 004 can map them onto its model windows to flag
  cues that fall outside a truncated context.
- These views are for annotators only. Spec 004 owns model rendering.

**Corrections never rewrite history.**

- `correct` marks the original row `superseded` and appends the fixed row.
- `context_corrections.csv` logs both hashes, the reason, and whether later evidence had already
  been seen.
- `validate` accepts a later-pass row built on a superseded row and reports it in coverage.

## Architecture

```
src/annotation/
  context_schema.py   enums, regexes, canonical hashing, cross-field rules, derived fields (pure)
  context_items.py    dialogue draw, literary registration, registry load/validate
  context_views.py    seg-v1 prior segments, target and continuation per stratum (pure)
  context_passes.py   snapshots, per-item eligibility, sheets, sheet parsing, immutable export (T4)
  context.py          CLI orchestration, source reconstruction (target texts), file wiring
data/annotations/     context_items.csv, intent_taxonomy.csv, context_{form,context,reveal}_<A>.csv,
                      context_corrections.csv
data/interim/context/ <batch>/<pass>_<A>.csv + sheet_info.json, form key,
                      <pass>_<A>_text.jsonl free text   (git-ignored; backed up to Google Drive)
docs/context_supplement.md   ctx-v0 rubric: function precedence, intents, slots/?, confidence,
                             depth, reveal; correction and backup procedure
```

Data flow:

```
items.jsonl ─draw─┐
screening.csv ─register-literary─┴→ context_items.csv
   └→ sheet form    (opaque row IDs) → [A edits] → export form    → context_form_A.csv
   └→ sheet context (sealed-form items) → [A edits] → export context → context_context_A.csv + text.jsonl
   └→ sheet reveal  (sealed-context items) → [A edits] → export reveal  → context_reveal_A.csv
   correct: supersede + append + context_corrections.csv
validate: recompute hashes + rules over all of the above; coverage: counts per annotator
```

Reuse rather than duplicate:

- spec 002's `escape_cell`/`unescape_cell` and the annotator regex. These move into a small
  shared `src/annotation/sheets.py` only if both modules need them. Otherwise they are imported
  from `screening`.
- `levels.labeled_turns` for the round exclusion. It is extended to return dialogue IDs.
- `literary.sources` for units and offsets.

## Alternatives Considered

- **Extend `levels_round*.csv` with new columns.** Rejected. It would mix wording-only historical
  labels with context labels in one row and invite silent remapping. Rubric v2 data must stay
  untouched (NFR-06).
- **One sheet with all passes and hidden columns.** Rejected. A spreadsheet can't enforce hiding,
  and the annotator would see context while judging form. Sealed, separate sheets make blinding
  something the tool checks.
- **Separate function and interpretation sheets** (spec 001's passes 2 and 3 taken literally).
  Rejected. Both use the same evidence, so the split costs an extra round trip and enforces no
  boundary.
- **Whole-batch gating.** Rejected in review (R3). Literary items registered late would block
  every dialogue item's next pass. Per-item eligibility with snapshots replaces it.
- **Evidence as unit IDs.** Rejected in review (R1). Aesop units are whole paragraphs, so
  evidence earlier in the target's own paragraph couldn't be cited. **Exact-span evidence**
  (copy the words, as in spec 002) was the precise alternative. Sandy chose sentence segments
  because they're faster.
- **Multi-select function.** This would allow `request;inform` together. Rejected by Sandy
  (2026-10-11) in favor of request-precedence, which keeps agreement nominal.
- **Stratified dialogue draw** (by user act, to boost hints). Rejected. It conditions selection on
  annotation-adjacent metadata, and it biases the coverage estimate that D-04 needs. Uniform
  one-turn-per-dialogue sampling makes the 40 items 40 independent groups.
- **Committing paraphrases.** Rejected per Sandy (2026-10-11) and the constitution. They often copy
  slot values and source wording. Instead, the hash is committed, the text is backed up on Drive,
  and the release is decided under FR-14.
- **Immutable labels with no correction path.** Rejected by Sandy (2026-10-11). It would invite
  hand-editing committed CSVs, which breaks the hash chain silently.

## Tradeoffs

- **Logged corrections, not silent edits.** Mistakes can be fixed, at the cost of a corrections
  log and a validator that accepts superseded rows in the hash chain. A correction made after
  seeing later evidence is allowed but flagged (`later_passes_sealed`). Agreement analysis can
  still use the first judgment.
- **Sentence segments for evidence** are fast and deterministic, but coarse for KJV's long
  "And… and…" verses. That's acceptable for a pilot of about 20 literary items. Revisit if spec
  004 needs finer cue visibility.
- **Request-precedence single label.** A mixed inform+request turn becomes `request`. That
  loses the "also informs" detail, which matters only for secondary slices.
- **Annotation view ≥ model view.**
  - Annotators see all prior context, while spec 004's `full` window (D-06) may be shorter. Gold
    can then rest on evidence a model never sees.
  - Evidence indices make this detectable as `cue_outside_window` in spec 004, rather than it
    silently counting as model error.
- **One turn per dialogue** gives the most independent groups, but no estimate of correlation
  within a dialogue. The test design (about 3–5 turns per group) will need that, and it is
  borrowed from literature or estimated from round 2.
- **A solo rater with sealed passes** still lets A1 *remember* context across batches. Sealing
  guarantees order, not ignorance.
- **Literary form labels aren't blind for Sandy** (the screener). Sandy chose to flag them
  `prior_exposure` and disclose this, rather than delay the pilot. Blind A2 labels can be added
  later.
- **Taxonomy v0 is drafted before the pilot.** This risks anchoring the categories the pilot is
  supposed to discover. `out_of_taxonomy` plus local notes is the escape valve, and coverage
  shows how often it fires.

## Risks

- **The pilot yields almost no L3 or no non-requests.** That is an informative result for D-04,
  not a failure. Coverage shows it. No items are added by hand to fill cells.
- **Too few literary includes.** Raise it before Oct 19. More families can be drawn with the
  spec 002 tooling, without code changes.
- **Excel mangles CSVs** (encoding, `L0` → formula, leading zeros in `t06`). Use the same UTF-8
  BOM and escaping as spec 002, and IDs that don't start with digits. Export rejects malformed
  rows loudly.
- **Loss of local free text**, which is the only copy of the slot-value and paraphrase gold.
  Back it up to Google Drive after each export. `validate` detects missing or altered files
  through `text_sha256`.
- **Item ID changes if `dialogues.jsonl` is rebuilt.** `target_sha256` is checked in `validate`,
  and a rebuild that changes text fails validation instead of drifting silently.
- **Hash serialization drifts between versions.** A test pins a known hash value (AC-003-10).
- **Scope creep into adjudication.** The schema reserves `context_final.csv`. Tooling waits for
  D-02 and its own spec.
