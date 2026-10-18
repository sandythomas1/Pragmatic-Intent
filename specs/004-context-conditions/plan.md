# Plan: Context conditions, invariants and the common-set manifest

> **Phase:** Plan · **Status:** validated · **Date:** 2026-10-14
> The *how*. Derived from [`spec.md`](spec.md) (clarified 2026-10-14). Must not contradict the spec.

## Summary

Move context rendering out of Stage 1 into one stdlib module, `src/data/contexts.py`, that every
model uses. It wraps the existing `build_context` (same conditions, same donor pairing) and adds the
D-06 budget: context plus target is at most 350 whitespace tokens, with the oldest whole turns dropped
first. The same module adds two commands. `check` verifies the §8 invariants on a whole split, and
`manifest` writes a text-free, hashed, per-example list of what each condition shows. Stage 1 replaces
its single "comparable" set with two sets. The **genuine** set (every example at `turn_index > 0`) is
used for none/one/full. The **mismatch** set (the genuine set minus examples with no donor) is used
for the two mismatch conditions. Each mismatch contrast gets a sensitivity line without donors that
mention a target value. Nothing in `items.jsonl`, `dialogues.jsonl` or the donor pairing changes.

## Architecture

```
data/interim/direct/{items,dialogues}.jsonl          (unchanged, git-ignored)
            │
            ▼
src/data/direct_dataset.py   build_context()          (unchanged: none/one/full/mismatched/_one)
            │
            ▼
src/data/contexts.py  NEW    render()  ── budget, dropped-turn count, input hash
                             cue_flags() ── donor / dropped-turn value overlap (reuses audit_fact_drift)
                             genuine() / in_mismatch_set()
src/data/context_manifest.py NEW  CLI: check | manifest [--verify]
                             (separate module: it needs src.stage1.data, which imports contexts)
            │                         │
            │                         └──► data/manifests/contexts_test.csv           (committed)
            │                              data/manifests/contexts_{dev,test}_summary.json (committed)
            │                              data/manifests/contexts_dev.csv            (git-ignored)
            ▼
src/stage1/data.py           model_inputs() → contexts.render()   (train + eval, budgeted)
src/stage1/runner.py         per-condition eval example lists; sets + flags into the scorer
src/stage1/{tfidf,encoder}.py  iterate the per-condition lists (one-line plumbing change each)
src/evaluation/stage1.py     per-set expected predictions, contrast set + n, sensitivity line
src/stage1/length_check.py NEW  tokenizer-only check of the 512-subword bound (Sandy, WSL)
```

**Responsibilities.** `contexts.py` owns what a model sees and the proof that it is valid.
`stage1/*` and the scorer only consume it. Sandy's future LLM, Stage 2 and hybrid code calls
`contexts.render` and gets the same text the encoder got (FR1).

### Rendering rules (FR1–FR6)

- `render(item, target, dialogues, condition, budget=BUDGET_WORDS) -> Rendered | None`, where
  `Rendered` is a frozen dataclass: `turns: tuple[Turn, ...]`, `context: str`, `target: str`,
  `dropped: int`. It returns `None` exactly when `build_context` does (mismatch with no donor).
- The serialization is the current `render_context`: oldest first, `"User: …"` / `"System: …"`,
  joined by `\n`. It moves into `contexts.py`; `stage1.data` imports it from there.
- **Budget:** `words(context) + words(target) ≤ 350`, where `words` is `len(text.split())` and
  speaker tags count. Only `full` and `mismatched` are budgeted (spec FR4), and each window is
  budgeted on its own. Whole turns are dropped from the front until the input fits. If the target
  alone exceeds the budget, the context is empty and `dropped` equals the window length.
  `one`/`mismatched_one` are never budgeted; `check` reports their maximum length.
- `RENDERER_VERSION = "render-v1"` names the format and the budget. `BUDGET_WORDS = 350` is a
  module constant, not a run-config key, so no model can drift from it (spec: "same for every
  model"). Changing either means a new version.
- Input hash: `sha256(json.dumps({"context": c, "target": t}, ensure_ascii=False,
  sort_keys=True, separators=(",", ":")).encode("utf-8"))`. A test pins one known value
  (AC-004-7). The target hash is `sha256(target.encode("utf-8"))`.

### Common sets (FR7, FR8)

- `genuine(item)`: `turn_index > 0`. `in_mismatch_set(item)`: genuine and `item["mismatch"]` is set.
- `build_examples(..., require_comparable=True)` becomes `require_context=True`, excluding only
  `turn_index == 0` (reason `no_prior_context`). `comparable()` is deleted. Training keeps its
  existing `contexts_defined` filter, so every training condition still fits the same examples.
- Runner: `Prepared.eval_sets: dict[condition, list[Stage1Example]]`, where none/one/full get the
  genuine examples and the mismatch conditions get the mismatch subset. `eval_inputs` stays aligned
  with them. The trainers change `prepared.eval` to `prepared.eval_sets[condition]` in their predict
  loops.

### Cue flags (FR9)

- **Target values:** the target turn's user-act `(slot, value)` pairs mapped to the fact-drift slot
  types (`Day→day`, `Time→time`, `Price→price`, `Area→area`, `Food→food`, `Dest/Depart/Name→place`).
  Values are lower-cased and whitespace-collapsed, and `dontcare`/`none`/empty are skipped.
- **Donor cue, one flag per mismatch condition:** `donor_cue` is set when any mention that
  `audit_fact_drift.extract_mentions` finds in the rendered (budgeted) `mismatched` context matches
  a target value of the same type (`_values_match`, nested for food/place). `donor_cue_one` is the
  same test on the single `mismatched_one` turn, so a cue the model never saw doesn't drop an
  example from that condition's comparison. The vocabulary is built from all items, as in
  `auto_levels`.
- **Dropped cue:** the same test against the turns the budget removed from `full`.
- These flags are only disclosed. The scorer uses `donor_cue` for comparisons involving
  `mismatched` and `donor_cue_one` for comparisons involving `mismatched_one`, for the sensitivity
  line only.

### Checks (FR10)

`python -m src.data.context_manifest check --split {dev,test}` runs over every genuine example and counts
failures per rule. It exits 1 if any rule fails, naming the first example per rule:

| Rule | Verifies |
|---|---|
| `target_identical` | the target is the same string under all five conditions |
| `no_future` | the rendered turns equal a contiguous suffix of `dialogue[:t]` (genuine) or `donor[:t]` (mismatch), sliced directly from `dialogues.jsonl` without calling `build_context`/`render`, so the check is independent of the code it checks; a sentinel test covers the original target, later turns, the other variant and act values |
| `budget` | `full`/`mismatched` respect FR4, the target is untouched, drops are a prefix |
| `donor_split` | the donor's split equals the item's split |
| `donor_distinct` | the donor dialogue differs from the target dialogue |
| `donor_window` | `start == 0`, `length == turn_index`, and the last donor turn is a system turn |
| `donor_domains` | the donor window's per-turn act domains share none with the item's `active_domains` |

`donor_domains` is weaker than the builder's rule, because `dialogues.jsonl` stores act domains
but not belief-state domains. It is a necessary condition: any hit is a real violation. Re-checking
belief states would need raw MultiWOZ, which is out of scope (see Risks).

### Manifest (FR11, FR12, FR14)

`python -m src.data.context_manifest manifest --split test [--verify]` writes or verifies:

- `contexts_<split>.csv`, one row per genuine example, sorted by `example_id`. Columns:
  `example_id, item_id, dialogue_id, turn_index, variant, mismatch_set (0/1), exclusion
  (""|no_donor), donor_dialogue_id, full_dropped, mismatched_dropped, donor_cue, donor_cue_one,
  dropped_cue, target_sha256, sha256_none, sha256_one, sha256_full, sha256_mismatched,
  sha256_mismatched_one`. Undefined conditions have an empty hash. There is no text.
- `target_sha256` is computed from each defined condition's `Rendered.target`. The build fails,
  naming the example, if they differ, so the single column is backed by a check (AC-004-1).
- `contexts_<split>_summary.json`: `renderer_version`, `budget_words`, `policy`,
  `items_sha256`, `dialogues_sha256`, `manifest_sha256` (CSV bytes), `built_at` (injectable),
  counts per set, exclusions by reason (including `build_examples` exclusions), dropped-turn counts
  per condition, `target_over_budget` (examples whose target alone exceeds the budget, so their
  `full`/`mismatched` context is empty), cue-flag counts per flag, and per-condition length stats
  in words (mean, median, p95, max, n over budget).
- `--verify` rebuilds in memory and fails if the bytes differ from the committed CSV (AC-004-14).
- **Cross-machine bytes:** both files are written as UTF-8 without BOM with `newline="\n"`, so
  Windows, WSL and macOS write the same bytes. A new `.gitattributes` line,
  `data/manifests/*.csv -text`, stops git from converting line endings on checkout, so `--verify`
  passes on every machine.
- Default `--out-dir data/manifests/`. `.gitignore` gains `data/manifests/contexts_dev.csv`.

### Scorer (FR13, AC-004-9, AC-004-13)

- `build_report(examples, predictions, slices=None, sets=None, ...)`. `sets` is a
  `ScoringSets(mismatch_ids: frozenset[str], cue_donor_ids: dict[condition, frozenset[str]])`,
  keyed by `mismatched` and `mismatched_one`. `None` means every example is in both sets and none
  is flagged (keeps the existing tests and callers simple).
- Expected predictions per condition: genuine examples for none/one/full, the mismatch subset for
  mismatch conditions. Missing, extra or duplicate rows are still errors.
- Each condition's metrics are computed on its own set, with `n` and `set` recorded. Each contrast
  records `set` and `n`. Contrasts touching a mismatch condition use the mismatch set on both sides
  and add `without_cue_donors: {n, difference, ci95}`, dropping the examples flagged for that
  comparison's mismatch condition.
- The report gains `sets: {genuine, mismatch, excluded_from_mismatch: {no_donor}, cue_donors:
  {mismatched, mismatched_one}}`
  and `renderer_version`. `results/stage1.jsonl` carries the same.
- The scorer CLI gains `--dialogues`, since cue flags need the donor text.

### Encoder length check (FR4's pre-freeze check)

`src/stage1/length_check.py` loads only the tokenizer named in an encoder config. It tokenizes
every budgeted train and eval input exactly as `encoder.encode` does and reports the maximum subword
length and the count of inputs at or over `max_length`, per condition. It runs on CPU in a few
minutes. Sandy runs it in WSL, because it needs the `gpu` dependency group and a Hugging Face
download. It and the `encoder.py` change sit in model-side files, so Sandy reviews them. A count above zero means the budget is lowered under a new renderer version. The encoder
itself also records `eval_inputs_at_max_length` per condition, next to the existing train count.

## Stack & Dependencies

- **Language:** Python 3.12, **standard library only** for `contexts.py` and the scorer
  (project constitution). This deviates from the global default (FastAPI etc.) because this is a
  local batch research pipeline with no service, as the project already documents.
- **Data store:** none. JSONL inputs, CSV/JSON outputs, as in specs 002/003.
- **New dependencies:** none. `length_check.py` uses `transformers`, which the pinned `gpu`
  group already contains.

## Deployment Target

- **Cloud/platform:** none (local CLI and library).
- **Compute:** a laptop CPU for `check`/`manifest`; WSL2 for `length_check` (Sandy).
- **IaC/CI:** none. Tests run with `python -m unittest discover -s tests -t .` (native Windows +
  WSL).
- **Guidance skill:** n/a.

## Data Model

- **Inputs (read-only):** `items.jsonl` (`item_id, dialogue_id, turn_index, split, *_utterance,
  user_acts, active_domains, mismatch{donor_dialogue_id,start,length}, mismatch_status`),
  `dialogues.jsonl` (`dialogue_id, turns[{speaker,text,domains}]`).
- **Derived per example:** `Rendered` per condition, set membership, cue flags.
- **Outputs:** the manifest CSV and summary above. The key is `example_id`
  (`<item_id>:<variant>`), unique, which the manifest checks.

## API Contract

- **Library:** `contexts.render`, `contexts.render_context`, `contexts.input_sha256`,
  `contexts.genuine`, `contexts.in_mismatch_set`, `contexts.cue_flags`,
  `RENDERER_VERSION`, `BUDGET_WORDS`.
- **CLI:** `python -m src.data.context_manifest {check,manifest} --split {dev,test} [--items]
  [--dialogues] [--out-dir] [--verify]`. Exit 0 on success, 1 on a failed rule or invalid input,
  with logged counts. Re-running is idempotent.
- **Breaking changes:** `build_examples(require_comparable=…)` becomes `require_context`;
  `src.stage1.data.render_context` is re-exported from `contexts`; `Prepared.eval_sets` is new.
  `results/stage1.jsonl` doesn't exist yet, so no logged result changes meaning.

## Security & Privacy

- Committed files hold IDs, flags, counts and SHA-256 only. A test asserts that no fixture
  utterance, turn or slot value appears in them (AC-004-8). DIRECT/MultiWOZ text stays in
  git-ignored `data/interim/`.
- Inputs are validated at the boundary: unknown condition, split or variant, a missing donor
  dialogue, a duplicate `example_id`, or a mismatch with `length != turn_index` is rejected with
  the example named. No input is coerced.
- Corpus text is never executed or interpreted. There are no secrets, network calls or PII
  (annotators don't appear here).

## Observability

- Logged counts for each command: examples, genuine, mismatch, excluded by reason, dropped per
  condition, cue flags, failures per rule. Errors name the example and the rule.
- Provenance in every artifact: renderer version, budget, policy, input hashes, manifest hash.
  Stage 1 metrics carry `renderer_version` and the set sizes.

## Testing Strategy

All tests are stdlib `unittest` with invented fixtures (`tests/test_contexts.py`, plus additions
to `tests/test_stage1.py`).

| AC | Proof |
|---|---|
| 004-1 | Fixture item: one target string across all conditions; a forced mismatch between two conditions' targets makes the manifest build fail |
| 004-2 | Sentinels in the original target, a later turn, the other variant and an act value never appear in any context |
| 004-3 | No-donor item: in genuine set and none/one/full scores, absent from both sides of mismatch contrasts, reason `no_donor` |
| 004-4 | Budget fixtures (small budget passed in): fits; oldest whole turns dropped; target over budget → empty context; under budget → byte-identical to the pre-change `model_inputs` output (golden fixture) |
| 004-5 | One corrupted fixture per donor rule → `check` exits 1 naming that rule |
| 004-6 | Donor window mentioning the target's `Day` value → `donor_cue`; the same value only in an earlier donor turn → `donor_cue` but not `donor_cue_one`; no mention → neither |
| 004-7 | Manifest built twice → identical bytes, with no `\r` and no BOM; one-character change in a context turn → that row's hash and `manifest_sha256` change; pinned hash value |
| 004-8 | Committed-output scan for fixture text |
| 004-9, 004-13 | Scorer report: `full-mismatched` has `set: mismatch`, `n` = mismatch size, and `without_cue_donors` |
| 004-10 | Smoke (reported, not CI): `check` passes on real dev and test; 44 test items / 72 examples without a donor |
| 004-11 | D-06 entry in `specs/memory/decisions.md` and the roadmap (doc task) |
| 004-12 | Full suite on native Windows Python 3.12 |
| 004-14 | `manifest --split test --verify` passes after a fresh build |

The runner test is updated so that a no-donor eval item appears under none/one/full only.

## Risks & Trade-offs

- **Risk:** the 350-word budget still overflows 512 subwords for some encoder (long numbers and
  postcodes tokenize badly). → **Mitigation:** `length_check.py` before the freeze; if needed,
  lower the budget under `render-v2` for all models. Never patch per model.
- **Risk:** budgeting changes Stage 1 training inputs. → **Mitigation:** no Stage 1 result is
  logged yet; `renderer_version` goes into every metrics file, so pre- and post-change runs can't
  be mixed silently.
- **Risk:** `donor_domains` can't see belief-state domains. → **Mitigation:** the builder already
  enforces the stricter rule; the check catches any act-level violation; the gap is documented in
  the summary (`donor_domain_check: "acts_only"`).
- **Risk:** cue flags miss paraphrased values ("the 5 pm one") or over-flag common values
  ("centre"). → **Mitigation:** they are a disclosed proxy that drives only a sensitivity line,
  never an exclusion. The fact-drift extractor is precision-first.
- **Risk:** line-ending or encoding differences make `--verify` fail on Windows. → **Mitigation:**
  explicit `newline="\n"` UTF-8 writes, `.gitattributes` `-text` for the manifests, a no-`\r` test.
- **Risk:** the test manifest adds about 5–6 MB to git. → **Mitigation:** accepted in `/clarify`;
  dev is git-ignored and regenerated.
- **Trade-off:** a module constant over a config key for the budget. Gains: one budget for every
  model by construction. Gives up: per-run experimentation with windows, which needs a version bump
  instead. Worth it because D-06 is a frozen study design choice, not a hyperparameter.
- **Trade-off:** reusing `build_context` unchanged and layering the budget on top. Gains: zero
  change to the stored data and pairing, and the smallest diff. Gives up: a budgeted `mismatched`
  window is no longer exactly turn-length-matched to the budgeted `full`. Both are budgeted the same
  way, and length stats per condition are reported (FR14).
- **Trade-off:** a word budget over subword tokens. Gains: model-agnostic and stdlib. Gives up:
  an exact encoder guarantee, which `length_check.py` covers instead.

## Skills Consulted

- `~/development/skills/ml_engineering.md`: leakage (no future information), reproducibility
  (versioned renderer, hashed inputs), the same feature logic for train and eval.
- `~/development/skills/testing.md`: deterministic tests, edge cases and failure modes, behaviour-level
  assertions, invented fixtures.
- Not used: system_design, gcp/aws_architecture, security (no service, no auth, no PII; the
  project constitution's data-handling bar applies instead).
