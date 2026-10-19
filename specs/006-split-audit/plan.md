# Plan 006: Split and prior-inspection audit

> **Phase:** Plan · **Date:** 2026-10-19 (revised after review R1–R9) · Spec: [spec.md](spec.md)

## Approach

There is one new stdlib module, `src/data/split_audit.py`, with these subcommands in the style of
`context_manifest`:

```
python -m src.data.split_audit register [--freeze-date YYYY-MM-DD]  # derived + manual rows (FR1–FR3, FR5, FR14)
python -m src.data.split_audit scan                                  # human-facing sheets vs registry (FR4)
python -m src.data.split_audit scan --transcripts <dir> [<dir> ...]  # one-time, local only, IDs only (FR6)
python -m src.data.split_audit check                                 # split grouping, official lists, dup dialogues (FR7, FR8)
python -m src.data.split_audit audit [--verify]                      # data/manifests/split_audit_test{.csv,_summary.json} (FR9–FR13)
```

**Registry.** `data/annotations/inspected_test_dialogues.csv` is committed, sorted by dialogue ID,
then source. Its columns are `dialogue_id, source, reason, inspector, inspected_on, phase,
registry_version`. Derived rows come from a fixed `SOURCES` table in code. Filenames are listed
explicitly, because the local `round2_items.csv` holds committed **round 3** data and the local
`round3_items.csv` is the obsolete sheet, so round numbers are never parsed from names:

| Source code | Input | Inspector | Inspected on | Pinned |
|---|---|---|---|---|
| `levels_round1` | committed `data/annotations/levels_round1.csv` | annotator column | round-1 date | committed in git |
| `levels_round3` | committed `data/annotations/levels_round3.csv` | annotator column | 2026-09-30 | committed in git |
| `obsolete_round3_sheet` | local `data/interim/labeling/round3_items.csv` | `claude` | 2026-10-01 | SHA-256 in table |
| `fact_drift_review` | local `data/interim/direct/fact_drift.jsonl`, test rows | `claude` | 2026-10-01 | SHA-256 in table |
| `claude_session` | rows written by `scan --transcripts` | `claude` | run date (written once) | committed rows |
| `manual` | rows added by hand with a reason enum | given | given | committed rows |

The exact dates and hashes are read from the files and the history in `specs/memory/` during
implementation and fixed in the table. A local source whose hash differs is refused. A missing one
keeps its committed rows with a warning.

**Phase.** The freeze date is read from the WP-08 freeze record once it exists, or from
`--freeze-date` in tests. Before the freeze, new rows are `pre_freeze`. After it, `register` and the
transcript scan write only `post_scoring`, and `pre_freeze` is refused. `primary` and the
audit's registry hash cover `pre_freeze` rows only.

**Canonical IDs.** One function, `canonical_dialogue_id(raw) -> str`, validates the
`^(PMUL|MUL|SNG|SSNG|WOZ)\d{3,5}(\.json)?$` shape and returns the `.json` form. Every reader calls
it: the registry, sheets, list files and transcripts.

**Transcript scan.** It reads JSONL files under the given directories line by line, with a bounded
line length, and applies the ID regex to the raw line. It keeps only matches that are test-split
dialogues and prints the sorted canonical IDs and counts. Lines are never printed or stored.
`register` takes the hits as `claude_session` rows. The run date is written once into those rows
and is not re-derived on later runs, which keeps them deterministic.

**`check`** reads `items.jsonl`, `dialogues.jsonl` and the two pinned MultiWOZ list files from
`data/raw/multiwoz/MultiWOZ_2.1/`. It doesn't import the builder's split logic, because it is meant
as an independent second implementation. Cross-split duplicate dialogues are keyed by SHA-256 of
the `dup-v1`-normalized user turns joined by `\n`, for dialogues with at least two user turns.

**`audit`** reuses spec 004's genuine-set construction (`src.data.contexts.genuine`,
`in_mismatch_set`) so that example IDs and set membership equal the committed context manifest. It
asserts that the IDs match that manifest exactly, and it refuses to run if the manifest's input
hashes don't match the current `items.jsonl`/`dialogues.jsonl`. `dup-v1` is: NFKC, casefold,
replace every non-alphanumeric run with one space, then strip. The train side is one `set` of
normalized utterances from all three variants of every train item (about 64k strings). Rule
levels for FR10 come from `auto-v1`.

**Scoring integration.** A small shared loader,
`load_test_audit(path, items_sha, dialogues_sha, registry_sha) -> {example_id: (primary, dup_exact)}`,
raises on any mismatch. Stage 1 (`src/evaluation/stage1.py`) and Stage 2
(`src/evaluation/stage2.py`; `transfer.py` is untouched) call it when `split == "test"`. They drop
non-primary examples before forming contrasts and add one `primary_minus_dup` block per contrast
next to the existing minus-cue-donor block, never crossed with it. Dev paths are untouched.

## Architecture

```
levels_round{1,3}.csv ─┐
round3_items.csv (pin) ─┼─ register ─► inspected_test_dialogues.csv (committed) ◄── scan ── sheets in data/interim/**, data/annotations/
fact_drift.jsonl (pin) ─┤      ▲                     │
transcripts ── scan --transcripts (IDs only) ─┘      │   freeze date (WP-08) ─► phase gate
items.jsonl, dialogues.jsonl, *ListFile.txt ─────────┼─ check (exit 0/1, counts, needs_decision)
contexts_test.csv (spec 004, committed) ─────────────┴─ audit ─► split_audit_test.csv + _summary.json (committed)
                                                                    │
                                     stage1 / stage2 test scoring ── load_test_audit ── primary + uncrossed sensitivities
```

- `src/data/split_audit.py`: registry schema and validation, source table, `canonical_dialogue_id`,
  register, scan, transcript scan, check, `dup-v1`, audit.
- `src/evaluation/test_audit.py`: `load_test_audit` (small, shared by both scorers).
- `tests/test_split_audit.py`, `tests/test_test_audit.py`, and additions to `test_stage1.py` and
  `test_stage2_cli.py`.
- Docs: `docs/analysis_plan.md` (exclusion, near-duplicate, phase and LLM-judge-sample policies),
  the module docstring, the roadmap, and a `decisions.md` entry.

**`scan` locations.** It reads CSVs under `data/interim/labeling/`, `data/interim/auto_levels/`,
`data/interim/context/`, `data/interim/literary/` and `data/annotations/`. A sheet must have a
column whose name contains `dialogue_id`, or an `item_id` resolvable through `items.jsonl`. Sheets
with neither (for example, a blind `sheet.csv` whose `key.csv` sibling holds the IDs) are resolved
through their key. Otherwise the scan fails. An `.xlsx` is accepted only if a sibling
`*_items.csv` with the same round prefix exists; otherwise the scan fails. Post-scoring sheets go
under `data/interim/error_audit/`, which is scanned against `post_scoring` rows.

## Alternatives Considered

- **Add an `excluded` column to spec 004's test manifest.** Rejected. It would change a committed
  freeze object and couple two concerns. A separate audit file that pins the manifest's hash keeps
  004 stable and makes the exclusion policy versionable on its own.
- **Hand-written exclusion list only (no `register`/`scan`).** Rejected. It is the status quo that
  missed 10 + 24 + 2 dialogues. Derivation plus scans makes omission a test failure, not a memory
  lapse.
- **Exclude at the item level (only inspected turns).** Rejected by FR-06/AC-04. The surrounding
  turns of an inspected dialogue were shown as context or are trivially recoverable.
- **One registry with no phase; post-scoring inspection simply not recorded.** Rejected (R1). The
  error audit is real inspection and must be disclosed. Without a phase, recording it would move
  the frozen primary set based on model errors.
- **Transcript hits reviewed by hand, one by one.** Rejected. Reviewing them means reopening the
  logged test text, which is itself inspection. Registering IDs conservatively costs about 11 items.
- **Fuzzy near-duplicates (MinHash/Jaccard) or delexicalized matching.** Deferred. Exact
  normalized match is transparent and cheap, and Sandy chose flag-only, so recall matters less
  than an explainable definition. It can be added later as `dup-v2` without changing the primary set.
- **Re-pair donors away from inspected dialogues.** Rejected by Sandy on 2026-10-19. It reopens
  spec 004's render/manifest version just before the freeze.

## Tradeoffs

- **Conservative exclusion.** About 180 items (fact-drift plus session hits) are dropped on
  uncertainty, not evidence of inspection. That costs about 2.5% of test, and in return the
  untouched claim needs no caveat.
- **Local-only sources.** Derived rows for the obsolete sheet and fact-drift can't be regenerated
  on a fresh clone. The committed registry is authoritative there, which is a deliberate
  asymmetry, documented in the module.
- **The transcript scan is a lower bound.** It finds only IDs that were printed. Text shown
  without its ID (for example, an utterance quoted from a fact-drift sample) is caught only by the
  fact-drift rule. The scan can't see sessions whose logs were deleted. The paper states the
  registry's basis.
- **Exact-match dup flag** undercounts paraphrase-level overlap, so the sensitivity line is a lower
  bound on memorization effects. The paper says so.
- **Scorer coupling.** Test scoring now hard-requires the audit file and cross-OS-identical input
  hashes. That is one more precondition, and it is the point: an unaudited test score can't be
  produced by accident.

## Risks

- **Cross-split duplicate dialogues exceed 1%.** `needs_decision` stops the freeze, not the tool.
  Mitigation: measured in the smoke check before the scoring changes land.
- **Example ID drift between 004's manifest and the audit.** Mitigation: the audit reuses 004's
  set builders and asserts that its example IDs equal the committed manifest's IDs exactly.
- **`items.jsonl` hashes differ on WSL or the lab machine.** That would block Sandy's test scoring
  there. Mitigation: Sandy runs `audit --verify` once in WSL before the freeze (AC-006-11). A
  difference is fixed in the build.
- **Future sessions keep printing test IDs.** Each one would add an exclusion at the next
  transcript scan. Mitigation: the working rule in the spec. The transcript scan is run once,
  immediately before the freeze, and later hits are `post_scoring`.
- **A new sheet format `scan` can't parse.** Mitigation: `scan` fails on it rather than skipping it.
- **Text leakage into committed files or logs.** Mitigation: a test plants sentinel text in
  fixtures and transcripts and asserts it's absent from every output and from captured logs.
