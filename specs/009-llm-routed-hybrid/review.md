# Review: Spec 009

Verdict: NEEDS REVISION → **READY after revision (2026-11-02)**

**Resolution.** Sandy chose to apply all findings and selected R7's recommended metric: the
hybrid's dev `request_interpretation` over all dev under `none`/`full`. R1–R14 are now in
`spec.md` (FR3, FR3b, FR5, FR5a, FR7, FR9, FR11, FR14, FR15, FR15b, FR16, FR17, FR18, the NFRs,
AC-009-3/3b/3c/5/6/7/8/10/11/12/13/14, OQ6) and in `plan.md` (Architecture, Key details,
Alternatives, Tradeoffs, Risks). The decision is logged in `specs/memory/decisions.md` on
2026-11-02.

_Reviewed 2026-11-02 against `specs/constitution.md`, spec 009 `spec.md`/`plan.md` (drafts of
2026-11-01), `docs/stage2_scoring.md`, `src/data/freeze.py`, `src/stage1/`, `src/analysis/inputs.py`,
`configs/freeze/freeze-v1.toml` and `configs/analysis/analysis-v1.toml`. Dev-only checks printed
counts, never text or IDs._

The design is sound: one cached answer per input, a route-independent interpretation, and a
deterministic composer are the right shape. Six gaps would each give a wrong or unverifiable
result, though. Each fix is small and needs no new human labour.

## Findings

### R1 — Committing P2's few-shot examples puts DIRECT text in git (blocking: constitution)

Plan, "Prompt rendering", says the train few-shot examples "are written into the committed prompt
file, so the pinned prompt hash covers them." The constitution says: "Source text lives only under
git-ignored `data/raw/` and `data/interim/`. Committed annotation files hold IDs, offsets, hashes
and labels, never source text." DIRECT has no stated license (OQ1).
- **Failure:** pushing that commit to GitHub (PR into `dev`) redistributes unlicensed corpus text,
  and the text then stays in the history.
- **Fix:** commit only `p2.template.txt` (instructions plus `{examples}`), a small generator, and
  `p2_examples.json`, which holds train `example_id`s and the seed but no text. The generator
  renders the full prompt into the git-ignored `outputs/llm/prompts/p2.txt` from pinned
  `data/raw`, byte-deterministically. The freeze pins the template, the ID list and the generator
  code, and the runner records the rendered prompt's SHA-256 in provenance and in the cache key.
  The rendered file is never committed. A test checks that rendering the fixture twice gives
  identical bytes.

### R2 — Sizing `max_model_len` from the p90 input would bias the H2 contrast (blocking: correctness)

The plan's Risks section sizes `max_model_len` "from the dev p90 input (183 words + prefix)".
Measured today on dev: p50 is 34 words, p90 183, and the maximum is 350 (the D-06 budget). The
longest inputs are almost all under `full`/`one`/mismatched. vLLM rejects a prompt longer than
`max_model_len`.
- **Failure:** about 10% of inputs, nearly all with context, either crash the run or become
  `invalid`. The `full − none` difference then measures input length, which confounds the
  confirmatory endpoint.
- **Fix:**
  - Size `max_model_len` from the worst case: the 350-word budget's maximum token count under the
    Qwen tokenizer, plus the longest prompt prefix (P2 included), plus `max_tokens`, plus a
    margin. Compute it on train and dev only; for test, the 350-word renderer bound is the
    guarantee.
  - Add **FR5a**: the runner computes each rendered prompt's token length before any call, and
    refuses to start if any exceeds the limit. Never truncate, and never mark a too-long input
    `invalid`.
  - Add an AC that an over-length fixture input stops the run before the first call.

### R3 — The freeze pins neither the LLM code nor the LLM recipe as a gate unit (blocking: freeze integrity)

Two separate gaps:
1. `freeze-v1.toml` `code` lists `src/stage1`, `src/evaluation` and `src/analysis`, but not
   `src/llm/*.py`. After the freeze, the parser, schema or composer could change and `freeze
   verify` would still pass.
2. The plan says the test gate "reuses `require_freeze` … compares the hash of its recipe with the
   frozen `recipe.<system>` pin". `check_run` (`src/data/freeze.py:670`) only knows Stage 1. It
   compares `recipe.<system>.stage1`, which LLM systems don't have; their recipe is a set of
   `recipe.<system>.file.<path>` pins.

- **Failure:** FR15/AC-009-11 can't be implemented as written. The tempting shortcut, calling
  `require_freeze` without `run=`, only checks that the repo is unchanged, not that *this* run
  used the frozen recipe, prompt and model ID. The hybrid composer on test also has no gate, so it
  could compose from router runs that were never in the frozen grid.
- **Fix:**
  - Add `"src/llm/*.py"` to `code` (FR14).
  - Add a small `check_llm_run(frozen, system, recipe_files, llm_model)` to `freeze.py`, with
    tests. It requires each recipe file's `text_sha256`, the rendered-prompt hash (R1) and
    `llm_model` to equal the frozen pins.
  - Add **FR15b**: `compose --split test` calls `require_freeze` and checks each router run with
    the existing `check_run` (system `deberta-v3-large`, its `stage1` recipe hash, seed and train
    condition). Its AC: a router run with an unfrozen seed or recipe is refused.

### R4 — FR11 doesn't say what the hybrid does when the interpreter row is invalid, or names `no_request` as a category (blocking: clarity/correctness)

- **Invalid rows.** If the router says `indirect` and the interpreter's row for that
  `(example_id, condition)` is `invalid`, FR11 doesn't say whether the hybrid row is `invalid` or
  the router's route with empty fields. Two implementers will differ, and the choice moves the
  primary endpoint's numerator and the reported invalid count.
- **Category enum.** FR3 asks for the interpretation "as if the target were a request". The
  contract's category enum still includes `no_request`, though. If the model emits
  `category: no_request` under the router's `direct`, the composed row is self-contradictory.
- **Fix:** state these in FR11 and cover each in AC-009-7:
  - Router `no_request` → the `no_request` row, whatever the interpreter said (valid or
    invalid).
  - Router route and interpreter invalid → `{"invalid": true}` (the example stays in the
    denominator, and the hybrid inherits the interpreter's failure honestly).
  - The interpretation schema's category enum is the four request categories only. The contract
    still allows null or `no_request`; they just can't be produced in the interpretation field.

### R5 — The transfer stream has no defined prompt or schema (blocking: completeness)

FR3/FR9 define one main-benchmark answer, with route plus `cat-v1` category plus MultiWOZ slot
keys, and FR4 derives the transfer output from "route ≠ no_request" and "a candidate value". The
IndirectRequests inputs have a different shape. Their fields are `utterance`,
`slot_description`, `candidates` and `candidate_aliases`, with no context, and the answer is a
choice from a **per-record** candidate list plus `<ambiguous>`. The main prompt can't ask that
question, and the FR9 selection doesn't cover it.
- **Failure:** the implementer has to invent a transfer prompt and schema mid-build, after the
  dev data has been seen. That is exactly what FR9's fixed procedure is meant to prevent.
- **Fix:** add **FR3b**:
  - one transfer prompt `t1.txt`, zero-shot, committed before any run, with no selection step;
  - a per-record schema of `{request: bool, value: enum(candidates ∪ {"<ambiguous>"})}`. vLLM and
    both APIs accept a per-request schema;
  - its own cache namespace (the task name goes in the cache key);
  - validation-split runs are dev checks only, as `docs/stage2_scoring.md` already says.

  Add the matching AC. Its pin goes in the LLM recipes' `files`.

### R6 — Transport failures and content failures are not separated (blocking: correctness of the invalid rate)

FR5 says the runner "never repairs or re-asks for an answer", but the observability line counts
"retried" and "rate-limited". Several cases are unspecified:
- a 429 or 5xx response, or a timeout;
- an API refusal (`stop_reason: refusal`);
- an output cut off at `max_tokens` (`finish_reason: length`);
- a vLLM worker crash.

- **Failure:** if network errors become `invalid`, the invalid rate depends on API weather, and
  that differs by provider, which biases H3. If they are retried with no bound, a paid run can
  loop.
- **Fix:** add a classification to FR5:
  - **Transport failures** (connection errors, timeouts, 429, 5xx, worker crash) get a bounded
    retry with exponential backoff and jitter, at most 5 attempts. After that the run **stops**,
    resumably, and writes no row. These are never `invalid`.
  - **Content failures** (parse/schema failure, refusal, `length` truncation, empty output) get
    exactly one call, become `invalid`, keep the raw response, and are counted by reason.

  Extend AC-009-3 with refusal and truncation cases, and add one AC that a fake backend's
  transient 5xx followed by success yields a valid row, while repeated 5xx stops the run without
  writing `invalid`.

### R7 — The prompt-selection metric and sample are ambiguous (blocking: clarity)

FR9 says "the higher `request_interpretation`", but **of which system** is unclear:
- the standalone LLM's (which includes the LLM's own routing, unused by the hybrid);
- the hybrid's (which needs router predictions on the sample);
- or the oracle interpretation.

The sample size is also unspecified, while a 0.01 tie margin only means something at a known
sample size.
- **Failure:** the choice of metric can flip the selected prompt, and a post-hoc choice of metric
  is the selection-on-outcome the fixed procedure exists to prevent.
- **Fix (recommended):**
  - Select on the **hybrid's** dev `request_interpretation`, averaged over `none` and `full` and
    over the five `deberta-v3-large` dev router seeds. That is the primary system's endpoint, and
    the router predictions exist for all of dev.
  - Fix the sample at **all dev dialogues under `none` and `full`**, about 22.8k distinct calls
    per prompt. That takes about 1–2 h per prompt on the 5090 with prefix caching. It removes
    sampling noise and the sampling seed, and the P1 run is then reused for FR10.
  - If the throughput measured in the smoke test makes that too slow, use a fixed 300-dialogue
    seeded sample, decided **before** the smoke test reports any accuracy.

### R8 — The spend cap can't be enforced "before" a call with post-hoc usage (non-blocking, but must be clear before any paid run)

FR16 says the run stops "before the cap would be exceeded, using the provider-reported usage".
Usage is only known **after** a call, and concurrent calls make it worse.
- **Fix:** before each call, the ledger reserves a worst-case cost: input tokens counted locally,
  plus `max_tokens`, at the dated price. A call is refused if `spent + reserved_in_flight +
  this_reservation > max_usd`. When usage is reported, the reservation is reconciled. AC-009-12
  then has a deterministic reading. Price-table staleness: `estimate` refuses a price table more
  than 30 days old.

### R9 — The router is a different set of weights on test than on dev (non-blocking clarity)

The header says the router is "the `deberta-v3-large` matched-trained runs from the 2026-10-27 lab
grid", and the Non-Goals confirm the weights weren't kept. On test, the router is therefore the
**WP-09 test-grid retrain** of the same frozen recipe and seeds. GPU training isn't
bit-reproducible, so those are different weights.
- **Fix:** say so in the header and in FR11. Then the test hybrid's inputs are
  `outputs/stage1/deberta-v3-large/…` runs with `eval_split = test`, and FR12 already checks the
  eval split. Optional, at no cost: run the test grid with `--save-model` for deberta-v3-large, so
  any later recomposition or transfer line has weights (in that case revisit the transfer
  Non-Goal).

### R10 — FR17's constitution exception is narrower than what the spec actually departs from (non-blocking)

The spec also departs from two other constitution lines:
- "ML dependencies stay in the pinned uv dependency groups (`classical`, `gpu`)", which the new
  `llm` and `api` groups break;
- "same pinned inputs … give byte-identical artifacts", which LLM outputs break.

- **Fix:** widen FR17's dated exception to cover all three. The cache and prediction files are the
  reproducibility artifacts for LLM outputs, and the composer and validators stay byte-exact.

### R11 — SDK error messages can carry corpus text (non-blocking, security)

Provider SDK exceptions (400 validation errors) can echo request content. The NFR "never echoed in
errors" covers keys but not corpus text, and a test-split echo would break the no-test-output rule.
- **Fix:** catch backend exceptions at the interface. Log only the exception class, HTTP status,
  provider request ID and the cache key hash. Put the full error body in the git-ignored raw log.
  Extend AC-009-5 to inject a sentinel string into a fixture input and assert it never appears in
  logs or stderr.

### R12 — Drop `paraphrase` from the LLM's output schema (non-blocking, cost and validity)

`paraphrase` is unscored (a Non-Goal). Under a 256-token `max_tokens` it is the field most likely
to cause `length` truncations (up to 500 characters), and it roughly doubles the paid output tokens.
- **Fix:** leave it out of the schema. The contract makes it optional, so nothing downstream
  changes.

### R13 — A fallback backend is a method change (non-blocking)

The plan's fallback for a vLLM/CUDA conflict is `transformers` generate. That has no built-in
guided JSON decoding, so the invalid rate and the outputs would differ.
- **Fix:** whichever backend passes the smoke test is fixed **before** prompt selection and is
  used for every Qwen run (dev and test), and it is recorded in the recipe. If it's the
  fallback, constrain decoding with a logits processor or an equivalent library, pinned in the
  `llm` group, or disclose unconstrained decoding.

### R14 — One interpreter run under five router seeds understates variance (non-blocking, disclosure)

The hybrid's five seeds share a single greedy interpreter pass. Its seed spread reflects router
variance only.
- **Fix:** one sentence in the limitations, and in spec 007's report notes for the `hybrid`
  system. No extra runs.

## Non-Issues Considered

- **FR2 subset claim**: rechecked on dev 2026-11-02. There are 56,862 routed and 22,560 oracle
  `(example_id, condition)` keys, and oracle ⊆ routed.
- **Router coverage (FR12)**: `deberta-v3-large/train-full/seed13` dev predictions cover exactly
  the 56,862 routed keys (none/one/full 11,394; mismatched/mismatched_one 11,340). The coverage
  check is satisfiable, not hypothetical.
- **Router label space**: Stage 1 is 3-class (`direct`/`indirect`/`no_request`,
  `src/stage1/data.py:41`). That maps one-to-one onto the contract's `prediction`, so no mapping
  layer is needed.
- **Interpretation independent of route (FR3)**: the rejected alternative (the LLM sees the
  router's label) really does break the oracle stream and multiply the calls by the seeds. This
  is a real comparison, not a strawman.
- **`llm_model` pinning (FR14)**: `freeze.py` already flags empty or `*latest` IDs
  (`llm_model_floating`) and missing ones (`llm_model_missing`).
- **Analysis inputs**: `src/analysis/inputs.py` already accepts an `untrained`, seed-0 Stage 2
  entry and refuses identical routed/oracle files. No spec 007 change is needed beyond the panel
  edits in FR13.
- **Hybrid transfer removal**: currently `analysis-v1.toml` lists `transfer` for `hybrid`.
  FR13's removal is required, not optional, or the analysis would expect a file that can't
  exist.
- **Memory fit**: bf16 Qwen2.5-7B (~15 GB) plus KV cache fits in about 22 GB free. With R2's
  worst-case `max_model_len` (~1k tokens), the KV cache per sequence is still small.
- **Prompt injection**: there are no tools, data goes in a delimited block, and closed-enum
  constrained output means a dialogue can at most produce a wrong label, which is scored.
- **Selection independence (constitution)**: prompt choice uses dev outcomes only, with a
  procedure fixed before any run. That is allowed. Item selection is untouched.
- **Scope**: API members are cleanly optional (OQ1/OQ2), and the primary system never depends on
  them. Batch APIs are deferred with a stated trigger. No scope creep found.
