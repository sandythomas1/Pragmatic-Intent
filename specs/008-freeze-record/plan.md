# Plan 008: Freeze record

_Revised 2026-10-22 after [review](review.md) (R1–R14)._

## Approach

Add one stdlib module, `src/data/freeze.py`, with a small CLI: `check`, `write`, `verify`, `amend`
and `show`. One function, `compute_pins(inputs, root) -> dict[str, str]`, computes the current
state. Every command is a comparison built on it:
- `check` and `write` run the preconditions over that state;
- `verify` compares it with the record's `pins`;
- `amend` diffs it against them.

Writing and verifying therefore cannot disagree about what a pin means.

Pins **reuse existing hashes and checks** wherever they exist. They never reimplement them:
- `split_audit.file_sha256` and `pre_freeze_sha256`;
- `test_audit.require_test_audit`;
- the context manifest summary's `manifest_sha256`;
- `analysis.config.load_config(...).sha256` and `canonical_sha256`;
- `auto_levels_v2.require_freeze`.

New hashes exist only where nothing exists today:
- **code files, prompts and committed TOML:** text hashed after CRLF→LF, as
  `auto_levels_v2.rules_sha256` does;
- **Stage 1 recipes:** a *recipe hash*, `canonical_sha256` of `RunConfig.to_dict()` with the
  run-time fields removed. It is computed the same way from a recipe TOML (at freeze time) and from
  a run's `config.resolved.json` (at analysis time), so the two can be compared directly.

The record is a flat JSON object. Spec 006 and spec 007 read `freeze_date` and
`analysis_config_sha256` at the top level, and they continue to. It holds:
- `pins`: the effective state;
- `original_pins`: the state at write time, which never changes;
- `amendments`: an append-only list. Each amendment carries the `content_sha256` of the record it
  replaced, so the history is a hash chain;
- `content_sha256`: the canonical hash of the record without that field, the same pattern as the
  split audit summary;
- informational fields (`written_at_commit`, `tool_version`, `inputs_path`), which are never
  verified.

The gates are one call, `require_freeze(*, run: RunIdentity | None = None) -> FreezeRecord`, made
at four test branches. Dev branches are untouched.
- The Stage 1 gate sits in `runner.load`. It has the seed, `--smoke` and the resolved config, and
  runs before any data is prepared.
- The analysis applies the same `RunIdentity` check to each Stage 1 run directory listed in the test
  inputs.

## Architecture

```
configs/freeze/freeze-v1.toml   analysis config path; code globs; per-system recipes, seeds, llm_model
src/data/freeze.py
  FreezeError(code, keys)       named failures; messages carry keys/codes, never IDs or text
  load_inputs(path)             strict schema; repo-relative, no '..', no absolute, no symlinks
  recipe_sha256(config_dict)    canonical hash minus eval_split/train_condition/micro_batch/grad_ckpt
  compute_pins(inputs, root)    -> {"data.items": ..., "membership.registry_pre_freeze": ...,
                                    "code.src/data/contexts.py": ..., "analysis.config": ...,
                                    "recipe.deberta-v3-large.stage1": ..., ".revision", ".seeds", ...}
  preconditions(...)            -> [Finding(status, code, key)]   (FR11; scan reported as counts)
  conditions_for(system)        matched -> none/one/full; test_time -> full; untrained llm -> untrained
  build_record / write_record   sorted keys, LF, trailing newline, <= 64 KiB, content_sha256
  require_freeze(path, run)     integrity + recompute + optional grid membership (FR12, FR17)
  amend(record, pins, on, reason)   FR13 refusals, incl. frozen_set_immutable for membership.*/data.*
  main(): check | write | verify | amend | show
data/manifests/freeze.json      written once; amended by append only (-text already)

gates (test branch only):
  src/stage1/runner.py          add --eval-split; in load(): test -> refuse --smoke, require_freeze(run=...)
                                record freeze content_sha256 in the run block of metrics.json
  src/evaluation/stage2.py      --split test -> require_freeze()
  src/evaluation/transfer.py    --split test -> require_freeze()
  src/analysis/__main__.py      run --split test -> require_freeze(); each Stage 1 run dir -> run identity check;
                                existing require_frozen_config stays (reads the verified top-level hash)
docs/freeze.md                  procedure, amendment disclosure, lab verify step
```

**Dependencies.** `freeze.py` imports `split_audit`, `test_audit`, `analysis.config`, `stage1.config`
and `auto_levels_v2`, all of which are stdlib. The gate modules import `freeze.py`. Nothing imports
the gates back, so there is no cycle. `analysis/freeze.py` stays the small reader the error audit
uses.

## Alternatives Considered

- **A two-stage freeze (data around Nov 1, then models before Nov 9).** Rejected by Sandy on
  2026-10-22. It needs a staged record and two dates, and the gain is small: between Nov 1 and Nov 9
  only dev is touched, and any test inspection in that window is still excluded as `pre_freeze`.
- **Pinning only the git commit.** Rejected. A commit can't pin the untracked `items.jsonl` or
  `dialogues.jsonl`. `HEAD` moves as soon as `freeze.json` is committed. And an unrelated edit would
  invalidate the freeze instead of producing a narrow amendment. The commit is kept as an
  informational field.
- **Hashing every tracked file.** Rejected for the same reason: too broad. A docs typo would become
  an amendment, and amendments would turn into noise that hides the real changes. Explicit globs
  keep new modules in scope without that noise.
- **Pinning Stage 1 recipes by file hash.** Rejected (review R2). A test run would need either an
  edited copy of the file (a different hash) or a raw-text pin that moves with comments. The recipe
  hash over parsed, run-time-neutral content is stable, and it can be compared with the
  `config.resolved.json` that every run already writes.
- **One global seeds × conditions grid.** Rejected (review R4). It contradicts spec 007's designs
  (`test_time` trains `full` only; an untrained LLM uses seed 0).
- **Rewriting `freeze.json` on amendment with no history, or one file per amendment.** Rejected. A
  rewrite loses the audit trail that spec 001 §7 requires. Separate files would need a second reader
  in specs 006/007.
- **Gating only the scorers and analysis.** Rejected by Sandy on 2026-10-22. A 5090 run that can't
  be reported should fail before it starts.
- **Gating in a wrapper script.** Rejected. It is easy to bypass by calling the module directly.

## Tradeoffs

- **Strictness vs. agility.** Pinning trainer code and recipes means any post-freeze fix is an
  amendment. That is the point: the paper must disclose it. It also adds friction during the Nov 9–13
  grid, when bugs are most likely. Amendments are cheap (one command), and that offsets the friction.
  Membership and data can't be amended at all. If the test set itself is wrong after the freeze,
  that is a new freeze version and a visible delay. That is the intended cost.
- **Verify cost on every test command.** It hashes about 70 MB plus the code, which takes seconds.
  `require_test_audit` re-hashes the same files; that duplicated cost is accepted to keep both checks
  independent. Caching by mtime was considered and dropped (YAGNI): a stale cache is exactly the
  failure a freeze must not have.
- **Tamper-evident, not tamper-proof.** Someone who edits both a pinned file and `freeze.json` and
  recomputes `content_sha256` defeats `verify`. Git history (`freeze.json` committed before the grid)
  is the defence. Anything stronger is out of scope for a solo class project.
- **One freeze date, strictly after the last pre-freeze inspection.** The transcript rescan has to
  happen at least a day before the freeze. Any test inspection before the freeze is `pre_freeze`,
  so the dialogue is excluded, which is the stricter treatment.
- **Grid membership is enforced for Stage 1 only.** Stage 2 and transfer files can't prove their
  recipe. The record pins the LLM prompt and snapshot, but which file came from which recipe is
  declared. This is stated as a limitation, not hidden.
- **Smoke runs on test are refused.** Sandy loses a quick end-to-end check on test. A dev smoke run
  plus `freeze verify` on the lab machine covers the same risk without touching test.

## Risks

- **The freeze slips past Nov 8**, because the primary system, recipes or the `auto-v2` decision
  are not ready. Mitigation: `check` exists from the first task and lists the gaps. The spec 007
  fallback question must be answered by about Nov 5.
- **Gate changes break existing tests** in stage1, stage2, transfer and analysis. Mitigation: add a
  fixture freeze helper to the existing test workspaces, and run the full suite on Windows *and*
  WSL, with and without GitHub Desktop's git on PATH.
- **Differences between the lab and local machines.** Regenerated `items.jsonl` could differ.
  Mitigation: spec 006 already showed WSL and Windows agree. `verify` names `data.items`, and
  `docs/freeze.md` makes running `verify` on the lab machine the step before the first grid run.
- **The recipe hash drifts from `config.resolved.json`**, for example through float formatting or
  tuple-vs-list. Mitigation: hash `RunConfig.to_dict()` after a JSON round trip on both paths, and
  test that a TOML and the resolved JSON written from it give the same hash.
- **Leaking test IDs** through scan messages or amendment reasons. Mitigation: counts and paths
  only (FR15), the ID-pattern check on reasons, and a no-ID output test.
- **Sandy's LLM code arrives late, in an unknown shape.** Mitigation: generic recipe files plus
  `llm_model`. Nothing LLM-specific is hard-coded.
