# Tasks: Spec 009

_Decomposed 2026-11-02 from the READY spec and plan (after review R1–R14; R7 = hybrid metric)._

**Dependency order:**
- **Pure core, all stdlib (T1–T7).** Each one can be built and tested in isolation:
  - schema/parser (T1);
  - prompts (T2, then T3);
  - input checks and preflight (T4);
  - cache (T5);
  - backend interface (T6);
  - spend ledger (T7).
- **Runner (T8).** It wires T1–T6 into `run` and writes the streams and provenance.
- **Hybrid (T9)** and the **freeze gates (T10)**.
- **Prompt selection (T11)** needs T8 and T9.
- **Real backends.** vLLM (T12) is on the critical path; the APIs (T13) are off it, because OQ1
  is still open.
- **Close-out.** Configs and panel (T14), then the lab runbook and the dev evidence (T15).

**Critical path to the Nov 5 lab smoke:** T1 → T2 → T4 → T5 → T6 → T8 → T12 → T15's runbook.
T3, T9, T10 and T11 must land before selection on Nov 5–6. T7 and T13 can slip past Nov 9
without blocking the freeze; the API members then stay out of the panel.

**Conventions for every task:**
- stdlib Python 3.12 and `unittest` in flat `tests/test_llm_*.py`, passing on native Windows and
  WSL **without** the `llm`/`api` groups (backends are faked; SDK modules are stubbed through
  `sys.modules` only in their own tests);
- invented fixtures only (`PMUL9xxx`-style IDs, tiny text), never DIRECT/MultiWOZ text;
- no command prints a test ID or utterance text;
- Claude runs dev only and never launches GPU or paid runs.

## T1: Governance exception, interpretation schemas and strict parser
- Description:
  - **Governance first.** Apply the FR17 dated, scoped exception to `specs/constitution.md`. It
    covers three things: Claude writes the spec 009 runner and composer and Sandy reviews them;
    there are new `llm`/`api` uv groups; LLM outputs are not byte-reproducible (cache and
    prediction files are the artifacts).
  - **Slot-key vocabulary.** `src/llm/schema.py` builds the closed slot-key enum from the
    MultiWOZ `domain.slot` names in train `Inform`/`Request` acts, through
    `src/evaluation/interpretation.reference`. It is committed as `configs/llm/slot_keys.json`:
    names only, no values, with a version and source hash.
  - **Main schema (FR3).** `route` enum; `category` enum of the four request categories only;
    `slots` as an array of `{slot: enum, value: bounded string}`; `requested_slots` as an array
    of enum. There is no `paraphrase` field.
  - **Transfer schema (FR3b).** Built per record: `{request: bool, value: enum(candidates ∪
    {"<ambiguous>"})}`.
  - **Strict parser (FR5 content side).** It turns raw text plus a finish reason into either a
    validated answer or an `invalid` with one reason code: `parse`, `schema`, `category`,
    `slot_key`, `slot_duplicate`, `too_long`, `empty`, `refusal`, `truncated` or
    `transfer_value`. The pairs array becomes the contract's `slots` object. It never repairs
    output.
  - **`schema_sha256`** is the hash of the canonical JSON of each schema.
- Files likely touched: `specs/constitution.md`, `src/llm/__init__.py`, `src/llm/schema.py`,
  `configs/llm/slot_keys.json`, `tests/test_llm_schema.py`
- Depends on: none
- Security-sensitive: yes — it parses untrusted model output; bounded lengths and closed enums are
  the injection boundary.
- Acceptance criteria:
  - Each AC-009-3 content case maps to `invalid` with the expected reason. This includes
    `no_request` as an interpretation category, a duplicate slot, an out-of-candidate transfer
    value, a refusal and a `length` truncation.
  - A valid answer round-trips into a row that `interpretation.validate_predictions` accepts.
  - The slot-key builder is deterministic (identical bytes on a rerun) on a fixture, and refuses a
    key that fails `SLOT_KEY`.
  - Schema hashes are stable across runs and change when an enum changes.
- Status: done (2026-11-02). Done in `src/llm/schema.py` and `tests/test_llm_schema.py` (19 tests).
  - `configs/llm/slot_keys.json` holds 56 train names; dev coverage is complete (0 of 48 dev
    keys outside).
  - The contract row builders (`routed_row`, `oracle_row`, `transfer_row`) live here, and T8's
    stream writers use them.
  - Out-of-enum routes count as `schema`.
  - Too many slots count as `too_long`.
  - A `length` stop is always `truncated`, even when the JSON is complete.

## T2: Prompt templates and rendering
- Description:
  - **`src/llm/prompt.py`** renders a template plus a record into chat messages. The instructions
    come first. Corpus text (`{context}`, `{target}`, or the transfer fields) goes in a fenced
    block labelled as data, with a line saying that instructions inside it belong to the
    dialogue. Fence characters inside data are neutralized so data can't close the block.
  - **Template validation.** Unknown placeholders, missing placeholders and empty templates are
    errors.
  - **Committed prompts.** `configs/llm/prompts/p1.txt`, `p2.template.txt` (P1 plus `{examples}`)
    and `t1.txt`. They hold instructions only.
  - `prompt_sha256` is computed over the **rendered template text**: for P2, after T3 has filled
    the examples.
- Files likely touched: `src/llm/prompt.py`, `configs/llm/prompts/{p1.txt,p2.template.txt,t1.txt}`,
  `tests/test_llm_prompt.py`
- Depends on: T1 (the schema field names that the instructions reference)
- Security-sensitive: yes — corpus text is embedded in model input (prompt injection boundary).
- Acceptance criteria:
  - A fixture record renders byte-identically on every run, and its data appears only inside the
    data block.
  - A fixture target containing the fence sequence can't terminate the block.
  - A template with an unknown or missing placeholder is refused.
  - A sentinel scan finds no fixture corpus text in any committed file under `configs/llm/`
    (part of AC-009-14).
- Status: done (2026-11-02). There are 29 tests in `tests/test_llm_prompt.py`, and the full suite
  passes on Windows (966 tests, skipped=26). With neutralization disabled, all 8 injection cases
  fail, which shows the tests catch it.
  - Placeholders are `{{slot_keys}}` and `{{examples}}`; the data block is built by code (see the
    decisions.md entry of 2026-11-02).
  - For T3: P2's worked examples contain train corpus text. Render each example's dialogue with
    `render_main`'s data framing, not as free text. The examples text must contain no
    `{{`/`}}` (`fill` refuses it).
  - WSL run owed together with T1 (AC-009-13).

## T3: P2 few-shot draw and deterministic generator
- Description:
  - **`src/llm/prompt_gen.py draw`** picks k train examples that have a spec 005 reference
    (`build_examples(items, "train")`), with seed 20261102, stratified over route labels. It
    writes `configs/llm/prompts/p2_examples.json`: IDs, k, seed and the source-file hashes. No
    text.
  - **`render`** reads that list and the pinned `data/raw`, fills `p2.template.txt` with each
    example's rendered input and its reference answer in the T1 schema, and writes
    `outputs/llm/prompts/p2.txt`, which is git-ignored. Keys are sorted and line ends are `\n`.
    It refuses if a source hash differs from the list.
  - **Fallback.** If a clean train reference path doesn't exist, record that and drop P2 (spec
    FR9 / plan Risks).
- Files likely touched: `src/llm/prompt_gen.py`, `configs/llm/prompts/p2_examples.json`,
  `.gitignore` (if `outputs/llm/` is not already covered), `tests/test_llm_prompt_gen.py`
- Depends on: T1, T2
- Security-sensitive: yes — corpus text must stay out of git (FR18, constitution).
- Acceptance criteria:
  - Rendering twice from the fixture list gives identical bytes (AC-009-14).
  - The draw is deterministic for a seed and contains train IDs only. A dev or test ID in the list
    is refused.
  - A source-hash mismatch is refused.
  - The output path must be under git-ignored `outputs/`. Writing elsewhere is refused.
  - Run once by Claude on real train data, the draw commits only the ID list. A sentinel test
    confirms that the committed JSON has no `text`/`context` fields.
- Status: done (2026-11-02). There are 19 tests in `tests/test_llm_prompt_gen.py`, and the full
  suite passes on Windows (985 tests, skipped=26).
  - The real draw found enough clean train examples, so the FR9 fallback is not needed.
    `p2_examples.json` holds 6 IDs (3 direct and 3 indirect, interleaved). The rendered P2 is
    1,235 words, and two renders give identical sha256.
  - Examples are drawn only from `direct`/`indirect`; `no_request` turns are not drawn. Each
    example uses the `full` condition, and a label has at most one example per dialogue. See
    decisions.md, 2026-11-02 "P2 examples". This can be changed before the Nov 5 selection.
  - Run the CLI with `python -E -s -m src.llm.prompt_gen`, not `-I`: `-I` drops the repo from
    `sys.path`.
  - WSL run owed together with T1/T2 (AC-009-13).

## T4: Input verification, stream subset check and length preflight
- Description:
  - **`src/llm/inputs.py`** loads routed, oracle and transfer input files with bounded reads. It
    validates each record's schema, `renderer_version` and `input_sha256` (recomputed) (FR1).
  - It checks that oracle is a subset of routed, keyed by `(example_id, condition)` with equal
    hashes (FR2).
  - It collapses records to distinct `input_sha256`s.
  - **`src/llm/preflight.py`** takes an injected token counter (stdlib in tests; the Qwen
    tokenizer in T12). It refuses the run if any rendered prompt's token count plus `max_tokens`
    exceeds `max_model_len` (FR5a). It reports counts only: the maximum, the number over the
    limit and the limit. It never reports IDs.
  - **Sizing helper.** `preflight size` computes the worst-case `max_model_len` from the train and
    dev inputs and the longest prompt (plan: rounded up to the next 512).
- Files likely touched: `src/llm/inputs.py`, `src/llm/preflight.py`, `tests/test_llm_inputs.py`,
  `tests/test_llm_preflight.py`
- Depends on: T2
- Security-sensitive: yes — validates untrusted input files at the boundary.
- Acceptance criteria:
  - AC-009-2: an oracle record missing from routed, or with a different hash, exits non-zero
    before any backend is constructed.
  - A tampered `input_sha256` or a wrong `renderer_version` is refused.
  - AC-009-3c: an over-length fixture prompt exits non-zero before the first call, and the error
    contains no ID or text.
  - The sizing helper returns the documented rounding on fixtures.
- Status: done (2026-11-03). Done in `src/llm/inputs.py`, `src/llm/preflight.py`, `tests/test_llm_inputs.py` and
  `tests/test_llm_preflight.py` (24 tests).
  - On the real dev files (counts only), routed has 56,862 records, oracle has 22,560 (subset holds)
    and there are 56,174 distinct hashes. The 136 transfer validation records verify. Load time is
    1.3 s.
  - `required_model_len` rounds to the next multiple of 512 **strictly above** prompt +
    `max_tokens`, so there is always a margin of at least one token. That is the spec's "plus a
    margin".
  - The library sizing helper (`size_model_len`) is done. Its CLI needs the Qwen tokenizer, so it
    is wired in T12 (`run.py size`).
  - Transfer hashes reuse the IndirectRequests exporter's canonical form, which includes
    `example_id`, so transfer records never collapse.

## T5: Append-only resumable response cache
- Description: `src/llm/cache.py` (FR6).
  - The key is the SHA-256 of the canonical JSON of `{task, backend, model_id, prompt_sha256,
    decoding, schema_sha256, input_sha256}`.
  - It is an append-only JSONL. Each entry holds the key, the raw text, the finish reason, the
    usage and a timestamp, and is flushed and fsynced per batch.
  - On load, a torn final line from a kill is dropped with a warning. Any other malformed line is
    a hard error.
  - Duplicate keys must carry identical content, or loading fails.
  - The cache lives under git-ignored `outputs/llm/cache/`.
- Files likely touched: `src/llm/cache.py`, `tests/test_llm_cache.py`
- Depends on: T1 (`schema_sha256`)
- Security-sensitive: yes — persists raw model output that may echo corpus text (must stay
  git-ignored).
- Acceptance criteria:
  - Changing any single key component misses the cache.
  - A truncated last line is recovered, and a corrupt middle line is refused.
  - Two writers appending the same key with different content are detected on load.
  - A path outside `outputs/` is refused.
- Status: done (2026-11-03). Done in `src/llm/cache.py`, `src/llm/paths.py` (shared `under_outputs`
  guard) and `tests/test_llm_cache.py` (15 tests).
  - Content equality covers raw text, finish reason and usage. `created` is metadata.
  - A torn tail is cut off at the first append, so a resumed file is byte-identical to an
    uninterrupted one (tested).
  - Raw text is bounded to `MAX_RAW_CHARS + 1`. Backends clip to that bound (T6), which keeps the
    parser's `too_long` outcome unchanged.

## T6: Backend interface, fake backend, retry and error sanitizing
- Description:
  - **`src/llm/backends/base.py`.** It defines `Backend.generate(batch[(key, messages, schema)]) →
    [(key, raw_text, finish_reason, usage)]` and the `TransportError`/`ContentOutcome`
    classification.
  - **Retry (FR5).** At most 5 attempts, with exponential backoff (base 2 s, cap 60 s), full
    jitter and `retry-after` honoured. Sleep and clock are injected. When retries are exhausted it
    raises `RunStopped`.
  - **Exception sanitizer.** Logs and stderr get only the class, status, provider request ID and
    key hash. The full body goes to the git-ignored raw error log.
  - **`backends/fake.py`.** Scripted outputs, scripted transient errors, scripted usage, and an
    optional echo of the request in its error message (for the leak test).
  - **Backend registry.** It is keyed by the recipe's `backend`, and imports are lazy.
- Files likely touched: `src/llm/backends/{__init__,base,fake}.py`, `tests/test_llm_backends.py`
- Depends on: T1
- Security-sensitive: yes — it is the external-call boundary, and it controls what error text
  reaches logs.
- Acceptance criteria:
  - AC-009-3b: a transient 5xx followed by success gives a valid answer and one counted retry.
    Five failures raise `RunStopped`, and no `invalid` is produced.
  - The backoff schedule matches the specification under a fixed RNG.
  - AC-009-5 (sanitizer part): a fake error that echoes a sentinel and a fake key shows neither
    in logs or stderr.
  - An unknown backend name is refused, and importing `src.llm` does not import vllm or the SDKs.
- Status: done (2026-11-03). Done in `src/llm/backends/{__init__,base,fake}.py` and
  `tests/test_llm_backends.py` (17 tests).
  - Retry works at batch level.
  - An exception that isn't a `TransportError` is "unmapped" and stops the run with no retry
    (fail closed). Real backends must map provider errors to `TransportError`.
  - `RunStopped` is raised `from None`, so a traceback can't print the original error text.
  - `retry-after` sets a floor on the delay and is capped at 300 s.
  - The raw error log is `ErrorLog` under `outputs/`.
  - `CallStats.calls` counts every attempted request, retries included.

## T7: Price table, estimate and worst-case spend ledger
- Description: `src/llm/spend.py` and `configs/llm/prices.toml` (FR16).
  - The price table is dated and Sandy-confirmed. It is refused if dated more than 30 days before
    the run.
  - `estimate` reports the call count, input tokens counted locally, the worst-case output
    (`max_tokens`) and the cost range.
  - The ledger reserves a worst-case cost per call before dispatch, refuses a call that would
    cross `--max-usd` given spend plus in-flight reservations, reconciles each reservation with
    the reported usage, and persists to git-ignored `outputs/llm/spend/` so that a resume keeps
    the totals.
  - API backends require both `--confirm-paid` and `--max-usd`.
- Files likely touched: `src/llm/spend.py`, `configs/llm/prices.toml`, `tests/test_llm_spend.py`
- Depends on: T6
- Security-sensitive: yes — guards paid external calls.
- Acceptance criteria:
  - AC-009-12: missing either flag, or a stale price table, refuses to start.
  - With concurrent in-flight reservations, the cap is never exceeded.
  - The run refuses the first call whose reservation would cross the cap, and a resume continues
    from the persisted ledger.
  - Local backends bypass the ledger and need no flags.
- Status: todo

## T8: Runner CLI, stream writers, provenance and progress logs
- Description: `src/llm/run.py run --recipe … --split dev --task main|transfer` (FR4, FR6, FR8).
  The steps, in order:
  1. Load the recipe.
  2. Verify the inputs (T4) and run the preflight.
  3. Collapse to distinct hashes.
  4. Serve cached keys.
  5. Send the misses to the backend in batches, append to the cache, and parse (T1).
  6. Write the streams atomically to `outputs/stage2/<system>/<split>/`:
     - routed: the model's route, or the no_request nulls;
     - oracle: the interpretation;
     - transfer: `request`/`value`.

     There is one row per input record, and `invalid` rows use the contract record.
  7. Write `provenance.json` with every FR8 field: counts by invalid reason, retries, the
     rendered-prompt hash, the schema hash, the input hash, and the code digest and git state
     through `src/stage1/provenance.git_state`.

  It logs structured progress every N calls, with no text. The API path goes through T7 when the
  recipe's backend is paid.
- Files likely touched: `src/llm/run.py`, `src/llm/streams.py`, `src/llm/recipe.py`,
  `tests/test_llm_run.py`
- Depends on: T1, T2, T4, T5, T6 (T7 for the API path)
- Security-sensitive: yes — orchestrates untrusted input, external calls and on-disk artifacts.
- Acceptance criteria:
  - AC-009-1: the fixture streams pass `interpretation.validate_predictions` and the transfer
    validator, with exactly one row per record.
  - AC-009-4: a kill-and-rerun makes zero calls for cached keys, and its output is byte-identical
    to an uninterrupted run. A changed prompt, schema or task invalidates every hit.
  - AC-009-5: provenance has every FR8 field, and no fake key or sentinel appears in provenance,
    logs or stderr.
  - `--split test` is refused by default. The freeze gate is added in T10, and until then the
    refusal is unconditional.
- Status: done (2026-11-03). Done in `src/llm/{recipe,streams,run}.py` and
  `tests/test_llm_run.py` (20 tests). Cache hardening is in `src/llm/cache.py`: a duplicate JSON
  key is refused, and `exclusive_lock` stops two runs from interleaving appends.
  - **Provenance** is `provenance.<task>.json`, because main and transfer share a directory.
  - **Output directory.** A non-selected variant, or a subset of conditions, writes to
    `outputs/llm/selection/<system>/<variant>/<split>/`, never to `outputs/stage2/`.
  - **Lazy backend.** The backend is built only when there are cache misses, so a fully cached
    rerun never loads the model.
  - **Preflight** covers every prompt, and `backend_options.max_model_len` is required when the
    backend has a token counter.
  - **Paid backends** are refused until T7.

## T9: Hybrid composer
- Description: `src/llm/compose.py compose --split dev --router-root outputs/stage1/deberta-v3-large
  --interpreter outputs/stage2/<llm>/<split>` (FR11, FR12). Pure stdlib.
  - **Composition rules.** Router `no_request` → the no_request row. Router route with a valid
    interpreter row → the router's route plus the interpretation. Router route with an invalid
    interpreter row → `{"invalid": true}`.
  - **Router roles.** A matched condition c uses train-c; mismatch conditions use train-full.
    Each run's `config.resolved.json` and `metrics.json` are checked against the declared
    `(train_condition, seed)` and `eval_split`.
  - **Checks.** Exact `(example_id, condition)` coverage between router and interpreter.
  - **Output.** It writes `outputs/stage2/hybrid/<split>/train-<c>/seed<s>/{routed,oracle}.jsonl`
    atomically, with provenance holding both input hashes. The output is byte-deterministic.
  - **Library entry point.** It exposes `compose_rows(...)` so that T11 reuses the same code.
- Files likely touched: `src/llm/compose.py`, `tests/test_llm_compose.py`
- Depends on: T8 (stream format)
- Security-sensitive: no — it is a local, deterministic transform of validated files. The test
  gate is in T10.
- Acceptance criteria:
  - AC-009-7: a hand-computed fixture covers all FR11 cases (router `no_request` with a valid and
    with an invalid interpreter row, a route with a valid row, a route with an invalid row). The
    matched/mismatch router selection is right, and two runs are byte-identical.
  - AC-009-8: a coverage mismatch, and a router run whose recorded train condition, eval split or
    seed is wrong, are each refused.
  - The composed files pass `interpretation.validate_predictions`.
- Status: done (2026-11-03). Notes:
  - **Spec gap fixed in the runner (T8).** The LLM `routed.jsonl` nulls the interpretation wherever
    the LLM itself routes `no_request`, but the hybrid needs that interpretation wherever the router
    routes a request (FR3). The main task now also writes `interpretation.jsonl`: one row per
    routed record, built like the oracle row. It is not scored. The composer reads it, not the cache.
  - **Router roles.** Each `train-<c>/seed<s>` routed file covers every condition its run
    predicted. The analysis already takes matched c from train-c and the mismatch conditions from
    train-full (spec 007 FR6). `router_train_condition()` encodes the same rule for T11.
  - **Run checks.** Smoke runs and `-smoke` directories are refused or skipped. All three train
    conditions must have the same seed set. `predictions.jsonl` must hash to the
    `predictions_sha256` recorded in the run's metrics.
  - **Interpreter check.** The interpreter must be the selected-variant, all-conditions main run.
  - **Output and provenance.** `oracle.jsonl` is a byte copy of the interpreter's oracle file.
    Every run is composed in memory before the first write, so a refusal writes nothing.
    `provenance.compose.json` is written last and has no timestamps.
  - **Test split.** Refused until T10 adds the freeze gate.
  - **Tests.** 30 tests in `tests/test_llm_compose.py`; the full suite has 1,108 tests, all OK.

## T10: Freeze pins and test gates for runner and composer
- Description:
  - **`src/data/freeze.py`.** Add `check_llm_run(frozen, system, recipe_files,
    rendered_prompt_sha256, llm_model)`. It requires each file's `text_sha256`, the
    rendered-prompt hash and `llm_model` to equal the frozen `recipe.<system>.*` pins. The
    rendered-prompt hash becomes a pin: an extra recipe key, `rendered_prompts`, keeps it
    additive.
  - **Code pins.** Add `src/llm/*.py` to the `code` list in `configs/freeze/freeze-v1.toml`
    (FR14).
  - **Runner gate (FR15).** `run --split test` calls `require_freeze` and then `check_llm_run`
    before it constructs a backend.
  - **Composer gate (FR15b).** `compose --split test` calls `require_freeze` and then
    `check_run` for each router run as `deberta-v3-large`.
- Files likely touched: `src/data/freeze.py`, `configs/freeze/freeze-v1.toml`, `src/llm/run.py`,
  `src/llm/compose.py`, `tests/test_freeze_llm.py`, `tests/test_llm_gates.py`
- Depends on: T8, T9
- Security-sensitive: yes — it is the fail-closed test-split gate (research integrity).
- Acceptance criteria:
  - AC-009-11: with no freeze, a moved recipe file, a different rendered-prompt hash or a
    different `llm_model`, the run exits non-zero before a backend is constructed (asserted
    through a fake backend factory that records construction).
  - A router run with an unfrozen seed or recipe makes `compose --split test` exit non-zero, and
    nothing is written.
  - The existing freeze suites still pass. `freeze check` on a fixture shows `src/llm/` files among
    the code pins.
- Status: done (2026-11-05). Done in `src/data/freeze.py`, `src/llm/{run,compose}.py`,
  `configs/freeze/freeze-v1.toml`, `tests/test_freeze_llm.py` and `tests/test_llm_gates.py`. Notes:
  - A test run must use the selected prompt, on every condition, with no sample: P1 stays a pinned
    file when P2 is selected, so the hash check alone would not catch `--variant p1`.
  - `smoke` and `size` stay dev only.

## T11: Prompt selection (`select-prompt`)
- Description: `src/llm/run.py select-prompt --variants p1 p2 --split dev` (FR9, R7).
  - It refuses any split but dev.
  - For each variant, it loads the variant's cached `none`/`full` outputs and composes them with
    the five dev `deberta-v3-large` routers through `compose_rows`.
  - It scores them with `src.evaluation.stage2` and the spec 007 `request_interpretation`
    definition.
  - It averages over the 2 conditions × 5 seeds, applies the 0.01 tie rule (P1 wins) and writes
    `outputs/llm/selection/report.json` with aggregates only.
  - **Sample fallback.** `--sample-dialogues 300 --seed 20261102` draws a dialogue-level dev
    sample. It may only be passed when the provenance shows that no variant output has been
    scored yet. The runner records whether the full set or the sample was used.
- Files likely touched: `src/llm/select.py`, `src/llm/run.py`, `tests/test_llm_select.py`
- Depends on: T8, T9
- Security-sensitive: no — it is a dev-only, local aggregation that refuses non-dev splits.
- Acceptance criteria:
  - AC-009-6: on fixtures, it picks the variant with the higher hybrid mean, picks P1 on a tie
    within 0.01, and the report has no IDs or text.
  - `--split test` is refused.
  - The selection numbers equal those produced by composing through T9 and scoring
    independently. The equivalence is tested.
  - The sample draw is deterministic and dialogue-level.
- Status: done (2026-11-04)
  - **Command and paths.** The command is `python -m src.llm.select select-prompt` (variants come
    from the recipe). The report is `outputs/llm/selection/<system>/report.json`. The sample flag
    is `run --sample`, fixed at the FR9 values. The decisions log of 2026-11-04 has the reasons.
  - **Tests.** `tests/test_llm_select.py` has 30 tests:
    - choose, including the 0.01 boundary;
    - the draw: deterministic, dialogue-level, independent of pool order;
    - end-to-end selection on a 30-dialogue fixture, with equivalence to T9 compose plus
      `stage2.build_report`;
    - refusals: test split, a missing, changed or other-shaped run, a changed prompt, coverage,
      samples that differ, a tampered sample block;
    - the runner's sample path and its guards.
  - **Full suite.** 1147 tests pass on Windows (with and without git) and in WSL.

## T12: vLLM backend, `llm` dependency group and Qwen recipe
- Description:
  - **`src/llm/backends/vllm_backend.py`.** Lazy imports. Model and tokenizer are pinned to the
    HF commit, dtype bf16, greedy decoding, `max_tokens` 256, guided JSON per request (the
    per-record schema for transfer), prefix caching, and `gpu_memory_utilization` and
    `max_model_len` from the recipe. vLLM's `finish_reason` maps to T1 reasons.
  - **Token counter.** It exposes the Qwen tokenizer count for the T4 preflight.
  - **Dependency group.** Add an `llm` uv group to `pyproject.toml` with pinned `vllm`. Sandy
    runs `uv lock` in the lab venv if Windows can't resolve it.
  - **Recipe.** Create `configs/llm/qwen2.5-7b-instruct.toml`: backend, HF repo and commit
    (resolved and pinned at implementation), decoding, `max_model_len` (placeholder until the
    smoke test fills it), and the memory share.
  - **Fallback.** A `transformers` backend stub with the same interface, documented as the
    fallback, with the constraint caveat (FR7, R13).
- Files likely touched: `src/llm/backends/vllm_backend.py`, `pyproject.toml`,
  `configs/llm/qwen2.5-7b-instruct.toml`, `tests/test_llm_vllm_backend.py`
- Depends on: T6, T8
- Security-sensitive: yes — it loads remote model weights (pinned revision only, with no
  `trust_remote_code`).
- Acceptance criteria:
  - With `vllm` stubbed in `sys.modules`, the backend passes the pinned revision and refuses a
    floating one. `trust_remote_code` is false, and `finish_reason=length` maps to `truncated`.
  - The suite passes without the `llm` group installed.
  - The recipe loader refuses a missing or floating revision and a `max_model_len` below the
    preflight requirement.
- Status: done (2026-11-03). Done in `src/llm/backends/vllm_backend.py`, the vLLM option checks
  in `src/llm/recipe.py`, `run.py size`, `configs/llm/qwen2.5-7b-instruct.toml`, the `llm` group
  plus uv conflicts in `pyproject.toml`/`uv.lock`, and `tests/test_llm_vllm_backend.py` (14
  tests, vllm/transformers stubbed).
  - **Pins.** vLLM 0.32.0 (2026-10-18; it pins torch 2.13.0). The Qwen commit is
    `a09a3545…bc28`. The revision must be a full 40-hex commit.
  - **Context window.** The loader refuses `max_model_len <= max_tokens`. The real
    per-prompt requirement is enforced by the preflight before any call, and reported by
    `size`, which loads the tokenizer only.
  - **Fallback.** The transformers fallback is documented in the module docstring and not built
    (no dead stub).
  - **Dry run (fake backend, real dev inputs).** 56,174 distinct inputs gave 56,862 routed and
    22,560 oracle rows, all passing the validators. Transfer gave 136 rows. The longest P2 prompt
    is 1,734 words.

## T13: Anthropic and OpenAI backends and `api` dependency group
- Description:
  - **Backends.** `anthropic_backend.py` and `openai_backend.py` use the official SDKs only,
    with lazy imports. Keys come only from environment variables. They use temperature 0,
    structured outputs with the T1 schema, and Anthropic prompt caching on the static prefix.
    Refusal and length stop reasons map to T1 reasons, and 429/5xx/timeouts map to
    `TransportError`. The usage they report feeds the T7 ledger.
  - **Dependency group.** Add an `api` uv group with the pinned SDKs.
  - **Model IDs.** Claude proposes the exact frontier snapshot IDs from the provider docs (OQ5)
    as recipe drafts that are not yet in the panel.
- Files likely touched: `src/llm/backends/{anthropic_backend,openai_backend}.py`, `pyproject.toml`,
  `configs/llm/{claude,openai}-*.toml` (drafts), `tests/test_llm_api_backends.py`
- Depends on: T6, T7, T8
- Security-sensitive: yes — API keys, outbound network and third-party data transfer (OQ1).
- Acceptance criteria:
  - With the SDKs stubbed, no key appears in requests' logged metadata, provenance or errors. A
    missing key fails fast with a message naming the variable, not its value.
  - Each SDK stop or error class maps to the right failure class.
  - A run without `--confirm-paid`/`--max-usd` refuses (through T7).
  - The suite passes without the `api` group.
  - No real call is made by Claude. Paid runs await OQ1/OQ2 and Sandy's explicit request.
- Status: todo

## T14: Panel, freeze recipe and analysis config edits
- Description:
  - **`configs/analysis/analysis-v1.toml`.** Replace the `llm` placeholder with
    `qwen2.5-7b-instruct` (llm, test_time; routed/oracle/transfer). Set the `hybrid` streams to
    routed and oracle (remove transfer). Add or rename the `h3-*` members. Keep `draft = true`
    until the freeze.
  - **`configs/freeze/freeze-v1.toml`.** Fill in the systems:
    - `hybrid`: files are the Qwen recipe, `p*.txt`/`p2.template.txt`, `p2_examples.json` and
      the router config; seeds are the router's five;
    - `qwen2.5-7b-instruct`: files and `llm_model`, the HF commit.
  - **Analysis inputs.** Update `configs/analysis/inputs-dev.toml` for the dev hybrid and LLM
    entries.
  - **Not here.** API members are added only once OQ1/OQ2 are resolved. OQ4 (RoBERTa) is
    Sandy's call at the freeze.
- Files likely touched: `configs/analysis/analysis-v1.toml`, `configs/freeze/freeze-v1.toml`,
  `configs/analysis/inputs-dev.toml`, affected analysis/freeze tests
- Depends on: T10, T12 (pinned Qwen revision), T11 (chosen prompt, for the `files` list)
- Security-sensitive: no — config only. The gate logic is in T10.
- Acceptance criteria:
  - AC-009-10: `python -m src.data.freeze check` shows no `recipe_missing`, `llm_model_floating`
    or `llm_model_missing` for `hybrid` and `qwen2.5-7b-instruct`.
  - The analysis config loads with the new panel and Holm family.
  - The full suite passes.
- Status: in-progress (2026-11-05). The panel and freeze configs are done: RoBERTa dropped (OQ4,
  Sandy, 2026-11-05), `auto-v1` kept, `llm` renamed, recipes and `llm_model` filled in. Still open:
  `rendered_prompts` (after the rerun's selection) and `configs/analysis/inputs-dev.toml` (after
  the dev evidence).

## T15: Lab runbook and dev close-out evidence
- Description:
  - **`docs/llm_lab_runbook.md`.** WSL/lab-ready, resumable commands for Sandy, in order:
    1. venv and `uv sync --group llm`;
    2. the 20-record smoke test, which reports the invalid rate, throughput and the worst-case
       `max_model_len` (AC-009-13). Its throughput decides the FR9 full-vs-sample switch;
    3. P1/P2 `none`/`full` runs, then `select-prompt`;
    4. the full dev run;
    5. `compose` over 15 router runs;
    6. `stage2 score` and `analysis run --split dev`.

    It marks the GPU-only steps and the expected durations.
  - **After Sandy's runs.** Record the evidence in `verification.md`, update the roadmap, the
    decisions log (chosen prompt, `max_model_len`, backend) and the limitations disclosures (FR17,
    R14).
- Files likely touched: `docs/llm_lab_runbook.md`, `specs/009-llm-routed-hybrid/verification.md`,
  `specs/001-pragmatic-intent-study/roadmap.md`, `specs/memory/decisions.md`
- Depends on: T8–T12, T14 (runbook drafted after T12; evidence after Sandy's lab runs)
- Security-sensitive: no
- Acceptance criteria:
  - AC-009-9: the composed dev hybrid files pass `stage2 score` and `analysis run --split dev`
    with `hybrid` reported `run`.
  - AC-009-13: the full suite passes on native Windows and in WSL without the `llm`/`api` groups.
    Sandy's smoke test completes within the memory share, and its numbers are recorded.
  - Every runbook command has been dry-run on fixtures or `--help` in WSL by Claude, with GPU steps
    excluded.
- Status: in-progress (2026-11-04). The runbook is drafted; the evidence is pending Sandy's lab runs.
  - **Done.** `docs/llm_lab_runbook.md`; the `run.py smoke` command (7 tests in
    `SmokeTests`); and `specs/009-llm-routed-hybrid/verification.md` with the pre-run evidence.
  - **Suite.** 1117 tests pass on Windows (with and without git) and in WSL.
  - **WSL fix.** A JSON nesting bound (`schema.MAX_NESTING`) fixes a WSL-only failure in T1's
    deep-nesting test.
  - **CLI checks.** In WSL, every runbook CLI passes `--help`. Each test-split refusal fires before
    any work.
  - **Still open.** The AC-009-9 analysis run and the roadmap/decisions close-out wait on the lab
    evidence. `select-prompt` landed with T11 on 2026-11-04.
