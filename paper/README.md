# Paper (FR-12)

NeurIPS 2026 style (`neurips_2026.sty`, `preprint` option) draft of the study. Every number in
the results comes from a generated fragment, not hand-typed text, so a rerun of the analysis
flows into the paper without edits.

| Path | What it is | Edit by hand? |
|---|---|---|
| `main.tex` | The paper | Yes |
| `references.bib` | Bibliography; surname-only entries still need first names | Yes |
| `generated/*.tex` | Tables and `\newcommand` number macros, each with a provenance header | No — regenerate |
| `figures/context_by_level.{pdf,svg}` | Figure 1 | No — regenerate |
| `neurips_2026.sty` | Official style file, unmodified | No |

Hand-typed data-description counts (test size, exclusions, rule agreement, truncation) cite their
source in a footnote or inline: `results/analysis/test/report.json` and
`data/manifests/split_audit_test_summary.json`.

## Rebuild

Run from the repository root.

1. **Tables and macros** (stdlib only):

   ```
   python -m src.analysis.paper_tables --tables results/analysis/test --out paper/generated
   ```

   A missing or duplicated input row fails by name, with no partial output.

2. **Figure** (needs the `figures` uv group for matplotlib):

   ```
   uv run --group figures python -m src.analysis.figures --data results/analysis/test/figure_data.csv --out paper/figures/context_by_level
   ```

3. **PDF.** On MiKTeX `latexmk` needs Perl, which is not installed here, so run the four steps
   yourself from `paper/`:

   ```
   pdflatex main.tex
   bibtex main
   pdflatex main.tex
   pdflatex main.tex
   ```

   With Perl installed, `latexmk -pdf main.tex` does the same thing. Build artefacts, including
   `main.pdf`, are ignored by git.

## Before submission

- Search `main.tex` for `\todo` (shown in red): affiliation, the error-audit section and the
  acknowledgements.
- Complete the surname-only entries in `references.bib` from the publisher's record.
- The `preprint` option prints the author block. For an anonymous submission, drop the option.
