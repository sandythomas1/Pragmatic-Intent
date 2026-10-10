# Plan 002: Literary source registration and screening inventory

## Approach

Reuse the existing pinned downloader unchanged. Literary editions are just two more manifest
entries plus one allowlisted host. Add a small `src/literary/` package:

1. `sources.py`: pure parsing. Pinned bytes → decoded text → `Unit` records with offsets. One
   function per edition format (`parse_aesop`, `parse_kjv`) behind a registry keyed by source name.
   It also provides helpers for episodes and whitespace-insensitive span resolution.
2. `screening.py`: the CLI (`families draw|assign`, `propose`, `export`, `validate`) and the
   record I/O. It follows the `src/annotation/levels.py` pattern: argparse subcommands, CSV with
   BOM for Excel, local text-bearing files under `data/interim/`, and committed text-free files
   under `data/annotations/`.

Offsets index into the decoded file with CRLF intact. That way `text[start:end]` reproduces the
source byte-for-byte after encoding, and nothing depends on a normalization step that could
silently change.

## Architecture

```
data/sources.toml ──(existing downloader)──► data/raw/<source>/pg*.txt   (ignored)
        │ sha256 pin                                  │
        ▼                                             ▼
src/literary/sources.py  load_units(source) ── verify hash ── parse_<format>() ──► [Unit]
        │
src/literary/screening.py
  families draw/assign ─► data/annotations/literary_families.csv           (committed)
  propose ──────────────► data/interim/literary/proposals.jsonl             (machine, ignored)
                         data/interim/literary/screening_sheet.csv          (human, ignored)
  export  (sheet + sidecar + units) ─► data/annotations/literary_screening.csv (committed)
  validate (raw + committed CSVs) ─► report / exit code
```

Specs 004 (rendering) and 003 (annotation) will consume `Unit`, the families file and the
screening log. They never read the sheet.

## Alternatives Considered

- **Commit public-domain text directly** (both editions are PD in the US). Rejected for
  consistency. One rule ("committed files are text-free") is easier to audit than per-source
  exceptions, and it keeps the release decision (FR-14) separate.
- **Line/character offsets into normalized LF text.** Rejected. It adds a normalization step
  whose exact behavior becomes part of the locator contract. Raw decoded offsets are simpler.
- **Screener edits offsets directly.** Rejected as error-prone. Screeners copy the exact words
  instead, and export resolves them uniquely within the episode or fails loudly.
- **Proposing only "promising" quotes**, using keywords or an LLM. Rejected. It's selection on a
  proxy for difficulty, and LLM filtering is circular (research-direction memory). Exhaustive
  enumeration within randomly drawn families keeps selection independent of models.
- **Chapter = family for the KJV automatically.** Kept as the default episode, but families are
  explicit so parallel or multi-chapter accounts can be grouped by a human.
- **A generic plain-text/EPUB parser.** YAGNI. Two formats, two small functions, and a registry
  for the next one.

## Tradeoffs

- Hash pinning against Gutenberg's live cache means an upstream regeneration breaks a fresh
  download. We accept that, because integrity matters more than convenience. The local copy
  remains valid, and `--verify-only` works offline.
- Heuristic quote merging may mis-split rare speech patterns. The screener's `target_text`
  overrides it, so heuristic errors cost screening time, not correctness.
- KJV proposals are whole verses (KJV has no quotation marks), so the screener trims them.
  That's more manual work, but it avoids a fragile speech-boundary parser for archaic syntax.
- Families are single episodes by default. Retellings across sources are grouped only by
  explicit `assign`, and that relies on the screener noticing them. The validator can't detect
  cross-edition retellings.

## Risks

- **Upstream file change**: covered by the hash check and a backup of the local copy. A migration
  is out of scope.
- **Sheet mangled by Excel** (encoding, leading zeros, formula cells): BOM UTF-8, text-only
  columns and formula-prefix escaping. Export validates every row, and unknown IDs are fatal.
- **Silent offset drift if the parser changes later**: `validate` re-hashes every target against
  the raw file, so any drift shows up as a hash mismatch.
- **Moral leakage**: morals are a distinct unit kind. Spec 004's renderer must exclude them, and
  this spec's validator blocks included moral targets.
