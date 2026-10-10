# Tasks: Spec 002

## T1: Pin the two Gutenberg editions
- Description: Add `www.gutenberg.org` to `allowed_hosts`, and add `aesop_jones1912` and `kjv_pg10`
  to `data/sources.toml` with size and SHA-256 from the 2026-10-10 retrieval. Document their
  roles, rights and the re-pin policy in `docs/data_sources.md`.
- Files likely touched: data/sources.toml, docs/data_sources.md, tests/test_download_sources.py
- Depends on: none
- Security-sensitive: yes. It extends the download host allowlist.
- Acceptance criteria:
  - The real manifest parses, and both sources are listed with https URLs on the allowlisted host (test).
  - `download_sources --only aesop_jones1912 kjv_pg10` then `--verify-only` passes (smoke, AC-002-1).
- Status: done

## T2: Segment pinned editions into located units
- Description: `src/literary/sources.py` with `Unit`, `parse_aesop`, `parse_kjv`, a source
  registry, `load_units` (hash-verified against the manifest), episode helpers and
  whitespace-insensitive unique span resolution.
- Files likely touched: src/literary/__init__.py, src/literary/sources.py, tests/test_literary_sources.py
- Depends on: T1
- Security-sensitive: no. It's a pure parser over pinned, hash-verified files.
- Acceptance criteria:
  - The fixture tests in AC-002-3 pass, and `text[start:end]` equals the unit text for every unit.
  - A corrupted file is refused before parsing (AC-002-1).
  - The real-file smoke check gives 284 fables, 66 books and John 2:3 (AC-002-2).
- Status: done

## T3: Family assignment (dev pilot groups)
- Description: The `families draw|assign` subcommands and the committed
  `literary_families.csv` read/write/validation.
- Files likely touched: src/literary/screening.py, tests/test_literary_screening.py
- Depends on: T2
- Security-sensitive: no. Local CLI arguments are validated, and the file is written to a fixed directory.
- Acceptance criteria:
  - AC-002-4: draws are deterministic and never repeat an assigned episode, and an oversize count is rejected.
  - Unknown episodes, non-dev splits and duplicate family IDs are rejected.
- Status: done

## T4: Mechanical candidate proposal and screening sheet
- Description: The `propose` subcommand: Aesop quote enumeration with interrupted-speech merging,
  KJV speech-verb verses, stable IDs, the append-only sheet and sidecar, and the
  formula-escape-on-write rule.
- Files likely touched: src/literary/screening.py, tests/test_literary_screening.py
- Depends on: T3
- Security-sensitive: yes. The sheet will be human-edited and opened in Excel (formula injection).
- Acceptance criteria:
  - AC-002-5: re-running adds no duplicate rows and preserves edits, and interrupted speech forms one candidate.
  - Cells beginning with `= + - @` are escaped.
- Status: done

## T5: Export and validate the committed screening log
- Description: The `export` and `validate` subcommands: sheet parsing (untrusted), target
  resolution, manual additions, the text-free committed log and full re-derivation checks.
- Files likely touched: src/literary/screening.py, tests/test_literary_screening.py
- Depends on: T4
- Security-sensitive: yes. It parses untrusted human-edited input into committed data.
- Acceptance criteria:
  - AC-002-5b, AC-002-6, AC-002-7, AC-002-8 and AC-002-9.
- Status: done

## T6: Documentation, real-source smoke run and roadmap update
- Description: Usage docs in `docs/source_collection_plan.md` and `README.md`. Run the full CLI
  flow against the real files in a scratch directory (no committed screening yet: that's Sandy's
  pilot). Update the roadmap. Run the full suite on Windows (AC-002-10).
- Files likely touched: docs/source_collection_plan.md, README.md, specs/001-pragmatic-intent-study/roadmap.md
- Depends on: T5
- Security-sensitive: no
- Acceptance criteria:
  - The smoke run's validate passes on real files. The suite passes on native Windows Python 3.12.
- Status: done
