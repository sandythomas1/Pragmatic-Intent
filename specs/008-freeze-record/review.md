# Review: Spec 008

Verdict: NEEDS REVISION, then **READY** after revision (2026-10-22). R1–R14 were applied to
`spec.md` and `plan.md` in the same session:
- R1 → FR11 (strictly-after date);
- R2 → FR8 recipe hash and FR18 `--eval-split`;
- R3 → FR16;
- R4 → FR1/FR2 per-system seeds and derived conditions;
- R5 → FR17 and Non-Goals;
- R6 → FR13 `frozen_set_immutable`;
- R7 → FR15;
- R8 → FR11 `git_unavailable`;
- R9 → FR9 informational fields;
- R10 → FR13 explicit preconditions;
- R11 → AC-008-01 on fixtures;
- R12 → FR1 globs;
- R13 → Non-Goals (the adapter's own source check);
- R14 → FR13 reason rules.

**Correction (T9, 2026-10-22).** R3 claimed that "there is no separate Stage 1 test scorer".
That was wrong. `src.evaluation.stage1` has a `--split test` CLI, and so does the legacy
`src.evaluation.run`. Both are now gated, and FR16 lists them. The check had searched for
`allow_test`, which neither of them uses.

The revision also adds two items:
- `gradient_checkpointing` is neutralized in the recipe hash (`encoder.py` exposes it as a memory
  knob);
- `--smoke` is refused on test.

Reviewed 2026-10-22 against `spec.md` and `plan.md` (draft of 2026-10-22). Each claim below was
checked in the code: `src/data/split_audit.py`, `src/stage1/runner.py` and `src/stage1/config.py`,
`src/analysis/inputs.py`, `src/evaluation/test_audit.py`, `src/analysis/freeze.py`, and the
encoder configs.

## Findings

### R1 (blocking, correctness): a freeze dated on the same day as an inspection breaks the registry
FR10 only forbids `--on` earlier than the latest `pre_freeze` `inspected_on`, so the two dates can be
equal. `split_audit.phase_for` is strict: an inspection is `pre_freeze` only if `inspected_on <
freeze_date`.

The scenario is the planned one. Claude reruns the transcript scan on the morning of the freeze,
which registers a row dated that day as `pre_freeze`. Then `write --on <same day>`. From then on:
- every `split_audit register` or transcript rescan re-derives that row as `post_scoring`;
- `merge_rows` sees that it "differs from the committed row" and fails;
- so the registry can never be updated again, and the post-scoring error audit can't register its
  sample.

**Fix:** FR10 requires `--on` to be **strictly after** every `pre_freeze` `inspected_on`. The rescan
therefore happens at least one day before the freeze. Add this case to AC-008-03.

### R2 (blocking, clarity): no test recipe can match a pinned dev recipe
`eval_split` exists only in the config file (`[data] eval_split`), with no CLI override. So a test
run needs either:
- a different TOML file, whose file hash differs from the dev recipe that was chosen; or
- a new override.

`config.sha256()` also covers the resolved `train_condition` and `micro_batch_size` overrides.
"Its config file hash is in the system's pins" (FR15) is therefore unimplementable as written, and
two engineers would build different things.

**Fix:**
- Define a **recipe hash**: canonical JSON of the parsed config with the run-time fields
  neutralized (`data.eval_split`, `data.train_condition`, `encoder.micro_batch_size`).
- Pin that, and add `--eval-split` to the runner's common args, so one recipe file serves both dev
  and test.
- In addition, pin the text hash of the recipe file, so comments can't silently change and a
  reader can find the file.

### R3 (blocking, clarity): the gate list names entry points that don't exist
- `src.stage1.runner` is not an entry point. Stage 1 runs through `src.stage1.tfidf` and
  `src.stage1.encoder`, which share `runner.load`/`runner.prepare`.
- There is no separate Stage 1 test scorer: scoring happens inside `runner.finish`.
- "Stage 1 ... test scorers" in FR14 has no target.

**Fix:**
- Put the Stage 1 gate in the shared runner path, at the same point as the existing
  `require_test_audit` (`runner.prepare`, `eval_split == "test"`). That covers both trainers and
  any future trainer that uses the runner.
- The other gates are `src.evaluation.stage2` (`--split test`), `src.evaluation.transfer`
  (`--split test`) and `src.analysis run --split test`.

### R4 (blocking, correctness): one global grid conflicts with spec 007's design rules
FR8 pins "the grid's training conditions and seeds" as a single set. Under spec 007 FR6 the
conditions depend on the system:
- `matched` systems train `none`, `one` and `full`;
- `test_time` systems train `full` only (`tfidf-context` cannot train `none`);
- an untrained LLM declares `untrained` with seed 0.

Seeds can differ too (TF-IDF has one dev seed; the encoders have 5). A global grid would either
refuse legitimate runs or admit runs that aren't intended.

**Fix:**
- Pin the seeds **per panel system** in the freeze inputs.
- Derive the conditions from the system's `design` in the frozen analysis config, using spec 007's
  rule, not a second list that could disagree.

### R5 (blocking, correctness): FR15 cannot apply to Stage 2 or transfer scoring
The Stage 2 and transfer scorers receive a predictions file and a `--model-family`. They have no
run identity (recipe, seed or condition) to check, and `inputs.py` admits that "Stage 2
provenance ... can only be declared". As written, FR15 is untestable for those gates.

**Fix:** enforce grid membership in two places only:
- the Stage 1 runner, when a run starts;
- the test analysis, for every Stage 1 run directory, using its `config.resolved.json` (recipe hash
  and train condition) and `metrics.json` (seed).

Stage 2 and transfer only `verify` the freeze. State in the spec that Stage 2 provenance is
declared, not enforced, and that the paper says so.

### R6 (blocking, research integrity): amendments must not move the frozen test set
Spec 006 says the frozen set never moves: a post-freeze inspection is `post_scoring`, and
`merge_rows` refuses new `pre_freeze` rows. FR12 lets `amend` repin any key, including:
- `membership.*` (audit, registry `pre_freeze`, manifest);
- `data.items` and `data.dialogues`.

So an amendment after test scoring could silently re-scope the test set. That is exactly the
selection-after-seeing-results problem the freeze exists to prevent.

**Fix:**
- `amend` refuses changes to `membership.*` and `data.*` pins, with the code
  `frozen_set_immutable`.
- Changed data means a broken regeneration: fix the regeneration, don't repin.
- A genuine data change after the freeze is a new freeze version, out of scope here, and disclosed.
- Add the refusal to AC-008-06.

### R7 (blocking, security/leakage): the freeze must not relay `split_audit scan` messages
`scan_sheets` failure strings contain test dialogue IDs (`"test dialogue {d} is not registered"`).
If `check`/`write` print scan failures, as FR9's "with a reason code" invites, the freeze tooling
prints test IDs. Each printed ID becomes a new exclusion, under the project rule that printed test
IDs count as inspected.

**Fix:**
- The freeze reports only `scan: <n> unregistered test dialogue(s) in <k> file(s)`, plus the paths.
- It points the user to run `split_audit scan` themselves.
- Add a test that runs `check` against a fixture with an unregistered test ID and asserts the ID is
  absent from stdout, stderr and logs.

### R8 (blocking, fail-open risk): the clean-tree check and missing git
`provenance.git_state` returns `None` when git isn't on PATH. That is the default in Sandy's
native-Windows shell, where git exists only via GitHub Desktop (spec 006 retro). If `write` treated
`None` as clean, it would fail open.

**Fix:**
- FR10: a missing git or an unknown dirty state is a refusal (`git_unavailable`).
- The ignore list is explicit: `results/` and `outputs/`, as in spec 006's `git_state(ignore=...)`.
- Add tests with and without git on PATH.

### R9 (should fix, clarity): FR6 pins a git commit that `verify` can't check
After `freeze.json` is committed, `HEAD` moves, and lab clones sit at later commits. If `verify`
compared the commit, every run would fail.

**Fix:** record it as informational (`written_at_commit`), outside `pins`. Say that it is never
verified.

### R10 (should fix, clarity): FR12's last bullet is garbled
"Fails a `write` precondition other than 'no record exists' and the clean-tree rule's ignore list"
doesn't say whether `amend` requires a clean tree, or a `draft = false` config.

**Fix:** list the amend preconditions explicitly:
- every write precondition except "no record exists";
- a clean tree with the same ignore list;
- `--on` not before `freeze_date`, and not before the last amendment;
- not in the future.

### R11 (should fix, testability): AC-008-01 depends on the live repo
It asserts that `check` finds `draft = true` and the `main` revisions today. It stops being true the
moment those are fixed, so it can't be a unit test.

**Fix:** move the per-finding cases into fixture tests. Keep the real-repo `check` as a smoke check
recorded in `verification.md`.

### R12 (non-blocking, scope): the declared code list belongs in the inputs, with a default
The spec's open question about strictness of code pins is real. Pinning trainer code is consistent
with "recipes are pinned", so keep it. But the list should be explicit globs in
`freeze-v1.toml` (for example `src/analysis/*.py`), so that a new analysis module added before the
freeze is not silently unpinned. A glob that matches no files is an error.

### R13 (non-blocking, completeness): IndirectRequests raw files are not pinned
Transfer inputs come from raw files that are pinned in `data/sources.toml`, but `verify` hashes
only the TOML. This is low risk, because the adapter already checks the pinned sizes and hashes,
with 123/136/194 records. Still, it is worth one line in the spec: the transfer gate relies on the
adapter's own source check.

### R14 (non-blocking, security): the amendment reason is free text in a committed file
The constitution keeps free-text notes out of committed *annotation* files. `freeze.json` isn't one,
but a reason could quote corpus text.

**Fix:**
- Allow printable ASCII only, at most 500 characters.
- Reject the DIRECT ID pattern (already planned).
- `docs/freeze.md` says: no quotes from the corpus.

## Non-Issues Considered

- **Top-level field compatibility.** `src/analysis/freeze.py` and `split_audit.resolve_freeze_date`
  read only `freeze_date` and `analysis_config_sha256`. Extra keys and the `amendments` list are
  ignored. `resolve_freeze_date` uses an unbounded `json.loads`, which is fine for a file this
  tool writes, and `read_freeze` is bounded at 64 KiB. The record must stay under 64 KiB:
  - pins are about 100 entries of about 120 bytes;
  - amendments are small.

  Add a size check on write and amend anyway.
- **Line endings.** `data/manifests/*.json` is already `-text`, so the record is byte-stable across
  checkouts. Normalizing code and TOML before hashing matches `auto_levels_v2.rules_sha256`.
- **Performance.** `items.jsonl` (51 MB) plus `dialogues.jsonl` (19 MB) is about 70 MB. Hashing in
  1 MiB chunks takes a few seconds, so the 30 s bound is comfortable. `require_test_audit` re-hashes
  the same files; the cost is tolerable and it keeps the code simple.
- **One freeze date and the registry.** With R1 applied, every existing row (latest
  `inspected_on` 2026-10-19) re-derives as `pre_freeze` after a November freeze.
- **The analysis config hash.** It reuses `load_config(...).sha256` (canonical, so comments don't
  move it). This is consistent with spec 007 and its tests.
- **Stack and constitution.** Stdlib only, `unittest`, no services, no network. Claude builds the
  tooling and Sandy decides and runs. Commits are left to Sandy.
- **Error-audit flow.** The sampler registers `post_scoring` rows. That changes neither the
  registry `pre_freeze` hash nor `membership.*`, so `verify` stays green through the audit.
- **Tamper-proofing.** Being tamper-evident only, with git as witness, is stated honestly in the
  plan's tradeoffs. It is adequate for a class study.
