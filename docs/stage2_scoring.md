# Option A interpretation and transfer tools

Spec [005](../specs/005-scoring/spec.md) provides local input exporters and deterministic
scorers. Sandy owns model code and model runs. There are no model/API calls in these tools.
Use Python 3.12 from the repository root (`py -3.12` on Windows; `python` in the WSL environment).

## Main benchmark: weak act recovery

References come from MultiWOZ user acts attached to DIRECT examples, not new human annotation:

- `category`: the single `cat-v1` primary category, in its fixed precedence order.
- `slots`: stated `Inform` values, keyed by lowercase `domain.slot`, such as `hotel.people`.
- `requested_slots`: `Request` slot names, such as `hotel.phone`; no value is invented for `?`.
- Empty/unknown values are not required. Conflicting values for one act slot are explicitly
  excluded from interpretation while the examples remain in detection. Coverage found 2 such
  dev examples and 8 test examples. A missing category is likewise excluded only from interpretation.

These scores measure observed act recovery, not complete execution parameters or free-paraphrase
adequacy. Multiple acts reduce to one primary category while retaining all observed slots.
DIRECT's paraphrase/type labels and their borrowed act references are weak supervision.

Prepare separate complete streams, using spec 004's renderer and genuine/mismatch membership:

```bash
python -m src.evaluation.stage2 inputs --split dev --mode routed --out data/interim/stage2/dev_routed_inputs.jsonl
python -m src.evaluation.stage2 inputs --split dev --mode oracle --out data/interim/stage2/dev_oracle_inputs.jsonl
```

Both files have already been prepared locally on 2026-10-18. A record carries `example_id`,
`condition`, `context`, `target`, renderer version and input hash. It carries no acts or reference
fields. The oracle stream contains every in-scope weak-indirect example, even if a detector will
miss it. The routed stream contains direct, indirect and non-request examples. No-donor examples
appear under `none/one/full`, not under mismatch conditions. Text exports are restricted to
git-ignored `data/interim/` or `outputs/`.

For **each** record, the model runner writes this structured prediction (invented example):

```json
{"example_id":"D_t02:indirect","condition":"none","prediction":"indirect","category":"booking","slots":{"hotel.people":"two"},"requested_slots":[],"paraphrase":"Reserve a room for two people."}
```

`prediction` is `direct`, `indirect` or `no_request`. `category` is a `cat-v1` category
(`info_seeking`, `booking`, `travel`, `recommendation`, `no_request`) or null. `slots` and
`requested_slots` are required even when empty. `paraphrase` is optional, at most 500 characters,
and is not scored or copied to metrics. For non-requests, null or `no_request` is an acceptable
category when the slot fields are empty. A claimed category or slot on a non-request is separately
counted as unsupported interpretation. Preserve malformed model outputs locally, and emit this
explicit failure record so the example stays in the denominator:

```json
{"example_id":"D_t02:indirect","condition":"none","invalid":true}
```

Score the routed and oracle files separately, with the same requested conditions:

```bash
python -m src.evaluation.stage2 score --split dev --predictions outputs/stage2/routed.jsonl --oracle-predictions outputs/stage2/oracle.jsonl --out outputs/stage2/metrics.json
```

Use `--conditions none full` when those are the only two conditions produced; omitting an
entire requested condition fails validation. Missing/extra/duplicate rows and malformed schemas
abort before replacing an existing report. `--rules-version auto-v2` explicitly selects the
provisional new level slices; the default is still v1. Stage 1 rescoring accepts the same flag.

Reports include category accuracy, exact category-plus-slot success, micro slot precision/recall
with their counts, invalid counts, request recall, non-request false positives, unsupported
interpretations and excluded-reference counts. Slot normalization `slot-norm-v1` covers
case/spacing/apostrophes, number words for counts, centre/price aliases and clock formats.
It does not fuzzy-match names or infer values. Zero denominators are null, not perfect scores.

Oracle interpretation ignores the oracle record's detector field and scores all eligible
weak-indirect requests. End-to-end requires the correct weak route label and interpretation on
direct **and** indirect routes; a missed indirect route fails even if oracle interpretation
succeeds. Context contrasts use common sets, resample whole dialogues and disclose donor-cue
sensitivity. Rule/category slices are mechanical and versioned. They are descriptive, not a
confirmatory context-by-indirectness interaction test.

**This report's `end_to_end` is not the primary endpoint.** Spec 007 (D-07) computes the primary
endpoint as spec 001 §5 defines it, from the same validated rows: `request_interpretation`, a
request detected (any route other than `no_request`) AND an exact interpretation. A rule-L0
"indirect" rewrite that is read as direct and interpreted exactly therefore counts as a success.

`end_to_end` stays as the secondary `type_exact` line, and the analysis checks that its totals
equal this report's. The confirmatory interaction test is the one in
`python -m src.analysis run` (see [analysis plan](analysis_plan.md)). Give the routed and oracle
files of each system and seed in `configs/analysis/inputs-<split>.toml`.

## IndirectRequests: separate generated transfer data

```bash
python -m src.evaluation.transfer inputs --split validation --out data/interim/stage2/indirect_requests_validation_inputs.jsonl
```

The validation inputs have already been prepared locally. Only utterance, slot description and
closed candidate labels/boolean aliases are supplied, under `none` context. Situation, target
value and crowd ratings are excluded. Files must match their manifest size/SHA-256 before loading;
candidate-list strings use bounded `ast.literal_eval`, never `eval`.

For every input, emit a boolean detection and candidate value (invented example):

```json
{"example_id":"ir:validation:0001","condition":"none","request":true,"value":"False"}
```

Use `<ambiguous>` for ambiguous recovery. Boolean description aliases are accepted by position;
an out-of-candidate value or null is a scored failure. Invalid outputs use the same three-field
invalid record as above. Then:

```bash
python -m src.evaluation.transfer score --split validation --predictions outputs/stage2/transfer.jsonl --model-family gpt --out outputs/stage2/transfer_metrics.json
```

Pass an honest explicit family (`gpt`, `llama`, `claude`, `other`, etc.). The report is marked
`llm_generated_transfer`, flags GPT/OpenAI/ChatGPT-family systems, and separates ambiguous from
unambiguous items. Request recall, value recovery regardless of detection, and end-to-end recovery
have the full denominator. Every item is a request, so this dataset cannot establish precision or
specificity. Keep this table separate from the human-authored main benchmark.

Both CLIs require `--allow-test` for test input export/scoring. That flag is an explicit opt-in,
not evidence that the study freeze has happened. Before test use, finish the split audit, WSL
encoder checks, model/prompt selection and WP-08 freeze. Train/validation transfer splits are dev
checks only; the adapter provides no training integration. No test model outputs were generated
or scored during implementation. LLM-judge/paraphrase calibration still needs model outputs and
Sandy's planned ratings.

**Main-benchmark test precondition (spec 006, 2026-10-19).** On `--split test`, `src.evaluation.stage2`
`inputs` and `score` first load the committed split audit (`data/manifests/split_audit_test.csv`
and its summary). They stop if it is missing, malformed or edited, or if its recorded hashes of
`items.jsonl`, `dialogues.jsonl` or the registry's `pre_freeze` rows differ from the current
files. Rebuild it with `python -m src.data.split_audit audit`.
- With a valid audit, only primary examples are exported and scored, and predictions for excluded
  examples are ignored.
- Every condition and contrast denominator counts primary examples only.
- Each contrast adds one `primary_minus_dup` line (primary minus `dup_exact` examples), never
  crossed with `without_cue_donors`.
- The report carries a `test_audit` block: its content hash and exclusion counts.
- Dev scoring and the IndirectRequests transfer scorer are unchanged.

**LLM-judge sample (spec 006 FR17).** The ~50 Stage 2 outputs rated to calibrate the LLM judge are
drawn from **dev**. Drawing them from test needs Sandy's explicit decision before the freeze, and
their dialogues are then registered `pre_freeze`
(`python -m src.data.split_audit register --add <ID> --reason llm_judge_sample ...`).
