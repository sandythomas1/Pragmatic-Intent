# Synthetic Data Plan (draft v0)

> **Status: parked (2026-09-25).** The user switched the project to an existing-data design built on
> DIRECT + MultiWOZ 2.1 (see "Design revision" at the top of [`research_plan.md`](research_plan.md)).
> This plan and its decision log are kept for reference. The only part likely to return is a small
> hand-written contrastive set, an optional add-on to the new design. Reuse this plan's §2 schema and
> §3.2–3.3 filters for it. Nothing here is being generated.

_Drafted 2026-09-25 for Phase 2 of [`research_plan.md`](research_plan.md). **Status: proposal only.**
No synthetic data has been generated and no generation code exists yet. Answers so far are in the
[§4 decision log](#decision-log-2026-09-25); the remaining open questions there block generation.
Source facts come from [`data_sources.md`](data_sources.md)._

The controlled benchmark varies three things at once: **indirectness** (L0–L3, by form), **context**
(none / 1 prior turn / full / mismatched), and **request status** (the same utterance is a request in
one context and not in another). No existing dataset varies these together, so the benchmark must be
authored. This plan covers what the downloaded data can and can't contribute (§1), the record format
(§2), how candidates are produced, filtered, and reviewed (§3), and the decisions that still need an
owner (§4).

---

## 1. Gap analysis

What each downloaded source actually contains, checked against the design. The numbers come from
profiling the files pinned in `data/sources.toml`.

| Design requirement | DIRECT | IndirectRequests | Circa | CLINC150 | MASSIVE en-US | Verdict |
|---|---|---|---|---|---|---|
| Same-scenario **L0–L3 ladder** | Partial: 2 points (direct/indirect), not CCSARP-controlled | No: one utterance per item, mostly L2 | No | No: L0/L1 only | No: L0/L1, plus ~30 natural L2 hints | **Author** |
| **Contrastive twins** (same string, request vs. not) | No | No | No | No | No | **Author** |
| **Multi-turn context** | Yes, through a join to MultiWOZ (not in the files) | No: a one-line `situation` only | One turn (the question) | No | No | **Author**. DIRECT only for transfer |
| **Mismatched context** (same length, other scenario) | Could be built, but domain-shifted | No | No | No | No | **Derive** from our own scenarios |
| **Assistant-style intents** | No: MultiWOZ booking/search services | No: SGD services | No: social chat | Yes: 150 intents, 10 domains | Yes: 60 intents, 18 scenarios | Partial, for the chosen list (Q1-E). Strong for information seeking, recommendation, planning/scheduling, and action/device. Weak for navigation and troubleshooting. None for advice/support and clarification |
| **3-way Stage 1 labels** | No: ~21% of rows are thanks/closings with no flag | No: all requests | No | No: `oos` ≠ `no_request` | No | **Author**. Weak labels possible for transfer only |
| **Stage 2 gold** (intent + key slot, paraphrase) | Paraphrase: `indirect → direct` | Key slot plus candidate set | No | Intent | Intent + slots | Useful for transfer and training |
| **Human-written** (decision #7) | Yes (MTurk, 2021) | No: GPT-3.5/4, then crowd-filtered | Yes | Yes | Yes (SLURP) | Useful as non-LLM comparison sets |
| **Redistributable** in our HF release | No: no license | Unclear: two licenses, SGD-derived | Unclear: BY vs BY-SA | Yes (CC BY 3.0) | Yes (CC BY 4.0) | Only CLINC and MASSIVE text may appear in the release |

What the data shows beyond the table:

- **Ladders don't exist anywhere.**
  - DIRECT's "indirect" side is not a level. About 15% of its indirect paraphrases still use
    "can/could/would you", which is L1 form. In the test file, 5% were judged *not* to keep the
    original intent, and 10.6% were rated "Bad" for directness ordering.
  - IndirectRequests varies *which slot value* is meant ("I could really go for some biryani" →
    cuisine), not *whether* a request is being made. 81 of its 453 items have an `<ambiguous>` target.
- **Natural hints are rare in intent corpora.** A crude regex finds about 30 hint-like utterances in
  16,521 MASSIVE utterances (for example "it's too dark here" → `iot_hue_lighton`) and 4 in 22,500
  CLINC ones. About half of both corpora starts with an imperative, a *wh*-word, or a modal. They are
  L0/L1 seed pools, not hint pools.
- **Surface-form mismatch is a built-in artifact risk.** MASSIVE and CLINC are 100% lowercase and
  almost never end in punctuation (2.1% and 0.4%). Generated or hand-written text will be cased and
  punctuated. If seeds go in verbatim, a classifier can read the level off the casing. Normalize both
  sides, or paraphrase every seed.
- **Context:** only DIRECT has multi-turn history, and only after joining to MultiWOZ. There, the
  assistant is a booking operator, which is not the assistant setting we study. Circa's single
  question turn is the only ready-made "1 prior turn" format.
- **`no_request` material:** Circa answers ("I put hot sauce on everything") and CLINC small talk
  (`greeting`, `thank_you`, `yes`, `no`, …) show what non-requests look like. Circa answers are also
  hint-*shaped*, which is the kind of distractor we need. CLINC's `oos` class is out-of-scope
  *requests* and must not be relabeled as `no_request`.

**How the sources will be used:**

| Source | Role |
|---|---|
| CLINC150, MASSIVE | Seed phrasings for L0/L1, slot vocabularies, and taxonomy grounding. The natural L2 hints serve as exemplars. |
| DIRECT | Stage 2 paraphrase supervision. Context-aware pre-training and transfer evaluation. A human-written comparison set. Stays local. |
| IndirectRequests | Stage 2 key-slot transfer test. It is GPT-generated, so report GPT-family models on it separately. |
| Circa | A "1 prior turn" pragmatic-inference transfer test and a style reference for `no_request` distractors. |
| Conversational Implicatures (George & Mamidi) | The context → response → implicated-meaning structure is the reference for Stage 2 annotation. Its 1,000 human-written implicatures (72% yes/no answers, about 3% with request markers) are `no_request` and implicature examples. It stays local, because its text is third-party copyrighted. |

Everything that carries the manipulation (ladders, twins, histories, mismatches, 3-way labels)
has to be authored.

---

## 2. Proposed record schema

### 2.1 Design principles

1. **The scenario is the unit of authorship and splitting.** A scenario holds one intent and its
   slots, two contexts (one where the target utterance is a request, one where it isn't), and every
   utterance variant. Splits are assigned per `split_group`, a family of scenarios that share a seed
   or template, so near-duplicates never straddle train and test (decision #6).
2. **Form and function are separate fields.** `form_level` (L0–L3) is the CCSARP strategy of the
   surface form and can be annotated from the utterance alone (decision #2). `stage1_label` depends on
   context. A contrastive twin keeps its `form_level` but changes its `stage1_label`. This also means
   the Stage 1 mapping (see Q3) can change later without relabeling anything.
3. **Contexts are stored once. The four conditions are derived.** Evaluation instances are built
   deterministically from each scenario:

   | Condition | Context shown |
   |---|---|
   | `none` | `[]` |
   | `prior_1` | the last turn of the item's context |
   | `full` | the whole context |
   | `mismatched` | the same-length context of `mismatch_scenario_id` |

   The mismatch pairing is stored, not re-sampled, so runs are reproducible. It must stay within
   the same split.
4. **Provenance travels with every item**: human vs. LLM, the exact model and version, the hash of
   the rendered prompt, the exemplar IDs shown to the generator, and every human edit. Decision #7
   analyses and license checks need all of it.

### 2.2 Scenario record (JSON Schema, draft 2020-12)

One scenario per line in `scenarios.jsonl`. Invariants that JSON Schema can't express are listed in §2.4.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "PragmaticIntentScenario",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "scenario_id", "split_group", "split", "intent", "slots", "setting",
               "contexts", "mismatch_scenario_id", "items", "provenance", "review"],
  "properties": {
    "schema_version": { "const": "0.1" },
    "scenario_id":    { "type": "string", "pattern": "^[a-z_]+-[0-9]{4}$" },
    "split_group":    { "type": "string", "description": "Scenarios generated from the same seed/template share a group; split is assigned per group." },
    "split":          { "enum": ["train", "dev", "test", null], "description": "null until the split is frozen." },
    "intent":         { "$ref": "#/$defs/intent" },
    "slots":          { "$ref": "#/$defs/slots" },
    "setting":        { "type": "string", "maxLength": 300, "description": "One or two sentences: where the user is and what the assistant can do." },
    "contexts": {
      "type": "object", "additionalProperties": false, "required": ["support", "contrast"],
      "properties": {
        "support":  { "$ref": "#/$defs/context", "description": "History in which the target utterance IS a request for this scenario's intent." },
        "contrast": { "$ref": "#/$defs/context", "description": "Same-length history in which the same utterance is NOT a request, or is a request for a different intent." }
      }
    },
    "mismatch_scenario_id": { "type": ["string", "null"], "description": "Donor of the 'mismatched' context; same split, different intent." },
    "items":      { "type": "array", "minItems": 5, "items": { "$ref": "#/$defs/item" } },
    "provenance": { "$ref": "#/$defs/provenance" },
    "review":     { "$ref": "#/$defs/review" }
  },
  "$defs": {
    "intent": { "enum": ["TBD_BY_TAXONOMY_V1"], "description": "Replaced by the taxonomy v1 ids. Working ids (Q1-E): information_seeking, recommendation, planning_scheduling, troubleshooting, navigation, advice_support, clarification, action_device." },
    "slots":  { "type": "object", "additionalProperties": { "type": "string" } },
    "turn": {
      "type": "object", "additionalProperties": false, "required": ["speaker", "text"],
      "properties": { "speaker": { "enum": ["user", "assistant"] }, "text": { "type": "string", "minLength": 1, "maxLength": 400 } }
    },
    "context": {
      "type": "object", "additionalProperties": false, "required": ["turns", "cue_turn_indices", "reading"],
      "properties": {
        "turns":            { "type": "array", "items": { "$ref": "#/$defs/turn" } },
        "cue_turn_indices": { "type": "array", "items": { "type": "integer", "minimum": 0 }, "description": "Turns that carry the disambiguating cue; used to counterbalance cue position." },
        "reading":          { "enum": ["request", "no_request", "other_intent"] },
        "other_intent":     { "oneOf": [{ "$ref": "#/$defs/intent" }, { "type": "null" }] }
      }
    },
    "item": {
      "type": "object", "additionalProperties": false,
      "required": ["item_id", "utterance", "form_level", "item_role", "context_key", "stage1_label", "intent",
                   "slots", "gold_request", "is_contrastive", "contrast_group_id", "provenance", "review"],
      "properties": {
        "item_id":           { "type": "string" },
        "utterance":         { "type": "string", "minLength": 1, "maxLength": 300 },
        "form_level":        { "enum": ["L0", "L1", "L2", "L3", null], "description": "CCSARP strategy of the surface form; null only for distractors." },
        "item_role":         { "enum": ["ladder", "contrast_twin", "distractor"] },
        "context_key":       { "enum": ["support", "contrast"] },
        "stage1_label":      { "enum": ["direct_request", "indirect_request", "no_request"] },
        "intent":            { "oneOf": [{ "$ref": "#/$defs/intent" }, { "type": "null" }], "description": "Gold Stage 2 intent; null for no_request." },
        "slots":             { "$ref": "#/$defs/slots" },
        "gold_request":      { "type": ["string", "null"], "description": "Canonical direct paraphrase of what is being asked (Stage 2 reference); null for no_request." },
        "is_contrastive":    { "type": "boolean", "description": "True for BOTH members of a twin pair." },
        "contrast_group_id": { "type": ["string", "null"] },
        "provenance":        { "$ref": "#/$defs/provenance" },
        "review":            { "$ref": "#/$defs/review" }
      }
    },
    "provenance": {
      "type": "object", "additionalProperties": false, "required": ["origin"],
      "properties": {
        "origin":    { "enum": ["human", "llm", "llm_human_edited", "source_dataset"] },
        "author_id": { "type": ["string", "null"], "description": "Pseudonymous id (e.g. 'A1'); never a name or email." },
        "generator": {
          "type": ["object", "null"], "additionalProperties": false,
          "required": ["provider", "model", "model_version", "prompt_template_id", "prompt_sha256", "params", "created_at"],
          "properties": {
            "provider":           { "type": "string" },
            "model":              { "type": "string" },
            "model_version":      { "type": "string", "description": "Dated snapshot id exactly as the API or model card reports it." },
            "prompt_template_id": { "type": "string", "description": "e.g. 'ladder@v3' (file under configs/generation/)." },
            "prompt_sha256":      { "type": "string", "pattern": "^[0-9a-f]{64}$", "description": "Hash of the fully rendered prompt." },
            "exemplar_ids":       { "type": "array", "items": { "type": "string" }, "description": "Seed scenario ids shown in the prompt (leakage audit)." },
            "params":             { "type": "object", "description": "temperature, top_p, seed, max_tokens, ..." },
            "response_sha256":    { "type": "string", "pattern": "^[0-9a-f]{64}$" },
            "created_at":         { "type": "string", "format": "date-time" }
          }
        },
        "derived_from": {
          "type": "array",
          "items": { "type": "object", "additionalProperties": false, "required": ["source", "record_id", "license"],
                     "properties": { "source": { "type": "string" }, "record_id": { "type": "string" }, "license": { "type": "string" } } }
        },
        "edits": {
          "type": "array",
          "items": { "type": "object", "additionalProperties": false, "required": ["editor_id", "at", "field", "before", "reason"],
                     "properties": { "editor_id": { "type": "string" }, "at": { "type": "string", "format": "date-time" },
                                     "field": { "type": "string" }, "before": { "type": "string" }, "reason": { "type": "string" } } }
        }
      }
    },
    "review": {
      "type": "object", "additionalProperties": false, "required": ["status"],
      "properties": {
        "status":  { "enum": ["candidate", "filtered_out", "needs_review", "accepted", "revised", "rejected", "adjudicated"] },
        "filters": { "type": "object", "additionalProperties": false,
                     "properties": { "failed": { "type": "array", "items": { "type": "string" } },
                                     "flagged": { "type": "array", "items": { "type": "string" } } } },
        "annotations": { "type": "array", "items": { "$ref": "#/$defs/annotation" } },
        "adjudication": { "type": ["object", "null"] },
        "notes": { "type": "string" }
      }
    },
    "annotation": {
      "type": "object", "additionalProperties": false, "required": ["annotator_id", "context_shown", "stage1_label", "created_at"],
      "properties": {
        "annotator_id":  { "type": "string" },
        "context_shown": { "enum": ["none", "prior_1", "full"], "description": "Lets the with/without-context human baseline come straight from annotations." },
        "stage1_label":  { "enum": ["direct_request", "indirect_request", "no_request"] },
        "form_level":    { "enum": ["L0", "L1", "L2", "L3", null] },
        "intent":        { "type": ["string", "null"] },
        "confidence":    { "enum": [1, 2, 3] },
        "naturalness":   { "enum": [1, 2, 3] },
        "created_at":    { "type": "string", "format": "date-time" }
      }
    }
  }
}
```

### 2.3 Example (abridged: 3 of 6 items shown, provenance on one)

This uses the plan's thermostat example, with an L3 twin in which the same sentence is not a request.

```json
{
  "schema_version": "0.1",
  "scenario_id": "action_device-0007",
  "split_group": "action_device-seed-02",
  "split": "test",
  "intent": "action_device",
  "slots": { "device": "thermostat", "target_state": "warmer" },
  "setting": "Winter evening at home. The assistant can control the smart thermostat, lights, and speakers.",
  "contexts": {
    "support": {
      "reading": "request", "other_intent": null, "cue_turn_indices": [2],
      "turns": [
        { "speaker": "user",      "text": "Finally home. The bus took forever." },
        { "speaker": "assistant", "text": "Welcome back! Long day?" },
        { "speaker": "user",      "text": "Very. And the heating was off the whole time I was out." },
        { "speaker": "assistant", "text": "That's rough. Anything you need before dinner?" },
        { "speaker": "user",      "text": "Not yet, just changing out of these wet clothes." },
        { "speaker": "assistant", "text": "Sounds good. I'm here if you need anything." }
      ]
    },
    "contrast": {
      "reading": "no_request", "other_intent": null, "cue_turn_indices": [2, 4],
      "turns": [
        { "speaker": "user",      "text": "Guess where I'm staying tonight." },
        { "speaker": "assistant", "text": "Tell me!" },
        { "speaker": "user",      "text": "The ice hotel up north. Everything is carved out of ice, even the beds." },
        { "speaker": "assistant", "text": "That sounds amazing. How cold is it inside?" },
        { "speaker": "user",      "text": "Minus five, on purpose. It's the whole point." },
        { "speaker": "assistant", "text": "Wow. How are you finding it so far?" }
      ]
    }
  },
  "mismatch_scenario_id": "navigation-0012",
  "items": [
    { "item_id": "action_device-0007-L0", "utterance": "Turn the heat up.", "form_level": "L0",
      "item_role": "ladder", "context_key": "support", "stage1_label": "direct_request",
      "intent": "action_device", "slots": { "device": "thermostat", "target_state": "warmer" },
      "gold_request": "Turn the heat up.", "is_contrastive": false, "contrast_group_id": null,
      "provenance": { "origin": "human", "author_id": "A1" }, "review": { "status": "accepted" } },
    { "item_id": "action_device-0007-L3", "utterance": "I can see my breath in here.", "form_level": "L3",
      "item_role": "ladder", "context_key": "support", "stage1_label": "indirect_request",
      "intent": "action_device", "slots": { "device": "thermostat", "target_state": "warmer" },
      "gold_request": "Turn the heat up.", "is_contrastive": true, "contrast_group_id": "action_device-0007-c1",
      "provenance": {
        "origin": "llm",
        "generator": { "provider": "<provider>", "model": "<model>", "model_version": "<dated snapshot>",
                       "prompt_template_id": "ladder@v1", "prompt_sha256": "<64 hex>",
                       "exemplar_ids": ["action_device-0002"], "params": { "temperature": 0.9, "seed": 17 },
                       "created_at": "2026-10-05T14:02:11Z" } },
      "review": { "status": "accepted", "filters": { "failed": [], "flagged": [] } } },
    { "item_id": "action_device-0007-L3-twin", "utterance": "I can see my breath in here.", "form_level": "L3",
      "item_role": "contrast_twin", "context_key": "contrast", "stage1_label": "no_request",
      "intent": null, "slots": {}, "gold_request": null,
      "is_contrastive": true, "contrast_group_id": "action_device-0007-c1",
      "provenance": { "origin": "human", "author_id": "A1" }, "review": { "status": "accepted" } }
  ],
  "provenance": { "origin": "llm_human_edited", "author_id": "A1" },
  "review": { "status": "accepted" }
}
```

### 2.4 Cross-field invariants (enforced by a validator, not by JSON Schema)

1. **Twins:** items sharing a `contrast_group_id` have byte-identical `utterance`s, and exactly one
   of them uses `context_key: "support"`. Every scenario has at least one group (decision #4).
2. **Ladder:** each accepted scenario has exactly one accepted `ladder` item per `form_level` L0–L3.
3. **Labels:** `stage1_label` is a function of `form_level` and the context's `reading` (see Q3).
   `no_request` implies `intent = null` and `gold_request = null`. `other_intent` readings carry the
   other intent in `intent`.
4. **Contexts:** `support` and `contrast` have the same number of turns, and every scenario in a
   benchmark version uses the same length (see Q7). The last turn is always `assistant`, so the target
   utterance is the user's next turn. The `mismatch_scenario_id` donor is in the same split, has a
   different intent, and its context has the same length.
5. **Splits:** every scenario in a `split_group` has the same `split`. No `exemplar_ids` entry may
   point to a `test` scenario. This is checked from the generation logs at freeze time.
6. **IDs:** `item_id` and `scenario_id` are unique across the whole benchmark version.

### 2.5 Derived evaluation instance (what models and the harness consume)

`instances.jsonl` has one row per item × condition. It is materialized at freeze time and hashed:

```json
{ "instance_id": "action_device-0007-L3::prior_1", "item_id": "action_device-0007-L3",
  "scenario_id": "action_device-0007", "split": "test", "condition": "prior_1",
  "context_turns": [{ "speaker": "assistant", "text": "Sounds good. I'm here if you need anything." }],
  "context_source_scenario_id": "action_device-0007",
  "utterance": "I can see my breath in here.", "form_level": "L3", "stage1_label": "indirect_request",
  "intent": "action_device", "slots": { "device": "thermostat", "target_state": "warmer" },
  "gold_request": "Turn the heat up.", "is_contrastive": true, "contrast_group_id": "action_device-0007-c1",
  "origin": "llm", "generator_family": "family_a", "benchmark_version": "1.0.0" }
```

The gold labels do not change across conditions. In `none` and `mismatched`, a twin pair is
unresolvable by design: an utterance-only model can score at most 50% on twins. That ceiling is part
of the artifact probe (§3.3).

---

## 3. Proposed generation pipeline

### 3.1 Stages

```text
Phase 0 lock ─► S0  Intent cards + assistant capability card + level rubric (versioned)
                S1  Human seed scenarios ─────────────► prompt-exemplar pool (train/dev only)
                S1b Held-out human scenarios ─────────► test only; never shown to any generator
S2  Scenario frames (LLM, JSON): intent, slots, setting, twin reading
S3  Contexts (LLM): support + contrast, fixed length, cue position assigned by the sampler
S4  Utterances (LLM): L0-L3 ladder + twin(s) + distractors; over-generate k=3 per slot
S5  Automatic filters (drop or flag; see 3.2)
S6  Selection: 1 per level, balance cue position x generator x twin type per intent x level
S7  Human review: accept / revise / reject  (origin -> llm_human_edited on any edit)
S8  Blind annotation of test (without context FIRST, then with context; double only once a
    second annotator exists, see Q9)
S9  Adjudication, kappa report, context-dependence measure
S10 Split by split_group; assign mismatch donors within split
S11 Materialize 4 conditions -> freeze: version, SHA-256 manifest, datasheet (Gebru et al.)
```

- **S0.** Each intent card contains a one-line definition, key slots, include/exclude boundary
  examples, and a **keyword lexicon** (intent words, slot names and values, and their synonyms) used by
  the L3 leakage filter. The capability card is a short list of what the assistant can do. It is
  shown identically to generators, annotators, and evaluated models (see Q2).
- **S1/S1b.** Humans write from the intent cards only. S1b is written before the author has seen
  generated items, or by someone not involved in prompt design, so it is a clean human-written
  comparison set (decision #7).
- **S2–S4.** One structured-output call per stage, validated against the schema, with the rendered
  prompt hashed into `provenance`. Generation parameters are fixed per template version. Exemplars
  are sampled only from S1 seeds of the same split group or train, never from test.
- **Where things live** (proposal; no `.gitignore` change needed):
  - Raw LLM requests and responses go under `data/interim/generation/` (ignored, large, hash-referenced).
  - Accepted scenarios go in `data/benchmark/scenarios.jsonl` (tracked, our own license).
  - Prompt templates go under `configs/generation/`.
  - Frozen releases go under `data/benchmark/release/v<N>/` with a `SHA256SUMS` file.

### 3.2 Automatic filters

Hard failures are dropped and regenerated. Soft failures are **flagged for human review, never
silently dropped**, because auto-dropping whatever a model finds odd biases the benchmark toward
model-easy items.

| Filter | Rule (initial thresholds; tune on the pilot) | Action |
|---|---|---|
| Schema | Record validates against §2.2 plus the §2.4 invariants | Drop, then regenerate |
| Exact duplicate | Normalized text (lowercase, strip punctuation, collapse spaces) equals another accepted utterance, except by-design twins | Drop |
| Near duplicate | Character-3-gram Jaccard ≥ 0.8 against any utterance in *another* scenario. Within a scenario, adjacent levels ≥ 0.9 means the levels aren't distinct. | Flag |
| Source overlap | Near-duplicate of DIRECT / Circa / IndirectRequests text (licenses) | Drop |
| | Near-duplicate of CLINC / MASSIVE | Keep, but require `derived_from` and attribution |
| Length | Utterance 2–25 words. Context turn 3–30 words. Per intent, median L3 length ≤ 2× median L0 length. | Drop if out of band. Flag the ratio |
| **L3 keyword leakage** | An L3 utterance contains any lexicon term of its intent (lemma match) | Drop, then regenerate |
| L2 element check | An L2 utterance contains **no** request element (device, object, slot value) | Flag (likely L3) |
| Form-level heuristics | L0 must match imperative / want patterns. L1 must match query-preparatory patterns ("can/could/would you", "is it possible", "would you mind"). L2/L3 must match neither. | Flag mismatches |
| Context leakage | The support history contains the L0 request string, its verb+object bigram, or an assistant offer of the exact action ("Want me to turn up the heat?") | Flag |
| Twin validity | A model from a family that did **not** generate the item labels the twin with its contrast context | Disagreement → review priority only |

### 3.3 Surface-shortcut audit (feeds the Phase 3 artifact probe)

This runs on every candidate batch and again at freeze time. It reports per `stage1_label`, per
`form_level`, and per generator:

- **Cue rates:** length; `?` / `!`; "please"; second-person *you*; first-person *I*; negation;
  modals; casing; trailing punctuation; emoji. Any cue whose rate differs by more than 15 points
  between labels within a level gets flagged, and the selection step (S6) rebalances it.
- **Lexical association:** chi-square / PMI of the top unigrams and bigrams with `stage1_label`, and
  with `intent` within L3.
- **Utterance-only probe:** a scenario-grouped, cross-validated TF-IDF + LR classifier on utterances
  alone. Its L3 intent accuracy is compared with the **human no-context accuracy** from S8. If the
  probe beats humans who can't see context, it is reading artifacts rather than meaning, so fix the
  data before Phase 3.
- **Generator-identity probe:** if two generator families are used, a classifier that predicts the
  generator from the text is fine *only if* generator is balanced across intent × level × label.
  S6 enforces that balance.

### 3.4 Human review and annotation

- **S7 review checklist (per scenario):**
  - naturalness (1–3)
  - `form_level` correct under the rubric
  - intent and slots correct
  - twin plausible in its contrast context
  - context not leaking the request
  - no harmful or identifying content

  Any edit sets `origin: llm_human_edited` and appends an `edits` entry. Record the time spent per
  scenario so later cost estimates are real numbers.
- **S8 blind annotation:** annotators see the utterance plus the capability card, but not the intended
  labels. Collect the **without-context pass first**, or use different annotators for each pass, so
  no-context judgments aren't contaminated by having seen the context. These passes produce κ (for
  level, intent, and Stage 1), the empirical context-dependence measure, and the human baseline.
- **IRB:** confirm with the professor or IRB office before anyone other than the author provides
  judgments (see research plan, Phase 2).

### 3.5 Keeping the human-written subset separate

- It is written in S1b under the rules above, stored with `origin: human`, and never used as a
  prompt exemplar. The S1 seeds that *are* exemplars stay in train/dev.
- It goes through the same filters and review.
- Report it (a) as its own test slice and (b) as a covariate (`origin`) in the mixed-effects model.
  That makes "does the model do better on LLM-written items?" a measured quantity.

### 3.6 Size targets

- **From the plan:** about 8 intents × 40 scenarios ≈ 320 scenarios. With 4 levels plus contrastive
  items that is about 1,500 utterances (1,280 ladder items plus about 220–320 twins), run under
  4 context conditions (~6,000 instances). Aim for **≥ 30 test items per intent × level cell**.
- **The tension:** each scenario contributes one item per level, so 30 test items per cell needs
  **≥ 30 test scenarios per intent**. At 40 per intent, that leaves 10 for train and dev together.
  Q6 proposes 55 per intent (30 test / 8 dev / 17 train):

  | Measure | Count |
  |---|---|
  | Scenarios | 440 |
  | Utterances (≈5.5 per scenario) | ≈2,400 |
  | Test utterances | ≈1,300 |
  | Test instances (4 conditions) | ≈5,300 |

- **Over-generation:** generate about 1.5× the scenarios and k = 3 candidates per slot, so the filters
  and selection have room. Expect to review about 2,400 items at 20–40 s each, roughly 15–25 hours,
  before double annotation. These are rough estimates to re-check after the pilot.

---

## 4. Open questions (blocking generation)

Each question lists options and a recommended default. The decision log below records the user's
answers; the options are kept for reference.

### Decision log (2026-09-25)

Answers were relayed by the coordinator. Status key:

- **Decided**: chosen by the user.
- **Provisional**: my recommended default, provisionally accepted (no objection); revisit before generation.
- **Deferred**: not decided yet.

| Q | Status | Answer | Consequences / notes |
|---|---|---|---|
| Q1 intents | **Decided** | **E, the proposal's 8 intents**, chosen with the clarification caveat known. Working ids: `information_seeking`, `recommendation`, `planning_scheduling`, `troubleshooting`, `navigation`, `advice_support`, `clarification`, `action_device`. | Seed data from CLINC/MASSIVE is thin for troubleshooting and navigation and absent for advice/support and clarification, so hand-written seeds carry those intents. **Open item, awaiting the user's confirmation:** keep `clarification`, but treat it as exploratory, exclude it from the confirmatory H2 test, and report it separately (pre-registered in `analysis_plan.md`). It also can't follow the Q7 cue-position counterbalance, because its referent is usually the immediately preceding assistant turn. |
| Q2 capability card | Provisional | A, revised for E (see Q2) | Adds maps/directions and device diagnostics. Drops messaging and bookings. |
| Q3 L1 label | Provisional | A: L0 → `direct_request`, L1–L3 → `indirect_request` | |
| Q4 generator LLMs | **Deferred** | No confirmed API key or 4090 access yet | **The Phase 1 pilot is hand-written only.** Generator choice is revisited before Phase 2. Options and the recommendation (B) are kept below. |
| Q5 human scenarios | **Deferred** (by the user) | n/a | Options unchanged. |
| Q6 scenarios per intent | Provisional | A: 55 per intent (440; 30 test / 8 dev / 17 train) | Includes `clarification`. If it is dropped instead of kept as exploratory, the total becomes 385. |
| Q7 history length | Provisional | B: fixed 6 turns, cue position counterbalanced | See the Q1 note on `clarification`. |
| Q8 `no_request` | Provisional | B: twins plus form-matched distractors (about 25% of Stage 1 items) | Option D (different-intent twins) is not adopted yet. |
| Q9 annotation | **Decided** | The user annotates alone for now | The Phase 1 κ ≥ 0.6 pilot still needs a **second labeler for about 50 items**. Whether that needs IRB review is an **open question for the user's professor**. Test-set double annotation and the non-author human baseline stay unresolved until someone else is available. |
| Q10 budget/access | **Deferred** | Same reason as Q4 | Same consequence as Q4. The token estimate and options are kept below. |
| Q11 third-party text | Provisional | A: release only our own text, CC BY 4.0 | |

**Q1. Which 8 intent categories?** _(Decided: E. See the decision log.)_
Option A below was my original recommendation and was **not chosen**. It is kept for the record.
Grounding: CLINC150 = C, MASSIVE = M, IndirectRequests = IR; "LLM-assistant" means no source covers it.

| # | Intent id | Definition (one line) | Key slot | L3 example | Grounding |
|---|---|---|---|---|---|
| 1 | `device_control` | Change the state of a device or the environment (temperature, lights, volume, appliances). | device + target state | "I can see my breath in here." | M `iot_*`, `audio_volume_*`; C `smart_home`, `change_volume` |
| 2 | `reminder_scheduling` | Create or change a reminder, alarm, timer, or calendar entry. | time / event | "I keep forgetting my pills at night." | M `alarm_set`, `calendar_set`; C `reminder`, `timer`, `schedule_meeting` |
| 3 | `information_lookup` | Retrieve a current, checkable fact (weather, traffic, hours, prices, status). | topic | "No idea if I'll need a jacket today." | M `weather_query`, `transport_traffic`, `qa_*`; C `weather`, `traffic`, `flight_status` |
| 4 | `recommendation` | Suggest options for the user to choose from (food, places, media, recipes). | category + constraint | "There's nothing in the fridge and I'm starving." | M `recommendation_*`, `takeaway_query`; C `restaurant_suggestion`, `meal_suggestion`; IR Restaurants/Movies |
| 5 | `booking_ordering` | Commit to a reservation or purchase on the user's behalf (table, ride, ticket, delivery). | service + constraint | "My flight lands at eleven and the trains stop at ten." | M `takeaway_order`, `transport_taxi`/`ticket`; C `book_flight`, `restaurant_reservation`, `uber`; DIRECT / IR domains |
| 6 | `communication` | Send, or relay, a message to a specific person (text, email, call, post). | recipient + gist | "Mom still thinks I'm coming Sunday." | M `email_sendemail`, `social_post`; C `text`, `make_call` |
| 7 | `writing_help` | Draft, rewrite, or edit text that the user will use themselves. | document type | "Forty applications and not one reply." | LLM-assistant (none) |
| 8 | `preparation_coaching` | Help the user practice, prepare, or plan for an upcoming event (interview, exam, talk, trip). | event | "Tomorrow's a big day and I'm so not ready." | LLM-assistant; the plan's interview example |

Boundary pairs that A would have needed to pilot: `recommendation` vs `booking_ordering` (suggesting vs.
committing); `communication` vs `writing_help` (sending vs. drafting); `writing_help` vs
`preparation_coaching`; and `device_control` vs media playback (volume). Alternates if a pair fails
κ: `explanation` (C `definition`, M `qa_definition`), `list_management` (M `lists_*`, C
`shopping_list`, `todo_list`), `media_playback` (M `play_*`).

- **A.** The mixed list above. (Originally recommended; not chosen.)
- **B.** Voice-assistant-only (8 MASSIVE scenarios such as iot, alarm, weather, music, email, takeaway,
  lists, calendar).
- **C.** LLM-assistant-heavy (writing, coding, explanation, advice, planning, …).
- **D.** Six intents, merging the riskiest boundary pairs.
- **E. The proposal's own list. CHOSEN.** The course proposal (`docs/Pragmatic_Intent_Detection_Proposal_Plain .pdf`)
  names "approximately six to eight" categories: "information seeking, recommendation,
  planning/scheduling, troubleshooting, navigation, advice/support, clarification, and action/device
  requests". Grounding for each, checked against the downloaded data:

  | Proposal intent | CLINC150 / MASSIVE grounding |
  |---|---|
  | information seeking | Strong. C `weather`, `traffic`, `time`, `definition`, `exchange_rate`, `flight_status`; M `qa_*`, `weather_query`, `news_query`, `datetime_query`. |
  | recommendation | Strong. C `restaurant_suggestion`, `meal_suggestion`, `travel_suggestion`; M `recommendation_events` / `_locations` / `_movies`. |
  | planning/scheduling | Strong. C `schedule_meeting`, `calendar`, `reminder`, `alarm`, `timer`, `todo_list`; M `calendar_*`, `alarm_*`, `lists_createoradd`. |
  | troubleshooting | Partial. Only C support-style intents (`card_declined`, `sync_device`, `reset_settings`, `jump_start`, `find_phone`); M none. |
  | navigation | Moderate. C `directions`, `distance`, `current_location`, `share_location`; M only part of `transport_query` (66 of 314 utterances mention directions or routes). |
  | advice/support | None as a category. C has only narrow how-to intents (`improve_credit_score`, `oil_change_how`); advice-like phrasing in M is scattered across `weather_query` and `cooking_recipe`. |
  | clarification | Nearly none. C `repeat` only ("i didn't hear you please repeat"), which asks for repetition, not re-explanation. M none: its "repeat" utterances are `music_settings` or volume commands. |
  | action/device requests | Strong. C `smart_home`, `change_volume`, `text`, `make_call`, `uber`; M `iot_*`, `audio_volume_*`, `play_*`, `email_sendemail`, `takeaway_order`. |

  Overlap with A: four intents match (information seeking ≈ `information_lookup`, recommendation,
  planning/scheduling ≈ `reminder_scheduling`, action/device ≈ `device_control`). E adds
  troubleshooting, navigation, advice/support, and clarification. A adds booking, communication,
  writing help, and preparation coaching.

  **Risk with `clarification`:** asking the assistant to re-explain its own previous turn ("Wait,
  what do you mean?", "I'm lost") is context-dependent at *every* indirectness level. Even L0
  "Explain that again" can't be resolved without the prior turn, because "that" points into it. Its
  context benefit comes from reference to the assistant's turn, not from indirectness. That can inflate
  the context × indirectness interaction (H2) for reasons unrelated to indirectness. It is the same
  trap as defining indirectness by context-need (plan decision #2), entering through the intent
  instead of the level. Suggested handling (**open item, awaiting the user's confirmation**): keep
  `clarification` as an exploratory intent that is excluded from the confirmatory H2 test and
  reported separately (pre-registered in `analysis_plan.md`).

*Why E:* it is the user's own framing from the proposal, and the user chose it knowing the
clarification caveat. What it costs:
- Three intents (troubleshooting, advice/support, clarification) have little or no seed data in
  CLINC/MASSIVE, so their seeds must be hand-written.
- The benchmark loses A's overlap with DIRECT's booking domain for transfer evaluation.
- The `clarification` open item above still needs an answer.

**Q2. What can the assistant do? (the capability card)** _(Provisional: A, revised for Q1-E.)_
- **A.** A text-chat assistant whose tools cover the chosen intents and nothing else. **Recommended.**
  It has:
  - web and knowledge lookup (information seeking)
  - recommendations
  - calendar, reminders, and lists (planning/scheduling)
  - device and settings diagnostics with step-by-step fixes (troubleshooting)
  - maps, directions, and live traffic (navigation)
  - smart-home and device control (action/device)

  Advice/support and clarification of its own answers need no tool. **Messaging and bookings are
  dropped.** Every listed capability makes more hints readable as requests, and a capability with no
  target intent would produce requests we can't label. That would blur the `no_request` twins.
- **B.** A voice assistant only (device-centric).
- **C.** A chat-only LLM with no tools, so no action/device or navigation intents.
- **D.** Leave it implicit.

*Why A:* whether "It's freezing in here" is a request depends on what the listener can do. Stating
that once, identically for generators, annotators, and models, removes a major source of annotator
disagreement.

**Q3. Which Stage 1 label does L1 ("Can you turn the heat up?") get?** _(Provisional: A.)_
- **A.** CCSARP-faithful: L0 → `direct_request`, L1–L3 → `indirect_request`. **Recommended.**
- **B.** Pragmatic: L0–L1 → `direct_request`, L2–L3 → `indirect_request`.
- **C.** A 4-way Stage 1 (direct / conventional / hint / none).

*Why A:* it matches the CCSARP grounding that reviewers will check. Because `form_level` is stored
separately, B can be reported as a robustness check with no relabeling.

**Q4. Which LLM(s) generate candidates?** _(Deferred: no confirmed API or 4090 access. The Phase 1 pilot is hand-written only.)_
- **A.** One closed API family.
- **B.** Two families (for example one closed API family plus one open-weight family), balanced
  across intent × level, with the generator recorded on every item. **Recommended.**
- **C.** Open-weight only, run on the 4090.
- **D.** Two families generate, and a third family is used only for twin validity and review routing.

*Implications for decision #7:*
- Every generator family must also be evaluated, and generator-matched vs. mismatched results must
  be reported. With B the generator × evaluated-model interaction is estimable.
- IndirectRequests is GPT-generated. If a GPT model also generates our data, GPT's advantage on both
  is confounded.
- Check each provider's terms on using outputs to train models (we fine-tune encoders, and maybe a
  QLoRA 7–8B), and the open-weight license terms for derived data.

*Why B:* it turns decision #7 from a limitation into a measured effect for about the cost of a
second prompt adaptation.

**Q5. How many hand-written scenarios, and how are they split between seeds and held-out?** _(Deferred by the user.)_
- **A.** 5 seeds per intent (the pilot only); everything else is generated.
- **B.** 8 seeds per intent (prompt pool, train/dev) plus 8 held-out human test scenarios per intent,
  for 128 human scenarios. **Recommended.**
- **C.** 10 + 10 per intent (160).
- **D.** At least 50% human-written.

*Why B:* the held-out human slice (about 320 test items) is large enough to compare human-written and
generated items with confidence intervals. Seeds used in prompts must never reach test. At about
10–15 minutes per scenario, that is roughly 20–30 hours of writing.

**Q6. How many scenarios per intent, given ≥ 30 test items per intent × level?** _(Provisional: A.)_
- **A.** 55 per intent (440 in total; 30 test / 8 dev / 17 train). **Recommended.**
- **B.** Keep 40, make the set test-heavy (30 / 4 / 6), and train encoders mainly on DIRECT.
- **C.** Keep 40 and write two variants per level in test scenarios (correlated items).
- **D.** Keep 40 and lower the cell target to about 20, relying on mixed-effects pooling.

*Why A:* with one item per level per scenario, the plan's numbers leave only 10 train/dev scenarios
per intent. The fine-tuned encoders need in-domain training data for a fair H3 comparison, and A
provides it for about 40% more review work.

**Q7. How long is "full history", and where does the cue go?** _(Provisional: B.)_
- **A.** A fixed 4 turns.
- **B.** A fixed 6 turns (3 exchanges, ending with an assistant turn). The cue is in the last turn for
  half the items and in earlier turns for the other half. **Recommended.**
- **C.** A variable 2–8 turns.
- **D.** Long, MultiWOZ-like histories (10+ turns).

*Why B:* a fixed length makes the mismatched condition exactly length-matched and keeps inputs at
about 150 tokens (well within 512-token encoders). Counterbalancing cue position is what makes
"1 prior turn" and "full history" differ by design rather than by accident.

**Q8. What goes into `no_request`?** _(Provisional: B.)_
- **A.** Contrastive twins only: at least one per scenario at L3, plus L2 where natural.
- **B.** Twins plus **form-matched distractors** (hint-shaped statements that request nothing, in the
  style of Circa answers), bringing `no_request` to about 25% of Stage 1 items. **Recommended.**
- **C.** B plus small-talk distractors (greetings, thanks).
- **D.** Also allow "different intent" twins (the contrast context maps the utterance to another
  intent) for up to 25% of twins.

*Why B (optionally with D):* twins alone leave Stage 1 at about 80% requests. Form-matched distractors
fix the balance without adding a class that surface features alone can detect, which small talk
would be (C).

**Q9. Who reviews and double-annotates?** _(Decided: the user annotates alone for now. See the decision log.)_
- **A.** You review everything, and one second annotator double-annotates ≥ 25% of test (the plan's
  minimum).
- **B.** You plus one second annotator double-annotate the **full** test set. **Recommended, if a
  second person can give about 10–15 hours.**
- **C.** Paid annotators (for example Prolific) for double annotation and the human baseline. This
  needs an IRB determination and a budget.
- **D.** An LLM judge as the second annotator. This is not acceptable as gold; it is fine for routing.

Also needed: who provides the with/without-context human baseline (at least 3 people who are not
authors), and whether they are available in Weeks 3–4.

*Why B:* full double annotation gives κ per cell, which reviewers ask for. The IRB question has to be
settled before any non-author judgment is collected.

**Q10. What budget and access do we have?** _(Deferred, with Q4.)_
We need to know:
- which API keys you hold (Anthropic, OpenAI, Google, other)
- a spending cap for generation, and a separate one for Phase 4 evaluation
- whether the 4090 is available for open-weight generation
- any course or university restrictions on sending data to APIs

Rough generation volume under Q6-A: about 660 scenarios (1.5× over-generation) × about 4 calls ×
2–3k tokens, or **roughly 5–10M tokens** before retries. Price it against the chosen models' current
rates.

- **A.** Small cap: generate with open-weight models on the 4090; use APIs only for evaluation.
- **B.** One API family plus one open-weight family for generation. **Recommended (default if capped).**
- **C.** Two API families.

*Why B:* it satisfies Q4-B at the lowest cost and keeps one generator fully reproducible (local
weights).

**Q11. Can third-party text appear in the released benchmark?** _(Provisional: A.)_
- **A.** Release only our own text (generated and human-written) under CC BY 4.0. Third-party
  datasets are used only for training and transfer evaluation, and are never redistributed.
  **Recommended.**
- **B.** A, plus CLINC/MASSIVE-derived seeds kept verbatim with attribution (licenses are compatible).
- **C.** Ask the DIRECT authors for permission to release DIRECT-derived items.
- **D.** Release under CC BY-SA 4.0 so Circa- or SGD-derived text can be included.

*Why A:* it sidesteps the four unresolved licenses (DIRECT, IndirectRequests, Circa, and the George &
Mamidi implicatures, whose dialogue text is third-party copyrighted). B is legal but brings in the
lowercase-text artifact from §1.
