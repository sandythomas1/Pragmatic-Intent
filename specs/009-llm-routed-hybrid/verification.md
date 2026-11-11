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

### Why P1's mean fell after the prompt fix (diagnosed 2026-11-11, dev only)

`scripts/diagnose_prompt_change.py` compared each variant's first selection run (commit `338fb00`)
with its repeat (`aea7d53`) on the `request_interpretation` population, 9,032 items per condition.
The code (`source_sha256` `4ff3631f…`), router inputs and model are the same in both runs; only the
prompt text changed. The runs came from the lab (`selection-runs.tar.gz`, sha256 `942221ea…`).
The reports hold totals only: `outputs/research/{p1,p2}-prompt-change.json`.

| | `none` exact | `full` exact | pooled change | lost / gained | mean slots (`none`, `full`) |
|---|---|---|---|---|---|
| P1 | 0.1313 → 0.1198 | 0.1489 → 0.1354 | −0.0125 | 642 / 416 | 2.10 → 2.30, 2.15 → 2.39 |
| P2 | 0.1598 → 0.1719 | 0.1737 → 0.1832 | +0.0109 | 351 / 547 | 1.79 → 1.88, 1.86 → 2.01 |

- The interpreter-only changes match the hybrid selection means: P1 −0.0124 and P2 +0.0109.
  The router plays no part in the drop.
- **The loss is on items that aren't train or taxi requests.**
  - P1 on hotel, restaurant and attraction items (5,936 per condition): 0.1253 → 0.1041 (`none`) and
    0.1242 → 0.1046 (`full`).
  - P1 on trip items (3,096 per condition): 0.1428 → 0.1499 and 0.1964 → 0.1944.
  - P2 rose on trip items (0.1780 → 0.2041 and 0.1906 → 0.2213) and held steady on the others.
- **How it fails: extra slots from the item's own domain.**
  - P1's `slots_extra` count rose by 211 (`none`) and 309 (`full`).
  - On the 364 non-trip items P1 lost, an ad-hoc tally using the script's functions found 476 added
    slot names. 386 are from the item's own domain (for example `restaurant.name`, `.addr`, `.ref`
    and `.phone` on restaurant requests), 53 are train or taxi slots, and 37 come from other domains.
- **The invalid rate fell, but few of those answers became exact.** P1's invalid answers fell by
  122 (`none`) and 164 (`full`); only 27 and 29 of them became exact.
- **Reading:** the longer slot instruction made the zero-shot prompt list more slots across the
  board, and exactness counts any extra slot as an error. P2's six examples anchor how many slots
  to list, so it gained from the same wording.
- **Effect on the study:** none. P2 was ahead under both prompts (0.1665 vs 0.1399, then 0.1774 vs
  0.1275). The paper can disclose P1's sensitivity to wording in one sentence.

## Step 5 and AC-009-9 (2026-11-09, native Windows CPU, commit a3bff5c)

Step 5 ran on Sandy's Windows machine, not the lab. It needs no GPU, and the 15 router runs were
already local (PR #6). Logs are in `outputs/verification/windows-20261109/`. The lab logs are in
`outputs/verification/lab-5090-20261105/`.
- **Evidence received:** `qwen-dev.tar.gz`, SHA-256 `d6b3e9de…7c81`. It arrived without its
  `.sha256`, so this hash is a record, not a transfer check. It holds only plain files under
  `outputs/`: no absolute or `..` paths, no links.
  - The four output files match the hashes in their provenance.
  - The three input hashes match the local `data/interim/stage2/` files.
  - The main run is `p2`, `selected_variant` true, all conditions, model commit
    `a09a3545…`, from commit `aea7d53` with a clean tree.
- **Compose:** 15 hybrid runs, 852,930 rows, 6,587 invalid. The lab's compose of the same inputs
  gave the same counts.
- **Scores:** all 17 `score` commands exit zero: Qwen dev, Qwen transfer (136 items, 0 invalid)
  and the 15 hybrid runs. Each dev score covers 11,394 weak examples.
- **AC-009-9 met.** `analysis run --split dev` exits zero with 6 systems run and 0 not run;
  `hybrid` runs on `full`, `none` and `one` × 5 seeds. The component check passed for 48 runs,
  with 1,786 statistics (0 sparse, 0 unstable).
- **Precision (FR-10; dev diagnostic, not a finding):** hybrid `request_interpretation` L2 − L0
  benefit difference, +0.010, 95% CI [−0.009, +0.029], half-width **0.019**. The second bootstrap
  seed agrees within 0.000, so B = 10,000 stands. This half-width is about 2.5 times
  DeBERTa-large's `stage1_correct` (0.008).
- **AC-009-10 met.** `freeze check` reports only `tree_dirty` and `analysis_draft`, with no
  recipe or `llm_model` findings.
- **Inputs-file setback:** in an earlier attempt, the analysis refused the inputs file with
  `system_outside_panel: ['qwen2']`. The table key `qwen2.5-7b-instruct` needed quotes in TOML.
