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

## Lab runs (Sandy)

Pending. To record from the evidence archive:
- **Smoke (20 calls) and probe (512 calls):** invalid rate by reason, finish reasons,
  calls/s, peak GPU memory, `required_max_model_len` and the FR9 decision.
- **Selection:** the chosen prompt and both variants' hybrid means (T11 report).
- **Dev run:** invalid counts, and `stage2 score` for Qwen and the 15 hybrid runs.
- **AC-009-9:** `analysis run --split dev` with `hybrid` reported `run`.
