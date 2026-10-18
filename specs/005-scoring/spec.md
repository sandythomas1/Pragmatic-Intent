# Spec 005: Option A rule revision, Stage 2 and transfer scoring

Status: Tooling implemented 2026-10-18; fresh human L3 check and model runs remain pending.
See [verification.md](verification.md). Requested by Sandy 2026-10-18: both `auto-v2` and Stage 2 /
IndirectRequests scoring. Parent: spec 001 v1.2, WP-06, FR-09, FR-15, AC-07 and AC-15.
The option-A direction overrides historical contextual-human-gold requirements.

## Scope and behavior

1. Preserve `auto-v1` predictions and the existing Stage 1 default. Add an explicitly selected
   `auto-v2` with wording rules for the failure classes disclosed on October 17: closing phrases,
   answer-like confirmations, missed conventional formulas and named details outside the slot
   vocabulary. Develop from the rubric, disclosed error classes and invented examples only.
2. Freeze the new rule source hash before evaluating adjudicated round 2. Report round 2
   separately as a held-out check; rounds 1/3 and the old L3 sheet are development evidence.
   Do not inspect per-item round-2 errors and then change this frozen rule version.
3. Prepare a reproducible, blinded, dev-only fresh L3 check for v2, excluding historical labeled
   turns and all turns drawn for the original v1 L3 check. Preserve v1 sheets. This check needs
   Sandy's judgments; no tool supplies gold labels or claims improved precision in advance.
4. Build Stage 2 weak references from existing DIRECT examples and MultiWOZ acts: `cat-v1`
   primary category; explicitly stated Inform slot/value pairs; and Request slot names.
   This is act recovery, not execution completeness or independently validated pragmatic gold.
   Unmapped requests remain requests and are excluded only from interpretation endpoints.
5. Render model inputs exclusively with spec 004's shared renderer. Inputs carry IDs, condition,
   context and target, never reference category, acts, slot values or the other DIRECT variant.
6. Validate routed and separate oracle prediction records against explicit requested conditions.
   Reject missing, foreign or duplicate IDs, unknown fields/types/enums, and unavailable mismatch
   conditions. An explicit invalid-output record counts as failure rather than disappearing.
7. Report category accuracy, normalized slot/requested-slot recovery, exact interpretation,
   oracle interpretation on every eligible weak-indirect example regardless of route prediction,
   and end-to-end success including direct routes. Route misses, missing interpretations,
   unsupported slots and invalid outputs fail the applicable endpoint. Report denominators,
   invalid counts and non-request false positives. Oracle and routed streams must be separate.
8. Keep genuine and mismatch sets as in spec 004. Report paired end-to-end contrasts on their
   common set with grouped bootstrap intervals and the donor-cue sensitivity line. Include
   mechanical rule-level and category slices with explicit versions.
9. Load pinned IndirectRequests JSONL locally using bounded `ast.literal_eval` for list strings.
   Validate candidates, aliases, target membership and record shapes. Export only `none` inputs:
   utterance, slot description and the closed candidate list (including `<ambiguous>`), without
   situation, gold or crowd rating. Score request recall and candidate recovery, with separate
   ambiguous/unambiguous slices. End-to-end requires detection and value recovery.
10. Transfer reports are separate and labeled LLM-generated, with an explicit model-family field
    and GPT-family flag. Train/validation are dev checks only. Test scoring requires an explicit
    opt-in; do not launch models or claim a study freeze. Reports contain counts/IDs/hashes only.

## Contracts and constraints

- Stdlib Python 3.12; `unittest`, invented fixtures, no model API, GPU work or new dependencies.
- Versioned, conservative slot normalization: case/space/apostrophes, number words and common
  price/centre/time aliases. Preserve distinctions and punctuation in names beyond these rules.
- Slot keys are lowercase `domain.slot`. Unstated, empty and `none` values are not required gold.
  MultiWOZ Request slots are scored separately, not as invented slot values.
- A source turn with conflicting Inform values for one slot has no single structured reference;
  report `conflicting_act_values`, exclude it from interpretation and retain it in detection.
- A structured prediction uses `example_id`, `condition`, `prediction` (direct/indirect/no_request),
  `category` (a cat-v1 value or null), `slots` (string map), `requested_slots` (unique string list),
  and optional `paraphrase` (local only, unscored). Alternatively, an invalid record has just
  `example_id`, `condition`, `invalid: true`. Wrong semantic values are scored, not schema errors.
- Oracle records use the same shape but their detection field does not gate interpretation.
- Transfer records use `example_id`, `condition: none`, `request` (boolean), `value` (candidate
  string or null), or the invalid-record shape. An out-of-candidate value is a scored failure.
- Free paraphrase adequacy and an LLM judge are deferred until Sandy has model outputs and can
  rate the planned sample. Deterministic act/slot scores do not stand in for that adequacy check.
- `auto-v2` stays provisional until its fresh L3 check. No silent replacement of v1 results.

## Acceptance criteria

- A1: All v1 tests pass; v2 handles invented closing/formula/detail/answer cases and mixed
  request-plus-thanks precedence. Unknown versions and nonpositive sample counts fail.
- A2: Frozen v2 source hash is recorded before held-out scoring. Round 2 has its own denominator;
  the fresh L3 draw is seeded, dev-only, excludes both old checks and keeps their sheets intact.
- A3: Duplicate/missing spot-check IDs and contradictory verdicts fail; snapshot records version,
  source hashes, seed and exclusions. No automatic human verdicts are written.
- A4: A Stage 1 route miss fails end-to-end while a correct separate oracle reading succeeds.
  Direct routes require interpretations; non-requests expose false positives; invalid outputs fail.
- A5: Wrong, missing and extra slots/requested slots affect precision/recall/exact recovery;
  number/time aliases match while distinct place names stay distinct. No-slot denominators are explicit.
- A6: Strict prediction validation covers every requested condition and exact expected sets.
  No-donor examples remain in genuine scores and leave both sides of mismatch contrasts only.
- A7: Input leakage sentinels for future text and gold are absent; reports contain no source text
  or predicted free text. Input hashes and source/version provenance are recorded.
- A8: Transfer handles list literals safely, boolean aliases, ambiguous targets, malformed values,
  candidate collisions and unknown splits; missing/duplicate predictions fail. No transfer data
  enters training or the main benchmark. Test use is explicit and reports carry generation flags.
- A9: Full native-Windows stdlib suite passes. Real-data adapter smoke checks report schema/count
  evidence separately without evaluating model performance or reading held-out per-item errors.

## Open decisions

None block this tooling. The fresh L3 verdicts, study freeze, model choices, LLM-judge calibration
and WSL encoder checks remain separate human/model work. This spec does not authorize paid runs.
