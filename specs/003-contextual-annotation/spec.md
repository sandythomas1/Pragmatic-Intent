# Spec 003: Contextual annotation supplement and dialogue pilot draw

Status: Implemented (T1–T13 done 2026-10-11; see [tasks.md](tasks.md)). The T7 taxonomy and
rubric content awaits Sandy's approval before the real context sheet. Reviewed: READY after
revision (Claude adversarial review 2026-10-11; R1–R14 applied with Sandy's decisions, see
[review.md](review.md)).

Parent: [spec 001](../001-pragmatic-intent-study/spec.md) WP-02b, WP-03, FR-03, FR-04, FR-05 (record
side only). Acceptance scenarios AC-02, AC-03, AC-11. Builds on [spec 002](../002-literary-sources/spec.md).

## Problem

Spec 001 separates three judgments that the current tooling can't store:

- wording-only form;
- what the speaker does in original context (function and request presence);
- what the speaker wants (intent, slots, paraphrase).

Rubric v2 and `levels_round*.csv` capture form only, so a wording-only INF turn that works as a
request in context has nowhere to go (AC-03). Nothing stops an annotator from seeing context, or
the story's ending, before a judgment meant to be made without it. The dialogue half of the
≈60-candidate dev pilot hasn't been drawn either. With no pilot labels, D-03 (taxonomy) and D-04
(test size and power) can't be decided in the Oct 19–25 window.

## Goals

- Draw a seeded, model-independent pilot of 40 original MultiWOZ dev turns: 40 dialogues, one
  turn each.
- Register dialogue pilot turns and screened-in literary candidates as one committed, text-free
  item registry with group and split provenance.
- Collect labels in three **sealed passes**:
  - form: the target only;
  - context: prior context only;
  - reveal: later evidence.

  The tool builds a pass's sheet for an item only after the annotator's previous pass for that
  item is exported. So no first judgment is made after seeing more evidence.
- Store per-annotator initial labels that are rater-agnostic (A1 Sandy, A2 professor, later
  raters). Committed files carry IDs, enums and hashes only. Corrections are logged, never silent.
- Validate the whole supplement from the raw sources and committed files. Report pilot coverage
  for D-03 and D-04.

## Non-Goals

- Adjudication tooling and final gold. The schema reserves `context_final.csv`, and adjudication
  follows D-02. Rubric v2 and historical `levels_round*.csv` are untouched and never remapped.
- Independent none/one/full condition judgments (spec 001 annotation pass 4). They need D-02 and
  counterbalanced raters, so they belong in a later spec.
- Test-group collection and the split-leakage audit (WP-04). That needs its own spec by Oct 26.
- Model input rendering, and cue-outside-window flags (spec 004). Scorers, slot-value
  normalization and contextual adapters (spec 005).
- Deciding the taxonomy (D-03). This spec ships a *provisional* v0 and the mechanism to version
  it. Sandy approves its content, and the professor optionally.
- Selecting, stratifying or reweighting pilot items by level, intent, user act or any model output.
- DIRECT rewrites. Only original MultiWOZ `target_utterance` turns are drawn.

## Requirements

### Functional

1. **FR1 Dialogue pilot draw.** `draw --count 40 --seed K --batch pilot1` first samples dialogues
   uniformly, without replacement, from the **dev** pool. It then picks one user turn with
   `turn_index > 0` uniformly within each dialogue.
   - The pool excludes:
     - dialogues containing any turn in `levels_round*.csv`, which removes round 2's 10 dev
       dialogues;
     - dialogues already in the registry;
     - dialogues with no user turn at `t > 0`.
   - Social-only turns stay eligible as authentic negatives.
   - The draw records seed, pool size and the `items.jsonl` SHA-256. The same inputs give the
     same turns.
2. **FR2 Item registry.** Committed `data/annotations/context_items.csv` has these columns:
   `item_id, stratum, batch, split, group_id, source_ref, target_sha256, draw, seed, pool_size,
   inputs_sha256, registered_on, protocol_version`.
   - Dialogue items:
     - `item_id = d:<dialogue stem>:t<NN>`, where the stem has no `.json`, e.g.
       `d:PMUL1234:t06`;
     - `group_id` = the dialogue stem;
     - `source_ref` = `<dialogue_id>#<turn_index>`.
   - `register-literary --batch pilot1` adds every `include` row of `literary_screening.csv` once.
     For these, `item_id = candidate_id`, `group_id` = family, `source_ref` = the source key
     (e.g. `aesop_jones1912`), `draw = screened`, and `seed`, `pool_size` and `inputs_sha256` are blank.
   - Rejected: a duplicate item; a group that spans splits; any split other than `dev`.
   - `batch` matches `^[a-z][a-z0-9_-]{0,31}$`, checked both at the CLI and on load.
3. **FR3 Taxonomy file.** Committed `data/annotations/intent_taxonomy.csv` has columns
   `taxonomy_version, intent_id, stratum (dialogue|literary|both), required_slots, optional_slots,
   description`.
   - IDs and slot names match `^[a-z][a-z0-9_]{0,39}$`.
   - `out_of_taxonomy` is reserved and always valid.
   - The file is **append-only by version**. A label validates against its own
     `taxonomy_version`, and deleting a version that a label references is an error.
   - Claude drafts `ctx-tax-v0`, and Sandy approves it before any context sheet is built.
   - v0 includes a `joint_action` intent for proposals and hortatives ("let us…"). Literary
     intents have no required slots in v0.
4. **FR4 Prior segments.** One versioned segmenter (`seg-v1`) defines the numbered prior context
   shown to annotators and used for evidence.
   - **Dialogue:** segment `i` = turn `i` for `0 ≤ i < t`.
   - **Literary:** the episode's `narrative`/`verse` units, in order, clipped at `target_start`.
     Each unit is split into sentences at `[.!?]`, plus any closing quote, plus whitespace.
     Segments never cross a unit boundary.
   - `title` and `moral` units are never segments.
   - Empty segments are dropped.
5. **FR5 Form pass (wording-only).** `sheet --pass form --batch B --annotator A` produces a sheet
   with columns `row_id, utterance, form, fragment, notes`.
   - `row_id` is opaque (`f-001…`), and the item mapping lives in a local key.
   - Rows are in seeded shuffled order.
   - No item ID, context, stratum, source or locator appears.
   - `form` takes the rubric v2 labels (`L0 L1 L2 L3 INF NR ?`), and `fragment` is `0|1`.
6. **FR6 Context pass (prior context only).** For each eligible item, the sheet shows its numbered
   prior segments and the target, never anything after the target. Eligible means that A's form
   row for the item is sealed. The annotator fills these columns:
   - `function` ∈ {`request`, `inform`, `decline`, `social`, `other`, `uncertain`}.
     **Precedence:** `request` if the turn contains any request of the addressee, including a
     proposal of joint action. Otherwise `decline` > `inform` > `social` > `other`. Use
     `uncertain` only when it can't be told whether a request is present.
   - `intent` and `alt_intent`, as taxonomy IDs or `out_of_taxonomy`.
   - `slots`: `name=value;…`, with the value in the source's own words, or `name=?` when the
     source leaves it unstated.
   - `paraphrase`.
   - `evidence`: segment indices, separated by `;`.
   - `confidence` ∈ {`certain`, `probable`, `uncertain`}.
   - `depth` ∈ {blank, `one_step`, `multi_step`, `uncertain`}, exploratory.
   - `notes`.

   Rules:
   - `request` requires `intent` and `paraphrase`.
   - A non-request (`inform`, `decline`, `social`, `other`) has blank `intent`, `alt_intent` and
     `slots`. `uncertain` may record a candidate intent (amended 2026-10-11 in T9).
   - Every required slot of `intent` is present, either with a value or as `?`.
   - Every slot name belongs to `intent`.
   - Evidence indices satisfy `0 ≤ i < n_segments`.
7. **FR7 Reveal pass (later evidence).** Eligible means that A's context row for the item is
   sealed. The sheet shows the continuation: the rest of the dialogue, or the rest of the episode
   including the moral. Beside it, for reference only, are the target and the annotator's own
   sealed context reading (amended 2026-10-11 in T10: the judgment is relative to that reading).
   The annotator records `future_dependence` ∈ {`none`, `corroborates`,
   `conflicts`, `required`} and `notes`. The sheet carries no earlier-pass columns, and export
   rejects any it finds.
8. **FR8 Sheet snapshots and export.**
   - Each `sheet` call writes `sheet_info.json` beside the sheet, recording:
     - pass, annotator, batch, seed, `seg-v1`, `built_at`;
     - the item IDs it covers;
     - registry and prior-pass file hashes.
   - Items registered later go into the next `sheet` call.
   - `export --pass P --batch B --annotator A [--rubric R]` requires **every row of that
     snapshot** to be labeled. Otherwise it aborts and lists the unlabeled rows.
   - It writes committed `data/annotations/context_<pass>_<A>.csv`. Each row carries:
     - `item_id` and the enum/ID fields;
     - `rubric_version` (form), or `taxonomy_version`, `taxonomy_sha256` and `segmenter_version`
       (context);
     - `prior_sha256` (FR10).
   - Free text (slot values, `paraphrase`, `notes`) goes to git-ignored
     `data/interim/context/<pass>_<A>_text.jsonl`. The committed row keeps slot names, a
     per-slot `?` flag, and `text_sha256`.
   - Export never changes an existing committed row. A changed label for an exported item is
     rejected with a pointer to `correct`.
9. **FR9 Corrections.** `correct --pass P --annotator A --item I --reason R` applies a fixed row
   from a one-row correction sheet. `R` ∈ {`typo`, `wrong_sheet`, `wrong_annotator`,
   `rubric_misread`, `other`}.
   - The original row stays in the pass file, marked `superseded`. The corrected row is appended.
   - Committed `context_corrections.csv` records `item_id, pass, annotator, old_sha256,
     new_sha256, reason, corrected_on, later_passes_sealed`.
     - `later_passes_sealed` is derived by the tool. It records whether the annotator had
       already seen later evidence for that item when correcting.
   - Later-pass rows built on the superseded row stay valid, and coverage reports them as
     `built_on_superseded`.
   - Agreement analyses can use first rows or corrected rows. Both stay recoverable.
10. **FR10 Canonical hashes.** A row hash is the SHA-256 of
    `json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))` encoded as
    UTF-8. Here `obj` is the committed row's fields minus `prior_sha256`, `text_sha256` and
    `status`.
    - A form row's `prior_sha256` = the hash of the item's registry row.
    - A context row's `prior_sha256` = the hash of the form row it was built on.
    - A reveal row's `prior_sha256` = the hash of the context row.
    - `text_sha256` covers `{item_id, pass, annotator, slots, paraphrase}`. It excludes `notes`.
11. **FR11 Derived fields.** The tool derives these and never asks for them:
    - `request_status`: `present` for request, `uncertain` for uncertain, else `absent`.
    - `request_type`: `direct` for request + L0; `indirect` for request + L1–L3;
      `form_unknown` for request + INF/NR/?; `uncertain` for uncertain status; `none` for absent.
    - `confirmatory_eligible = false` when `future_dependence = required`.
    - `needs_adjudication = true` when `future_dependence = conflicts`.

    The historical INF label is never mapped to absent (AC-03). Unknown form is never forced
    into L0–L3.
12. **FR12 Validation.** `validate` recomputes everything from `dialogues.jsonl`, the pinned
    literary editions, the committed CSVs and the local text files. It exits non-zero and lists
    every problem with its item and rule:
    - target hashes;
    - group and split consistency;
    - the registry against the screening log;
    - taxonomy integrity and versions;
    - enums and the cross-field rules in FR6;
    - evidence bounds;
    - the `prior_sha256` chain, accepting superseded rows recorded in corrections;
    - correction-log consistency;
    - duplicate or foreign IDs;
    - a missing local text file, or one whose hash doesn't match.
13. **FR13 Coverage.** `coverage --batch B` prints counts for every cell, including zeros, in
    these breakdowns:
    - stratum × function;
    - form (L0–L3, INF, NR, ?) × request type;
    - intent;
    - `?` slots per intent;
    - confidence;
    - future dependence;
    - `needs_adjudication`;
    - `prior_exposure`;
    - `built_on_superseded`.

    Counts are given per annotator and never pooled across raters.
14. **FR14 Exposure flag.** A literary item whose annotator is also its screener in
    `literary_screening.csv` is `prior_exposure = true` for **all three passes**, because the
    screener has read the target in context, ending included. This is a disclosed limitation,
    not an error. Blind literary form labels from A2 can be added later, and the tool compares
    them per annotator with no change.

### Non-Functional

- Security: sheets are human-edited, untrusted input.
  - Validate row and item IDs against the snapshot and registry, plus enums and regexes.
  - The annotator matches `^[A-Za-z][A-Za-z0-9_-]{0,15}$`, and batch matches FR2.
  - Slot values, `paraphrase` and `notes` are single-line and ≤500 characters.
  - Reuse spec 002's spreadsheet formula escaping (`= + - @` tab, CR).
  - Every path resolves under the configured directories, and tests cover `../`.
  - No network code. Corpus text is data: nothing in a sheet is executed or acted on.
- Data handling: committed CSVs hold no source text, slot values, paraphrases or notes.
  - Dialogue `source_ref` values and literary locators are bibliographic IDs only.
  - DIRECT rewrites never appear in any sheet.
  - Local free text is the only copy of slot-value and paraphrase gold. After each export, back up
    `data/interim/context/` to Sandy's Google Drive, as documented in the rubric doc.
    `validate` detects a lost or altered file.
- Determinism: the same inputs, seed and labels give byte-identical committed CSVs, apart from
  `registered_on`, `corrected_on` and `built_at`, which tests can inject.
- Observability: each command logs counts (pool, drawn, registered, eligible, labeled, missing,
  rejected, corrected). Errors name the item and the failed rule.
- Stdlib only, Python 3.12, following the patterns in `src/annotation/levels.py` and
  `src/literary/screening.py`.

## Acceptance Criteria

- AC-003-1: Drawing with the same seed and inputs twice gives identical items. No drawn dialogue
  is in any `levels_round*.csv`, every turn has `t > 0`, and every item is in `dev`. A count
  larger than the pool is rejected.
- AC-003-2: `register-literary` adds only `include` rows, is idempotent, and rejects a non-dev
  family. A batch of `../x` is rejected.
- AC-003-3: The form sheet has no item ID, context, stratum or source column. Its order equals
  `random.Random(seed)` shuffling of registry order, tested with a fixture of ≥5 items.
- AC-003-4: A context sheet includes only items with a sealed form row, and a reveal sheet only
  items with a sealed context row. Items registered after a snapshot appear in the next sheet
  without blocking the current export.
- AC-003-5: Prior segments never contain text after the target. A test plants a sentinel in the
  continuation and asserts it is absent. They never contain title or moral text. A literary
  target mid-paragraph gets the paragraph's earlier sentences as separate segments.
- AC-003-6: Export rejects each of these, naming the item:
  - `request` without `intent`;
  - a non-request with `intent`;
  - a missing required slot;
  - a slot not defined for the intent;
  - an evidence index ≥ `n_segments`;
  - an unknown intent or taxonomy version;
  - a snapshot row left unlabeled.

  `area=?` satisfies a required slot.
- AC-003-7: Re-exporting a changed label fails and points to `correct`. `correct` keeps the
  superseded row and logs old and new hashes, plus `later_passes_sealed` computed correctly in
  both the true and the false case. `validate` still passes afterwards.
- AC-003-8: Wording-only `INF` + context `request` derives `form_unknown` and `present`, never
  `absent` (AC-03). `required` derives `confirmatory_eligible = false`. `conflicts` derives
  `needs_adjudication = true`.
- AC-003-9: `validate` passes on a fresh export. Each of these edits makes it fail with a named
  rule:
  - a committed label;
  - a `prior_sha256`;
  - a registry `target_sha256`;
  - a group's split;
  - a local text file.
- AC-003-10: Hashes follow FR10 exactly. A test pins one known hash value, so any change in
  serialization fails.
- AC-003-11: Committed CSVs contain no fixture utterance, paraphrase, slot value or note text,
  and a test asserts this.
- AC-003-12: Coverage lists every form × function cell, including zeros, and keeps annotators
  separate. A screener-annotator's literary items are `prior_exposure` in every pass.
- AC-003-13: Smoke check (reported separately, not in CI): the real pilot draw against
  `data/interim/direct/` yields 40 dev dialogues outside round 2, and the registry validates.
- AC-003-14: The full suite passes on native Windows Python 3.12, using invented fixtures only.

## Open Questions

- **Taxonomy v0 and `ctx-v0` rubric content.** Claude drafts both: definitions, precedence, one
  invented example per value, and the correction and backup steps. Sandy approves them before
  the context pass.
- **Literary pilot size.** If screening yields far fewer than about 20 `include` rows, should
  more families be drawn with the spec 002 tooling before Oct 19? No code change is needed
  either way.
- **Professor's blind literary form labels** (R7, optional). Ask alongside D-02. They are added
  as A2 whenever available and never block the pilot.
