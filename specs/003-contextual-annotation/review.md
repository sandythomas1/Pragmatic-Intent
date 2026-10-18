# Review: Spec 003

Verdict: READY (after revisions R1–R14 were applied to spec.md and plan.md on 2026-10-11)

The initial verdict was NEEDS REVISION, with blocking findings R1–R5. They were discussed with
Sandy on 2026-10-11, who decided:

- **R5:** request-precedence single label, and proposals/hortatives count as requests
  (`joint_action` intent).
- **R2:** `name=?` for unstated required slots, values typed in the source's own words, and no
  required slots for literary intents in v0.
- **R1:** sentence/turn segment indices for evidence (`seg-v1`).
- **R7:** flag `prior_exposure` and disclose. Professor's blind literary labels are optional and
  come later. This avoids delaying experiments.
- **R14:** a logged correction path (`correct`), not "immutable until adjudication".
- **R8:** back up local free text to Google Drive.

R3, R4, R6 and R9–R13 were applied as written. The findings below are kept as originally raised.

## Findings

1. **R1 (blocking, correctness): literary evidence can't be expressed as unit IDs.**
   - FR5 records literary evidence as unit IDs, and AC-003-6 rejects evidence "at or after the
     target". But Aesop narrative units are whole paragraphs, and most fables are one or two
     paragraphs. The committed screening log already has two candidates inside "THE OLD LION,
     para 1".
   - The cue for a hint is usually earlier in the *same* paragraph. Citing it means citing the
     target's own unit. Either validation rejects correct evidence, or the rule is loosened until
     it can't catch anything. Two implementers would also clip differently.
   - Spec 004 needs evidence that is finer than a unit, to flag cue loss when the model's `full`
     window is truncated (spec 001 §8).
   - *Fix:* define a deterministic **prior-segment** view shared by both strata.
     - Dialogue: segment = prior turn, index `t`.
     - Literary: segment = sentence of the prior text, after clipping at `target_start`. Split on
       `[.!?]` + optional closing quote + whitespace, and never across a unit boundary.
     - The sheet shows numbered segments. Evidence is a list of segment indices, validated
       against `< n_segments`.
     - The segmenter is versioned (`seg-v1`) and recorded on every context row.

2. **R2 (blocking, correctness): required slots force fabrication.**
   - FR5 requires every required slot of the chosen intent to be present. An implied request
     often leaves a required value unstated. "We're a big group, and we're hungry" implies
     `find_restaurant` with no area or food stated.
   - Under the rule as written, the annotator must invent a value, which is the inference the
     benchmark measures and the constitution forbids in gold. Otherwise they must
     mis-classify to dodge the rule.
   - *Fix:* each required slot is either `name=value` or `name=?` (unspecified in the source).
     `?` satisfies presence, and spec 005 treats it as "not scored". The coverage report counts
     `?` slots per intent, which is D-03 evidence for which slots are realistically "required".

3. **R3 (blocking, clarity): batch completeness contradicts incremental export, and literary
   intake can stall dialogue work.**
   - FR7 says both "re-export adds new items" and "every batch item must be labeled; missing
     items abort".
   - FR5 and FR6 gate a whole batch on a prior pass. If `register-literary` adds items to
     `pilot1` after A1 has exported the dialogue form pass, A1 can't get a context sheet for any
     dialogue item until the new literary items are form-labeled. That's likely: literary
     screening is Sandy's still-open task, and the Oct 19 window is tight.
   - *Fix:*
     - Each `sheet` call snapshots the eligible items into `sheet_info.json`, recording the
       pass, annotator, item IDs, seed, built time and the registry/prior-file hashes.
     - Eligible means the item is in the batch, its prior pass is sealed for this annotator, and
       this pass isn't yet exported.
     - Export requires every row *of that snapshot* to be labeled.
     - Items registered later are picked up by the next `sheet` call.
     - Drop "every batch item" wording.

4. **R4 (blocking, clarity/testability): hash canonicalization is unspecified.**
   - `prior_sha256`, `text_sha256` and the form pass's own prior have no defined byte encoding.
     The form pass has no earlier pass. One engineer would hash the raw CSV line and another a
     JSON object, and Excel's CRLF/BOM round-trips would break the first silently.
   - AC-003-9 depends on this.
   - *Fix:* the hash is SHA-256 of `json.dumps(obj, sort_keys=True, ensure_ascii=False,
     separators=(",", ":"))` encoded as UTF-8, where `obj` is the committed row's fields minus
     the hash field itself.
     - Form `prior_sha256` = the hash of the item's registry row.
     - `text_sha256` covers `{"item_id", "pass", "annotator", "slots", "paraphrase"}`. It
       excludes `notes`, so local notes can be annotated later without breaking the chain.

5. **R5 (blocking, clarity): one `function` value can't represent the commonest MultiWOZ turn.**
   - "I need a train to Cambridge. There will be 5 of us." informs *and* requests. FR8 derives
     `request_status` from `function` alone. If two annotators resolve mixed turns differently,
     a turn can be "inform" for A1 and "request" for A2.
   - That disagreement comes from an unwritten precedence rule, not from real ambiguity, and it
     goes straight into the H2 endpoint population.
   - *Fix:* state the precedence in the spec, not just the rubric. `function = request` if the
     turn contains any request of the addressee; otherwise `decline` > `inform` > `social` >
     `other`. Precedence is applied before `uncertain`, which is reserved for "can't tell
     whether a request is present".

6. **R6 (non-blocking, internal contradiction): form-pass item IDs leak the source.**
   - FR4 bans stratum and source columns, yet shows `item_id`. That's `d:PMUL1234:t06` or
     `lit-…`, which names the stratum, dialogue and turn.
   - The style already reveals the stratum, so the practical risk is small. But AC-003-3 can't
     be tested consistently against a spec that contradicts itself.
   - *Fix:* the form sheet uses opaque row IDs (`f-001…`) mapped through a local key, as
     `src.annotation.levels` does. Export maps them back to item IDs.

7. **R7 (non-blocking, honest limits): `prior_exposure` covers only the reveal pass.**
   - A screener has seen the literary target *in context*, and has edited its `target_text`. So
     their literary form pass isn't wording-only either.
   - *Fix:* `prior_exposure` applies to all three passes for a screener-annotator. The coverage
     report shows exposed vs. unexposed counts. The spec also suggests (without requiring) that
     A2, if available, takes literary form labels.

8. **R8 (non-blocking, durability): gold free text exists in one gitignored file.**
   - Slot values and paraphrases are Stage 2 gold (spec 005 scores required slots). They live
     only in `data/interim/context/*_text.jsonl`. A disk loss or an accidental `git clean -fdx`
     destroys them, and the committed hashes can verify a restore but can't replace one.
   - *Fix:* add a Risk and a documented step. After each export, back up `data/interim/context/`
     to Sandy's private storage. `validate` reports a missing or mismatched text file as an
     error naming the item.

9. **R9 (non-blocking, security): `--batch` is used in a path but has no regex.**
   - `data/interim/context/<batch>/` with `--batch ../../x` escapes the work directory. The
     general "paths resolve under configured dirs" rule covers it, but nothing names the check.
   - *Fix:* batch must match `^[a-z][a-z0-9_-]{0,31}$`, validated at the CLI and on every
     registry load. Add a test with `../`.

10. **R10 (non-blocking, clarity): taxonomy versions.**
    - FR3 puts `taxonomy_version` in the file, but doesn't say whether old versions stay.
      Replacing v0 with v1 would invalidate every context row labeled under v0.
    - *Fix:* the taxonomy file is append-only by version. A row validates against its own
      `taxonomy_version`. Removing a version that a committed label references is a
      validation error.

11. **R11 (non-blocking, design gap to note): annotation view vs. model view.**
    - Annotators judge with *all* prior context. Spec 004's model `full` window (D-06) may be
      shorter or truncated. Gold could then rest on evidence the model never sees, and that would
      look like a model failure.
    - *Fix:* add this as a plan tradeoff. Spec 004 must use the R1 evidence segments to flag
      `cue_outside_window` per item and condition. No change to 003's scope beyond R1.

12. **R12 (non-blocking, testability): AC-003-3's "row order differs" is flaky.** A seeded
    shuffle can return the identity order for tiny fixtures. *Fix:* assert that the order equals
    `random.Random(seed).shuffle` of registry order, using a fixture of ≥5 items.

13. **R13 (non-blocking, completeness): `future_dependence = conflicts` has no consequence.**
    A label contradicted by the story's own continuation is the strongest adjudication signal
    available. *Fix:* FR8 derives `needs_adjudication = true` for `conflicts`, and coverage
    lists those items. They are still not edited (rows stay immutable).

14. **R14 (non-blocking, process): no defined path for an honest mistake.**
    - Immutable export (FR7) with no correction mechanism invites hand-editing committed CSVs,
      for example after exporting from the wrong sheet or under the wrong annotator ID. That
      breaks the hash chain and hides the correction.
    - *Fix:* the spec explicitly names correction as out of scope until adjudication. The interim
      rule is that a mistaken export is reverted with git *before commit*. After commit, the row
      stands and is fixed by adjudication. This is documented in the rubric doc.

## Non-Issues Considered

- **Selection independence.** The draw is uniform over dialogues, then over eligible turns. It
  uses no acts, labels or model output, and social-only turns stay in as negatives. This complies
  with the constitution.
- **Round exclusion.** Round 2 is the only round with dev dialogues (verified: 10 dialogues).
  Rounds 1 and 3 are all test and can't collide with a dev draw. Excluding whole dialogues, not
  just turns, is correct because Sandy has read them.
- **DIRECT text exposure.** The sheets use `dialogues.jsonl`, which holds original MultiWOZ text
  (MIT), and never the DIRECT rewrites. `data/interim/` is gitignored (`.gitignore` line 21).
- **Screened candidate whose `target_text` was later edited.** The `candidate_id` stays stable
  because it hashes the proposal span, but `target_sha256` changes. FR9's registry-vs-screening
  check catches this loudly. That is the right behavior.
- **Turn 0 exclusion.** It matches `levels.py` and spec 001. A turn-0 item can't show a context
  contrast.
- **Missing mismatch donors** (172 corpus-wide). These are deliberately not filtered, per AC-06.
  Coverage and donors are spec 004's concern.
- **Sealing doesn't prevent a determined annotator from reading `dialogues.jsonl`.** This is
  accepted and already stated in plan.md: sealing guarantees tool order, not ignorance.
- **Claude as annotator.** The tooling is rater-agnostic, so labels under a Claude ID could be
  exported. Coverage never pools annotators, and the constitution already bars Claude labels from
  gold. No extra rule is needed.
- **Hashes of short free text.** Hashing a short paraphrase could be reversed by dictionary
  attack, but the text isn't confidential. It's local for licensing and constitution reasons, so
  this isn't a security issue.
- **Constitution consistency.** Stdlib only, text-free commits, pseudonymous IDs, determinism and
  no network code are all respected. Rubric v2 and the historical CSVs are untouched.
