# Decision Log

Append-only log of significant technical and methodological decisions across specs. Each entry
records what was decided, why, the alternatives considered, and which spec or task it came from.

<!-- New entries go at the top, most recent first -->

## 2026-10-21: Estimands, run command, tables, figure and error audit (Spec 007 / T6–T13)
Decision:
- **Only prespecified tests carry a p-value**: the primary test and the Holm members. Every
  other statistic gets an interval only.
- **Statistics.** Base statistics are seed-averaged rates and paired differences. Every contrast
  of contrasts is flattened to a linear combination of bases, so all share the one bootstrap.
- **Holm member status.**
  - `not_run`: its system did not run.
  - `untestable`: the system ran but the statistic is empty, sparse or unstable.
  - Both keep p = 1.
- **H4's population** is the spec 005 oracle population (gold indirect). Its L0 cell is
  therefore the rule-L0 indirect rewrites; an empty cell is reported `empty`, never imputed.
- **Dev precision report** covers every run system (the primary design on its main endpoint,
  with a `stage1_correct` fallback). D-07 thus gets dev evidence before the LLM or hybrid exists.
- **Committed tables** are refused if a dialogue-ID pattern appears. Number lists are never
  formula-escaped.
- **Figure.** It uses the reference palette's categorical slots 1–3 with distinct marker shapes,
  and hollow markers for untested cells. The validator was not run (no Node); the slots are the
  palette's validated ones and shape gives secondary encoding. matplotlib 3.10.9 is in a new
  `figures` uv group.
- **Error-audit inspector** must be `A<n>`: `claude` is refused, because Claude never inspects
  test output.
- **Error-audit writes.**
  - A second sample is refused while a sheet exists.
  - A failure after the registry write restores its original bytes.
  - No `register_rows` refactor was needed: spec 006's `merge_rows` → `validate_registry` →
    `write_registry` already form the validated append path.

Why:
- **p-values.** A p-value on every slice invites unplanned testing; intervals suffice for
  exploration.
- **Precision report.** Precision evidence is needed before the freeze, and no Stage 2 system
  exists yet.
- **Error-audit writes.** Re-sampling would make the audit selectable. A registry row without its
  sheet is harmless, but the spec asks for all-or-nothing.

Alternatives considered:
- **p for every statistic.** Rejected.
- **Imputing or skipping an empty H4 cell.** Rejected: silent.
- **A new `register_rows` in split_audit.** Unnecessary.
- **Allowing `claude` as the error-audit inspector.** Rejected.

## 2026-10-21: Inputs, outcome table and endpoint populations (Spec 007 / T3–T5)
Decision:
- **Inputs file.** Each system's entry declares its runs per stream (`stage1`, `stage2`,
  `transfer`), each with `train_condition` and `seed`.
  - **What a design accepts.** A design accepts only the training conditions it uses: `matched`
    needs `none`/`one`/`full`, `test_time` needs `full`, and `llm` needs `untrained`. Any other
    run (for example a mismatched-trained encoder run) is rejected as unused, not ignored.
  - **What each Stage 1 run must agree with.** It must match what it recorded: the
    `config.resolved.json` name equal to the panel name, the train condition, `eval_split`, the
    `metrics.json` seed, and `smoke = false`.
- **Hash once, verify on read.** Every file is hashed when the inputs are loaded and re-read only
  through `read_verified`, so the parsed bytes are the hashed bytes. Bounded reads are chunked.
  The earlier `read(limit + 1)` pre-allocated 512 MiB per file and made loading 25× slower.
- **Outcome storage.**
  - Predictions are kept as tuples aligned to the evaluation set's member lists. Endpoints are
    computed on demand by module-level functions, so a corrupted formula fails the component
    check.
  - A system's detection endpoints come from its Stage 1 runs when it has them, otherwise from
    its routed file.
- **Populations (spec FR3 clarified).**
  - `type_exact` keeps spec 005's `end_to_end` population, non-requests included, so its totals
    equal the scorer's.
  - `request_interpretation` is restricted to gold requests.
- **Scorer errors that name an example** (`stage1.check_predictions`) are replaced with an ID-free
  `invalid_predictions`.

Why:
- **Inputs.** The inputs file is written after test runs, so it must not be able to choose
  which runs count.
- **Run checks.** Recorded-vs-declared checks catch a mislabelled folder: a full-trained run
  passed off as `none`, a dev run in a test list, or a smoke run.
- **Populations.** Over non-requests, "detected AND exact" would reward predicting a request with
  no slots on a non-request.

Alternatives considered:
- **Ignoring unused runs.** Rejected: an ambiguous role.
- **Per-example dicts.** Rejected: about 10× the memory for a 5-seed grid.
- **One population for both Stage 2 endpoints, as FR3's old wording implied.** Rejected: either
  the `type_exact` equality check or the primary endpoint's meaning breaks.

## 2026-10-21: Bootstrap engine internals (Spec 007 / T2)
Decision:
- **Undefined replicates are stored as NaN** in one `array('d')` per statistic. Derived statistics
  are computed as linear combinations after the pass. NaN propagates through `map(operator.mul)`
  and `map(operator.add)`, so a derived value exists exactly where all its inputs do.
- **Zero-coefficient terms are dropped first.** An undefined L1 doesn't void the (−1, 0, +1)
  contrast.
- **Each statistic is compiled to its support** (the dialogues with a non-zero denominator).
  - Weights are picked with `operator.itemgetter`.
  - Statistics with the same support share one pick per replicate.
  - Statistics with the same denominator (same examples, other systems or conditions) share one
    denominator sum.
- **Percentile tails** are `round((1 − confidence) / 2, 12)`. At 0.95 that gives exactly 0.025 and
  0.975, so the order statistics equal `metrics._percentile_interval`'s (tested for 8 lengths).
- **Draws** use `rng.choices(range(n), k=n)`, which consumes the same random numbers as
  `metrics.py`'s `rng.choices(groups, k=n)`. The intervals therefore match the per-run scorer
  exactly (AC-007-6).
- **An unstable statistic** keeps its interval but gets p = None. A statistic never drawn gets
  neither.

Why:
- **Dense multiply-adds** would run over all 944 dialogues even for an L3 or INF slice that
  touches about 120–200 of them. The compiled form projects to about 4 minutes for 1,440 statistics at B = 10,000 (synthetic
  timing), inside the 15-minute bound.
- **NaN propagation** makes "only replicates where every input is defined" automatic. It needs no
  per-derived bookkeeping.

Alternatives considered:
- **Python lists of floats for replicates.** Rejected: about 4× the memory of `array('d')`, roughly
  115 MB at 1,440 × 10,000.
- **Computing derived statistics inside the replicate loop.** Rejected: same arithmetic, and the
  loop gets more complex.
- **Allowing derived statistics to reference other derived statistics.** Rejected for now: T6 can
  flatten every contrast (benefits, trends, level − L0) into base terms, because they are all
  linear.

## 2026-10-20: Analysis config shape and hash (Spec 007 / T1)
Decision:
- **Hash.** SHA-256 of the parsed TOML as sorted-key, compact JSON. It is computed only after
  validation, so it covers validated values only. Comments, key order and number spelling
  (`0.95` vs `9.5e-1`) don't move it. Array order does, including `streams`.
- **Every key is required.** There are no defaults, so the frozen file is the whole plan.
- **Holm members are typed by `kind`:** `h1_trend`, `h2_trend`, `h3_difference`, `h4_contrast`,
  `mismatch_control`. Each kind has its own required keys. `h3_difference` must reference the
  primary system.
- **Endpoint → streams.**
  - The Stage 2 endpoints need `routed` + `oracle`, because the component check runs
    `stage2.build_report`, which takes both.
  - `stage1_correct` accepts `stage1` or `routed` + `oracle`.
  - An `llm` system must be `test_time`.
- **Cross-field checks.**
  - `alpha` must equal 1 − `confidence`, since the interval decides the primary test and alpha
    feeds Holm.
  - Level lists must follow L0 < L1 < L2 < L3 < INF. A reordered list would silently flip a
    trend's sign.
- **Default panel designs.**
  - `tfidf-utterance` and `tfidf-context` are `test_time`. The first is context-blind; the second
    cannot train on `none`.
  - Encoders and `hybrid` are `matched`.
- **H1 family member** is scored under `none` (the utterance-only replication setting). *To
  confirm at the freeze.*
- **`git_state` without git.** It returns `None` for both fields when no git binary is on PATH,
  instead of raising.

Why:
- **The hash** can be recomputed with `tomllib` + `json` alone, by spec 008 or a reader.
- **Required keys** stop a missing key from silently taking a code default that could change
  between versions.
- **Typed members** make "primary test inside the family" and "member outside the panel"
  mechanical checks.
- **`git_state` without git.** Native Windows has git only inside GitHub Desktop. Without this,
  `src.evaluation.run` failed and a Stage 1 run crashed at `finish()`. That latent bug was hidden
  whenever git was on PATH.

Alternatives considered:
- **Hashing the dataclass form.** Rejected: renaming a field in code would move the hash of an
  unchanged file.
- **Normalizing `streams` order before hashing.** Rejected: keeping the raw parsed form is
  simpler to reproduce.
- **Free-form member names with an implied test.** Rejected: names can't be validated.
- **Allowing `alpha` ≠ 1 − `confidence`.** Rejected: the CI rule and the Holm level would then
  disagree.

## 2026-10-20: Spec 007 review: primary endpoint, frozen panel, H3 design, error-audit gate (Spec 007 / R1–R8)
Decision:
- **Primary endpoint.** `request_interpretation` (predicted ≠ `no_request` AND an exact
  interpretation), following spec 001 §5. Spec 005's type-exact `end_to_end` becomes the
  secondary `type_exact` line. *(R1)*
- **Panel.** The frozen analysis config enumerates the model panel. The inputs file only maps it
  to files. A missing system is `not_run` with p = 1 and keeps its place in the Holm family. *(R2)*
- **H3 design.** The Holm-tested H3 differences use test-time lines for every system. The
  primary-line comparison is descriptive (Sandy, option a). *(R6)*
- **Bootstrap.** One joint draw of all dialogues per replicate, example-weighted ratios.
  Zero-denominator replicates are dropped per statistic, and a statistic losing more than 1% of
  replicates is `unstable` and untested. *(R3)*
- **Error audit gate.** The freeze date comes only from `freeze.json`. The sampler requires `--on`
  on or after it, `--inspector`, and the frozen test report. The codes file is committed under
  `results/error_audit/`, which is added to spec 006's post-scoring scan directories.
  Over-inference is reported by the false-positive rate, not audited. *(R4, R5, R8)*
- **Spec 001 v1.3 note** records the D-07 amendment. *(R7)*

Why:
- The type-exact score penalizes reading rule-L0 "indirect" rewrites as direct, inside the
  L2 − L0 contrast.
- An inputs-derived panel would let the Holm family and the H3 tables depend on test results.
- Primary lines mix matched and test-time designs across families.
- A CLI freeze date would let test be inspected before the freeze while being recorded as
  post-scoring.

Alternatives considered:
- Keeping `end_to_end` as primary.
- H3 on primary lines (R6b) or on same-design pairs only (R6c).
- Slice-only resampling.
- An NR stratum in the error audit (about 15 more items of labeling).

## 2026-10-20: D-07 statistics, H2 status, context contrast and error-audit size (Spec 007 draft)
Decision (Sandy, 2026-10-20):
- **D-07 method.** A dialogue-grouped bootstrap difference-in-differences on seed-averaged
  outcomes, with one shared bootstrap for every statistic. No mixed model, in any role.
- **H2 status.** One confirmatory test: the L0–L2 linear trend of the full − none benefit, for one
  prespecified system, on the `end_to_end` endpoint. L3 and INF are exploratory. The secondary
  family is Holm-corrected.
- **Context contrast for trained models.** Matched training (train c, evaluate c) is primary. A
  full-trained model scored at test time is a secondary line. Mismatch controls stay test-time.
- **Error audit.** 60 errors (15 per level, L0–L3), seeded and stratified. Dialogues are
  registered `post_scoring` before the sheet is written.

Why:
- The bootstrap is stdlib-only and deterministic, and it extends the verified scorers. A GLMM
  adds a dependency and convergence risk on sparse cells, too close to Dec 3.
- `auto-v1` L3 precision is 12/40, so L3 can't carry a confirmatory claim.
- Test-time ablation of a trained model confounds context with train/test shift.
- About 1 hour of labeling keeps pace with the deadline.

Alternatives considered:
- A GLMM as a sensitivity line or as the primary analysis.
- Letting L3 enter by a precision threshold, or estimation-only H2.
- Test-time ablation as primary, or both lines with no primary.
- 120 errors, or deciding the size at the freeze.

Open: the primary system (D-05), the endpoint fallback if no end-to-end system is ready, the rules
version at the freeze, and the `freeze.json` writer (WP-08).

## 2026-10-19: Test audit is fully deterministic, fails closed, and registers 51 dialogues (Spec 006 / T5–T9)
Decision:
- **No timestamp in the audit summary.** `audit --verify` byte-compares both files.
- **Content hash.** The summary's `content_sha256` covers everything except the `post_scoring`
  disclosure.
- **Test scoring needs a current audit.** Stage 1 (scorer and trainer) and Stage 2 (inputs and
  score) refuse to run on test without it. "Current" means `items.jsonl`, `dialogues.jsonl` and
  the `pre_freeze` registry rows all match. Predictions for excluded examples are ignored.
- **Exclusion precedence.** Inspection outranks cross-split duplication.
- **Scan reading.** The sheet scan reads every CSV cell, and accepts spec 003's
  `<sheet>_sheet_info.json` as a blind sheet's key.
- **Registry size.** It holds 51 `pre_freeze` dialogues, not the spec's 49. The boundary-safe
  pattern found 2 session-log dialogues mentioned only inside item IDs. All are registered under
  the conservative session-log policy.

Why:
- A timestamp would make `--verify` compare only the CSV. A tampered or stale summary would then
  pass.
- Keeping post-scoring disclosure out of the hash is what lets the error audit be recorded
  without moving the frozen set (FR14).
- The trainer checks the audit before training, so a stale audit costs no GPU time.
- Rejecting a ragged row, or a spec 003 sheet with an existing key, added no safety: both are
  fully readable for IDs. A truly malformed CSV still fails.

Alternatives considered:
- An injectable timestamp, as in spec 004's summary. It weakens `--verify` for no benefit.
- Hashing the summary bytes. Then post-scoring rows would move the hash.
- Re-pairing excluded donors. Sandy rejected that on 2026-10-19.
- Unregistering the item-ID-only mentions. That contradicts the approved conservative policy and
  would need someone to reopen the logs to judge them.

## 2026-10-19: Lab RTX 5090s; large encoders and five seeds (Spec 001 / D-05, NFR-04)
Decision:
- Reported GPU runs move to the lab RTX 5090 (32 GB). The 4090 is the fallback.
- New configs `encoder_deberta_v3_large.toml` (micro-batch 8) and `encoder_roberta_large.toml`
  (16) keep the effective batch of 32, max_length 512 and 2 epochs. They use learning rate 1e-5
  with 10% warmup, where the base configs use 2e-5 with 6%.
- `stage1_grid.sh` defaults to five seeds. The first three are the original grid.
- Training data is unchanged.
Why:
- Sandy reported the new hardware and asked to ramp up the settings and data. No run has been
  logged yet, so the recipe can still change without any reported number moving.
- Large encoders are the clearest quality gain the extra memory buys.
- Five seeds give a usable estimate of seed variation (§13).
- Large DeBERTa is known to diverge or collapse at 2e-5. 1e-5 with a longer warmup is the
  standard published setting, chosen in advance rather than tuned on dev.
- Training already uses all 101,460 DIRECT train examples. More data would mean training on dev
  (removing the selection split), on test (leakage) or on IndirectRequests (forbidden by AC-15).
Alternatives considered:
- Raise the effective batch: it changes the optimization and buys no accuracy, only speed.
- Raise max_length or the context budget: D-06 and the committed test manifest fix the budget,
  and RoBERTa's limit is 512.
- A long-context encoder: it would reopen D-06 and spec 004 a week before the freeze.
- More epochs: there is no evidence 2 underfits at 101k examples, and checking would mean
  selecting on dev.

## 2026-10-19: Inspection sources are pinned and dated in code; scans match IDs by pattern, not column (Spec 006 / T2–T4)
Decision:
- `DERIVED_SOURCES` fixes each inspection's file, date and inspector. It pins the git-ignored
  obsolete round-3 sheet and `fact_drift.jsonl` by the SHA-256 they had when inspected.
- `register` never changes or drops a committed row. A changed pinned file is refused.
- After a freeze date (from `data/manifests/freeze.json`, or `--freeze-date` until it exists), a
  new `pre_freeze` row is an error, and rows dated on the freeze day are `post_scoring`.
- Sheet and transcript scans find dialogue IDs with one pattern: no letter or digit before, no
  digit after. It runs over every CSV cell or the raw text, not over named columns.
Why:
- Pinning stops a rerun of the fact-drift audit, or a regenerated sheet, from silently moving the
  test set.
- Erroring on a late `pre_freeze` row makes a missed inspection visible instead of letting it be
  backfilled after scores exist.
- IDs appear inside compound values (`<stem>_tNN` item IDs, `d:<stem>:tNN`, `<stem>.json#N`), so
  column-based resolution would have missed `context_items.csv` and every `key.csv`.
Alternatives considered: deriving dates from file timestamps (they change on copy, so the hash
changes too); per-column item_id resolution through `items.jsonl` (misses compound values);
reading transcripts line by line (some log lines are megabytes); treating rows dated on the freeze
day as `pre_freeze` (then an error audit started on the freeze day would be refused).

## 2026-10-19: Inspected-dialogue registry rejects formula-leading values rather than escaping them (Spec 006 / T1)
Decision: the T1 criterion "a formula-leading cell is escaped on write" is met by construction.
Every registry field is a validated dialogue ID, enum, pseudonymous inspector ID, ISO date or
version constant, none of which can start with `=`, `+`, `-` or `@`, so such a value is rejected
before anything is written. A dialogue may have one row per source. The exclusion reason uses the
precedence `levels_round1` > `levels_round3` > `obsolete_round3_sheet` > `fact_drift_review` >
`claude_session` > `manual`, over `pre_freeze` rows only. Canonical dialogue IDs are the
`items.jsonl` form (`PMUL1762.json`), with digits ASCII-only, and padding is not stripped.
Why: this is the convention `context_items.py` already uses for committed registries. Escaping
would write a `'` prefix into a committed file that the scorers then must un-escape, and a
formula-like ID is a data error to reject, not a value to preserve. Strict, unstripped IDs make a
hand-edited typo fail loudly instead of matching silently.
Alternatives considered: escape on write and un-escape on read (adds a second encoding to a freeze
input); stripping whitespace and lower-casing IDs (hides edit errors); one row per dialogue with a
list of sources (hard to diff, and the per-source dates get lost).

## 2026-10-18: Explicit provisional auto-v2 and separate oracle/transfer scoring (Spec 005)
Decision: Sandy requested both the rule revision and Stage 2/IndirectRequests scoring. V1 stays
the default and retains every corpus prediction; v2 is an explicit selection, source-frozen
before adjudicated round 2. Both score 29/30 on that check; no L3 validation is inferred because
there are no gold L3 rows. A fresh seeded dev audit excludes all historical/original-check turns.

Stage 2 uses `cat-v1` primary categories, explicit Inform values and Request names. Conflicting
act values have no single structured reference and leave interpretation only, with a named
count (2 dev / 8 test examples); detection keeps them. Oracle predictions are a separate complete
stream, so route misses fail end-to-end without shrinking oracle coverage. Required-slot recovery
means observed acts, not execution completeness. Free-paraphrase/LLM-judge adequacy is deferred
until model outputs and Sandy's small rating sample exist.

IndirectRequests remains pinned, none-context-only and separate, with ambiguous slices, boolean
aliases, generation labels and explicit model-family metadata. Inputs contain no situation or
gold fields. Alternatives rejected: replacing v1 silently; tuning on round-2 per-item errors;
pooling generated transfer data with the benchmark; or equating act exact match with paraphrase
adequacy. Details: [spec 005](../005-scoring/spec.md).

## 2026-10-17: Round 2 adjudicated; "I need/want to leave" is L0 (Spec 001 / WP-01)
Decision: Sandy adjudicated all 30 round 2 rows under rubric v2. Q1 is reading (a): "I need / I want
to + travel verb" is an `L0` need/want statement, recorded as rubric rule R8, and R6's example is
replaced. 13 first labels were kept, 16 changed to the suggestion, and 1 (r2-23) was kept at `INF`
against the suggested `NR`. Round 1 and 3 gold is **not** re-adjudicated to match R8: its
"need to leave/arrive" items stay `L2`: the 3 known `auto-v1` misses (r3-04 among them) and r3-24
(R6's old example, which `auto-v1` already labels `L2`).
Why: (a) follows the decision procedure, needs no new rule, and matches `auto-v1`. Editing round 3
gold toward the rules after their predictions are known would raise the reported 79% / κ 0.74 after
the fact. Adjudicated round 2 is the fresh check for `auto-v2`: per-item `auto-v1` errors on round 2
should not be read while writing `auto-v2`.
Alternatives considered: re-adjudicate round 3 to L0 and report both numbers (post hoc, toward the
rules); reading (b) `L2` (consistent with round 3, but needs a v3 rule that `auto-v1` breaks).

## 2026-10-14: D-06 context budget and separate genuine / mismatch sets (Spec 004)
Decision: every model sees inputs from one renderer, `render-v1` (`src/data/contexts.py`). Under
`full` and `mismatched`, context plus target is at most **350 whitespace tokens** (speaker tags
count), in training and evaluation alike. The oldest whole turns are dropped first; the target is
never cut. The budget is a renderer constant, not a run setting. Stage 1 scores none / one / full
on the *genuine* set (every turn with prior context) and the mismatch conditions on the *mismatch*
set (genuine turns with a donor). Donors that mention a target act value are disclosed, with one
sensitivity line per mismatch contrast. The test manifest (`data/manifests/contexts_test.csv`,
IDs and hashes only) is committed as the freeze object; dev is regenerated.
Why: D-06 asks for a common input budget. Without one, the encoder silently left-truncated at 512
subwords while an LLM would see the full history. 350 words truncates 104 of 11,195 test examples
(0.9%) and 71 dev examples (0.6%). The old "comparable" filter dropped 72 test examples (44 items)
without a donor from *every* condition, violating spec 001 AC-06.
Alternatives considered: no budget (models see different windows); an evaluation-only budget
(train and test inputs differ); a last-K-turns cap (long turns can still overflow the encoder);
removing cue donors (shrinks the control); committing only manifest summaries (the freeze would
depend on regeneration). Pending: `src.stage1.length_check` on the chosen encoders, run by Sandy
in WSL before the freeze; if any input exceeds 512 subwords, the budget is lowered for all models
under `render-v2`.

## 2026-10-13: Option A, rule-assigned levels and MultiWOZ acts instead of new labeling (Spec 001 v1.2)
Decision: no new hand labeling. Directness levels come from the frozen wording rules `auto-v1`, a
transcription of rubric v2 (`src/data/auto_levels.py`). Intents come from MultiWOZ user acts,
mapped onto the proposal's categories by `cat-v1` (`src/data/intent_categories.py`). The test set
is DIRECT's test split. This is a scoped exception to the constitution's "human annotators decide
every label": rule levels are mechanical, versioned, validated against human labels, and never
called gold.
Why: Sandy does not want to keep labeling. The remaining plan needed about 200–280 turns through
three passes (roughly 10–13 hours). The rules were written from the rubric's text and its invented
examples only, frozen, then scored once: 31/39 (79%), κ = 0.74 on the adjudicated rounds 1 and 3,
above the plan's κ ≥ 0.6 bar for two humans. They give hundreds to thousands of test examples per
level, against the plan's 25–40.
Known rule errors on that check: answers with no detail labeled L3 where humans said INF (4), and
"I need to leave/arrive …" labeled L0 where humans said L2 (3). Rubric v2 is itself inconsistent
on the second case (R6's example vs. step 3). Fixes go in a new version (`auto-v2`) checked on
labels the rules have not been tuned on (adjudicated round 2), never by editing `auto-v1`.
Alternatives considered: (B) a form pass only on about 200 test turns (about an hour); keeps human
gold levels. (C) LLM-assigned levels checked against human labels; circular when LLMs are also
evaluated, and the constitution bars Claude as an annotator.

## 2026-10-12: Re-scope to the December class paper under the course professor (Spec 001 v1.1)
Decision:
- The research is conducted through Sandy's Machine & Deep Learning course professor. The
  original proposal is the governing design. "Professor" (P) in every spec means this professor.
- The only target is the December class paper, written as a computer-science paper. WDSI, the
  2027 timeline and the 2015–2025 hallucination review are removed. FR-13, FR-14, WP-12, AC-14
  and D-08 are withdrawn (IDs kept, so cross-references stay stable). FR-11 is ordinary related work.
- Screened literary exchanges become an optional add-on: reported separately, cut first. The spec
  002/003 literary tooling stays as built.
- IndirectRequests returns as a separate transfer test (new FR-15, AC-15), as in proposal week 2:
  Stage 1 recall and Stage 2 slot-value recovery under `none` context, with GPT-family models
  flagged. Nothing new is generated, and the main benchmark stays human-written.
Why: the course professor said not to change the plan or proposal, to add some of the newer data
methods, and to optimize for the December deadline. All four choices were Sandy's (2026-10-12).
Alternatives considered:
- Keeping the literary quota (20–40 test items, ≥10 families): rejected. It is the largest
  human-labour item that the proposal never promised.
- Dropping literary work entirely: rejected. The professor allowed adding the methods, and the
  tooling is already built.
- Keeping the no-synthetic rule: rejected. It removed a proposal deliverable, and IndirectRequests
  is an already-pinned, cheap way to test L2-style hints, which are rare in MultiWOZ.
- Restoring new LLM-assisted examples as well: rejected. It adds labeling work before December.

## 2026-10-11: `validate` names a rule per finding; `coverage` reads only validated data (Spec 003 / T12, T13)
Decision:
- `validate` is read-only and checks the whole workspace (every batch and annotator). Each
  finding names one of 13 rules (`registry`, `group-split`, `target-hash`, `screening-log`,
  `taxonomy`, `labels`, `evidence`, `prior-chain`, `corrections`, `row-hash`, `local-text`,
  `duplicate-id`, `foreign-id`) and its item, and one run lists all of them.
- A label edited after export is caught through the local text file. Each text record already
  carries its committed row's key, so an edited row matches no record (`row-hash`). An edited
  form label with a context row built on it also breaks `prior-chain`.
- `n_segments` and stratum are recomputed from the sources, closing the T9 note that a tampered
  local snapshot could slip an out-of-range evidence index or a wrong-stratum intent past export.
- Group/split consistency is checked against the sources (`items.jsonl` for dialogues, the
  spec 002 families file for literary items), not just within the registry.
- `coverage --batch B` runs `validate` first and refuses on any finding. It prints both
  form × function (AC-003-12) and form × request type (FR13), plus intents, slots
  (stated / `?` / absent), confidence, future dependence, `needs_adjudication`, `prior_exposure`
  and `built_on_superseded`. Every cell is printed, one section per annotator. Titles are ASCII so
  the report survives redirection on Windows code pages.
Why: one run that lists every named problem is what makes a weekly "validate, then back up"
habit cheap. Recomputing from sources is the only check a stale or edited local file can't pass.
Refusing coverage on bad data keeps D-03/D-04 decisions off corrupted counts.
Alternatives considered:
- Committing a per-row label digest so edits are caught without local text: rejected. The
  committed row already is the labels, so a digest beside it is edited just as easily. The local
  text record is the independent copy.
- Coverage on unvalidated data with a warning: rejected, because counts from a broken chain look
  just as plausible as real ones.
Known limits: an annotator who edits both the committed row and its text record consistently
is not caught (integrity against accidents, not adversaries). `built_on_superseded` can't see a
paraphrase-only context correction, because FR10's chain hash excludes `text_sha256` by design.
`later_passes_sealed` is checked only for contradiction (a later row built on the corrected
row), since the sheets that existed at the time aren't recorded.

## 2026-10-11: Corrections are two-step, and "seen later evidence" includes built sheets (Spec 003 / T11)
Decision:
- `correct --prepare` writes a one-row correction sheet (`correct_<pass>_<A>.csv`), prefilled with
  the live row's labels and its local free text. `correct --reason R` applies it. The snapshot
  records the corrected row's identity, so a row changed in between is refused.
- `later_passes_sealed` is true when a later pass has an exported row **or a built sheet** for
  that item and annotator.
- A corrected row's `prior_sha256` points at the *current* live prior row.
- The log stores FR10 chain hashes, so a correction that changes only slot values or a paraphrase
  logs `old_sha256 == new_sha256`. The text change shows in the row's `text_sha256` and in the
  separate text record kept for each version.
Why:
- One command with hidden state ("first run writes, second run applies") is easy to misuse.
- A built sheet has already shown the evidence, even before anything was exported.
Alternatives considered: correcting by editing a full pass sheet (invites multi-row edits);
logging a full-row hash that includes free text (departs from FR10, which chains on labels only).

## 2026-10-11: Context and reveal pass shapes (Spec 003 / T9, T10)
Decision:
- Context and reveal sheets also use opaque, shuffled row IDs (`c-`, `r-`). The snapshot keeps
  each item's stratum and `n_segments`.
- Committed context rows hold `slot_names` and `unstated_slots` (names only), `request_status`
  (it depends only on `function`), the taxonomy version and hash, and `segmenter_version`.
  `request_type` is not committed. It needs the form row too, so it is derived at analysis time
  and can't go stale after a form correction.
- Reveal rows commit the derived `confirmatory_eligible` and `needs_adjudication`, which depend
  only on the row's own value.
- `function = uncertain` may record a candidate intent. A `request` needs a paraphrase.
- The reveal sheet shows the target and the annotator's own sealed reading (display only) beside
  the continuation. This departs from FR7's literal "only the continuation".
- The context sheet defaults to the newest taxonomy version. Export refuses if that version was
  edited in place after the sheet was built.
- Local text records are keyed by `(item_id, row_sha256)`, and `merge_export` compares that
  full-row key. Without it, a re-export that changed only a paraphrase would pass as identical,
  because FR10 excludes `text_sha256`.
Why:
- Item IDs name a dialogue that can be looked up, so opaque IDs keep every pass blind.
- `future_dependence` is defined relative to the context reading. Making the annotator recall 60
  readings from memory adds noise, and the reading was sealed in the previous pass.
- A candidate intent under `uncertain` is the most useful input for adjudication.
Alternatives considered: item IDs on context sheets (lookup risk); committing `request_type`
(staleness); a blank reveal sheet with no reading (recall burden, no extra blinding).

## 2026-10-11: Draft taxonomy `ctx-tax-v0` (Spec 003 / T7)
Decision: 11 dialogue intents (`find_`/`book_` per MultiWOZ domain, plus `ask_attribute` with a
required `attribute`), 5 literary intents with no required slots, and `joint_action` for both
strata. Bookings require the slots needed to act (people/day/time, people/day/stay, people,
departure/destination). Searches require none. Slot names are lowercase readable versions of
MultiWOZ's `*-Inform`/`*-Request` names (`leave_at`, `arrive_by`, `train_id`).
Why: required slots mean "can't be executed without it", so `name=?` marks a genuinely missing
detail rather than an unconstrained search. There is no catch-all literary intent such as
`do_action`: `out_of_taxonomy` plus coverage shows what v0 misses, which is the evidence D-03 needs.
Alternatives considered: one intent per MultiWOZ act (too fine, tied to the corpus); a generic
literary `act` intent (would hide every gap).

## 2026-10-11: Taxonomy rules and a per-version content hash (Spec 003 / T6)
Decision:
- `out_of_taxonomy` takes no slots, and its details go in local notes.
- Slot values may contain `=` but not `;`. Empty segments are ignored, and an empty value is an
  error that suggests `name=?`.
- `canonical_slots` sorts the pairs by name, for hashing.
- Each version gets a canonical content hash (`version_sha256`) covering stratum and the sorted
  required/optional slots per intent, excluding descriptions. Context rows will record it as
  `taxonomy_sha256` (T9, spec FR8 amended).
Why:
- "Append-only by version" stops deletion but not redefinition. Editing `ctx-tax-v0`'s required
  slots after labels exist would silently change what every earlier label means.
- Descriptions are excluded so that fixing a typo isn't treated as a redefinition.
- An `out_of_taxonomy` intent has no slot schema, so any slot on it is unverifiable.
Alternatives considered: trusting git history for in-place edits (invisible to `validate`);
hashing the raw CSV lines (sensitive to row order and typo fixes); allowing free-form slots on
`out_of_taxonomy` (can't be validated or scored).


## 2026-10-11: Sealed-pass machinery in its own module; the snapshot is the form key (Spec 003 / T3, T4)
Decision:
- Pass logic lives in `src/annotation/context_passes.py`. `context.py` is CLI orchestration plus
  source reconstruction.
- The per-sheet snapshot (`<pass>_<A>_sheet_info.json`) is also the form pass's row-ID → item key,
  and it stores each item's prior hash. Export refuses a row whose prior row changed after the sheet
  was built.
- Form utterances are shown whitespace-collapsed.
- `sheet` refuses to overwrite a sheet with unexported items.
- Spec 002 gains a public `load_log`.
- `Dirs.literary_work_dir` is configurable.
Why:
- Keeping pass logic out of `context.py` stops that file from collecting every pass's logic by T12,
  and the machinery can be tested without argparse.
- A separate key file would duplicate the snapshot and could drift from it.
- Storing prior hashes per item proves which version of the prior row a label was made on.
- Literary targets span CRLF line breaks, so the sheet collapses whitespace for display.
- Overwriting an unexported sheet would destroy an annotator's work.
- With the literary work dir hard-coded, tests would have written into Sandy's real
  `data/interim/literary/screening_sheet.csv`. This was caught before any test ran.
Alternatives considered: everything in `context.py` (as plan.md first sketched); a separate
key CSV; showing raw text with line breaks; a `--force` overwrite flag (deleting the sheet is an
explicit, visible equivalent).
Limitation: a committed row edited by hand before its next-pass row exists has no successor hash
to catch it. Git history is the audit trail for that window.


## 2026-10-11: Registry and draw details (Spec 003 / T2)
Decision:
- A dialogue `target_sha256` hashes the turn text from `dialogues.jsonl` (original MultiWOZ),
  not DIRECT's `target_utterance`.
- `draw` refuses a batch that already holds drawn items.
- The draw ignores `mismatch_status`, unlike `levels.eligible_items`.
- The registry is written sorted by `item_id`.
- A literary `source_ref` is the source key, and `seed`/`pool_size`/`inputs_sha256` stay blank.
- Dialogue stems must start with an alphanumeric character.
Why:
- DIRECT stripped outer whitespace on 4,024 rows, and `validate` (T12) recomputes from
  `dialogues.jsonl`. Hashing a different string would fail every whitespace-stripped item.
- Re-running `draw` wouldn't be idempotent: the pool excludes registered dialogues, so a second
  run would quietly add 40 *different* dialogues.
- Donor availability is spec 004's concern (spec 001 AC-06), never a selection criterion.
- A sorted registry gives the stable order that the form-sheet shuffle starts from (AC-003-3).
- Strict field shapes keep the committed file text-free and free of formula prefixes.
Alternatives considered: hashing `items.jsonl` text (breaks validation for stripped rows); making
`draw` append and trusting the operator (silent over-sampling); an `--append` flag (YAGNI, since
a new batch name does the same job and is visible in the registry).


## 2026-10-11: Schema core choices (Spec 003 / T1)
Decision:
- `request_type` gains an `uncertain` value for `function = uncertain`. FR11 had left that case
  undefined.
- `canonical_hash` accepts **string values only**. Rows are hashed exactly as they're written to
  and read back from CSV.
- Annotator free text rejects Unicode categories Cc/Cf/Zl/Zp/Cs (controls, invisible format and
  bidi characters, line separators). It does not use `str.isprintable()`.
- Batch names also exclude Windows device names (`con`, `nul`, `com1`…).
Why:
- Without the `uncertain` type, an uncertain-presence item would be forced into `none` or
  `form_unknown`, which would silently move it into or out of the detection denominators.
- Coercing an int at export but hashing a string at validation would break the hash chain
  without any visible cause.
- `isprintable()` rejects non-breaking spaces, which Excel and pasted text often contain.
- A batch becomes a directory name on native Windows.
Alternatives considered: mapping uncertain to `none` (hides ambiguity); `str()`-coercing values
before hashing (silent mismatches); reusing spec 002's `_single_line` (false rejections of NBSP).


## 2026-10-11: Contextual annotation uses sealed passes and request precedence (Spec 003 review)
Decision: labels are collected in three sealed passes per annotator: form (target only), context
(prior segments only) and reveal (later evidence). Each sheet is built per item from the previous
pass's committed export, and rows are hash-chained.
- `function = request` whenever a turn contains any request of the addressee, including
  proposals of joint action. Otherwise decline > inform > social > other.
- Unstated required slots are `name=?`, never invented.
- Evidence is recorded as `seg-v1` sentence/turn indices.
- Mistakes are fixed with a logged `correct` command that supersedes and never rewrites.
Why: the order of evidence exposure is the validity threat in a solo-rater pilot, so the tool
enforces it rather than relying on discipline. Precedence removes disagreement that comes from a
missing rule rather than real ambiguity. `?` slots stop gold from containing invented inference.
Alternatives considered: one sheet with hidden columns (a spreadsheet can't enforce hiding);
multi-select function (messier agreement); exact-span evidence (slower); immutable labels with
no correction path (invites hand-edits that break the chain).


## 2026-10-10: Literary locators are raw decoded offsets, and screeners copy words, not offsets (Spec 002 / T2, T5)
Decision: unit and target offsets index the pinned file decoded as UTF-8 with CRLF intact. Screeners
edit `target_text`, and export resolves it to offsets: whitespace-insensitive, word-bounded, and
required to be unique in the episode.
Why: raw offsets reproduce source bytes exactly, with no normalization contract. Copying words is
far less error-prone than typing offsets, and the uniqueness rule makes resolution unambiguous.
Alternatives considered: offsets into LF-normalized text (adds a hidden contract); screener-entered
offsets (error-prone); committing the public-domain text (breaks the single "committed files are
text-free" rule).

## 2026-10-10: Exhaustive mechanical proposals inside pre-assigned dev families (Spec 002 / T3, T4)
Decision: families are assigned to dev, by seeded draw or by explicit logged reason, before anyone
reads them. Every quoted span (Aesop) or speech-verb verse (KJV) in them is proposed. Missed
utterances are added as `origin=manual` rows, so they stay visible in the log.
Why: it keeps selection independent of models and of the researcher's attention (constitution).
Pre-assignment also stops a fable that was read during the pilot from leaking into test.
Alternatives considered: keyword or LLM pre-filtering (selection on difficulty, and circular);
hand-picking (invisible selection).

## 2026-10-10: Security review of spec 002 (Spec 002 / T1, T4, T5)
Decision: the review found no findings at or above the reporting bar. One low finding was fixed:
committed `family_id` values are now regex-validated on every load, and the sheet escapes
`family_id`/`locator` against spreadsheet formula injection.
Why: the families CSV is committed, so it is untrusted, and it flows into a sheet that is opened
in Excel.
Alternatives considered: escaping only, which would leave malformed IDs flowing into the committed log.

## 2026-10-10: Spec 001 is an umbrella; code work goes through child specs (Spec 001)
Decision: Spec 001 does not go through `/spec-review` → `/spec-decompose` → `/spec-implement`.
It stays the protocol source of truth, and `roadmap.md` tracks it. Each code-bearing work package
gets a small child spec (002+) that does run the full lifecycle. Human research work (adjudication,
screening, labeling, freezes, writing) is tracked as roadmap checklist items.
Why: about half of spec 001's 12 work packages are human judgments or writing, which unit tests
can't verify. The lifecycle is valuable where a silent bug would corrupt results: source
locators, rendering invariants and scorers.
Alternatives considered: (a) Full lifecycle on 001. Its review and decomposition would duplicate
§11/§14/§15, which already exist, and yield untestable "tasks" like "adjudicate round 2".
(b) No specs at all, following the roadmap ad hoc. That loses adversarial review on exactly the
components where validity bugs hide.
