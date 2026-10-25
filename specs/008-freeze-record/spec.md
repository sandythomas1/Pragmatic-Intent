# Spec 008: Freeze record

> **Phase:** Implemented · **Status:** T1–T9 done 2026-10-22 ([verification](verification.md)); revised after [review](review.md) (R1–R14) · **Owner:** Sandy (freeze decisions, runs), Claude (tooling) · **Date:** 2026-10-22
> The *what* and *why*. Implementation detail belongs in `plan.md`.

Parent: [spec 001](../001-pragmatic-intent-study/spec.md) WP-08, FR-06, §7 "Splits and freezes",
D-04–D-07; [constitution](../constitution.md) "Freeze before reporting". It consumes the hashes that
[spec 004](../004-context-conditions/spec.md) (context manifest), [spec 005](../005-scoring/spec.md)
(rules, scorers), [spec 006](../006-split-audit/spec.md) (split audit, registry) and
[spec 007](../007-analysis-error-audit/spec.md) (`analysis_config_sha256`, `freeze_date`, panel
designs) already produce.

Decided with Sandy on 2026-10-22:
- **One freeze**, written once, just before the Nov 9 test grid. It happens after the dev encoder
  grid and the choice of primary system, not as a separate data freeze around Nov 1. Until then a
  read-only `check` reports what is ready.
- **Dated amendments.** The original pins never change. `amend` appends a dated, reasoned entry,
  and the gates enforce the latest pins.
- **Gates.** Stage 1 test runs, Stage 2 and transfer test scoring, and the test analysis all refuse
  to run unless the freeze verifies.

## Problem

Spec 001 says every reported test number needs a freeze record that fixes "IDs, source/text hashes,
label version, splits, exclusions, renderer/donor mapping and analysis choices", plus the models and
prompts (WP-08: "freeze record, hashes, final comparison list"). No such record exists.

- **Pieces exist, but nothing binds them.** Most pieces are already hashed: the test manifest
  (spec 004), the split audit and registry (spec 006), the `auto-v2` rule freeze (spec 005) and the
  analysis config (spec 007). Each is checked only by the tool that uses it. Nothing records that
  these particular versions, together, are the study.
- **Readers are waiting.** Spec 007 reads `data/manifests/freeze.json` for `freeze_date` and
  `analysis_config_sha256`. Spec 006 reads `freeze_date` for its registry phases. Nothing writes
  the file, so test analysis and the error audit cannot run.
- **Model recipes are not pinned.** Three of the four encoder configs use `revision = "main"`.
  Only `deberta-v3-base` is pinned to a commit. If a model or prompt changes between the dev choice
  and the test grid, the reported number would come from a recipe nobody selected on dev.
- **`--allow-test` is just a flag.** Any Stage 1 or Stage 2 test run with the flag runs. That
  includes runs whose code, config or data changed after the plan was fixed. Also, `eval_split`
  can only be set in the config file, so a test run needs an edited copy of the chosen recipe.

## Goals

- `freeze.json` is written once by one command. It pins every input that determines a reported test
  number: data, test membership, rules, renderer, scoring and analysis code, the analysis plan, model
  recipes, prompts, per-system seeds and the environment lock.
- The writer refuses to freeze anything that isn't ready. Examples: a draft analysis config, an
  unpinned model revision, a stale split audit, a dirty tree, or a panel system with no recipe.
- One `verify` recomputes every pin. Every test-time entry point calls it and fails closed.
- Any post-freeze change is a dated, reasoned, hash-chained amendment that the paper can disclose
  as a list. Amendments can never move the frozen test set.
- A read-only `check`, usable from today, says which pins are ready and which are missing. This
  turns the Nov 9 deadline into a visible checklist.

## Non-Goals

- **Making the choices.** The panel, the primary system, the prompts and the D-05 budget belong to
  Sandy. The record captures them; it doesn't choose them. The spec 007 fallback question (the
  primary system if no LLM/hybrid is ready) stays open there.
- **Re-implementing existing checks.** `require_test_audit`, the context manifest check, the
  `auto-v2` freeze and the IndirectRequests adapter's own source-hash check keep their logic. The
  freeze calls them or relies on them, and records their hashes.
- **Hashing model weights or predictions.** Pinning revisions, recipes, seeds and the lock fixes
  what gets trained. Prediction provenance is already in each run's result line.
- **Enforcing Stage 2 or transfer provenance.** Those prediction files carry no run identity
  (spec 007 `inputs.py`), so it can only be declared. The paper says so.
- **Changing the frozen test set after the freeze.** A genuine data change after the freeze would
  be a new freeze version (a future spec), disclosed. `amend` cannot do it.
- **The transcript rescan** of Claude session logs. It stays a manual step, done at least one day
  before the freeze (spec 006; FR10). The writer runs only the mechanical `split_audit scan` of
  sheets.
- **Signing, timestamps from a third party, or anything networked.** Git history is the external
  witness.
- **The literary add-on.** It is not collected.

## User Stories

- As **Sandy before the Nov 9 grid**, I want one command to tell me what is still missing before I
  can freeze, and one to freeze, so the freeze is a 10-minute step and not a hunt.
- As **Sandy on the lab 5090**, I want a test run to fail in seconds if anything differs from the
  freeze, before I spend GPU hours on a run I couldn't report.
- As **the course professor or a reader**, I want one committed file that lists exactly which data,
  code, plan and recipes produced the numbers, and every change made after the freeze, with a date
  and a reason.
- As **spec 006 and spec 007**, we want `freeze_date` and `analysis_config_sha256` at the top level,
  where we already read them.

## Functional Requirements

**Freeze inputs**

1. What to pin MUST be declared in one versioned TOML file (`configs/freeze/freeze-v1.toml`). It
   lists:
   - the analysis config path;
   - the code to pin, as repo-relative globs (for example `src/analysis/*.py`). A glob that matches
     no file is an error;
   - per panel system:
     - its recipe files (a Stage 1 TOML, prompt files, an LLM config);
     - its seeds;
     - an optional `llm_model` snapshot ID.

   Unknown keys are errors. Every path stays inside the repo: no `..`, no absolute paths, and no
   symlinks.
2. The panel systems in the freeze inputs MUST equal the panel in the analysis config, with none
   missing and none extra. Each system's **training conditions** are not declared. They are derived
   from its `design` in the frozen analysis config, by spec 007's rule:
   - `matched`: `none`, `one`, `full`;
   - `test_time`: `full`;
   - an untrained LLM: `untrained`.

**Pins** (each pin is a stable dotted key with a SHA-256 or an exact version)

3. **Sources and data** (`data.*`): `data/sources.toml` (text-normalized), and `items.jsonl` and
   `dialogues.jsonl` (byte-exact, as spec 006 hashes them).
   **Environment** (`env.uv_lock`): `uv.lock`, text-normalized. It is a separate family so that
   a post-freeze dependency fix can be amended. `data.*` cannot be amended (FR13). This split was
   made while implementing T6, on 2026-10-22.
4. **Test membership** (`membership.*`):
   - from the split audit summary: `content_sha256`, `audit_sha256` and the primary-set counts;
   - the registry's `pre_freeze` hash;
   - from the context manifest: `manifest_sha256`, `renderer_version` and the budget.

   The manifest hash MUST equal the one the split audit recorded.
5. **Labels** (`labels.*`):
   - `rules_version` from the analysis config;
   - for `auto-v2`, the existing `auto-v2` freeze record, which MUST verify.

   The rule and category modules are pinned as code (FR6).
6. **Code** (`code.<path>`): a source hash for each file matched by the code globs, taken after
   CRLF→LF normalization, so a Windows and a WSL checkout of the same commit agree.
7. **Analysis** (`analysis.*`): `analysis_config_sha256` (spec 007's canonical hash) and the config
   version.
8. **Recipes** (`recipe.<system>.*`), per panel system:
   - **for each Stage 1 TOML, a recipe hash.** This is the canonical JSON of the parsed config,
     with the run-time fields removed: `data.eval_split`, `data.train_condition`,
     `encoder.micro_batch_size` and `encoder.gradient_checkpointing`. These are memory knobs that
     leave the effective batch, and so the result, unchanged. Comments don't move the hash;
   - **for every other recipe file** (prompts, an LLM config), its text hash after line-ending
     normalization;
   - **for encoders, `pretrained` and `revision`.** The revision MUST be a 40-hex commit, not
     `main` or a tag;
   - **for an LLM, `llm_model`.** It MUST NOT be a floating alias: an empty value, or one ending
     in `-latest`, is refused;
   - **the system's seeds.**
9. The record also carries **informational** fields, which are never verified: `written_at_commit`,
   `tool_version` and the freeze-inputs path.

**Commands** (`python -m src.data.freeze <command>`; stdlib only)

10. `check` is read-only. It evaluates every `write` precondition and prints one line per pin or
    precondition: `ready`, `missing` or `problem`, with a reason code. It exits 0 only if `write`
    would succeed.
11. `write --on YYYY-MM-DD` MUST refuse, with a distinct reason code each, unless every
    precondition passes:
    - no `freeze.json` exists (write-once);
    - the analysis config loads and `draft = false`;
    - `require_test_audit` passes against the current items, dialogues and registry;
    - the context manifest and its summary agree with each other and with the split audit;
    - `split_audit scan` (sheets) passes;
    - the `auto-v2` freeze verifies, if `auto-v2` is the rules version;
    - every recipe is pinned (FR8) and the panel matches (FR2);
    - git is available and the tree is clean, ignoring only `results/` and `outputs/`. Missing git
      or an unknown state is a refusal (`git_unavailable`), never treated as clean;
    - `--on` is not after the local date;
    - `--on` is **strictly after** the latest `inspected_on` of every `pre_freeze` registry row
      (so a re-derived row keeps its phase; review R1);
    - the record is under 64 KiB.

    It writes `data/manifests/freeze.json` with:
    - top-level `freeze_date` and `analysis_config_sha256`;
    - `pins` (the effective state);
    - `original_pins`;
    - an empty `amendments` list;
    - the informational fields;
    - a `content_sha256` over the record without that field.

    A refused write leaves no file.
12. `verify` recomputes every pin and compares it with `pins`. It also checks:
    - `content_sha256`;
    - that `original_pins` overlaid by the amendments, in order, equals `pins`;
    - the amendment hash chain;
    - that the top-level `analysis_config_sha256` equals `pins["analysis.config"]`.

    It exits non-zero and names each mismatched pin key, never a value from test data. Its library
    form, `require_freeze()`, raises `FreezeError(code, keys)`.
13. `amend --on YYYY-MM-DD --reason "<text>"` recomputes the pins and appends one amendment holding:
    - the date;
    - the reason;
    - the changed keys, with old and new values;
    - the previous `content_sha256`.

    It then updates `pins`, the top-level `analysis_config_sha256` and `content_sha256`.
    `freeze_date` never changes. It MUST refuse when:
    - no record exists, or the existing record fails its own integrity check;
    - nothing changed;
    - any changed key is under `membership.*` or `data.*` (`frozen_set_immutable`; review R6);
    - the reason is empty, longer than 500 characters, not printable ASCII, or matches the DIRECT
      dialogue/item ID pattern;
    - `--on` is before `freeze_date`, before the last amendment's date, or after the local date;
    - any `write` precondition other than "no record exists" fails (so `draft = false`, a clean
      tree, pinned recipes and so on still hold);
    - the record would exceed 64 KiB.
14. `show` prints the freeze date, the effective pins and the amendment list (dates, reasons,
    changed keys) for the paper's disclosure section.
15. **No test IDs in output.** No command prints a dialogue or item ID, or any corpus text. A
    failing sheet scan is reported as `scan: <n> unregistered test dialogue(s) in <k> file(s)`, with
    the file paths, and points to `python -m src.data.split_audit scan` (review R7).

**Gates**

16. These MUST call `require_freeze()` and refuse to run if it fails:
    - the Stage 1 runner, when `eval_split` is `test`. The check sits in `runner.load`, which
      knows the seed, before any data is prepared or a model is trained. It covers
      `src.stage1.tfidf`, `src.stage1.encoder` and any trainer built on the runner. `--smoke` on
      test is refused, because a smoke run on dev exercises the same code;
    - `src.evaluation.stage2` and `src.evaluation.transfer` with `--split test`;
    - the standalone Stage 1 re-scorer `src.evaluation.stage1 --split test`, and the legacy
      `src.evaluation.run --split test`. Review R3 had missed these; they were added during T9 on
      2026-10-22;
    - `src.analysis run --split test`. Spec 007's config-hash check stays, and it reads the
      verified top-level `analysis_config_sha256`.
17. **Grid membership:**
    - **Stage 1 runner, at run start:** a test run is refused unless its config's recipe hash is
      pinned for the system named by `[run] name`, its `--seed` is among that system's seeds, and
      its train condition is among the conditions derived for that system (FR2).
    - **Test analysis:** every Stage 1 run directory in the inputs must pass the same check, using
      its `config.resolved.json` (recipe hash, train condition) and `metrics.json` (seed).

    Stage 2 and transfer runs are verified for the freeze only (Non-Goals).
18. The Stage 1 runner gains `--eval-split {dev,test}`, which overrides `[data] eval_split`. One
    recipe file then serves dev and test (review R2). `--allow-test` is still required for test.
19. Dev paths MUST behave exactly as they do today, with or without `freeze.json`.

## Non-Functional Requirements

- **Security / integrity:**
  - Treat `freeze.json` and the freeze inputs as untrusted. Read them bounded (64 KiB), with strict
    schemas.
  - Hashes are lowercase 64-hex. Dates are ISO `YYYY-MM-DD`.
  - The record holds hashes, versions, counts, dates and amendment reasons only: no dialogue IDs and
    no corpus text.
  - It is tamper-evident (`content_sha256`, plus the amendment chain), not tamper-proof. Git history
    is the external witness.
- **Determinism:** the same repo state and `--on` give a byte-identical `freeze.json`, with sorted
  keys, LF line endings and a trailing newline. It is already `-text` under `.gitattributes`.
  `verify` gives the same answer on native Windows and in WSL for the same commit and data.
- **Performance:** computing every pin hashes about 70 MB of interim data plus the code. It must
  finish in under 30 s, so it is cheap enough to run on every test-time command.
- **Observability:** each command logs the number of pins checked and a summary line. Failures name
  the pin key and a reason code. Gates record the freeze `content_sha256` they checked in their
  own provenance (`metrics.json` run block, the analysis report).
- **Testing:** stdlib `unittest` with invented fixtures and temporary repos, no DIRECT text. Run
  both with and without git on PATH. The full suite passes on native Windows Python 3.12 and in
  WSL.

## Acceptance Criteria

- **AC-008-01** **`check` on fixtures.** On fixture repos, `check` reports each `write` precondition
  failure with its reason code, including:
  - `draft = true`;
  - a `revision = "main"` encoder;
  - a panel system without a recipe;
  - a floating LLM alias;
  - an unmatched code glob.

  It exits 0 only on a ready fixture. The real-repo `check` is a smoke check recorded in
  `verification.md`.
- **AC-008-02** **Compatibility with existing readers.** `write` on a ready fixture produces a
  record whose `freeze_date` and `analysis_config_sha256` are accepted, unchanged, by
  `src.analysis.freeze` and `split_audit.resolve_freeze_date`.
- **AC-008-03** **Write refusals.**
  - `write` refuses each failing FR11 precondition with a distinct code, including:
    - `--on` equal to the latest `pre_freeze` `inspected_on`;
    - git missing;
    - a dirty tracked file outside `results/` and `outputs/`.
  - A refused write leaves no file.
  - A second `write` refuses while a record exists.
- **AC-008-04** **The no-ID rule.** With an unregistered test dialogue in a fixture sheet, `check`
  fails, and that dialogue's ID appears in neither stdout, stderr nor the captured logs.
- **AC-008-05** **What `verify` detects.** `verify` passes on an untouched fixture. It fails, naming
  the right key, after a change to any of these:
  - items;
  - the registry `pre_freeze` rows;
  - the manifest;
  - a pinned code file;
  - the analysis config content;
  - a prompt file;
  - a semantic field of a Stage 1 recipe;
  - `uv.lock`;
  - `freeze.json` itself, any field;
  - a broken amendment chain.

  It does not fail after:
  - adding registry `post_scoring` rows;
  - CRLF line endings in pinned code;
  - a comment-only change to the analysis config or to a Stage 1 TOML.
- **AC-008-06** **Amendments.**
  - `amend` records a dated, reasoned, chained entry. Afterwards, `verify` passes on the new state
    and fails on the old one.
  - Each FR13 refusal has its own test, including `frozen_set_immutable` for a `membership.*` and
    a `data.*` change.
- **AC-008-07** **Gates.**
  - Each gate in FR16 refuses when there is no record and when the record fails.
  - The Stage 1 runner and the test analysis refuse each of these:
    - a recipe hash that isn't pinned;
    - a seed outside the system's seeds;
    - a train condition outside its derived conditions.
  - Each gate proceeds when everything matches.
  - Dev runs behave identically with and without the record (FR19).
  - `--eval-split test` without `--allow-test` is refused.
- **AC-008-08** **Determinism.** Two `write` runs on the same fixture and `--on` are
  byte-identical. `verify` agrees on CRLF and LF checkouts of the same code.
- **AC-008-09** **Real-repo timing.** On the real repo, on native Windows and in WSL, `check`, which
  computes every pin, finishes in under 30 s. This is recorded in `verification.md`.
- **AC-008-10** **Docs.** `docs/freeze.md` gives the procedure:
  1. `check`;
  2. settle the open items;
  3. do the transcript rescan at least one day before;
  4. commit;
  5. `write`;
  6. commit `freeze.json`;
  7. run `verify` on the lab machine;
  8. run the grid.

  It also covers amendments and their disclosure, with no corpus quotes in reasons. The roadmap
  WP-08 row points to it.

## Open Questions

- **The `auto-v2` decision** (spec 007 open question) must be settled before `write`. `check`
  reports the current `rules_version`, but cannot decide it.
- **LLM recipe shape.** This depends on Sandy's LLM code, which doesn't exist yet. Recipes are
  generic (files plus `llm_model`); revisit if that code needs more, such as a temperature
  outside the files.

Resolved in review (2026-10-22): trainer code is pinned as code (any post-freeze fix is an
amendment). The clean-tree check ignores `results/` and `outputs/` only.
