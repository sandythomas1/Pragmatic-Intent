# Tasks: Spec 008

_Decomposed 2026-10-22 from the reviewed spec (R1–R14 applied). Target: tooling done well before the
Nov 8 freeze. T1–T6 are `src/data/freeze.py` on its own, T7–T8 wire the gates, and T9 closes out._

## T1: Freeze inputs schema and loader
- Description: `configs/freeze/freeze-v1.toml` (draft content for the current panel) and
  `load_inputs()` in `src/data/freeze.py`, plus `FreezeError(code, keys)`.
  - Strict schema: analysis config path, code globs, and per-system `recipes`, `seeds` and optional
    `llm_model`.
  - Repo-relative path safety, and glob expansion (an empty match is an error).
  - `conditions_for(system)`, derived from the analysis config design (FR2).
  - The panel-match check against the analysis config.
- Files likely touched: `src/data/freeze.py` (new), `configs/freeze/freeze-v1.toml` (new),
  `tests/test_freeze_inputs.py` (new)
- Depends on: none
- Security-sensitive: yes. It parses an untrusted TOML and resolves paths from it (traversal,
  absolute paths, symlinks).
- Acceptance criteria:
  - Unknown keys, wrong types, non-integer or duplicate seeds, and a missing `[systems.*]` table each
    raise a named error.
  - `..`, absolute paths, drive letters and a path through a symlink are each refused. A glob
    matching nothing is refused (`glob_empty`).
  - A panel mismatch (missing or extra system) is reported with the system names.
  - `conditions_for`: matched gives `none`/`one`/`full`; test_time gives `full`; an untrained LLM
    gives `untrained`.
  - The input file is bounded at 64 KiB.
- Status: done (2026-10-22).
  - 26 tests in `tests/test_freeze_inputs.py`.
  - The full suite: 757 tests ran, OK (8 skipped).
  - The real `freeze-v1.toml` loads and matches the real panel.
  - Manual security pass: the `security-review` skill needs git on PATH. The pass added the rejection
    of `:` paths (Windows alternate data streams) and of UNC paths.

## T2: Recipe hash and `--eval-split`
- Description: `recipe_sha256(config_dict)`: canonical hash of `RunConfig.to_dict()` (after a JSON
  round trip) with `data.eval_split`, `data.train_condition`, `encoder.micro_batch_size` and
  `encoder.gradient_checkpointing` removed. Add `--eval-split {dev,test}` to
  `runner.add_common_args` and apply it in `runner.load` (FR18).
- Files likely touched: `src/data/freeze.py`, `src/stage1/runner.py`, `tests/test_freeze_recipe.py`
  (new), existing stage1 runner tests
- Depends on: T1
- Security-sensitive: no
- Acceptance criteria:
  - A recipe TOML and the `config.resolved.json` written from it (under any train condition,
    micro-batch or eval split) give the same recipe hash.
  - Changing a semantic field (learning rate, revision, `ngram_max`, epochs) changes the hash.
    Comments don't.
  - `--eval-split test` without `--allow-test` is refused. `--eval-split dev` behaves exactly as
    before. Existing runner tests pass unchanged.
- Status: done (2026-10-22).
  - 13 tests in `tests/test_freeze_recipe.py`.
  - The full suite: 770 tests ran, OK (8 skipped).
  - The recipe hash keeps `name`, `kind`, data paths and bootstrap settings: everything except the
    four run-time fields.
  - All 6 committed Stage 1 configs hash distinctly.

## T3: Compute pins
- Description: `compute_pins(inputs, root)` gives every FR3–FR8 pin under stable dotted keys,
  reusing the existing hash functions:
  - `split_audit.file_sha256` and `pre_freeze_sha256`;
  - the split audit and context manifest summaries;
  - `analysis.config.load_config().sha256`;
  - text-normalized code hashes;
  - recipe hashes, encoder `pretrained`/`revision`, `llm_model` and seeds.

  It returns the pins plus "problem" findings: an unpinned revision, a floating alias, or a manifest
  hash that differs from the split audit's.
- Files likely touched: `src/data/freeze.py`, `tests/test_freeze_pins.py` (new)
- Depends on: T1, T2
- Security-sensitive: no
- Acceptance criteria:
  - On a fixture repo, every key family is present (`data.*`, `membership.*`, `labels.*`,
    `code.*`, `analysis.*`, `recipe.*`).
  - CRLF and LF checkouts of the same code give identical `code.*` pins.
  - `revision = "main"` or a tag gives `revision_unpinned`. An empty or `-latest` `llm_model` gives
    `llm_model_floating`. A manifest mismatch gives `manifest_mismatch`.
  - Registry `post_scoring` rows don't change `membership.registry_pre_freeze`.
- Status: done (2026-10-22).
  - 23 tests in `tests/test_freeze_pins.py`, plus a shared fixture repository,
    `tests/freeze_fixtures.py`.
  - The full suite: 793 tests ran, OK (8 skipped).
  - Real repo: 74 pins in about 0.5 s. The data and membership hashes equal those committed in the
    split audit summary.
  - Real findings: `analysis_draft`, 3 × `revision_unpinned`, `recipe_missing` for llm and hybrid,
    and `llm_model_floating`.
  - Design notes:
    - The split audit is pinned by its CSV bytes plus its recomputed `content_sha256`, not by the
      summary's bytes, because `disclosure` grows after scoring.
    - The context manifest is pinned by its CSV, not by its summary, because the summary carries
      `built_at`.

## T4: Preconditions and `check`
- Description: `preconditions()` covers every FR11 rule, and the `check` CLI prints one
  `ready`/`missing`/`problem` line per item and exits 0 only when `write` would succeed. The rules:
  - write-once;
  - `draft = false`;
  - `require_test_audit`;
  - the manifest agreement;
  - `split_audit scan`, reported as counts and paths only (FR15);
  - the `auto-v2` freeze;
  - pinned recipes;
  - git available and clean, ignoring `results/` and `outputs/`, failing closed;
  - `--on` not in the future;
  - `--on` strictly after every `pre_freeze` `inspected_on`.
- Files likely touched: `src/data/freeze.py`, `tests/test_freeze_check.py` (new)
- Depends on: T3
- Security-sensitive: yes. Test-ID leakage through relayed messages, and a fail-open git check.
- Acceptance criteria:
  - Each precondition failure has its own reason code and a fixture test. That includes `--on`
    equal to the latest `inspected_on`, git not on PATH, and a dirty tracked file outside the
    ignore list.
  - With an unregistered test dialogue in a fixture sheet, `check` fails, and the ID is absent from
    stdout, stderr and the captured logs.
  - `check` exits 0 on a ready fixture and is read-only: no file is created or modified.
- Status: done (2026-10-22).
  - 21 tests in `tests/test_freeze_check.py`. 2 of them use real git and skip when git isn't on
    PATH.
  - Full suite without git: 814 tests ran, OK (10 skipped). With git: 814 tests ran, OK.
  - `provenance.git_state` gained a `cwd` parameter (additive).
  - Real-repo `check` ran in 1.9 s and exits 1 with 8 items:
    - `tree_dirty`;
    - 3 × `revision_unpinned`;
    - `llm_model_floating`;
    - `analysis_draft`;
    - 2 × `recipe_missing`.

    The test audit and the sheet scan pass.
  - Manual security pass:
    - IDs: counts and paths only, plus `mask_ids` on every printed line;
    - git fails closed;
    - subprocess with list arguments, so no shell.

## T5: Record, `write`, `verify`, `require_freeze`
- Description: Build the record:
  - top-level `freeze_date` and `analysis_config_sha256`;
  - `pins` and `original_pins`;
  - `amendments: []`;
  - the informational fields;
  - `content_sha256`.

  Serialize it deterministically: sorted keys, LF, a trailing newline, at most 64 KiB, written
  atomically.
  - `write --on`, which runs every precondition first.
  - `verify` and the library `require_freeze(path, run=None)`. They check integrity (content hash,
    the overlay of `original_pins` by the amendments equals `pins`, the amendment chain, the
    top-level hash equals the `analysis.config` pin), then recompute, then do the optional
    `RunIdentity` grid check (FR17).
- Files likely touched: `src/data/freeze.py`, `tests/test_freeze_record.py` (new)
- Depends on: T4
- Security-sensitive: yes. It persists the record and parses an untrusted `freeze.json`.
- Acceptance criteria:
  - Two writes of the same fixture with the same `--on` are byte-identical. A refused write leaves
    no file. A second write refuses.
  - The written record is accepted by `src.analysis.freeze.require_frozen_config` /
    `freeze_date` and by `split_audit.resolve_freeze_date` (AC-008-02).
  - `verify` fails, naming the key, after each AC-008-05 change. It passes after a `post_scoring`
    registry row, CRLF code, or a comment-only config change.
  - The `RunIdentity` check refuses an unpinned recipe hash, a seed outside the system's seeds, and
    a condition outside `conditions_for`, and passes a matching run.
  - An oversized, non-object, or malformed-hash record raises `FreezeError`; it doesn't crash.
- Status: done (2026-10-22).
  - 33 tests in `tests/test_freeze_record.py`.
  - The full suite: 847 tests ran, OK (10 skipped; git not on PATH).
  - Record keys: `schema_version` `freeze-record-v1`, `freeze_date`, `original_pins`, `pins`,
    `amendments`, `analysis_config_sha256`, `written_at_commit`, `inputs_path` and
    `content_sha256`.
  - `verify` reads `inputs_path` from the verified record itself and re-validates it as a repo
    path.
  - Manual security pass: bounded read, exact key set, hex/date checks, atomic write, and the
    write-once check.

## T6: `amend` and `show`
- Description: `amend --on --reason` appends a chained amendment (date, reason, changed keys with
  old and new values, previous `content_sha256`), then updates `pins`, the top-level analysis hash
  and `content_sha256`. It has every FR13 refusal, including `frozen_set_immutable` for `membership.*`
  and `data.*`. `show` prints the freeze date, the effective pins and the amendment list.
- Files likely touched: `src/data/freeze.py`, `tests/test_freeze_amend.py` (new)
- Depends on: T5
- Security-sensitive: yes. It writes free text into a committed file (the reason) and must refuse
  ID patterns and non-ASCII text.
- Acceptance criteria:
  - After `amend`, `verify` passes on the new state and fails on the old state. Two amendments
    chain correctly, and tampering with an earlier amendment breaks `verify`.
  - Each refusal has a test:
    - no record;
    - nothing changed;
    - a `membership.*` change;
    - a `data.*` change;
    - an empty, overlong, non-ASCII or ID-bearing reason;
    - `--on` before the freeze, before the last amendment, or in the future;
    - a failing write precondition (for example a dirty tree);
    - the size cap.
  - `freeze_date` never changes. `show` output has no IDs.
- Status: done (2026-10-22).
  - 17 tests in `tests/test_freeze_amend.py`.
  - The full suite: 864 tests ran, OK (10 skipped; git not on PATH).
  - `uv.lock` moved from `data.uv_lock` to `env.uv_lock`, so that a dependency fix is amendable;
    spec FR3 was updated.
  - Each amendment also records its `commit`.
  - `verify` checks each amendment's fields and date order, as well as the chain.
  - Manual security pass: reasons are limited to printable ASCII, at most 500 characters, and are
    refused if they match a dialogue/item ID (case-insensitive). A refused amendment leaves the
    file byte-identical.

## T7: Gates in the Stage 1 runner, Stage 2 and transfer
- Description:
  - **`runner.load`**, when `eval_split` is test: refuse `--smoke`; call
    `require_freeze(run=RunIdentity(name, recipe_sha256, seed, train_condition))`. Then record the
    freeze `content_sha256` in the run block of `metrics.json` and in the results line.
  - **`stage2.py` and `transfer.py`**, with `--split test`: call `require_freeze()`.
  - **Dev paths** are unchanged.
- Files likely touched: `src/stage1/runner.py`, `src/evaluation/stage2.py`,
  `src/evaluation/transfer.py`, their tests, and a shared fixture-freeze helper in `tests/`
- Depends on: T5
- Security-sensitive: no. It enforces an existing boundary and adds no new input surface.
- Acceptance criteria:
  - Each gate refuses with no record and with a failing record. The runner also refuses an
    unpinned recipe, a seed off the grid, a condition off the grid, and `--smoke` on test.
  - Each gate proceeds on a verifying fixture freeze.
  - Dev runs behave identically with and without `freeze.json`. The existing stage1, stage2 and
    transfer tests pass.
- Status: done (2026-10-22).
  - 15 tests in `tests/test_freeze_gates.py`.
  - The full suite: 879 tests ran, OK (10 skipped).
  - The gate is in `runner.load`, which covers the tfidf and encoder trainers. The freeze hash goes
    into `metrics.json` `run` and the results line.
  - Stage 2 and transfer gate both `inputs` and `score` on test, and stamp
    `freeze_content_sha256` into their score reports.
  - Two existing tests now stub the gate: `test_test_audit` Stage 2 scoring and
    `test_freeze_recipe` eval-split.
  - Seen, not fixed (out of scope): `transfer.main` doesn't catch `ManifestError` from a malformed
    `sources.toml`.

## T8: Gate in the test analysis
- Description: `src.analysis run --split test` calls `require_freeze()`. Every Stage 1 run directory
  in the test inputs must pass the `RunIdentity` check: the recipe hash from `config.resolved.json`,
  the train condition, and the seed from `metrics.json`. The report records the freeze
  `content_sha256`. The existing `require_frozen_config` stays.
- Files likely touched: `src/analysis/__main__.py`, possibly `src/analysis/inputs.py`,
  `tests/test_analysis_cli.py`, `tests/test_analysis_report.py`
- Depends on: T5
- Security-sensitive: no
- Acceptance criteria:
  - The test analysis refuses with no record, with a failing record, and with a run directory whose
    recipe, seed or condition is off the grid.
  - It proceeds on a verifying fixture. The report carries `freeze_content_sha256`.
  - The dev analysis is unchanged, and the existing analysis tests pass (fixtures updated to write a
    real freeze where they used a two-field stub).
- Status: done (2026-10-22).
  - `test_freeze_gates.py` now holds 20 tests, 5 of them on the analysis gate with a real
    freeze: `gate_test` and `check_frozen_runs`.
  - The full suite: 885 tests ran, OK (10 skipped).
  - Gate order:
    1. `--allow-test`;
    2. `draft`;
    3. the audit;
    4. spec 007's config-hash check;
    5. `require_freeze`;
    6. the grid check, after `load_inputs`. It reads only each run's verified
       `config.resolved.json`.
  - Deviation: the 3 existing test-analysis tests (cli, report, error audit) stub
    `require_freeze` and `check_frozen_runs`. They were not rebuilt on a real freeze. Those tests
    are about spec 007 behavior; the gates are covered with a real freeze in
    `test_freeze_gates`.
  - The error-audit sampler still reads only `freeze_date` (spec 007 FR23), unchanged.

## T9: Docs, real-repo smoke checks, verification
- Description:
  - `docs/freeze.md`, covering:
    - the procedure: `check` → settle open items → transcript rescan at least one day before →
      commit → `write` → commit `freeze.json` → `verify` on the lab machine → grid;
    - amendments and their disclosure, with no corpus quotes in reasons.
  - The roadmap WP-08 row, and the `docs/stage1_baselines.md` test-run command with
    `--eval-split test --allow-test`.
  - The real-repo `check`, on native Windows and in WSL (counts and codes only, timed).
  - `verification.md`, mapping AC-008-01…10.
  - The full suite on Windows (with and without git on PATH) and in WSL.
- Files likely touched: `docs/freeze.md` (new), `docs/stage1_baselines.md`,
  `specs/001-pragmatic-intent-study/roadmap.md`, `specs/008-freeze-record/verification.md` (new)
- Depends on: T6, T7, T8
- Security-sensitive: no
- Acceptance criteria:
  - The real `check` finishes in under 30 s on both platforms and prints no IDs. Its open items are
    listed in `verification.md`. At the time of writing, these are expected to include `draft`, the
    `main` revisions and the placeholder LLM/hybrid recipes.
  - The full suite passes on Windows, with and without git on PATH, and in WSL.
  - Every AC-008-NN has evidence in `verification.md`.
- Status: done (2026-10-22).
  - The full suite, 888 tests:
    - Windows without git: OK (10 skipped);
    - Windows with git: OK;
    - WSL: OK (5 skipped).
  - Real `check`: 1.9 s on Windows and 3.4 s on WSL, with the same 8 items and the same pin digest.
  - Gaps found and closed here (R3 had missed them): `src.evaluation.stage1 --split test` and
    `src.evaluation.run --split test` are now gated (+4 tests).
  - Written: `docs/freeze.md`, `docs/stage1_baselines.md`, the roadmap and `verification.md`.
