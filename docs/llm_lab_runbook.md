# Qwen interpreter lab runbook (spec 009)

Prepared 2026-11-04 for Sandy (spec 009 T15). This is a **dev-only** handoff for the lab RTX 5090.
It covers the AC-009-13 smoke test, prompt selection (FR9), the full dev run and the hybrid
composition. Nothing here touches the test split; every command refuses `--split test` until the
freeze gate (T10) lands.

| Step | Where | GPU | Expected duration |
|---|---|---|---|
| 1. Checkout, data, environment | lab | no | ~30 min (vLLM wheels + 15 GB weights on first use) |
| 2. Size, smoke, throughput probe | lab | yes | ~15 min, mostly model load |
| 3. P1/P2 selection runs + select-prompt | lab | yes | 2 × 22,116 calls; probe's `selection.estimated_gpu_hours` |
| 4. Full dev run + transfer | lab | yes | ~34,000 new calls; probe's `full_dev.estimated_gpu_hours` minus the cached share |
| 5. Compose + `stage2 score` | lab | no | minutes |
| 6. Evidence back; `analysis run --split dev` | Claude, locally | no | minutes |

Steps 2–4 are GPU-only. The durations in steps 3–4 come from the step 2 probe and are recorded,
not guessed. For scale: the FR9 sample fallback triggers only below about 1.5 calls/s.

## Rules for the whole session

- **Order and concurrency.** Run the steps in order, in one checkout, with one process at a time.
  The response cache takes an exclusive lock, and a second runner stops rather than waits.
- **Interruptions.** Every `run` command is resumable: repeat the identical command. Cached answers
  are served without the GPU, and only the misses are sent.
- **Tracked files.** Don't edit tracked files (recipe, prompts, configs) in this checkout. An edit
  makes the tree dirty, and every provenance file records that. If a step below says to change the
  recipe, stop and send me the reported numbers. I'll commit the change, and you `git pull` before
  the selection runs.
- **What to share.** Smoke and size reports, provenance files and logs hold counts and hashes only,
  so they are safe to paste to me. Stream files (`*.jsonl` under `outputs/stage2/` and
  `outputs/llm/`) and the cache echo corpus text. Keep them in private project storage, like the
  dataset (`docs/data_sources.md`).

## 1. Checkout, data and environment

Use a fresh clone on the lab's Linux filesystem. `OLD` is the DeBERTa-large checkout from
2026-10-27, which holds the 15 router runs.

```bash
set -euo pipefail
OLD=~/path/to/deberta-large-checkout          # adjust
git clone --branch feature/009-llm-routed-hybrid \
  https://github.com/sandythomas1/Pragmatic-Intent.git pi-llm
cd pi-llm
git log -1 --format='%H %s'                  # must include the smoke command (T15)

# vLLM pins torch 2.13 and numpy < 2.5, so it gets its own environment, outside the repo
# (an in-repo .venv-* directory would make the tree dirty).
export UV_PROJECT_ENVIRONMENT=$HOME/.venvs/pi-llm
export TOKENIZERS_PARALLELISM=false
export VLLM_USE_FLASHINFER_SAMPLER=0      # the GPU machines have no nvcc; decoding is greedy
export PI="uv run --locked --no-sync python -E -s"
uv sync --locked --group llm

$PI -m src.data.download_sources --only direct multiwoz indirect_requests
mkdir -p data/interim/stage2 outputs/verification
$PI -m src.data.build_direct_dataset > data/interim/direct-rebuild-summary.json
$PI -m src.evaluation.stage2 inputs --split dev --mode routed \
  --out data/interim/stage2/dev_routed_inputs.jsonl
$PI -m src.evaluation.stage2 inputs --split dev --mode oracle \
  --out data/interim/stage2/dev_oracle_inputs.jsonl
$PI -m src.evaluation.transfer inputs --split validation \
  --out data/interim/stage2/indirect_requests_validation_inputs.jsonl
sha256sum -c <<'CHECKSUMS'
c7f56b41bde43598f04b867ad6a52189d632c53578cf49734d44b6034550fe83  data/interim/direct/items.jsonl
574ae000db5562521e3a767f4ee55e4e64abdf89e60d9038c47f4f7d25059949  data/interim/direct/dialogues.jsonl
17d068f798e8378fa2d8cc57fff33d6acc97b295eebac875259a1774d87a7ff4  data/interim/stage2/dev_routed_inputs.jsonl
6bd85316ed05a426f7910e7571a261d289eda6505b98449dffe6672483dd2c4c  data/interim/stage2/dev_oracle_inputs.jsonl
be970b0abb1cdc4897d9038dc17e2651857a80ce07372f66680cfbe73a2bb396  data/interim/stage2/indirect_requests_validation_inputs.jsonl
CHECKSUMS

# P2 holds six train examples, so it is rendered into git-ignored outputs/ (FR18).
$PI -m src.llm.prompt_gen render --out outputs/llm/prompts/p2.txt

# The router runs, byte for byte (compose re-checks their prediction hashes).
mkdir -p outputs/stage1
cp -a "$OLD/outputs/stage1/deberta-v3-large" outputs/stage1/
git status --short                            # must print nothing
```

**Stop conditions.**
- All five checksums must pass. They are the files my dry runs used.
- `git status --short` must be empty.

## 2. Size, smoke test and throughput probe (GPU)

First check what else is using the card. vLLM reserves `gpu_memory_utilization` (0.85) of the
card's **total** memory at startup, about 27 GB of 32 GB. It fails if another process holds more
than the remainder.

```bash
nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free --format=csv \
  | tee outputs/verification/llm-gpu.log
```

If free memory is below about 28 GB, stop and send me the line. I'll lower the share in the recipe
and commit it. The share is not part of the cache key, so changing it later doesn't invalidate any
answers.

**2a. Size (tokenizer only, no GPU).**

```bash
$PI -m src.llm.run size --recipe configs/llm/qwen2.5-7b-instruct.toml --split dev \
  | tee outputs/verification/llm-size.json
```

`size` measures P1, P2 and the transfer prompt. If `fits` is `true`, leave `max_model_len = 4096`
as it is. A larger window costs nothing at these lengths, and an unchanged recipe keeps the tree
clean. If `fits` is `false`, stop and send me `required_max_model_len`.

**2b. Smoke test (AC-009-13).** This sends 20 real calls: the longest P2 prompt, plus 19 others.
It runs the length preflight over every prompt and reports counts only. It never writes to the
cache or the scored streams. P2 is used because it is the longer prompt, so it is the worst case
for memory.

```bash
$PI -m src.llm.run smoke --recipe configs/llm/qwen2.5-7b-instruct.toml --split dev \
  --variant p2 --records 20 2>&1 | tee outputs/verification/llm-smoke-20.log
```

While it loads, watch `nvidia-smi -l 5` in a second terminal and note the peak. The command prints
the report and saves it as `outputs/llm/smoke/qwen2.5-7b-instruct/report.p2.20.json`. Check:

- `invalid_rate`: if it is above `invalid_rate_limit` (0.02), stop. The schema or prompt is fixed
  before any selection run (plan Risks). Send me `invalid_by_reason` and `finish_reasons`.
- `transport_errors` should be 0, and `finish_reasons` should be all `stop`. A `truncated` reason
  means `max_tokens` is too small; stop and send me the report.
- `required_max_model_len` should agree with step 2a.
- Report any OOM or CUDA error together with the `nvidia-smi` line from above.

**2c. Throughput probe (the FR9 decision).** 20 calls fill only a fraction of one 256-wide batch,
so they understate throughput. The selection decision therefore uses this probe of 512 P2 calls
(two full batches). The rule was fixed on 2026-11-04, before any accuracy was seen.

```bash
$PI -m src.llm.run smoke --recipe configs/llm/qwen2.5-7b-instruct.toml --split dev \
  --variant p2 --records 512 2>&1 | tee outputs/verification/llm-smoke-512.log
```

`selection.sample_fallback` in this report is the FR9 decision:
- If it is `false`, selection uses the full `none`/`full` dev set. This is expected: it is `true`
  only below about 1.5 calls/s.
- If it is `true`, add `--sample` to both step 3 `run` commands. That runs both variants on the
  FR9 sample: 300 dev dialogues, seed 20261102. Tell me the decision either way.
  - `--sample` is refused once a selection report exists, so decide it here, before step 3.

The estimate prices both variants at P2's rate, so it errs towards the sample.

## 3. Prompt selection (GPU, then CPU)

Run both variants on `none` and `full` only. A condition subset is written under
`outputs/llm/selection/`, never as a scored stream.

```bash
for v in p1 p2; do
  $PI -m src.llm.run run --recipe configs/llm/qwen2.5-7b-instruct.toml --split dev \
    --task main --variant "$v" --conditions none full \
    2>&1 | tee -a "outputs/verification/llm-select-$v.log"
done
```

Each pass ends by writing
`outputs/llm/selection/qwen2.5-7b-instruct/<variant>/dev/provenance.main.json`. A pass without
that file is incomplete; repeat the identical command. Check each log for the parsed and invalid
counts. Invalid outputs stay in the denominator as failures (FR10).

**Select the prompt (CPU, T11).**

```bash
$PI -m src.llm.select select-prompt --recipe configs/llm/qwen2.5-7b-instruct.toml --split dev \
  --router-root outputs/stage1/deberta-v3-large 2>&1 | tee outputs/verification/llm-select.log
```

The rule is the hybrid's `request_interpretation`, averaged over the 2 conditions × 5 router seeds.
P1 wins a tie within 0.01.

The decision is written to `outputs/llm/selection/qwen2.5-7b-instruct/report.json`, and a summary
is printed. Before scoring, it checks:
- each variant's provenance and stream hashes;
- the rendered prompt;
- coverage;
- if sampled, that both variants used the same sample.

It refuses on a mismatch and writes nothing; send me the error line.

A `warning:` line means a variant's invalid rate is above 2%. Selection still completes, because
invalid outputs already count as failures, but tell me.

If the summary shows `"recipe_needs_update": true` (P2 won), I commit `prompts.main = "p2"` in the
recipe and you pull it. The recipe change doesn't affect the cache key, so P2's `none`/`full`
answers are reused in step 4.

## 4. Full dev run and transfer (GPU)

The selected prompt over all five conditions writes the scored streams to
`outputs/stage2/qwen2.5-7b-instruct/dev/`. The winner's `none`/`full` answers come from the cache,
so only about 34,000 calls are new.

```bash
$PI -m src.llm.run run --recipe configs/llm/qwen2.5-7b-instruct.toml --split dev --task main \
  2>&1 | tee -a outputs/verification/llm-dev-main.log
$PI -m src.llm.run run --recipe configs/llm/qwen2.5-7b-instruct.toml --split dev --task transfer \
  2>&1 | tee -a outputs/verification/llm-dev-transfer.log
```

The main run writes `routed.jsonl`, `oracle.jsonl` and `interpretation.jsonl`, then
`provenance.main.json` last. The transfer run (136 IndirectRequests validation items) writes
`transfer.jsonl` and `provenance.transfer.json`.

## 5. Compose the hybrid and score (CPU)

```bash
$PI -m src.llm.compose compose --split dev \
  --router-root outputs/stage1/deberta-v3-large \
  --interpreter outputs/stage2/qwen2.5-7b-instruct/dev \
  2>&1 | tee outputs/verification/llm-compose.log

Q=outputs/stage2/qwen2.5-7b-instruct/dev
$PI -m src.evaluation.stage2 score --split dev --predictions $Q/routed.jsonl \
  --oracle-predictions $Q/oracle.jsonl --out outputs/stage2/metrics/qwen2.5-7b-instruct.dev.json
$PI -m src.evaluation.transfer score --split validation --predictions $Q/transfer.jsonl \
  --model-family qwen --out outputs/stage2/metrics/qwen2.5-7b-instruct.transfer.json
for c in none one full; do for s in 13 42 2026 314 2718; do
  H=outputs/stage2/hybrid/dev/train-$c/seed$s
  $PI -m src.evaluation.stage2 score --split dev --predictions $H/routed.jsonl \
    --oracle-predictions $H/oracle.jsonl --out outputs/stage2/metrics/hybrid/train-$c.seed$s.dev.json
done; done
```

The metrics go under `outputs/stage2/metrics/`, so the composer's directories hold exactly what
it wrote.

`compose` checks all 15 router runs (roles, seeds, prediction hashes) and exact coverage before
writing anything. It writes `outputs/stage2/hybrid/dev/provenance.compose.json` last. Every
`score` must exit zero. A failure here (missing or extra rows, schema) is a pipeline bug; send me
the error line.

## 6. Bring the evidence back

```bash
tar -czf ../llm-dev-evidence.tar.gz \
  outputs/stage2 outputs/llm outputs/verification
sha256sum ../llm-dev-evidence.tar.gz > ../llm-dev-evidence.tar.gz.sha256
git log -1 --format='%H' > ../llm-dev-evidence.commit
```

The archive holds model outputs that echo corpus text, so transfer it privately.
- **Why the cache is included.** With it, every stream can be rebuilt without a GPU, because a
  fully cached run never constructs the backend.

I then do the following locally, where all the other panel systems' dev runs live:
- **Analysis.** Add the Qwen and hybrid entries to `configs/analysis/inputs-dev.toml` (T14) and run
  `python -m src.analysis run --split dev --inputs configs/analysis/inputs-dev.toml` (AC-009-9).
- **Records.** Record the chosen prompt, `max_model_len`, the peak memory and the throughput in
  `specs/009-llm-routed-hybrid/verification.md`, the roadmap and the decisions log.

## Dry-run evidence (2026-11-04)

- **Checksums.** Regenerating the three stage-2 input files on Windows reproduced the committed
  local files byte for byte (the checksums above).
- **Counts.** 56,174 distinct dev inputs: 22,116 under `none`/`full`.
- **Smoke command.** Covered by `tests.test_llm_run.SmokeTests` against a fake backend:
  - counts, the fallback decision and the longest-first sample;
  - no cache or stream writes;
  - preflight before any call;
  - test refused.
- **WSL `--help` checks.** See `specs/009-llm-routed-hybrid/verification.md`.
- **`select-prompt` (T11).** It is covered end to end by `tests.test_llm_select` on fixture runs.
  In WSL, `--help` exits zero, and `--split test` and `run --sample` without `--conditions` are
  refused.
- **Not exercised by Claude.** The GPU steps (2–4), and `select-prompt` on real variant runs.
