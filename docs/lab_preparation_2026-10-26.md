# Lab preparation closeout, 2026-10-26

The DeBERTa-v3-large dev handoff is packaged locally. Follow the
[lab runbook](deberta_large_lab_runbook.md) to transfer, restore, verify and run it
on the lab RTX 5090 or RTX 4090. Lab training has not started.

## Repository and scope

Fetched `origin` and ran `git pull --ff-only origin main`: already up to date at
`1016c258eeb1070542b07899812d87f1a92ab89b`. Preserved all existing uncommitted
lab-readiness changes, including the existing byte-pinned manifest files.

Sandy selected **DeBERTa-large preparation for the lab GPU** as the next priority.
Validation and packaging ran under Ubuntu 22.04 in
`/home/sandy/pi-research-20261026`, using the existing Python 3.12.15 environment
at `/home/sandy/Pragmatic-Intent/.venv`. Other WSL checkouts and completed
DeBERTa-base results were preserved. No model weights were downloaded and no
training process was launched.

## Package

The git-ignored `outputs/lab/` directory holds:

- `pi-deberta-large-20261026.tar.gz` (approximately 17 MB compressed);
- `pi-deberta-large-20261026.tar.gz.sha256` (exact archive checksum).

The archive includes an existing-history Git bundle, a working-tree overlay,
the two pinned local dataset files, per-file SHA-256 checksums, a manifest and
the runbook. The manifest records the base commit, dirty provenance, model
revision, three training conditions, five seeds, source digest and resolved
recipe hashes for both lab resource profiles. Old outputs, checkpoints, virtual
environments, machine Git configuration and credentials are excluded.

The dataset files contain third-party source text. This is a private local
handoff, not a public dataset release. Source terms remain in
[data_sources.md](data_sources.md).

## Verification evidence

| Check | Result |
|---|---|
| WSL source snapshot suite | 918 tests passed, 5 skipped, 16.242 s |
| Lockfile | `uv lock --check --offline` passed |
| Local environment | RTX 5060, torch 2.11.0+cu128; bf16 matmul passed |
| DeBERTa-large pinned tokenizer | All five train/dev conditions passed; maximum 482 train / 472 dev tokens, zero over 512 |
| Both real grid dry runs | 15 dev commands per profile; no training |
| Initial archive round trip | Bundle/history, all 205 initial exported files and source digest verified |
| Deliberate recipe edit | Checksum verification rejected it; original bytes restored and reverified |
| Restored-checkout suite | 918 tests passed, 5 skipped, 14.631 s |
| Final archive | Rebuilt with closeout docs, restored and checksum-verified again |
| Freeze readiness | 75 ready pins; five unresolved items |

Evidence is copied to `outputs/verification/lab-20261026/`. The five expected
freeze findings are `tree_dirty`, `llm_model_floating`, `analysis_draft`, and
`recipe_missing` for the LLM and hybrid. No freeze was written, no model-panel
choice was made, and no held-out examples were inspected or scored.

## Next lab action

Transfer the archive and sidecar, restore into a new Linux directory, run the
environment/length preflight, and inspect the selected GPU profile's smoke before
launching its 15-run dev grid. Keep effective batch 32 and the selected resource
profile fixed. Return the evidence archive described in the runbook for dev
analysis. The WP-08 freeze remains a separate prerequisite for reported test runs.
