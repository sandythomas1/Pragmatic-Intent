# WP-09 frozen test grid on one RTX 5090 (runbook)

Prepared 2026-11-18 for Sandy. It runs the whole WP-09 test grid on **one** lab RTX 5090, in
sessions, in priority order. Every tool here refuses to start unless the freeze verifies
(`data/manifests/freeze.json`, content `5c5759f767c9` after amendment 1).

Nothing in this pipeline ever needed two GPUs: each trainer and vLLM use one device. The launcher
now enforces that. `GPU=<index>` becomes `CUDA_VISIBLE_DEVICES`, so the other card is never
touched.

## Time budget

Training time doesn't depend on the eval split, so the dev grid's lab timings carry over.

| Work | Runs | GPU time | Source |
|---|---|---|---|
| TF-IDF utterance + context | 2 | ~1 min (CPU) | measured |
| Qwen2.5-7B test run (main + transfer) | 1 | ~30 min, mostly model load | dev main run, 2026-11-05 |
| DeBERTa-v3-large | 15 (5 seeds × none/one/full) | **11.7 h**: 2.3 h per seed (0.6 + 0.6 + 1.1) | measured, lab 2026-10-27 |
| Hybrid compose + scoring | — | minutes (CPU) | dev, 2026-11-05 |
| DeBERTa-v3-base | 15 | ~4–6 h | estimate: never run on the 5090 (24.2 h on the RTX 5060) |

**Total ≈ 17 h of one GPU.** It doesn't have to be in one block: every unit below is resumable.

**Plan chosen by Sandy on 2026-11-18: two overnight blocks.**

| When | What | Sections below |
|---|---|---|
| Evening 1, while you're at the lab (~1.5 h) | Session 0 setup, then Session 1. Watch both: any freeze or test-gate problem shows up here, not at 3 a.m. | Session 0, Session 1 |
| Night 1 (~11.7 h) | All 15 DeBERTa-large runs in one go: `GPU=0 SYSTEMS="deberta-v3-large" scripts/stage1_test_grid.sh lab-5090` in tmux, with no `MAX_RUNS` | Sessions 2–6 |
| Morning 2 (minutes) | Compose, scoring, and the evidence archive | Session 7 |
| Night 2 (~4–6 h) | DeBERTa-base: the same command with `SYSTEMS="deberta-v3-base"` and no `MAX_RUNS` | Sessions 8–9 |

- **If night 1 stops early:** rerun the same command the next night. Verified runs are skipped.
- **Base is the cut.** If night 2 can't happen before Nov 26, skip it. The paper then says it
  wasn't run on test.

## Order and why

1. **TF-IDF, then the Qwen test run.** Both are cheap, and each exercises a different test gate
   (Stage 1 trainer, LLM runner) end to end. A freeze or audit problem then shows up in minutes,
   not after hours of training.
2. **DeBERTa-v3-large, seed by seed.** These are the primary system's routers: the hybrid needs
   all 15. Each seed's none/one/full runs together, so a stop leaves complete seeds.
3. **Compose the hybrid and score.** CPU only, once all 15 large runs exist.
4. **DeBERTa-v3-base last.** It's a secondary baseline. If the time runs out before Nov 26, drop
   it; the paper then discloses that it wasn't run on test.

## Rules for every session

- **One GPU, one job.** Pick the card with `nvidia-smi` and use the same `GPU=` every session.
  Never run vLLM and an encoder at the same time on it: vLLM reserves 80% of the card.
- **Use tmux.** Long runs must survive an SSH drop: `tmux new -s wp09`, and later `tmux attach -t wp09`.
- **Stopping.**
  - **Clean stop:** `touch outputs/stage1-test/STOP` ends the session after the current run.
    Delete the file before the next session.
  - **Ctrl-C is also safe.** The encoder resumes from its last checkpoint (every 250 steps), so
    at most a few minutes of training is lost.
  - **Resuming:** rerun the same command. Verified runs are skipped.
- **Don't edit tracked files** in this checkout. A dirty tree is recorded in every provenance
  file. If something needs a change, stop and send me the error line.
- **What to share.**
  - Safe to paste to me: logs, `results/stage1-test.jsonl` and `metrics.json` files. They hold
    aggregates, hashes and counts.
  - Never paste: `predictions.jsonl`, stage-2 streams or cache files. They contain **test**
    example IDs or corpus text. Keep them in private storage.

## Session 0: setup (no GPU, ~45 min)

Use a fresh clone of `main` on the lab's Linux filesystem, made after the WP-09 launcher PR
has merged. Before that merge, `main` doesn't have `scripts/stage1_test_grid.sh`. Setup steps
match `docs/llm_lab_runbook.md` step 1, but on `main` and for the test split.

Any free lab computer with a 5090 works. Run `nvidia-smi` and use the 5090's index as `GPU=`
everywhere below; the examples say `GPU=0` and `CUDA_VISIBLE_DEVICES=0`. Keep the
`lab-5090` label, so the test runs match the dev grid's provenance.

```bash
set -euo pipefail
git clone --branch main https://github.com/sandythomas1/Pragmatic-Intent.git pi-test
cd pi-test
git log -1 --format='%H %s'                    # send me this line
unset UV_PROJECT_ENVIRONMENT                    # Stage 1 uses the project .venv
uv sync --locked --group gpu
PY="uv run --locked --no-sync python -E -s"
$PY -m src.data.download_sources --only direct multiwoz indirect_requests
$PY -m src.data.build_direct_dataset > /dev/null
$PY -m src.llm.prompt_gen render --out outputs/llm/prompts/p2.txt    # pinned, git-ignored (FR18)
$PY -m src.data.freeze verify                   # must print "verified"; otherwise stop and send me the output
git status --short                              # must print nothing
GPU=0 scripts/stage1_test_grid.sh lab-5090 --dry-run   # 32 planned runs, nothing written
```

**Stop conditions:**
- `freeze verify` doesn't print `verified`. If `data.items` or `data.dialogues` differ, the
  regenerated data isn't the frozen data. **Do not amend**; send me the output.
- `git status --short` prints anything.
- The dry run doesn't end with `32 run(s) planned`.

**LLM inputs for the test split.** These run in the vLLM environment, inside a subshell so
`UV_PROJECT_ENVIRONMENT` never leaks into the Stage 1 launcher. The launcher refuses to run if
that variable is set.

```bash
(
  export UV_PROJECT_ENVIRONMENT=$HOME/.venvs/pi-llm
  PI="uv run --locked --no-sync python -E -s"
  uv sync --locked --group llm
  mkdir -p data/interim/stage2 outputs/verification
  $PI -m src.evaluation.stage2 inputs --split test --allow-test --mode routed \
    --out data/interim/stage2/test_routed_inputs.jsonl
  $PI -m src.evaluation.stage2 inputs --split test --allow-test --mode oracle \
    --out data/interim/stage2/test_oracle_inputs.jsonl
  $PI -m src.evaluation.transfer inputs --split test --allow-test \
    --out data/interim/stage2/indirect_requests_test_inputs.jsonl
  sha256sum data/interim/stage2/test_*_inputs.jsonl data/interim/stage2/indirect_requests_test_inputs.jsonl
)
```

Send me the three checksums. I'll regenerate the files on Windows and compare them, as for dev.

## Session 1: TF-IDF and the Qwen test run (~45 min)

```bash
GPU=0 SYSTEMS="tfidf-utterance tfidf-context" scripts/stage1_test_grid.sh lab-5090

(
  export UV_PROJECT_ENVIRONMENT=$HOME/.venvs/pi-llm TOKENIZERS_PARALLELISM=false
  export VLLM_USE_FLASHINFER_SAMPLER=0 CUDA_VISIBLE_DEVICES=0      # the same card as GPU=
  PI="uv run --locked --no-sync python -E -s"
  $PI -m src.llm.run run --recipe configs/llm/qwen2.5-7b-instruct.toml --split test --task main \
    2>&1 | tee -a outputs/verification/llm-test-main.log
  $PI -m src.llm.run run --recipe configs/llm/qwen2.5-7b-instruct.toml --split test --task transfer \
    2>&1 | tee -a outputs/verification/llm-test-transfer.log
)
```

- **Inputs and prompt.** A test run always uses the recipe's selected prompt (P2) on every
  condition. `--conditions`, `--sample` and `--variant` are refused on test.
- **Resuming.** Both runs resume from the response cache if repeated.
- **Done check.**
  - Main: `outputs/stage2/qwen2.5-7b-instruct/test/provenance.main.json` exists.
  - Transfer: `provenance.transfer.json` exists in the same folder.

## Sessions 2–6: DeBERTa-v3-large (2.3 h each, or 11.7 h overnight)

Three runs make one seed:

```bash
GPU=0 SYSTEMS="deberta-v3-large" MAX_RUNS=3 scripts/stage1_test_grid.sh lab-5090
```

- **Repeat it once per session.** Each repeat skips the finished seeds and starts the next one.
- **To run more than one seed:** raise `MAX_RUNS`, or leave it unset to run all that remain.
- **Progress:**
  - Each session ends by printing `session: N run(s) started, M left for a later session`.
  - To watch a run live: `tail -f outputs/stage1-test/logs/*.log`.

## Session 7: compose the hybrid and score (CPU, minutes)

Run this once all 15 large runs exist and the Qwen main run has finished.

```bash
(
  export UV_PROJECT_ENVIRONMENT=$HOME/.venvs/pi-llm
  PI="uv run --locked --no-sync python -E -s"
  Q=outputs/stage2/qwen2.5-7b-instruct/test
  $PI -m src.llm.compose compose --split test \
    --router-root outputs/stage1-test/deberta-v3-large --interpreter $Q \
    2>&1 | tee outputs/verification/llm-test-compose.log
  $PI -m src.evaluation.stage2 score --split test --allow-test --predictions $Q/routed.jsonl \
    --oracle-predictions $Q/oracle.jsonl --out outputs/stage2/metrics/qwen2.5-7b-instruct.test.json
  $PI -m src.evaluation.transfer score --split test --allow-test --predictions $Q/transfer.jsonl \
    --model-family qwen --out outputs/stage2/metrics/qwen2.5-7b-instruct.transfer-test.json
  for c in none one full; do for s in 13 42 2026 314 2718; do
    H=outputs/stage2/hybrid/test/train-$c/seed$s
    $PI -m src.evaluation.stage2 score --split test --allow-test --predictions $H/routed.jsonl \
      --oracle-predictions $H/oracle.jsonl --out outputs/stage2/metrics/hybrid/train-$c.seed$s.test.json
  done; done
)
```

`compose` checks every router run and the Qwen run against the freeze before writing anything.
Every `score` must exit zero; if one fails, send me its error line.

**Evidence back** (send it privately: it holds test predictions):

```bash
tar -czf ../wp09-test-evidence.tar.gz outputs/stage1-test outputs/stage2 outputs/verification \
  results/stage1-test.jsonl
sha256sum ../wp09-test-evidence.tar.gz > ../wp09-test-evidence.tar.gz.sha256
git log -1 --format='%H' > ../wp09-test-evidence.commit
```

Then I write `configs/analysis/inputs-test.toml` (`split = "test"`, Stage 1 runs under
`outputs/stage1-test/`) and run `python -m src.analysis run --split test` locally.

## Sessions 8–9: DeBERTa-v3-base (~4–6 h)

```bash
GPU=0 SYSTEMS="deberta-v3-base" MAX_RUNS=6 scripts/stage1_test_grid.sh lab-5090
```

`MAX_RUNS=6` is two seeds per session. Send its `outputs/stage1-test` runs with a second
evidence archive, or wait and include them in the first one.

## How the launcher protects the grid

| Risk | Guard |
|---|---|
| Using both GPUs | `GPU` must be one index; it becomes `CUDA_VISIBLE_DEVICES` |
| A run outside the frozen grid | `scripts/plan_test_grid.py` checks every run with the trainers' own freeze check before the first model loads |
| Reusing a stale or edited run | a completed run is skipped only if its artifacts verify **and** it was written under the current freeze content; anything else refuses the whole plan |
| Overwriting the dev grid | test runs write to `outputs/stage1-test/` and `results/stage1-test.jsonl` only |
| Two launchers at once | a lock on `outputs/stage1-test/.lock` |
| Syncing GPU packages into the vLLM env | the launcher refuses while `UV_PROJECT_ENVIRONMENT` is set |
| A trainer eating the plan | each trainer's stdin is `/dev/null` |
