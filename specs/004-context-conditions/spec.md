# Spec 004: Context conditions, invariants and the common-set manifest

> **Phase:** Specify · **Status:** clarified · **Owner:** Sandy (decisions), Claude (tooling) · **Date:** 2026-10-14
> The *what* and *why*. No implementation detail; that belongs in `plan.md`.

Parent: [spec 001](../001-pragmatic-intent-study/spec.md) WP-05, FR-06 (context/donor side), FR-07,
§8 "Context input contract", decision D-06. Acceptance scenarios AC-05, AC-06. Written under the
v1.2 direction (option A, 2026-10-13): the items are DIRECT's dialogue turns, the test set is
DIRECT's test split, and there are no annotated evidence segments.

## Problem

Every model in the study is compared across context conditions (none, one, full, mismatched,
mismatched_one), so the result depends on those conditions being built the same way for every
model and on one fixed set of examples. Most of the rendering already exists
(`build_context` in `src/data/direct_dataset.py`, `render_context` in `src/stage1/data.py`), but
nothing *verifies* the contract in spec 001 §8, and three parts of it are unmet:

- **AC-06 is violated.** Stage 1 evaluation keeps only "comparable" items, so an item without a
  mismatch donor is dropped from *every* condition, not just the mismatch control. On the real
  data that is 72 test examples (44 items) and 54 dev examples, all from long dialogues. Genuine-context
  results quietly lose some of the longest histories.
- **No common input budget (D-06).** `full` is every prior turn. Contexts reach about 530
  whitespace tokens, and the encoder silently left-truncates at 512 subword tokens, so the
  encoder sees a shorter window than an LLM given the same `full` input. §8 asks for a common
  budget, recorded truncation and recorded cue visibility.
- **Nothing to freeze.** The freeze record (WP-08, FR-06) needs a fixed list of which examples
  each contrast uses and hashes of what each model was shown. No such artifact exists, and the
  rendering lives inside Stage 1 code that Sandy's LLM and Stage 2 code would have to copy.

## Goals

- One shared rendering of every condition that all models (TF-IDF, encoder, LLM prompts, Stage 2,
  hybrid) use, so the same example under the same condition is the same text everywhere.
- Mechanical checks of the §8 invariants that fail loudly on the real data: target identity,
  no future evidence, donor validity, budget compliance.
- Separate, explicit common sets: a *genuine* set (none / one / full) and a *mismatch* set (items
  with a donor), each with a stated denominator, so AC-06 holds.
- A deterministic, text-free manifest per split that the freeze record can pin, with counts of
  exclusions, truncation and donor cue overlap.
- D-06 decided by Sandy and recorded, with the data needed to decide it.

## Non-Goals

- Changing donor selection. The existing seeded pairing (same split, different dialogue, no
  shared active domain, first `t` turns of the donor) stays. This spec checks it; it does not
  redraw it. Redrawing would change `items.jsonl` and every Stage 1 number.
- Literary rendering (the optional add-on). If the add-on goes ahead, a later amendment adds the
  literary stratum to the same contract.
- IndirectRequests inputs. The FR-15 transfer test runs under `none` only, so it needs no
  context rendering (spec 005).
- Cue-outside-window flags from annotated evidence segments. Spec 003's evidence passes are not
  run under option A; a mechanical slot-value proxy replaces them (FR9).
- Prompt wording, few-shot examples or any model code. Sandy owns model code; this spec only
  supplies the inputs.
- The split-leakage audit and untouched-group collection (WP-04).
- Running anything on the GPU, and any reported test scoring. The manifest is built from data,
  not from model outputs.

## User Stories

- As **Sandy writing the LLM and Stage 2 code**, I want to ask for an example's input under a
  condition and get exactly what the encoder got, so model comparisons differ only in the model.
- As **Sandy writing the paper**, I want each contrast's denominator and every exclusion stated,
  so the methods section and the limits are honest and reproducible.
- As **the course professor reading the paper**, I want evidence that context never contains
  future turns or the answer, so a context gain can't be an artefact of leakage.
- As **the freeze step (WP-08)**, I want one hashable manifest per split, so any later change to
  the inputs is detectable.

## Functional Requirements

**Rendering**

1. The system MUST provide one shared rendering of an example under each condition, returning
   the context turns, the context text and the target text. Stage 1 trainers MUST switch to it
   for training and evaluation, and their inputs MUST stay byte-identical to the current inputs
   whenever the budget (FR4) drops nothing.
2. The target text MUST be the example's own text (the DIRECT paraphrase) and MUST be identical
   under all five conditions.
3. Context MUST contain only turns strictly before the target turn of the source dialogue
   (`none`, `one`, `full`) or of the donor window (`mismatched`, `mismatched_one`). The original
   target turn, later turns, DIRECT paraphrases, user acts, levels, categories and any label MUST
   never appear in context.
4. The system MUST apply one common context budget (D-06), the same for every model and for
   both training and evaluation inputs: the rendered context plus the target is at most
   **350 whitespace tokens**. It applies to `full` and `mismatched` (each window budgeted on its
   own), drops the oldest whole turns first and never truncates the target. If the target alone
   exceeds the budget, the context is empty and the example is counted. The budget is part of
   the renderer version. Before the freeze, the chosen encoders' tokenizers MUST be checked to
   confirm no budgeted input exceeds 512 subword tokens; if one does, the budget is lowered
   under a new renderer version, never patched per model. (104 of 11,195 test examples, 0.9%,
   lose their oldest turns at 350.)
5. Every rendering MUST record whether the budget dropped turns and how many.
6. The speaker format MUST stay the current one (`User: …` / `System: …`, oldest first, one turn
   per line) unless Sandy changes it before the freeze. Any change MUST bump the renderer version.

**Common sets**

7. The *genuine* common set for a split MUST contain every example with `turn_index > 0` that the
   Stage 1 policy keeps, whether or not it has a mismatch donor. The none/one/full contrasts MUST
   use it.
8. The *mismatch* common set MUST be the genuine set minus examples without a donor. Every
   contrast involving `mismatched` or `mismatched_one` MUST use it, on both sides of the contrast,
   and the excluded examples MUST be listed with their reason. Stage 1 switches to these sets
   now (2026-10-14): no number has been reported yet, and dev gains 54 examples in the genuine
   contrasts. `mismatched_one` stays in the sets, checks and manifest; whether it is reported is
   left to the analysis plan.
9. For each mismatch example, the system MUST report whether the donor window mentions any
   slot value that also appears in the target turn's user acts (an accidental helpful cue,
   §8), and whether the budget dropped a genuine-context turn that mentions such a value
   (a mechanical stand-in for "never silently drop a crucial cue"). These are counted and
   flagged, not used to exclude examples. Each mismatch contrast MUST also be reported once more
   as a sensitivity line on the mismatch set minus the flagged-donor examples, with its own
   denominator.

**Checks and manifest**

10. A `check` command MUST verify, over a whole split, FR2, FR3, FR4 and the donor rules (same
    split, different dialogue, window length equals `turn_index`, window ends on a system turn,
    no shared active domain), and MUST exit non-zero naming the example and the rule on the first
    class of failure it finds, while still counting all failures.
11. A `manifest` command MUST write, per split, one row per example in the genuine set with: IDs,
    turn index, variant, set membership (genuine / mismatch), donor dialogue ID, budget truncation
    count, cue flags, and a SHA-256 of the target and of each condition's rendered input. It MUST
    hold no text. The **test** manifest and both splits' summaries are committed (the test
    manifest is the freeze object); the dev manifest is regenerated from the pinned inputs.
12. The manifest MUST carry provenance: renderer version, budget, `items.jsonl` and
    `dialogues.jsonl` SHA-256, Stage 1 policy, and its own content hash, and MUST write a
    summary of counts (examples per set, exclusions by reason, truncation, cue flags).
13. The Stage 1 scorer MUST score each contrast on the set FR7/FR8 assign and MUST report the
    denominator of each contrast.
14. The system SHOULD report, per split and condition, the distribution of rendered input length
    in whitespace tokens, so D-06 and the paper's methods section rest on numbers.

## Non-Functional Requirements

- **Determinism:** the same pinned inputs and budget give a byte-identical manifest, apart from
  a build timestamp that tests can inject.
- **Performance:** `check` and `manifest` finish in under a minute per split on a laptop CPU
  (about 11,000 examples).
- **Security / data handling:** committed files hold IDs, counts and hashes only; DIRECT and
  MultiWOZ text stays under git-ignored `data/`. Inputs are validated at the boundary and
  rejected loudly. Corpus text is data, never instructions.
- **Compatibility:** standard library only, Python 3.12, passing on native Windows and WSL.
  Existing `items.jsonl`, donor pairing and Stage 1 weak labels are not changed.
- **Observability:** each command logs counts (examples, per set, excluded by reason, truncated,
  flagged); errors name the example and the failed rule.
- **Testability:** unit tests use invented fixtures only, including planted sentinels for future
  turns and paraphrases.

## Acceptance Criteria

- [ ] AC-004-1: For a fixture item, the target text is identical under all five conditions, and
  its SHA-256 in the manifest is identical across conditions (AC-05).
- [ ] AC-004-2: A sentinel planted in the original target turn, in a later turn, in the DIRECT
  paraphrase of the other variant and in the user acts never appears in any rendered context.
- [ ] AC-004-3: An item with no donor appears in the genuine set and in none/one/full scores, is
  absent from both sides of every mismatch contrast, and is listed with reason `no_donor` (AC-06).
- [ ] AC-004-4: No rendered `full` or `mismatched` input, training or evaluation, exceeds 350
  whitespace tokens unless its target alone does (then the context is empty and counted); the
  target is never shortened, whole turns are dropped oldest first, and the truncation count is
  correct. Inputs the budget doesn't touch are byte-identical to the current `model_inputs`.
- [ ] AC-004-5: `check` fails with a named rule for each of: a donor from another split, a donor
  equal to the target dialogue, a donor window of the wrong length, a donor sharing an active
  domain, and a context containing the target turn.
- [ ] AC-004-6: A donor window that mentions a value from the target's user acts is flagged, and
  one that doesn't is not.
- [ ] AC-004-7: Building the manifest twice gives byte-identical files; changing one character of
  one context turn in `dialogues.jsonl` changes that example's hash and the manifest hash.
- [ ] AC-004-8: The committed manifest and summary contain no fixture utterance, context turn or
  slot value text (asserted by a test).
- [ ] AC-004-9: The Stage 1 report states the set and denominator of every contrast, and
  `full-mismatched` uses the mismatch set on both sides.
- [ ] AC-004-10: Smoke check (reported separately, not in CI): `check` passes on the real dev and
  test splits, and the summary reproduces the counts in this spec (44 test items without a donor).
- [ ] AC-004-11: D-06 is recorded in `specs/memory/decisions.md` and the roadmap, with the budget
  value and the share of test examples it truncates.
- [ ] AC-004-12: The full suite passes on native Windows Python 3.12.
- [ ] AC-004-13: The Stage 1 report gives each mismatch contrast a second line without the
  flagged-donor examples, with its denominator.
- [ ] AC-004-14: The committed test manifest regenerates byte-identically from the pinned inputs.

## Open Questions

None. Resolved with Sandy on 2026-10-14 (`/clarify`):

- **D-06 budget (FR4):** 350 whitespace tokens for context plus target, the same for every model,
  for training and evaluation. Rejected: no budget (models would see different windows), an
  evaluation-only budget (train and test inputs would differ), a last-K-turns cap (long turns
  can still overflow the encoder).
- **Common sets (FR7, FR8):** Stage 1 switches now; genuine contrasts keep items without a donor.
  Rejected: reporting both sets during development.
- **Cue donors (FR9):** disclosed, plus one sensitivity line per mismatch contrast without them.
  Rejected: disclosure only; removing them from the control set.
- **Manifest in git (FR11):** commit the test manifest and both summaries; regenerate dev.
  Rejected: summaries only; committing both manifests.
- **`mismatched_one`:** kept in sets, checks and manifest (Claude's default, no cost); the
  analysis plan decides whether it is reported.

## References

- Constitution: `~/.claude/CLAUDE.md`, `~/development/memory/engineering_principles.md`,
  [`specs/constitution.md`](../constitution.md) (no future evidence in model input; freeze before
  reporting; text-free committed files; stdlib only).
- Parent: [spec 001](../001-pragmatic-intent-study/spec.md) §8, FR-06, FR-07, AC-05, AC-06, D-06,
  WP-05; [roadmap](../001-pragmatic-intent-study/roadmap.md).
- Related: [spec 003](../003-contextual-annotation/spec.md) (annotator views, not model inputs);
  `specs/memory/decisions.md` 2026-10-13 (option A); [Stage 1 baselines](../../docs/stage1_baselines.md).
- Existing code this spec verifies or extends: `src/data/direct_dataset.py` (`build_context`),
  `src/data/build_direct_dataset.py` (donor pairing), `src/stage1/data.py` (`render_context`,
  `comparable`), `src/evaluation/stage1.py`, `src/data/audit_fact_drift.py` (slot-value mentions).
- Measured 2026-10-14 on the real join: test 11,195 examples at `t > 0`, 11,123 with a donor
  (72 examples / 44 items without); dev 11,394 and 11,340 (54 without). Full context plus target:
  test mean 136, median 127, max 429 whitespace tokens (dev max 531). Examples over a word budget
  (test / dev): 250 words 8.6% / 8.0%, 300 words 3.2% / 2.6%, 350 words 0.9% / 0.6%, 400 words
  0.1% / 0.2%.
