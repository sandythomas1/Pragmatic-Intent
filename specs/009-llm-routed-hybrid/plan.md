# Plan 009: LLM interpreter and routed hybrid

## Approach

One call per distinct input gives everything. The oracle stream is a strict subset of the routed
stream with identical input hashes, so the runner asks each model one question per distinct
rendered input:
- what route is this?
- reading it as a request, what are its category and slots?

Three files come out of that one answer cache:
- the LLM's own routed file;
- its oracle file;
- through the composer, the hybrid's routed files, one per router seed and condition.

That costs about 56k calls per split instead of about 80k, and it guarantees that the hybrid and
the standalone LLM share exactly the same interpretations. As a result, any difference between
them is attributable to routing alone, which is the attribution spec 001 §4 asks for ("declare
any shared interpretation component").

The work splits along the constitution's existing seam:
- **Pure stdlib core**, testable on native Windows. This covers the prompt rendering, JSON schema,
  strict parser, cache, provenance, stream writers, prompt-selection report, composer, spend
  ledger and freeze gate. It holds all the validity-relevant logic, and it is where the tests go.
- **Thin backends**, in new uv dependency groups and imported lazily:
  - `llm`, with `vllm` pinned, for Qwen on the 5090 in the lab, where Sandy runs it;
  - `api`, with the `anthropic` and `openai` SDKs pinned, for paid runs that Sandy approves.

  Each backend implements one method: a batch of `(key, prompt, schema)` goes in and
  `(key, raw_text, usage)` comes out. Tests use a fake backend.

The schedule is fixed by the Nov 9 grid:
- Nov 2: `/spec-review` (done, R1–R14 applied), then decompose.
- Nov 2–4: implement the core, the prompt generator, the composer and the freeze run check
  (Claude).
- Nov 5: Qwen smoke test on the lab 5090 (Sandy). It fixes the backend and `max_model_len` and
  measures throughput (FR5a, FR7). It is followed by prompt selection: P1 and P2 on all dev
  records under `none`/`full`, about 22.8k distinct calls each.
- Nov 6: the full dev run (reusing the cached `none`/`full` answers), dev hybrid composition and
  the dev analysis.
- Nov 7–8: panel and freeze edits, then `freeze write`.

The API members slot in whenever OQ1 and OQ2 are resolved. If they aren't resolved by Nov 8, they
are left out of the panel, and the freeze goes ahead without them.

## Architecture

```
data/interim/stage2/{dev,test}_{routed,oracle}_inputs.jsonl   (spec 005, unchanged)
            │  verify schema + input_sha256, check oracle ⊂ routed (FR1, FR2)
            ▼
src/llm/prompt.py      render(prompt_file, record) → messages; data in a delimited block
src/llm/prompt_gen.py  p2.template.txt + p2_examples.json + pinned data/raw → outputs/llm/prompts/p2.txt (FR18)
src/llm/schema.py      main + transfer JSON schemas (closed enums) + strict parse + failure reasons (FR3, FR3b, FR5)
src/llm/preflight.py   tokenize every rendered prompt; refuse if any > max_model_len − max_tokens (FR5a)
src/llm/cache.py       append-only JSONL keyed by sha256(task|backend|model|prompt_sha|decoding|schema_sha|input_sha) (FR6)
src/llm/backends/      base.py (interface, transport/content split, retry, error sanitizing) · fake.py (tests)
                       · vllm_backend.py · anthropic_backend.py · openai_backend.py (FR5, FR7)
src/llm/spend.py       dated price table, estimate, worst-case reservation ledger, --max-usd stop (FR16)
src/llm/run.py         CLI: size | smoke | run [--sample]; writes streams + provenance (FR4, FR8, FR9, FR15)
src/llm/select.py      CLI: select-prompt (dev only) → outputs/llm/selection/<system>/report.json (FR9, T11)
            │
            ├──► outputs/stage2/<llm>/{dev,test}/{routed,oracle}.jsonl, transfer.jsonl, provenance.json
            ▼
src/llm/compose.py     hybrid = router predictions.jsonl × interpreter rows (FR11, FR12, FR15b)
            │  reads outputs/stage1/deberta-v3-large/train-<c>/seed<s>/{config.resolved.json,metrics.json,predictions.jsonl}
            ▼
outputs/stage2/hybrid/<split>/train-<c>/seed<s>/{routed,oracle}.jsonl + compose provenance
            ▼
configs/analysis/inputs-<split>.toml → src.evaluation.stage2 score / src.analysis run (unchanged)

src/data/freeze.py                     + check_llm_run(frozen, system, files, rendered_prompt_sha, llm_model) (FR15)
configs/llm/qwen2.5-7b-instruct.toml   backend, HF repo + commit, decoding, max_model_len, gpu_memory_utilization
configs/llm/prompts/p1.txt             instructions only; committed before any dev run (FR9)
configs/llm/prompts/p2.template.txt    P1 + {examples} placeholder; no corpus text (FR18)
configs/llm/prompts/p2_examples.json   train example_ids + draw seed; no text (FR18)
configs/llm/prompts/t1.txt             transfer prompt, fixed, no selection (FR3b)
outputs/llm/prompts/p2.txt             rendered, git-ignored; its hash is checked at run time (FR18)
configs/llm/prices.toml                dated, Sandy-confirmed; used only by estimate/ledger
configs/freeze/freeze-v1.toml          code += src/llm/*.py; llm/hybrid recipe files + llm_model (FR13, FR14)
configs/analysis/analysis-v1.toml      panel + h3 family edits; hybrid streams = routed, oracle (FR13)
```

Key details:
- **Slot keys** are a closed enum built from the spec 005 reference vocabulary: the MultiWOZ
  `domain.slot` names seen in `Inform`/`Request` acts on train. Free-form object keys can't be
  constrained in JSON Schema, so the model returns `slots` as an array of `{slot, value}` pairs
  with `slot` as an enum, and the parser turns that into the contract's object. A duplicate slot
  in the array is invalid.
- **Prompt rendering** is a plain-text template with `{context}` and `{target}` placeholders.
  Corpus text is inserted after the instructions, inside a fenced block labelled as data, with a
  line telling the model that any instructions inside it are part of the dialogue.
- **P2 few-shot examples (FR18).** These are drawn once, with a fixed seed, from train examples
  that have a spec 005 reference. Only their `example_id`s and the seed are committed
  (`p2_examples.json`). `prompt_gen.py` renders the examples' text and references into the
  git-ignored `outputs/llm/prompts/p2.txt`, reading the pinned `data/raw` through
  `build_examples(items, "train")` and the reference module. The output is byte-deterministic,
  with sorted keys and `\n` line ends. The freeze pins the template, the ID list and
  `src/llm/*.py`. The runner hashes the rendered file into the cache key and provenance, and on
  test checks it against the pin (FR15). Train has no inspection constraint. If a clean train
  reference path doesn't exist, P2 is dropped and P1 is the only variant; a single variant is a
  valid fixed procedure.
- **Decoding.**
  - Qwen: vLLM greedy decoding, `max_tokens` 256, guided JSON decoding with the schema, and
    automatic prefix caching (the instruction prefix is shared). Revision and dtype (`bfloat16`)
    are pinned.
  - API: temperature 0 and the provider's structured-output mode, with the same schema.
    Anthropic prompt caching is on for the static prefix.
  - The schema has no `paraphrase` field, which keeps outputs short and truncation rare (R12).
- **`max_model_len` (FR5a)** is the worst case, never a percentile. That is the maximum token
  count, under the pinned Qwen tokenizer, of the 350-word-budget inputs on train and dev, plus
  the longest prompt prefix (P2), plus 256, rounded up to the next 512. The smoke test computes
  it and the recipe records it. The test split's guarantee is the renderer's 350-word bound, and
  the preflight refuses any test prompt over the limit before a call. Dev words: p50 34, p90 183,
  max 350.
- **Failure classes (FR5).** `backends/base.py` owns retry. Transport errors (connection,
  timeout, 429, 5xx, worker crash) get up to 5 attempts with exponential backoff (base 2 s, cap
  60 s, full jitter, honouring `retry-after`), then a resumable stop. Content outcomes (parse or
  schema failure, refusal stop reason, `length` finish reason, empty output) get exactly one call,
  then an `invalid` row with a reason code. Exceptions are reduced at the interface to class,
  status, request ID and key hash. The full body goes to the git-ignored raw log.
- **Transfer (FR3b)** reuses the runner, cache, backends and provenance. The changes are the task
  name (`transfer`), prompt `t1.txt` and a per-record schema whose `value` enum is the record's
  candidates plus `<ambiguous>`. vLLM guided decoding and both API structured-output modes
  accept a per-request schema.
- **The cache key** is SHA-256 of the canonical JSON of `{task, backend, model_id, prompt_sha256,
  decoding, schema_sha256, input_sha256}`. Here `prompt_sha256` is the rendered prompt's hash,
  and for transfer `schema_sha256` is the per-record schema's hash. Duplicate inputs (56,862
  records, 56,174 distinct hashes on dev) share an entry.
- **Prompt selection (FR9)** composes each variant's `none`/`full` outputs with the five dev
  `deberta-v3-large` router runs, scores them with `src.evaluation.stage2`, and computes the
  hybrid's `request_interpretation` with the spec 007 endpoint definition. It writes aggregates
  only to `outputs/llm/selection/report.json`. The selection code calls the same composer as
  FR11, so selection and reporting can't diverge.
- **Composer router roles** follow `src/analysis/inputs.py` FR6. Each run's `config.resolved.json`
  and `metrics.json` are read and checked against the declared `(train_condition, seed)` and the
  split's `eval_split`.
- **The test gates** reuse `src.data.freeze.require_freeze` (spec 008).
  - Runner: a new `check_llm_run` compares each recipe file's `text_sha256`, the rendered-prompt
    hash and `llm_model` with the frozen `recipe.<system>.*` pins, before it imports a backend.
    The existing `check_run` is Stage 1 only.
  - Composer: it calls `check_run` for every router run as system `deberta-v3-large`, and
    `check_llm_run` for the identity the interpreter run recorded in its provenance.

## Alternatives Considered

- **Separate detection and interpretation calls, or interpret only routed items.** Rejected:
  that doubles the calls, makes the hybrid's interpretations differ from the LLM's (which
  confounds routing with interpretation), and ties the interpreter's work to one router seed.
  One cached answer per input serves all five seeds.
- **The LLM sees the router's label in its prompt.** Rejected: the interpretation would depend on
  the route, so the oracle stream would no longer be route-independent (spec 001 §4 "Oracle
  Stage 2"), and each router seed would need its own calls.
- **Committing the rendered P2 prompt** so its git hash covers the examples. Rejected: it
  puts unlicensed DIRECT text in git (constitution). An ID list plus a deterministic generator
  gives the same pinning without the text.
- **Selecting the prompt on the standalone LLM's `request_interpretation`, or on oracle
  interpretation.** Rejected (Sandy, 2026-11-02): the standalone metric mixes in Qwen's own
  routing, which the hybrid never uses. Oracle interpretation ignores routed non-request
  traffic, so it is not the reported endpoint. Selecting on the primary system's own dev
  endpoint matches what is reported.
- **Selecting on a seeded dev sample.** Kept only as a throughput fallback: Qwen is local and
  free, and all of dev under `none`/`full` removes sampling noise and makes the 0.01 tie margin
  meaningful.
- **Sizing `max_model_len` from a percentile and truncating or invalidating the tail.** Rejected:
  the long tail is almost all `full`/`one`/mismatched, so any length failure would land on the
  treatment arm of the H2 contrast.
- **Free-text JSON with retry-on-failure.** Rejected: retries on invalid output are hidden prompt
  engineering, and they make the invalid rate depend on the retry budget. Constrained decoding
  plus a counted `invalid` row is the honest measure (FR5).
- **Batch APIs (Anthropic Message Batches, OpenAI Batch).** Deferred: they halve the cost but
  turnaround is asynchronous, up to 24 h, and they need a second code path. Add them only if
  `estimate` under the chosen scope (OQ2) exceeds the cap (OQ3).
- **Tuning a prompt per API model.** Rejected for this deadline, and because it would make H3
  partly about prompt effort. It is a disclosed limitation.
- **FP8 or 4-bit Qwen to save memory.** Rejected: bf16 weights (about 15 GB) plus the KV cache
  for short inputs fit in the roughly 22 GB left on the shared card, and quantizing would change
  the model being reported.
- **Retraining a router with saved weights for a hybrid transfer line.** Rejected: it would mean
  new GPU runs for a secondary, LLM-generated table. The hybrid's transfer stream is dropped
  instead.

## Tradeoffs

- **Reproducibility is weaker than the rest of the repo.** GPU batching and API models are not
  bit-reproducible on rerun. We treat the cache and prediction files as the artifacts and hash
  them, and the paper states it. The composer and validators remain byte-deterministic, which is
  where the validity logic lives.
- **The "as if a request" interpretation** makes the standalone LLM's routed file slightly
  artificial: its interpretation exists even when it said `no_request`, and is then nulled. This
  is deliberate, because the alternative couples interpretation to routing.
- **One shared prompt chosen on Qwen** may under-serve the frontier models, which biases H3
  slightly toward the reference system. It is disclosed, and it is cheap.
- **Two new dependency groups**, `vllm` especially, add lock and CUDA-pin risk. They're isolated
  from the stdlib core, and the suite must pass without them.
- **Claude writes model code** (FR17). It is faster, but it reverses the constitution's
  ownership seam. Mitigations: Sandy reviews every diff, the selection procedure is fixed before
  any run, and the paper discloses it.
- **Selecting on the hybrid** couples prompt choice to the dev routers. A prompt that is good on
  exactly the examples the router routes as requests wins. That is the intended behaviour for
  the primary system, but it makes the chosen prompt slightly less "neutral" for the standalone
  LLM and the API members. It is disclosed.
- **One interpreter pass under five router seeds.** The hybrid's seed spread understates its
  variance. It is disclosed; no extra runs.
- **Rendered P2 lives outside git.** A fresh clone must run the generator before a P2 run. The
  runner refuses if the rendered file is missing or its hash differs from the pin.

## Risks

- **vLLM vs the lab CUDA/torch stack.** vLLM wheels pin their own torch, which may conflict with
  the `gpu` group's cu128 torch. *Mitigation:* a separate `llm` group, installed in its own venv
  on the lab machine. The first lab step is a 20-record smoke test (AC-009-13). Fallback: the
  `transformers` generate backend with the same interface, which is slower but enough for 56k
  short inputs. Using the fallback is a method change. Whichever backend passes the smoke test is
  fixed in the recipe **before** prompt selection and used for every Qwen run (FR7). The fallback
  keeps constrained decoding through a pinned logits-processor library in the `llm` group, or
  else unconstrained decoding is disclosed.
- **The shared GPU runs out of memory.** *Mitigation:* `gpu_memory_utilization` and the
  worst-case `max_model_len` (about 1k tokens, see Key details) go in the recipe. The KV cache per
  sequence stays small at that length. The resumable cache makes an OOM restart lossless.
- **Train references for few-shot examples.** The spec 005 exporter accepts only dev/test.
  *Mitigation:* `prompt_gen.py` builds them through `build_examples(items, "train")` and the
  existing reference module (FR18). If that is not clean, P2 is dropped and P1 is the only
  variant.
- **A high invalid rate** under constrained decoding would mean a schema/prompt mismatch, not
  model weakness. *Mitigation:* the smoke run reports the invalid rate, and above 2% on dev we fix
  the schema/prompt before selection. That is disclosed as a dev-time change.
- **Contamination.** Qwen and the frontier models have likely seen MultiWOZ, and perhaps DIRECT.
  This can't be mitigated, so it is disclosed as a limitation. It affects absolute levels more
  than the within-item context contrast.
- **OQ1/OQ2 stay unresolved past Nov 8.** *Mitigation:* the API members are left out of the panel
  before `freeze write`. A later addition would be a dated amendment and is reported as
  exploratory.
- **The H2 test is null.** Encoder dev evidence suggests a small matched context benefit. This is
  acceptable under spec 001 §3. It is not a reason to change the primary system after seeing dev
  hybrid numbers. The primary system is fixed now, before any hybrid output exists.
