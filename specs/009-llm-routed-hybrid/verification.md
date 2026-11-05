# Spec 009 verification

Evidence for the acceptance criteria that need runs, not just unit tests. Counts and hashes only;
no example IDs or corpus text.

## Pre-run checks by Claude (2026-11-04, T15)

- **Full suite (AC-009-13), run without the `llm` and `api` groups:**

  | Platform | Tests | Skipped |
  |---|---|---|
  | Native Windows, Python 3.12, git on PATH | 1117 OK | 16 |
  | Native Windows, Python 3.12, no git on PATH | 1117 OK | 26 |
  | WSL Ubuntu 22.04, uv Python 3.12.15 | 1117 OK | 13 |

  The first WSL run had one failure: JSON nesting depth gave a platform-dependent invalid reason.
  It was fixed with `schema.MAX_NESTING` (decisions, 2026-11-04).
- **Runbook CLIs (`docs/llm_lab_runbook.md`).** In WSL, every one exits zero on `--help`:
  `download_sources`, `build_direct_dataset`, `stage2 inputs/score`, `transfer inputs/score`,
  `prompt_gen render`, `llm.run size/smoke/run`, `llm.compose compose`, `analysis run`.
- **Test-split refusals.** `smoke`, `run` and `compose` with `--split test` stop with the
  freeze-gate message before any work.
- **Input checksums.** Rebuilding the three stage-2 input files reproduced the local copies byte for
  byte; their SHA-256s are pinned in the runbook.
- **Counts.** 56,174 distinct dev inputs, 22,116 of them under `none`/`full`.
- **T11 (`select-prompt` and `run --sample`):**
  - The full suite is 1147 OK on all three platforms above, with skips of 16, 26 and 13 as before.
  - In WSL, `select-prompt --help` exits zero.
  - `select-prompt --split test` stops with "prompt selection runs on dev only (FR9)".
  - `run --sample` without `--conditions` is refused before the corpus is read.
- **Not exercised by Claude:**
  - every GPU step;
  - `select-prompt` on real variant runs.

## Lab runs (2026-11-05, `cbu-5090-right`)

Run through Slurm by Claude at Sandy's request. Settings: `gpu_memory_utilization = 0.80` and
`VLLM_USE_FLASHINFER_SAMPLER=0` (decisions, 2026-11-05).

- **Size:** `fits` true, `required_max_model_len` 3072, so `max_model_len` stays 4096.
- **Model load:** 14.29 GiB of weights, 8.92 GiB of KV cache (166,992 tokens).
- **Smoke (20 calls, P2, before the prompt fix):** 0 invalid, 20 `stop`, 0 transport errors.
- **Probe (512 calls, P2, before the prompt fix):** 48.2 calls/s; 1.56% invalid (7 `slot_duplicate`,
  1 `truncated`); finish reasons 511 `stop`, 1 `length`; 0 transport errors; peak 31,456 MiB
  including about 4.8 GB held by no listed process. FR9: `sample_fallback` false.
  - Sandy kept `max_tokens` at 256 after the one `length` stop.
- **Selection, first run (full `none`/`full`, 22,116 calls per variant):** P1 mean 0.1399, 2.23%
  invalid; P2 mean 0.1665, 2.02% invalid. Both were over the 2% limit, so the prompts were fixed.
- **Selection, repeat under the new prompts:** P1 mean 0.1275, 0.94% invalid; **P2 mean 0.1774,
  0.61% invalid; P2 selected** (`higher_mean`). Neither is over the limit.
- **Dev run (P2, commit `aea7d53`, clean tree):** 56,174 distinct inputs, 22,116 cache hits, 34,058
  calls, 0 retries, 0 transport errors; 446 invalid calls (0.79%): 429 `slot_duplicate`, 17
  `truncated`.
- **Transfer:** 136 records, 0 invalid.
- **First run:** kept under `outputs/archive/run1-2026-11-05/` on the lab for disclosure.

Pending:
- **Step 5:** `compose`, and `stage2 score` for Qwen and the 15 hybrid runs.
- **AC-009-9:** `analysis run --split dev` with `hybrid` reported `run`.
