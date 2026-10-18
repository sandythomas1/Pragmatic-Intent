# Tasks: Spec 003

Ordering puts Sandy's **form pass on the critical path**. T1–T5 deliver a real form sheet, which
needs no taxonomy or segmenter, so labeling can start around Oct 14. The context-pass work
(T6–T9) follows while Sandy labels form. Approval of taxonomy v0 and the rubric (T7) is the human
gate before the context sheet goes out.

Tests use the stdlib `unittest` and invented fixtures only. Run them with
`python -m unittest discover -s tests -t .` (native Windows Python 3.12).

## T1: Schema core — enums, canonical hashing, derived fields
- Description: Add `src/annotation/context_schema.py`, which holds only pure functions.
  - The enums are passes, strata, form labels (rubric v2), function, confidence, depth,
    `future_dependence` and correction reasons.
  - The ID regexes are annotator, batch, item ID, intent/slot names and opaque row IDs.
  - FR10 canonical row hashing: `canonical_hash(row, exclude=...)`.
  - FR11 derived fields: `request_status`, `request_type`, `confirmatory_eligible`,
    `needs_adjudication`.
  - Single-line, length-limited free-text checks (≤500 characters).
- Files likely touched: src/annotation/context_schema.py, tests/test_context_schema.py
- Depends on: none
- Security-sensitive: yes. These regexes and length checks are the input-validation boundary
  that every later task relies on, including the batch regex that guards paths.
- Acceptance criteria:
  - A pinned known-value hash test fails if key order, separators, `ensure_ascii` or the
    excluded fields change (AC-003-10).
  - The derivation table is fully covered. INF + request gives `form_unknown`/`present`, never
    `absent`. `required` gives `confirmatory_eligible=false`. `conflicts` gives
    `needs_adjudication=true` (AC-003-8).
  - Batch `../x`, `pilot1/..` and an empty value are rejected. An annotator with spaces or more
    than 16 characters is rejected. Free text with a newline or more than 500 characters is
    rejected.
- Status: done

## T2: Item registry and dialogue pilot draw
- Description: Add `src/annotation/context_items.py`.
  - Registry dataclass and CSV I/O for `context_items.csv` (FR2).
  - Registry load-time validation: duplicate IDs, a group spanning splits, non-dev rows, the
    batch regex, and a bad `item_id` form.
  - `draw_dialogues(items, labeled_dialogues, registry, count, seed)` implements FR1.
    - It draws dialogues uniformly, then one turn with `t > 0` uniformly within each.
    - It does **not** filter on `mismatch_status` (AC-06), unlike `levels.eligible_items`.
    - It records seed, pool size and the `items.jsonl` SHA-256.
  - Extend `levels` with `labeled_dialogues()`. It returns dialogue IDs from all rounds and
    reuses `labeled_turns`.
  - Add CLI `python -m src.annotation.context draw`. `src/annotation/context.py` starts here
    with Dirs/paths and argparse.
- Files likely touched: src/annotation/context_items.py, src/annotation/context.py,
  src/annotation/levels.py, tests/test_context_items.py, tests/test_annotation_levels.py
- Depends on: T1
- Security-sensitive: yes. It writes a committed file and builds paths from CLI arguments.
- Acceptance criteria:
  - The same seed and inputs give identical items. Drawn dialogues exclude every
    `levels_round*` dialogue and every already-registered dialogue. Every turn has `t > 0` and
    is in dev. A count larger than the pool is rejected and the pool size is reported (AC-003-1).
  - A dialogue whose only user turn is `t = 0` never enters the pool. A social-only turn can
    be drawn.
  - Registry round-trip is byte-identical with an injected `registered_on`. A duplicate item, a
    cross-split group or a `test` row fails loading with a named rule.
- Status: done

## T3: Literary registration
- Description: `register-literary --batch B`.
  - It reads the committed `literary_screening.csv` and `literary_families.csv`, and adds every
    `include` row once.
  - For each: `item_id` = `candidate_id`, `group_id` = family, `draw` = `screened`, and
    `target_sha256` taken from the log.
  - It is idempotent, and it rejects a non-dev family.
  - It reuses the `src.literary.screening` loaders rather than re-parsing.
- Files likely touched: src/annotation/context_items.py, src/annotation/context.py,
  tests/test_context_items.py
- Depends on: T2
- Security-sensitive: yes. It reads committed CSVs that a human edited, which are untrusted.
- Acceptance criteria:
  - Only `include` rows are registered. Running it twice adds nothing.
  - A screening row in a non-dev family is rejected. A batch of `../x` is rejected (AC-003-2).
  - `pending` and `exclude` rows never appear in the registry.
- Status: done

## T4: Sheet snapshots and the form pass (sheet + export)
- Description: This task builds the generic pass machinery in `context.py` and exercises it with
  the form pass.
  - **Snapshot:** `sheet_info.json` records pass, annotator, batch, seed, `built_at`, item IDs,
    and the registry and prior-file hashes.
  - **Per-item eligibility:** the item is in the batch, its prior pass is sealed for this
    annotator, and this pass isn't exported yet.
  - **Export immutability:** a changed exported row is rejected with a pointer to `correct`.
  - **Chaining:** `prior_sha256` is set on every exported row.
  - **Form sheet (FR5):** opaque `f-NNN` row IDs with a local key, seeded shuffle, and only the
    utterance shown. Excel escaping uses spec 002's `escape_cell`/`unescape_cell`.
  - **Form export:** rubric v2 labels, `fragment`, a `rubric_version` argument, and
    `prior_sha256` set to the registry-row hash.
  - **Utterance source:** dialogue text from `dialogues.jsonl`, literary text from the pinned
    edition and the log offsets.
- Files likely touched: src/annotation/context.py, tests/test_context_passes.py,
  tests/context_fixtures.py
- Depends on: T1, T3
- Security-sensitive: yes. It parses human-edited spreadsheets (untrusted), guards against
  formula injection and writes committed files.
- Acceptance criteria:
  - The form sheet has no item ID, context, stratum or source column. Row order equals
    `random.Random(seed)` shuffling of registry order, tested with 5 or more items (AC-003-3).
  - Export rejects an unknown or missing row ID and any unlabeled snapshot row, naming the
    row. A cell starting with `=` round-trips intact.
  - Re-export with a changed label fails and names `correct`. Export after new items are
    registered covers only the snapshot (AC-003-7 first half, AC-003-4 last clause).
  - The committed form CSV contains no fixture utterance text (AC-003-11, form part).
- Status: done

## T5: Real pilot draw, smoke check and form sheet hand-off  *(Sandy approves the draw)*
- Description:
  - Run the smoke check against the real `data/interim/direct/` (AC-003-13): 40 dev dialogues
    outside round 2.
  - **With Sandy's approval of the seed**, run the actual `pilot1` draw and build Sandy's form
    sheet.
  - Add CLI usage to `docs/source_collection_plan.md`.
  - Nothing is committed without Sandy's request.
- Files likely touched: docs/source_collection_plan.md, data/annotations/context_items.csv
  (generated), specs/001-pragmatic-intent-study/roadmap.md
- Depends on: T4
- Security-sensitive: no. It runs existing tooling, with no new input surface.
- Acceptance criteria:
  - The smoke check output reports pool size, 40 drawn items, 0 overlap with `levels_round*`
    dialogues, all dev, all `t > 0`.
  - `data/interim/context/pilot1/form_A1.csv` exists and is shared with Sandy.
- Status: done

## T6: Taxonomy mechanism
- Description:
  - Loader and validator for `intent_taxonomy.csv` (FR3).
    - Rows are append-only by version, with unique `(version, intent_id)`.
    - It validates ID and slot regexes and the stratum enum. The reserved `out_of_taxonomy`
      is always valid.
    - A label is checked against its own version's slots.
  - `taxonomy-check` CLI. It exits non-zero listing every problem.
  - A function that validates `slots` strings (`name=value;…` / `name=?`) against an intent's
    required and optional slots.
- Files likely touched: src/annotation/context_schema.py (or context_taxonomy.py),
  src/annotation/context.py, tests/test_context_taxonomy.py
- Depends on: T1
- Security-sensitive: yes. The committed taxonomy file is untrusted input that flows into
  sheets and validation.
- Acceptance criteria:
  - A duplicate intent within a version, a bad slot name or an unknown stratum each fail with
    a named rule.
  - Deleting a version that a fixture label references is reported (FR3).
  - `area=?` satisfies a required slot. A missing required slot, an undefined slot, a
    duplicate slot name or a malformed pair are each rejected (AC-003-6, slot part).
- Status: done

## T7: Draft taxonomy v0 and `ctx-v0` rubric  *(human gate: Sandy approves)*
- Description: Draft the two documents Sandy approves before the context pass.
  - **`ctx-tax-v0` taxonomy:**
    - MultiWOZ-grounded intents: `find_<domain>`, `book_<domain>`, `ask_attribute` with slots
      drawn from MultiWOZ `*-Inform`/`*-Request` slot names;
    - generic literary intents: `give`, `help`, `permit`, `stop`, `inform_me`, `joint_action`,
      with no required slots.
  - **`docs/context_supplement.md`:** definitions and function precedence, `?` slots, slot
    values in the source's own words, evidence segments, confidence, depth and reveal values.
    It gives one invented example per value, and covers the correction procedure, the Google
    Drive backup step and the `prior_exposure` disclosure.
  - Invented examples only. No DIRECT, MultiWOZ or literary text.
- Files likely touched: data/annotations/intent_taxonomy.csv, docs/context_supplement.md,
  docs/annotation_guidelines.md (pointer only)
- Depends on: T6
- Security-sensitive: no. It's documentation and a data file validated by T6.
- Acceptance criteria:
  - `taxonomy-check` passes on the draft.
  - The rubric covers every enum value in `context_schema.py`, and a test asserts each value
    is mentioned.
  - Sandy's approval is recorded in the roadmap before T9's sheet is built for real.
- Status: done (draft; Sandy approves the content before the real context sheet is built)

## T8: Prior segments and continuation views (`seg-v1`)
- Description: Add `src/annotation/context_views.py` (FR4), which holds only pure functions.
  - **Dialogue:** prior turns `0..t-1`, speaker-tagged, and the continuation `t+1..end`.
  - **Literary:**
    - prior = the episode's `narrative`/`verse` units, clipped at `target_start` and split
      into sentences at `[.!?]` plus an optional closing quote plus whitespace;
    - segments never cross a unit, empty segments are dropped, and `title`/`moral` are never
      segments;
    - continuation = from `target_end` to the episode end, including the moral, for the
      reveal pass only.
- Files likely touched: src/annotation/context_views.py, tests/test_context_views.py,
  tests/literary_fixtures.py
- Depends on: T1
- Security-sensitive: no. These are pure functions over already validated, hash-verified text.
- Acceptance criteria:
  - A sentinel planted after the target never appears in prior segments, in either stratum.
    Title and moral text never appear (AC-003-5).
  - A mid-paragraph literary target gets the paragraph's earlier sentences as separate
    segments. A closing quote stays with its sentence.
  - The dialogue prior at `t` equals `direct_dataset.build_context(..., "full")` text for the
    same item.
- Status: done

## T9: Context pass (sheet + export + local free text)
- Description: The context pass, built on T4's machinery (FR6, FR8).
  - **Sheet:** covers items with a sealed form row. It shows numbered prior segments and the
    target, plus the annotator columns.
  - **Export:** validates function precedence enums, the request/intent rules, slots (T6),
    evidence bounds against `n_segments`, `taxonomy_version` and `segmenter_version`.
  - **Free text:** slot values, `paraphrase` and `notes` go to
    `data/interim/context/context_<A>_text.jsonl`. The committed row keeps slot names, the
    `?` flags and `text_sha256`, which covers `{item_id, pass, annotator, slots, paraphrase}`.
  - **Chaining:** `prior_sha256` is the form row hash.
  - **Taxonomy freeze:** each row also records `taxonomy_sha256` (T6 `version_sha256`), so a version
    edited in place after use is detectable (added 2026-10-11 during T6).
- Files likely touched: src/annotation/context.py, tests/test_context_passes.py
- Depends on: T4, T6, T8
- Security-sensitive: yes. It parses untrusted free text and writes committed and local files.
- Acceptance criteria:
  - The context sheet includes only items with a sealed form row (AC-003-4).
  - Every AC-003-6 rejection fires, naming the item.
  - The committed CSV contains no paraphrase, slot value or note fixture text. The local file's
    hash equals `text_sha256` (AC-003-11).
- Status: done

## T10: Reveal pass (sheet + export)
- Description: The reveal pass (FR7).
  - **Sheet:** covers items with a sealed context row. It shows only the continuation, with
    `future_dependence` and `notes` columns.
  - **Export:** rejects any earlier-pass column.
  - **Chaining:** `prior_sha256` is the context row hash.
- Files likely touched: src/annotation/context.py, tests/test_context_passes.py
- Depends on: T9
- Security-sensitive: yes. It parses an untrusted sheet.
- Acceptance criteria:
  - The reveal sheet includes only items with a sealed context row.
  - A sheet carrying a `function` or `form` column is rejected on export.
  - The derived `needs_adjudication` and `confirmatory_eligible` values match T1's table on the
    exported rows.
- Status: done

## T11: Corrections
- Description: `correct --pass P --annotator A --item I --reason R` (FR9).
  - It reads a one-row correction sheet and validates it with the same per-pass rules.
  - It marks the old row `superseded` and appends the new one.
  - It appends `context_corrections.csv`, recording old and new hashes, the reason,
    `corrected_on` (injectable) and a derived `later_passes_sealed`.
  - Later-pass rows keep their `prior_sha256`.
- Files likely touched: src/annotation/context.py, tests/test_context_corrections.py
- Depends on: T10
- Security-sensitive: yes. It modifies committed annotation files.
- Acceptance criteria:
  - The superseded row is preserved, and the old and new hashes are logged (AC-003-7).
  - `later_passes_sealed` is true when a later pass exists for that item and annotator, and
    false otherwise. Both cases are tested.
  - An invalid reason, an unknown item, or correcting a row that doesn't exist each fail with
    a named rule.
- Status: done

## T12: Full validation
- Description: `validate` (FR12) recomputes everything from `dialogues.jsonl`, the pinned
  editions, the committed CSVs and the local text files, and lists every problem with its item
  and rule. Checks:
  - target hashes;
  - group and split consistency;
  - registry vs. screening log;
  - taxonomy integrity and versions;
  - enums and cross-field rules;
  - evidence bounds;
  - the `prior_sha256` chain, accepting superseded rows recorded in corrections;
  - correction-log consistency;
  - duplicate or foreign IDs;
  - missing or altered local text files.
- Files likely touched: src/annotation/context.py, tests/test_context_validate.py
- Depends on: T11
- Security-sensitive: yes. It's the integrity gate for committed annotation data.
- Acceptance criteria:
  - It passes on a fresh fixture export, including one correction.
  - Each of these edits fails with a named rule (AC-003-9): a committed label, a
    `prior_sha256`, a registry `target_sha256`, a group's split, a local text file.
  - A screening row flipped from `include` to `exclude` after registration is reported.
- Status: done

## T13: Coverage report and exposure flag
- Description: `coverage --batch B` (FR13, FR14). It shows per-annotator counts for every cell,
  including zeros, in these breakdowns:
  - stratum × function;
  - form × request type;
  - intent;
  - `?` slots per intent;
  - confidence;
  - future dependence;
  - `needs_adjudication`;
  - `prior_exposure`, which is derived when annotator = screener, for all passes;
  - `built_on_superseded`.

  Plain-text output, with no pooling across raters.
- Files likely touched: src/annotation/context.py (or context_coverage.py),
  tests/test_context_coverage.py
- Depends on: T12
- Security-sensitive: no. It only reads already validated data.
- Acceptance criteria:
  - Every form × function cell is printed, including zeros. Two annotators are reported
    separately (AC-003-12).
  - A literary item labeled by its screener is `prior_exposure` in all three passes. A
    non-screener annotator's item is not.
  - The full suite passes on native Windows Python 3.12 (AC-003-14), and the spec status,
    roadmap and decisions are updated.
- Status: done
