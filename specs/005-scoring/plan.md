# Plan 005

Use additive modules and explicit versions. Keep `auto_levels.auto_level` as v1, and dispatch
`level_item(..., version=...)` to a separate `auto_levels_v2` module only when requested. Add a
v2 CLI for freeze/held-out validation/fresh spot checks, reusing the v1 label loader and metrics.
Reconstruct the old v1 spot-check membership from its recorded seed and pinned input when the
git-ignored key is absent on this checkout; record that provenance and exclude those turns.

`src/evaluation/interpretation.py` owns weak act references, conservative normalization,
strict structured predictions and exact/slot outcomes. `src/evaluation/stage2.py` owns the
CLI, shared input export, per-condition denominators, oracle/routed streams, slices and grouped
paired contrasts. Reuse Stage 1 example selection and `scoring_sets`; no new data selection.

`src/data/indirect_requests.py` validates local transfer records and exports safe input fields.
`src/evaluation/transfer.py` scores detection/value recovery separately. Candidate aliases are
paired by position; ambiguous is always an available abstention candidate. Input exports and
predictions stay under git-ignored local output; committed docs and reports have counts only.

Risks: noisy weak acts, sparse L3 ground truth, accidental held-out tuning, and denominator
drift. Mitigations: label weak metrics honestly, freeze/hash rules before the held-out check,
keep v1 default, require complete streams, test route failures and common-set pairing, and
document missing human evidence. Normalization is intentionally limited and versioned.

Test first in small invented fixtures; run focused modules, then the whole suite. Smoke-check
all pinned transfer split schemas and act-reference coverage without model inference. Verify
v1 predictions remain unchanged on a corpus-level digest captured before editing.
