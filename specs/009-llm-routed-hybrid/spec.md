# Spec 009: LLM interpreter and routed hybrid

> **Phase:** Reviewed · **Status:** READY, in implementation (R1–R14 applied 2026-11-02; [tasks](tasks.md); FR17 exception applied with T1) · **Owner:** Claude (runner, composer, tests), Sandy (review, GPU runs, paid-run approval) · **Date:** 2026-11-01, revised 2026-11-02
> The *what* and *why*. Implementation detail belongs in `plan.md`. Review: [review.md](review.md).

Parent: [spec 001](../001-pragmatic-intent-study/spec.md) WP-07 and WP-09 (model side), §4 "Stage 2",
§5 primary H2 endpoint, §6 December target ("one LLM, small hybrid"), D-05, FR-15. It produces the
files that [spec 005](../005-scoring/spec.md) scores, that [spec 007](../007-analysis-error-audit/spec.md)
analyzes and that [spec 008](../008-freeze-record/spec.md) pins.

Decided with Sandy on 2026-11-01:
- **Primary system: the routed hybrid.** A `deberta-v3-large` matched-trained router plus an
  open-weights LLM interpreter. On dev, the router runs are the 2026-10-27 lab grid. On test, they
  are the WP-09 test-grid runs of the same frozen recipe and seeds. Those are retrained weights,
  because the dev weights weren't kept (R9).
- **Interpreter: `Qwen2.5-7B-Instruct`** at a pinned Hugging Face revision, run locally on the lab
  RTX 5090.
- **API panel members, if feasible:** one Claude model and one OpenAI model, both **frontier tier**,
  each a dated snapshot.
- **Claude writes the runner and composer code, with tests, and Sandy reviews it.** This reverses
  the constitution's Ownership line for this spec only (see FR17).
- **Rules stay `auto-v1`.**
- **Open:** whether DIRECT text may be sent to the APIs (OQ1), and how much the API members run
  (OQ2).

Decided with Sandy on 2026-11-02 (review R7): **the prompt is selected on the hybrid's dev
`request_interpretation`** (FR9).

## Problem

The confirmatory H2 endpoint is `request_interpretation`: a request is detected, **and** its
`cat-v1` category and slots are recovered (spec 001 §5). No system in the panel can produce it
today.

- **The encoders only detect.** The TF-IDF and DeBERTa runs output a route label only. Spec 001 §4
  says such classifiers "belong in detection tables, not an end-to-end intent comparison".
- **Placeholders block the freeze.** The analysis config's primary system and Holm family point at
  a `hybrid` that doesn't exist, and `freeze check` lists `recipe.llm` and `recipe.hybrid` as
  missing. Without them the test grid can't start on Nov 9, and the primary test and every Holm
  member would be `not_run`.
- **No LLM output pipeline exists.** The Stage 2 contract (`docs/stage2_scoring.md`) defines
  exactly what a runner must emit. Nothing yet turns rendered records into validated prediction
  rows, keeps raw outputs, records provenance or controls paid API spend.

## Goals

- One LLM runner turns the existing Stage 2 input streams into contract-valid routed, oracle and
  transfer prediction files for any panel LLM (local or API), with full provenance.
- One deterministic composer builds the hybrid's per-seed, per-condition routed and oracle files
  from the router's recorded predictions and the interpreter's outputs.
- The interpreter's prompt is chosen on dev by a procedure fixed before it runs, so that test
  results come from a recipe chosen without looking at test.
- Every LLM and hybrid recipe and all LLM code are pinned by `freeze check`/`write`. The test-split
  runner and the composer fail closed on `freeze verify` and on a run-level recipe check.
- Paid API runs can't start or exceed a cap without Sandy's explicit approval.
- The open-model path (primary system) never depends on the API questions (OQ1, OQ2).
- No corpus text enters git, and no failure mode that correlates with a condition (length,
  network) is silently turned into a scored outcome.

## Non-Goals

- **Training or fine-tuning any LLM.** Every LLM is used as-is: `untrained`, `test_time` design.
- **New routers.** The router is the existing `deberta-v3-large` recipe. RoBERTa stays on hold.
- **Scoring changes.** Spec 005 scorers and spec 007 analysis are reused as they are. The
  composed files must pass them unchanged.
- **Paraphrase adequacy or an LLM judge.** `paraphrase` stays optional and unscored (spec 005),
  and the LLM output schema leaves it out (R12).
- **A hybrid transfer line.** The router was trained on DIRECT detection only, and the dev
  weights weren't kept. IndirectRequests transfer is run by the LLM panel members only, and the
  hybrid's `transfer` stream is removed from its panel entry (FR13).
- **Per-model prompt tuning for the API members.** They reuse the prompt chosen for the
  interpreter (FR9), so the family comparison (H3) is about the model, not prompt effort.
- **Prompt selection for the transfer task.** It has one fixed prompt (FR3b).
- **Batch APIs, multi-reading policies and literary items.**

## Requirements

### Functional

**Runner**
- **FR1 Inputs.** The runner reads a spec 005 routed or oracle input file (or the IndirectRequests
  transfer inputs). It verifies each record's schema, `renderer_version` and `input_sha256` before
  making any call.
- **FR2 One call per distinct input.** The oracle stream is a subset of the routed stream with
  identical input hashes (checked on dev 2026-11-01 and 2026-11-02: 22,560 oracle keys within
  56,862 routed keys). The runner therefore makes at most one call per distinct
  `(task, model, prompt, decoding, schema, input_sha256)` and derives both streams from it. It
  must check that subset relation and refuse to run if it doesn't hold.
- **FR3 One structured answer (main benchmark).** Each call returns:
  - a route label: `direct`, `indirect` or `no_request`;
  - an interpretation: `category`, `slots` and `requested_slots`.

  The interpretation is given **as if the target were a request**, even when the model's route is
  `no_request`. That keeps the interpretation independent of the route, which the oracle stream
  and the hybrid both need. So the interpretation's `category` enum is the four request
  categories only (`info_seeking`, `booking`, `travel`, `recommendation`), never `no_request` or
  null. The output schema has no `paraphrase` field.
- **FR3b Transfer task.** IndirectRequests records (`utterance`, `slot_description`,
  `candidates`, `candidate_aliases`; no context) use their own task:
  - a single zero-shot prompt `t1`, committed before any run, with no selection step;
  - a per-record schema `{request: bool, value: enum(candidates ∪ {"<ambiguous>"})}`;
  - their own cache namespace (`task = transfer` in the key).

  Validation-split transfer runs are dev checks only.
- **FR4 Stream outputs.**
  - *LLM standalone, routed:* the model's own route. A `no_request` route gets a null category
    and empty slots.
  - *Oracle:* the interpretation for every oracle record.
  - *Transfer:* `request` and `value` from FR3b.
  - Every file has exactly one row per input record and passes the spec 005 validator.
- **FR5 Strict parsing and failure classes.** Output is constrained to a JSON schema with closed
  enums for route, category and slot keys, and bounded string lengths. Every call ends in exactly
  one of two classes:
  - **Content failure.** The response can't be parsed or fails the schema, is empty or a
    refusal, or was cut off at the output-token limit. It becomes the contract's `invalid` record,
    so the example stays in the denominator. The raw response is kept locally, and the failure is
    counted by reason. The runner never repairs or re-asks for an answer.
  - **Transport failure.** This covers a connection error, timeout, HTTP 429/5xx or a backend
    worker crash. The call is retried with exponential backoff and jitter, at most 5 attempts.
    After that the run **stops**, resumably, and writes no row. A transport failure is never
    recorded as `invalid`.
- **FR5a Length preflight.** Before any call, the runner tokenizes every rendered prompt with the
  recipe's tokenizer. It refuses to start if any prompt plus the output-token limit exceeds the
  recipe's `max_model_len` (local) or context limit (API). Inputs are never truncated, and an
  over-length input is never an `invalid` row. The local limit is sized from the worst case: the
  D-06 350-word budget's maximum token count on train and dev, plus the longest prompt prefix,
  plus the output-token limit, plus a margin. It is not sized from a percentile.
- **FR6 Resumable cache.** Responses go to an append-only local cache keyed as in FR2. A rerun
  makes no new calls for cached keys. An interrupted run resumes without duplicating rows or
  spend. A cache entry made under a different task, model, prompt, decoding, schema or input is
  never reused.
- **FR7 Backends.** There are three backends behind one interface: local `vllm` (Qwen), Anthropic
  and OpenAI. All use greedy or temperature-0 decoding with a bounded output length and the
  provider's structured-output mode. The backend is chosen by the recipe, never by data. The
  local backend that passes the AC-009-13 smoke test is fixed in the Qwen recipe **before** prompt
  selection, and it is used for every Qwen run on dev and test.
- **FR8 Provenance.** Every run writes a provenance record with:
  - backend and the exact model ID or revision;
  - the SHA-256 of the prompt template and of the rendered prompt;
  - decoding parameters, the schema SHA-256 and the input-file SHA-256;
  - code digest, git commit and `git_dirty` state;
  - start/end times;
  - call, cache, retry and invalid counts (by reason), and token usage;
  - estimated, reserved and actual spend.

  It contains no API keys and no corpus text.

**Prompt selection (dev only)**
- **FR9 Fixed procedure.** At most two prompt variants are written and committed before any dev
  run:
  - P1: zero-shot schema instructions;
  - P2: P1 plus k few-shot examples drawn mechanically, with a fixed seed, from the DIRECT
    **train** split.

  P2's committed form is a template plus a list of train `example_id`s (FR18). Both are run on
  **all dev records under `none` and `full`**. The selection metric is the **hybrid's** dev
  `request_interpretation`: compose each variant's outputs with the five `deberta-v3-large` dev
  routers (FR11), and average over the two conditions and the five seeds. That metric is neutral
  about H2. On a tie within 0.01, P1 wins. The comparison and the choice are written to a
  selection report that holds aggregates only. The API members use the chosen prompt unchanged.

  *Fallback, fixed now:* if the smoke test's measured throughput makes two full passes take more
  than 8 hours of GPU time, both variants run instead on one seeded 300-dialogue dev sample
  (seed 20261102). That switch is decided from throughput alone, before any accuracy is seen.
- **FR10 Full dev run.** After selection, the interpreter runs on the complete dev routed stream
  (all five conditions), reusing cached `none`/`full` answers. The dev hybrid is composed from it,
  and the spec 007 dev analysis and error-audit dry run use these outputs.

**Hybrid**
- **FR11 Composition.** For each router run `(train_condition, seed)` and each evaluation
  condition, the composer writes a routed file. For each `(example_id, condition)`:
  - router `no_request` → `prediction = no_request`, null category, empty slots, whatever the
    interpreter returned (including `invalid`);
  - router `direct`/`indirect`, valid interpreter row → the router's route plus the interpreter's
    `category`, `slots` and `requested_slots`;
  - router `direct`/`indirect`, invalid interpreter row → `{"invalid": true}`.

  The hybrid's oracle file is the interpreter's oracle file. Matched condition c uses the
  c-trained router, and mismatch conditions use the full-trained router, as in spec 007 FR6. On
  each split, the router runs are those whose recorded `eval_split` is that split.
- **FR12 Composition checks.** The composer refuses to run if:
  - router predictions and interpreter rows don't cover exactly the same `(example_id,
    condition)` set;
  - a router run's recorded config (name, train condition, eval split, seed) doesn't match its
    declared role.

  It records the hashes of both inputs in its output provenance. It is pure stdlib and
  byte-deterministic.

**Freeze and analysis integration**
- **FR13 Panel.** `configs/analysis/analysis-v1.toml` and `configs/freeze/freeze-v1.toml` replace
  the placeholders with these entries:
  - `hybrid`: matched. Its streams are routed and oracle (no transfer), and its seeds are the
    router's five. Its recipe files are the interpreter recipe, the prompt template and example-ID
    list, and the router config.
  - `qwen2.5-7b-instruct`: llm, test_time. Its streams are routed, oracle and transfer.
  - the Claude and OpenAI frontier members: llm, test_time, with streams per OQ2. They are listed
    only once OQ1 and OQ2 are resolved; otherwise they are left out of the panel before the
    freeze.

  Matching `h3-*` Holm members are added. `primary.system` stays `hybrid`.
- **FR14 Recipe and code pins.** Each LLM recipe is a TOML plus prompt files.
  - `llm_model` is the exact provider snapshot ID or the Hugging Face commit, never an alias.
  - `freeze-v1.toml` `code` adds `src/llm/*.py`.
  - `freeze check` reports every recipe ready.
- **FR15 Test gate (runner).** With `--split test`, the runner first calls `freeze verify`. It then
  checks, at run level, that its recipe files, rendered-prompt hash and `llm_model` equal the
  frozen pins of the system it claims to be. Otherwise it stops before loading a model, importing
  a backend or making a call.
- **FR15b Test gate (composer).** `compose --split test` calls `freeze verify` and checks each
  router run against the frozen `deberta-v3-large` recipe (stage1 recipe hash, seed and train
  condition) through the existing Stage 1 run check. It also checks that the interpreter run
  recorded the frozen recipe file, rendered prompt and `llm_model`. Both happen before it writes
  anything.

**Paid-run controls**
- **FR16 Spend cap.** Before an API run, `estimate` prints the call count, token estimate and cost
  from a dated price table that Sandy confirms. It refuses a price table dated more than 30 days
  before the run.
  - A paid run needs both `--confirm-paid` and a `--max-usd` cap.
  - Before each call, a worst-case cost is reserved: the locally counted input tokens plus the
    output-token limit, at the table price.
  - A call is refused if spent plus in-flight reservations plus this reservation would exceed the
    cap. Each reservation is reconciled with the provider-reported usage, and the run stops
    cleanly and resumably.
  - No API run is launched without Sandy's explicit request (constitution).

**Governance**
- **FR17 Constitution exception.** The constitution gets one dated, scoped exception for
  spec 009, applied after this spec is approved. It covers three departures:
  1. Claude writes the LLM runner and hybrid composer, and Sandy reviews them.
  2. LLM dependencies go in new pinned uv groups, `llm` and `api`.
  3. LLM outputs are not byte-reproducible on rerun. Their cache and prediction files are the
     hashed reproducibility artifacts, while the composer and validators stay byte-deterministic.

  The paper's methods section discloses all three.
- **FR18 No corpus text in git.** Committed prompt files hold instructions and placeholders only.
  P2's few-shot examples are committed as a list of train `example_id`s with their draw seed. A
  committed generator renders the full prompt from pinned `data/raw` into git-ignored
  `outputs/llm/prompts/`. It is byte-deterministic: the same inputs give identical bytes. The
  freeze pins the template, the ID list and the generator code, and the runner checks the
  rendered prompt's hash (FR15).

### Non-Functional

- **Security.**
  - API keys are read only from environment variables, and never logged, written or echoed in
    errors.
  - Network calls go only through the official SDKs to their fixed hosts. No URL comes from data
    or config.
  - Corpus text is untrusted data. It goes in a delimited data block, the model has no tools,
    and only schema-validated fields leave the parser.
  - Backend exceptions are caught at the backend interface. Logs and stderr show only the
    exception class, HTTP status, provider request ID and the cache-key hash. Full error bodies,
    which may echo corpus text, go to the git-ignored raw log.
  - Raw responses, rendered prompts and anything with corpus text stay under the git-ignored
    `outputs/` or `data/interim/`.
  - No test-split text or IDs are printed (see the no-test-split-output rule).
- **Data handling.** No DIRECT text is sent to a third-party API until OQ1 is resolved. The open
  model runs locally, and nothing leaves the lab.
- **Reproducibility.** The cache and prediction files are the reproducibility artifacts. Their
  hashes go in provenance and in the analysis inputs. GPU batching and API models are not
  bit-reproducible on rerun, and the paper says so. Composition, validation and the prompt
  generator are byte-deterministic.
- **Performance and scale.** There are about 56k distinct inputs per split. On dev the word count
  is p50 34, p90 183 and max 350. The local run must fit beside the other team's 8–10 GB on the
  shared 32 GB card (configurable memory share), and should finish the full dev stream in a few
  hours.
- **Observability.** The runner logs progress every N calls: done, cached, invalid (by reason),
  retried, rate-limited and spend so far. Logs are structured, with no corpus text.
- **Testing.** Stdlib `unittest`, with invented fixtures. Backends are faked behind the interface,
  so nothing calls a model or the network in the test suite. The suite passes on native Windows
  and WSL without the `llm` or `api` dependency groups installed.
- **Disclosure.** The hybrid's five seeds share one greedy interpreter pass, so its seed spread
  reflects router variance only. The paper's limitations and spec 007's notes for `hybrid` say so.

## Acceptance Criteria

- **AC-009-1** On fixtures, the runner emits exactly one valid row per input record for the
  routed, oracle and transfer streams, and spec 005's validators accept each file. (FR1, FR3b,
  FR4)
- **AC-009-2** When an oracle record is not in the routed stream, or has a different input hash,
  the runner exits non-zero before any call. (FR2)
- **AC-009-3** Each of these model outputs produces an `invalid` record, a kept raw response and
  a counted reason, and the example stays in the denominator:
  - malformed JSON;
  - an out-of-enum category, including `no_request` in the interpretation;
  - an unknown or duplicate slot key;
  - an over-long value;
  - an empty response;
  - a refusal;
  - a truncation at the output-token limit;
  - a transfer value outside the record's candidates. (FR3, FR3b, FR5)
- **AC-009-3b** A fake backend that returns a transient 5xx and then a valid answer yields a valid
  row and one counted retry. A backend that fails 5 times stops the run non-zero, writes no
  `invalid` row, and a rerun resumes from the cache. (FR5)
- **AC-009-3c** A fixture input whose rendered prompt exceeds the recipe limit makes the run exit
  non-zero before the first call, and no input is truncated. (FR5a)
- **AC-009-4** When a run is killed mid-stream and rerun, the second run makes zero calls for
  cached keys. Its output is byte-identical to that of an uninterrupted run with the same fake
  backend. Changing the prompt, the schema or the task invalidates every cache hit. (FR6)
- **AC-009-5** Provenance contains every FR8 field. A test injects a fake API key and a sentinel
  string in a fixture input. It asserts that the key never appears in provenance, logs or error
  text, and that the sentinel never appears in logs or stderr, including when the fake backend
  raises an error that echoes its request. (FR8, Security)
- **AC-009-6** On fixtures, prompt selection composes each variant with fixture routers. It picks
  the variant with the higher hybrid `request_interpretation`, averaged over two conditions and
  the seeds, and picks P1 on a tie within 0.01. The report holds aggregates only, with no IDs or
  text. (FR9)
- **AC-009-7** The composer reproduces a hand-computed routed file for a fixture that covers all
  three FR11 cases: router `no_request` (with valid and with invalid interpreter rows), router
  route with a valid interpreter row, and router route with an invalid interpreter row.
  Matched/mismatch router selection follows FR11. Two runs are byte-identical. (FR11)
- **AC-009-8** The composer refuses a coverage mismatch and a router run whose recorded train
  condition, eval split or seed differs from its declared role. (FR12)
- **AC-009-9** The composed dev hybrid files (5 seeds × 3 matched conditions, plus mismatch
  conditions) pass `src.evaluation.stage2 score` and `src.analysis run --split dev` with `hybrid`
  reported as `run`. (FR10, FR11, FR13)
- **AC-009-10** `python -m src.data.freeze check` shows no `recipe_missing`, `llm_model_floating`
  or `llm_model_missing` findings for the hybrid and LLM systems. `src/llm/*.py` appears among the
  pinned code. (FR13, FR14)
- **AC-009-11** `--split test` exits non-zero before loading a model or calling an API in these
  cases:
  - no freeze verifies;
  - a recipe file, the rendered-prompt hash or `llm_model` differs from the frozen pins.

  `compose --split test` exits non-zero when given a router run with an unfrozen seed or recipe.
  (FR15, FR15b)
- **AC-009-12** An API backend run without `--confirm-paid` or `--max-usd` refuses to start, as
  does one with a price table older than 30 days. With a fake backend and a cap, the run refuses
  the first call whose worst-case reservation would cross the cap. It never exceeds the cap, even
  with in-flight calls, and it resumes cleanly. (FR16)
- **AC-009-13** The full suite passes on native Windows and in WSL without the `llm`/`api` groups
  installed. A real Qwen smoke run on 20 dev records completes on the lab GPU (Sandy), within the
  configured memory share. It reports the invalid rate, throughput and the worst-case token
  length used for `max_model_len`. (Testing, Performance, FR5a, FR7)
- **AC-009-14** Rendering P2 twice from the fixture template and fixture ID list gives identical
  bytes. No committed file under `configs/llm/` contains fixture corpus text, which a test
  enforces by a sentinel scan. (FR18)

## Open Questions

- **OQ1 (Sandy, open): DIRECT text and third-party APIs.** DIRECT has no stated license, which
  means all rights are reserved by default (`data/sources.toml`). May its rewrites and the
  MultiWOZ contexts be sent to the Anthropic and OpenAI APIs? The options are:
  - yes, with disclosure;
  - yes, after the professor agrees;
  - no, and replace the API members with a second open family.

  The API backends are built either way, and no paid run happens until this is answered.
- **OQ2 (Sandy, open): API run scope.** The options are:
  - test `none` + `full` only, plus a small dev format check;
  - all test conditions;
  - full dev + test.

  This sets the API members' panel streams and the cost estimate.
- **OQ3 (Sandy, at freeze): spending cap** for the API members, set after `estimate` runs on real
  token counts.
- **OQ4 (Sandy, at freeze): drop RoBERTa from the panel?** Panel members that aren't run keep
  p = 1 in the Holm family, and every extra member makes the Holm thresholds stricter.
  Recommendation: drop both RoBERTa entries before the freeze if they won't run.
- **OQ5 (Sandy): exact frontier model IDs.** Claude: a dated Opus/Sonnet-class snapshot. OpenAI: a
  dated flagship snapshot. Claude proposes the IDs at implementation time from the provider docs,
  and Sandy confirms them.
- **OQ6 (Sandy, optional, before Nov 9): save test-grid router weights?** Run the WP-09
  `deberta-v3-large` test grid with `--save-model`. It costs disk only and would allow later
  recomposition or a hybrid transfer line. Without it, the hybrid's test routes exist only as
  prediction files, which is enough for this spec.
