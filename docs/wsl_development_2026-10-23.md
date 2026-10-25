# WSL development run, 2026-10-23

The current research work is running under Ubuntu 22.04 in
`/home/sandy/pi-wsl-20261023`, on the Linux filesystem. This is an isolated snapshot;
`~/Pragmatic-Intent` and `~/pi-007-dev` were preserved.

## State and provenance

- Source commit: `ab3e49d349182d94dc83634fb6d8acc30ae3fbe2`, plus the current working-tree
  overlay. The snapshot is deliberately recorded as `git_dirty: true`; these are dev runs.
- The snapshot manifest is `outputs/wsl_snapshot.json` in the WSL checkout. It records hashes
  for 114 overlaid files. Committed files came from a local clone without Git hardlinks.
- GitHub fetch and `git pull --ff-only` completed inside this checkout: already up to date.
- `items.jsonl` and `dialogues.jsonl` match the Windows workspace and both older WSL checkouts
  by SHA-256. Existing TF-IDF dev runs were copied from `~/pi-007-dev` for the later analysis.
- Python: `~/Pragmatic-Intent/.venv/bin/python`, version 3.12.15. The existing environment is
  reused without modifying dependencies: torch 2.11.0+cu128, transformers 4.57.6,
  scikit-learn 1.9.1, NumPy 2.5.3. The RTX 5060 is visible as sm_120; bf16 passes.

## Completed checks

| Check | Result |
|---|---|
| WSL stdlib suite | 888 tests, OK, 5 skipped, 12.809 s |
| DeBERTa pinned-tokenizer length check | All five training and dev conditions fit 512 tokens; maximum 482 training, 472 dev; no truncated inputs |
| Original micro-batch-8 smoke | Initial attempt failed with a CUDA unknown error inside TorchScript; synchronous retry completed, peak allocated memory 7.50 GiB |
| Micro-batch-4 + gradient-checkpointing smoke | Completed in 142.4 s, 64 optimizer steps, peak allocated memory 3.48 GiB; no inputs at the 512-token limit |
| Read-only freeze check | 74 ready pins and the same 8 unresolved items; no freeze written |

The CUDA error's root cause remains unconfirmed. Isolated relative-position operations and
model forward/backward checks passed. The successful smoke tests used `CUDA_LAUNCH_BLOCKING=1`;
the grid records and retains that runtime setting. No model source or package version was changed.
Smoke scores are pipeline checks, not evidence of final model quality.

## Dev grid

**Complete** at `2026-10-25T05:55:56Z`; see [Grid complete](#grid-complete). The detached
supervisor was started at `2026-10-24T03:42:32Z` (PID **599**), with
encoder checkpointing (see [Restart with checkpointing](#restart-with-checkpointing)); the
original launch was `2026-10-23T16:57:37Z`, PID 365.
It runs DeBERTa-v3-base for `none`, `one`, `full` training conditions, each with seeds
`13`, `42`, `2026`, `314`, `2718`: **15 runs**, scored under all five dev context conditions.

- Config: `configs/stage1/encoder_deberta_v3_base.toml`.
- Model revision: `8ccc9b6f36199bec6961081d44eb72fb3f7353f3`.
- Runtime overrides: micro-batch 4, gradient checkpointing, effective batch 32, bf16, two epochs,
  `--checkpoint-every 250` (about every 6 minutes).
- Environment controls: `TOKENIZERS_PARALLELISM=false`, `OMP_NUM_THREADS=4`.
  `CUDA_LAUNCH_BLOCKING` has been off since 2026-10-24T05:41Z. A failed run is retried once
  with it on, resuming from the run's checkpoint (see [Launch blocking off](#launch-blocking-off)).
- Each run writes the existing predictions, resolved config, metrics and result-log artifacts.
- The supervisor stops on the first failed run. It preserves completed runs and refuses a
  changed-code resume or a duplicate live supervisor.
- After all 15 runs succeed, it writes `outputs/verification/inputs-dev-with-encoder.toml`
  containing those runs and the two existing TF-IDF runs, then runs the dev analysis. The
  expected report is `outputs/analysis/dev/report.json`.

Check live state in WSL:

```bash
cd ~/pi-wsl-20261023
cat outputs/verification/deberta-dev-grid-state.json
tail -n 20 outputs/verification/deberta-dev-grid-supervisor.log
```

The state's `current.log` points to the active run log. To resume after a stopped/failed run,
first inspect and resolve the recorded failure, then run:

```bash
cd ~/pi-wsl-20261023
~/Pragmatic-Intent/.venv/bin/python -u outputs/verification/run_deberta_dev_grid.py
```

Resumption skips completed matching runs. An interrupted training run resumes from its last
checkpoint (`outputs/stage1/deberta-v3-base/train-<condition>/seed<N>/checkpoint.pt`), so a
crash or sleep costs at most 250 steps. Keep the snapshot's source and config fixed while the
supervisor runs. This grid
will take many hours on the 5060. It does not run the held-out test split, settle the primary
system or rules-version choices, or create a freeze.

At handoff the first run had reached step 100/6,342, with average loss 1.0736 and approximately
20 training examples/s. That early throughput suggests roughly two days for the full grid;
this is a rough estimate, and longer-context runs can differ. No full run had finished yet.

## Interruption and resume

The first attempt at `none`/seed 13 reached step 5,000/6,342 (12:04 PDT, average loss 0.23,
about 21 examples/s), then stopped without a traceback. Windows logs show it was not a GPU
or driver fault: at 12:06:33 PDT the host entered sleep (Kernel-Power 42, reason "Application
API", requested through `winlogon.exe`; event 187). It resumed at 18:46 PDT and the WSL VM
restarted, killing the supervisor while its state still read `running`. Idle sleep on AC was
already *Never*, so this was an explicit sleep request (Start → Sleep, a sleep key or the power
button), not a timeout.

The supervisor was resumed at `2026-10-24T01:49:18Z` (PID 394; first run PID 398) with the
same code-inputs digest `a1e90bac…`. No run had completed, so `none`/seed 13 restarted from
step 0; the interrupted attempt stays in the same run log above a new `GRID ATTEMPT` marker.
The pre-resume state is kept as `outputs/verification/deberta-dev-grid-state.interrupted-20261023.json`.
Before checkpointing, each interruption lost the current run (about 2.7 hours).

## Restart with checkpointing

At Sandy's request, `src/stage1/encoder.py` gained `--checkpoint-every N`. It saves the model,
optimizer, scheduler, data order and RNG states every N optimizer steps and when training
ends. It writes atomically and refuses a checkpoint from another run's fingerprint. A resumed
run reproduces the uninterrupted run's batches and dropout stream.
- Tests: `tests/test_encoder_checkpoint.py`, 10 tests. They include bitwise-identical final
  weights after an interruption mid-epoch, at an epoch boundary, and twice in a row. The full
  suite gives 898 tests, OK, in WSL (5 skipped) and on Windows (18 skipped, no torch).
- GPU check: `deberta-smoke-checkpoint-resume-20261024.log`. The smoke run was SIGKILLed after
  its step-32 checkpoint, then resumed at 32/64 and finished. The checkpoint (2.2 GB, 2–4 s per
  save) was deleted afterwards, `resumed_at_steps = [32]` was recorded, and the peak memory was
  unchanged at 3.48 GiB.

The source change alters the code-inputs digest, so the grid could not resume the old state.
The second attempt at `none`/seed 13 (about 1 h 50 min, unfinished) was stopped. Its state was
archived as `deberta-dev-grid-state.superseded-20261024.json`, its log as
`deberta-v3-base-train-none-seed13.pre-checkpoint.log`, and the previous supervisor as
`run_deberta_dev_grid.pre-checkpoint.py`. The snapshot manifest records the five synced files
under `amendments`. The fresh grid started at `2026-10-24T03:42:32Z`, digest `3a7e23bf…`,
with all 15 runs still to do.

## Launch blocking off

The GPU sat at about 14% utilization with `CUDA_LAUNCH_BLOCKING=1`. At Sandy's request the grid
was stopped right after the step-4,750 checkpoint of `none`/seed 13, so no steps were lost.
The supervisor was patched (previous version: `run_deberta_dev_grid.blocking.py`) and
relaunched at `2026-10-24T05:41:03Z`, PID 794. The code digest is unchanged.
- **Default:** `CUDA_LAUNCH_BLOCKING` is now unset for runs and the analysis.
- **Fallback:** if a run exits nonzero, the supervisor sets `cuda_launch_blocking = true` and
  logs the event in `blocking_fallbacks`. It then retries that run once, resuming from its
  checkpoint. A second failure stops the grid as before.
- **Logs:** each attempt's log line records its `CUDA_LAUNCH_BLOCKING` value. A supervisor
  restart resets the setting to off.

| Steps (`none`/seed 13) | Blocking on, first attempt | Blocking off, after resume |
|---|---|---|
| 4,900 | loss 0.2366, 21 ex/s | loss 0.2366, 36 ex/s |
| 5,000 | loss 0.2316, 21 ex/s | loss 0.2316, 37 ex/s |

Throughput rose about 1.75× and GPU utilization to about 30–40%. The logged losses match the
uninterrupted first attempt to four decimals. That also checks checkpoint resume at full
scale: this attempt had been stopped and resumed twice. Estimated remaining time dropped from
about 45 h to about 27 h (rough; context runs are slower).

## Grid complete

All 15 runs completed, the last at `2026-10-25T05:54:25Z`, with no failed run and no fallback to
`CUDA_LAUNCH_BLOCKING`. Each run took 1 h 39 m – 1 h 46 m. Context runs were not noticeably
slower than `none`. The whole grid took about 26 hours from the 03:42Z restart; the PC stayed
awake. Each run's checkpoint was deleted after it finished.

The supervisor then wrote `outputs/verification/inputs-dev-with-encoder.toml` and ran the dev
analysis: 17 runs, component check passed, 480 statistics with none sparse or unstable, 91 s.
A manual rerun took 90 s and gave a byte-identical `report.json`.

Matched dev accuracy, mean of 5 seeds (dev diagnostics, not findings):

| Train = eval | `none` | `one` | `full` |
|---|---|---|---|
| `deberta-v3-base` | 0.906 | 0.907 | 0.908 |

Seed SD is at most 0.0016 in each cell. The precision numbers and the context contrasts are in
the 2026-10-25 D-07 entry of `specs/memory/decisions.md` and in spec 007's
[verification](../specs/007-analysis-error-audit/verification.md). This closes T14, pending Sandy's
review.

## Evidence files

Live logs, launcher and state are under `~/pi-wsl-20261023/outputs/verification/`.
Copies of the completed preflight evidence are under the Windows workspace's
`outputs/verification/wsl-20261023/`. Those copies are snapshots, not live progress files. The
final grid state, the supervisor and analysis logs, the analysis inputs, and the dev analysis
report and tables (`analysis-dev/`) were copied there on 2026-10-25.

## Final checkout checks

Git's local `core.autocrlf=true` matches the overlaid Windows text files without changing
file bytes. Byte-pinned manifest files keep their existing line endings. The CRLF-aware
whitespace check passes. A conservative transcript rescan read 30 session-log files and found
22 mentioned test dialogues, all already in the inspection registry: **zero unregistered**.
No registry or held-out membership was changed.
