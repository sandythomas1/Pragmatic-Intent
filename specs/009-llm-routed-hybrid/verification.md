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
  freeze-gate message before any work. T10 replaced this behaviour; see below.
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

## Freeze gates (2026-11-06, T10)

- **Full suite:** 1191 OK, with skips of 26 (Windows, no git), 16 (Windows, git) and 13 (WSL).
- **AC-009-11.** `tests.test_llm_gates` runs against real freeze records in a fixture repository.
  With no freeze, a moved recipe file, a different rendered prompt or a different `llm_model`, the
  fake factory records no backend, and no cache or stream is written.
- **Composer.** An unfrozen seed, an unfrozen recipe or an interpreter outside the freeze stops
  `compose --split test`, and `outputs/stage2/hybrid/test` is not created.
- **Real commands, this repository (no freeze record yet):**
  - `llm.run run --split test` and `llm.compose compose --split test` exit 1 with `freeze_missing`;
  - `llm.run smoke --split test` exits 1 with the dev-only refusal.
- **`freeze check`** on the real inputs lists six items: `tree_dirty`, `llm_model_floating`,
  `analysis_draft`, two `recipe_missing` and the new `rendered_prompts_missing`. T14 and Sandy's
  commit clear them.
- **Not exercised:** a test run on the real recipe. It needs T14 and a freeze record.

## Lab runs (Sandy)

Pending. To record from the evidence archive:
- **Smoke (20 calls) and probe (512 calls):** invalid rate by reason, finish reasons,
  calls/s, peak GPU memory, `required_max_model_len` and the FR9 decision.
- **Selection:** the chosen prompt and both variants' hybrid means (T11 report).
- **Dev run:** invalid counts, and `stage2 score` for Qwen and the 15 hybrid runs.
- **AC-009-9:** `analysis run --split dev` with `hybrid` reported `run`.
