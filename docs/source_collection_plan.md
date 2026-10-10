# Human-Authored Source Collection Plan

_2026-10-09. Method specification for the [research plan](research_plan.md).
No literary corpus, new labels or ingestion pipeline has been created by this document._

## Collection unit and source roles

Collect a **communicative episode**, not a whole story's moral: exact target speech, identifiable
speaker/addressee and source-grounded preceding context. Items from the same dialogue, story,
episode or retelling family share one split group.

| Source | December role | Screening |
|---|---|---|
| MultiWOZ original turns via existing join | Main assistant-dialogue gold sample | Verify contextual function, supported intent/slots and prior history; preserve official splits. |
| DIRECT human-written rewrites | Existing weak training; separate paired diagnostics | Elicited paraphrase provenance; review fact drift. Variant names are not L0-L3 gold. |
| Aesop dialogue | Literary pilot and held-out transfer | Addressed speech required; a moral alone is not request interpretation. |
| Parables/religious narrative exchanges | Same, with translation/edition identified | Separate request evidence from theological interpretation and later outcomes. |
| Other literature, including documented jokes | Additional sources if feasible | Verify rights, speaker/addressee and preceding context. Punchline meaning is not automatically a request. |
| Circa / George and Mamidi implicatures | Annotation reference; screened negatives/transfer | Indirect answers require independent function review. |
| IndirectRequests / LLM-generated examples | Related work or separate later comparisons | Excluded from human-only December benchmark. |

Human-authored does not mean spontaneous: MultiWOZ is elicited task-oriented dialogue, DIRECT
includes commissioned rewrites, and literature is crafted communication. Preserve these distinctions.

## Initial literary source inventory

These **candidate editions** were checked on 2026-10-09. They have not been downloaded, hashed,
screened or added to data/sources.toml. Source availability does not establish eligible examples.

| Edition | Stable source | Pilot decision |
|---|---|---|
| Aesop, V. S. Vernon Jones translation, 1912 | [Project Gutenberg #11339](https://www.gutenberg.org/ebooks/11339) | Screen addressed exchanges; record fable/offsets. Catalog lists this edition as public domain in the USA. |
| King James Bible | [Project Gutenberg #10](https://www.gutenberg.org/ebooks/10) | Screen John 2:1-11 as the meeting's water-to-wine candidate; record book/chapter/verse. Catalog lists the text as public domain in the USA. No gold intent is assigned here. |
| Additional dialogue-rich work or documented joke collection | Select an exact edition in the pilot | Verify source rights and request coverage first; no anonymous scraped joke pool. |

Pin downloaded artifact, edition, translator, retrieval date, hash and reuse terms. An old work's
status does not establish rights for modern translations/commentary. Preserve source notices and
check intended release territory. Keep new text under ignored data/raw/literary/ until release
status is recorded.

## Screening workflow

1. Register bibliographic identity, canonical URL, edition, authorship/provenance, rights and hash.
   Preserve exact text and log OCR/encoding corrections.
2. Find exchanges, not conclusions. Identify target, addressee, source offsets and actual prior
   context. Do not invent an assistant interlocutor.
3. Screen for action/information requested of the addressee. Otherwise consider an authentic
   non-request control. Morals, motives, irony and indirect answers may belong to an exploratory
   pragmatics set without becoming requests. Out-of-scope requests are not negatives.
4. Record textual evidence for proposed readings. Store later replies/commentary separately,
   never as input. Flag post-target-dependent gold; keep exploratory unless prior evidence suffices.
5. Keep inclusion/exclusion reasons: no addressed speech, no context, uncertain reading, out of
   scope, duplicate story, rights pending or future-evidence dependence. Never select by model error.
6. Screen about 60 dev candidates and revise guidelines based on agreement/coverage. Pilot groups
   never become test.
7. Group before expanding: all turns/variants/context renderings from an episode stay together.
   Hold initial literary data out of training and few-shot prompts. Group retellings/translations.
   Later literary training requires independent works and collection-level transfer testing.
8. Draw new test groups. Preserve official MultiWOZ splits and exclude entire previously inspected
   calibration dialogues, including test dialogues containing rounds 1/3 turns. Deduplicate against
   training/dev/prompts. Freeze IDs, labels, contexts, donors, exclusions and hashes before scoring.

Report coverage by request function, intent, wording level, source/genre, group count and certainty.
Empty cells stay visible. Literary-only L3 and dialogue-only L0 confound genre with level; do not
pool them as H2 evidence.

## Annotation: separate form, function and interpretation

Preserve [rubric v2](annotation_guidelines.md) for historical calibration. Create a versioned new
supplement; the current exporter cannot store these new fields.

- **Wording-only:** label form L0-L3, informing, social non-request or undecidable under existing
  form rules. Hide DIRECT variant, moral, proposed gold and model output. Record uncertainty rather
  than using imagined context to assign form.
- **Full-context function:** determine whether this speaker requests action/information, informs,
  declines or does something else. Record addressee and capability evidence. Wording-only INF may
  function as a request in context; preserve both labels.
- **Interpretation:** record supported intent(s), required key slots, concise direct paraphrase,
  evidence spans, confidence and alternatives. Later replies/explanations corroborate, but do not
  uniquely determine gold.
- **Ambiguity/context dependence:** collect independent judgments under none/one/full. Use different
  raters or counterbalanced assignment so knowing the full story does not contaminate no-context
  judgments. Disagreement is only a proxy for ambiguity.
- **Implication depth, exploratory:** record an evidence chain as one step, multiple steps or
  uncertain under a piloted rubric. Count interpretive links, not story length, model chain of
  thought, required context length or observed difficulty. Do not equate depth and L0-L3.

Existing labels are single-annotator calibration work. Seek independent second labels on the full
new test set; the December minimum goal is 25% stratified across sources/levels, including difficult
literary cases. Report initial agreement separately from adjudicated labels, with denominators
and uncertainty. Use nominal agreement for function/intent and ordinal agreement for form when
applicable. A rough kappa of 0.6 is a diagnostic goal, not proof of validity; revise/narrow before
scaling when agreement is poor. Without a second rater, gold remains provisional. Obtain the
university/professor's determination before recruiting non-author human participants.

Human-written gold paraphrases are **annotations**, not authored model inputs. Keep them out of
prompts. LLM discovery/formatting assistance requires source verification and does not establish
independent gold.

## Record contract to implement next

This is a field specification, not implemented tooling. Keep restricted text/quoting notes out of
committed labels.

| Fields | Purpose |
|---|---|
| item_id, source_id, episode_id, split_group, split | Identity and leakage control. |
| source_kind, edition, translation, source_url, source_sha256, locator | Distinguish original dialogue, elicited rewrite and literary speech; reconstruct edition. |
| speaker, addressee, target_span, prior_context_spans, context_units | Verbatim input and source-grounded roles. |
| form_label, contextual_function, request_status, intent_ids, slots, gold_request | Independent form/function and Stage 1/2 targets. |
| evidence_spans, post_target_evidence, alternative_intents, ambiguity, implication_depth | Support, future dependence, uncertainty and inference complexity. |
| initial_annotations, adjudication, annotator_ids, rubric_version | Independent judgment history. |
| mismatch_donor_id, condition_manifest, cue_visibility, render_hashes | Reproducible paired context coverage and truncation audit. |
| rights_status, release_mode, screening_status, exclusion_reason | Source handling and selection transparency. |

## Context construction, negatives and release

Keep target wording identical. Freeze source window/segmentation and a token budget that fits
every compared model; log truncation and cue loss. For dialogue, one context is the prior speaker
turn; for literature, the last preceding speech/narrative unit. Report strata separately because
units differ. Fixed role identifiers may appear in all conditions but reveal no inferred intent.

Choose unrelated donors within the same split/stratum, matched on unit count, token budget and
format; prefer comparable roles/capabilities without shared episode or target intent. Review
accidental relevant cues and freeze mappings. Without compatible donors, exclude only from the
paired control analysis and disclose common-set coverage. Mismatches are corrupted controls, not
authentic new meanings.

Include original informing, refusals, thanks, literal observations and indirect answers as negatives
only after validating no request in original context. Include hint-shaped negatives where available.
Separate authentic contradictions, DIRECT rewrite fact drift and deliberate mismatches. The existing
fact-drift audit flags candidate rewrite errors; it neither adjudicates nor evaluates literary meaning.

Use genuine repeated wording in different observed contexts if available. Do not manufacture
contrastive twins or complete L0-L3 ladders. Their absence limits causal claims about indirectness
but still permits same-item context ablation.

Canonical fables, biblical exchanges and jokes may be familiar from pretraining. Keep story IDs
for audit; omit identifying titles/verse labels from input when unnecessary. Inspect lesser-known
versus canonical cases where coverage permits. No source is guaranteed absent from model training.
A familiar example alone cannot establish contextual reasoning or assistant generalization.
Modernized rewrites create a different benchmark and remain outside the main experiment.

Freeze a datasheet/manifest. Release source-permitted inputs with notices, or IDs/offsets, own
annotations and reconstruction instructions. Existing DIRECT restrictions in
[data_sources.md](data_sources.md) remain. The MIT code license does not cover all third-party text.
