"""Context-by-level figure from the analysis's figure data (spec 007 T11).

Run from the repository root (needs the ``figures`` uv group: ``uv run --group figures ...``)::

    python -m src.analysis.figures --data outputs/analysis/dev/figure_data.csv \\
        --out outputs/analysis/dev/figures/context_by_level

The figure shows small multiples: one panel per system and line, all on one shared y-scale. Each
panel plots the full − none benefit by rule level with its 95% interval, and a zero reference
line marks "no benefit".

**Encoding.** Endpoints use the reference palette's categorical slots 1–3 in fixed order, plus
a distinct marker shape and a legend entry, so identity never rests on colour alone. Sparse,
unstable or empty statistics are drawn hollow and named in the legend.

**Determinism.** Output is deterministic: a fixed ``svg.hashsalt``, text kept as text, and no date
metadata. Only this script depends on matplotlib; the analysis itself stays stdlib-only.
"""

from __future__ import annotations

import argparse
import csv
import io
import math
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from src.analysis.files import AnalysisError, read_bounded
from src.analysis.report import FIGURE_COLUMNS

MAX_FIGURE_DATA_BYTES = 16 << 20
LEVEL_ORDER = ("L0", "L1", "L2", "L3", "INF", "NR")
# Reference palette, light surface: categorical slots 1-3, never cycled; text and grid in ink tokens.
SERIES = {"request_interpretation": ("#2a78d6", "o"), "type_exact": ("#eb6834", "s"), "stage1_correct": ("#1baf7a", "^")}
SURFACE, TEXT_PRIMARY, TEXT_SECONDARY, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
ENDPOINT_LABELS = {"request_interpretation": "request + interpretation (primary)",
                   "type_exact": "type-exact (spec 005)", "stage1_correct": "detection (Stage 1)"}
_NUMERIC = ("point", "ci_low", "ci_high")


def read_figure_data(path: Path) -> list[dict[str, Any]]:
    """Rows of the T10 figure data, with numbers parsed; a malformed file fails with a named error."""
    try:
        text = read_bounded(path, MAX_FIGURE_DATA_BYTES).decode("utf-8")
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        missing = [c for c in FIGURE_COLUMNS if c not in (reader.fieldnames or ())]
        if missing:
            raise AnalysisError("missing_column", f"{path.name} lacks {missing}")
        raw_rows = list(reader)
    except (UnicodeDecodeError, csv.Error):
        raise AnalysisError("invalid_csv", f"{path.name} is not UTF-8 CSV") from None
    rows = []
    for line, raw in enumerate(raw_rows, start=2):
        row: dict[str, Any] = dict(raw)
        if row["level"] not in LEVEL_ORDER or row["endpoint"] not in SERIES:
            raise AnalysisError("unknown_value", f"{path.name} line {line}: unknown level or endpoint")
        for column in _NUMERIC:
            row[column] = _number(raw[column], f"{path.name} line {line} {column}")
        if (row["point"] is None) != (row["ci_low"] is None) or (row["ci_low"] is None) != (row["ci_high"] is None):
            raise AnalysisError("bad_number", f"{path.name} line {line}: point and interval must be given together")
        rows.append(row)
    return rows


def _number(value: str, where: str) -> float | None:
    if value == "":
        return None
    try:
        number = float(value)
    except ValueError:
        raise AnalysisError("bad_number", f"{where} is not a number") from None
    if not math.isfinite(number):
        raise AnalysisError("bad_number", f"{where} is not finite")
    return number


def render(rows: Sequence[dict[str, Any]], out: Path) -> list[Path]:
    """Write ``out``.svg and ``out``.pdf; returns the paths."""
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    matplotlib.rcParams.update({"svg.hashsalt": "pragmatic-intent-figure", "svg.fonttype": "none",
                                "font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": GRID,
                                "axes.labelcolor": TEXT_SECONDARY, "xtick.color": TEXT_SECONDARY,
                                "ytick.color": TEXT_SECONDARY, "pdf.fonttype": 42})
    panels = sorted({(row["system"], row["line"]) for row in rows})
    if not panels:
        raise AnalysisError("no_data", "the figure data has no rows")
    columns = min(3, len(panels))
    grid_rows = math.ceil(len(panels) / columns)
    figure, axes = plt.subplots(grid_rows, columns, figsize=(3.2 * columns, 2.6 * grid_rows), sharey=True,
                                squeeze=False, facecolor=SURFACE)
    endpoints = [e for e in SERIES if any(row["endpoint"] == e for row in rows)]
    for axis, (system, line) in zip(axes.flat, panels):
        present = [e for e in endpoints if any((r["system"], r["line"], r["endpoint"]) == (system, line, e) for r in rows)]
        offsets = {e: (i - (len(present) - 1) / 2) * 0.18 for i, e in enumerate(present)}  # centred per panel
        axis.set_facecolor(SURFACE)
        axis.axhline(0, color=TEXT_SECONDARY, linewidth=0.8, zorder=1)
        axis.grid(axis="y", color=GRID, linewidth=0.6, zorder=0)
        axis.set_axisbelow(True)
        levels = [lv for lv in LEVEL_ORDER if any(r["level"] == lv and (r["system"], r["line"]) == (system, line)
                                                   for r in rows)]
        for endpoint in present:
            color, marker = SERIES[endpoint]
            for row in rows:
                if (row["system"], row["line"], row["endpoint"]) != (system, line, endpoint) or row["point"] is None:
                    continue
                x = levels.index(row["level"]) + offsets[endpoint]
                hollow = row["status"] != "ok"
                axis.errorbar([x], [row["point"]], yerr=[[row["point"] - row["ci_low"]], [row["ci_high"] - row["point"]]],
                              fmt=marker, color=color, markersize=6, linewidth=1.5, capsize=0,
                              markerfacecolor=SURFACE if hollow else color, markeredgewidth=1.5, zorder=3)
        axis.set_xticks(range(len(levels)), levels)
        axis.set_title(f"{system} · {line.replace('_', '-')}", color=TEXT_PRIMARY, fontsize=9, loc="left")
        for side in ("top", "right"):
            axis.spines[side].set_visible(False)
    for axis in list(axes.flat)[len(panels):]:
        axis.set_visible(False)
    for axis in axes[:, 0]:
        axis.set_ylabel("full − none benefit (95% CI)")
    handles = [plt.Line2D([], [], color=SERIES[e][0], marker=SERIES[e][1], linestyle="", markersize=6,
                          label=ENDPOINT_LABELS[e]) for e in endpoints]
    handles.append(plt.Line2D([], [], color=TEXT_SECONDARY, marker="o", linestyle="", markersize=6,
                              markerfacecolor=SURFACE, label="sparse / unstable (not tested)"))
    figure.legend(handles=handles, loc="upper center", ncol=len(handles), frameon=False, fontsize=8,
                  labelcolor=TEXT_PRIMARY, bbox_to_anchor=(0.5, 1.02))
    figure.tight_layout(rect=(0, 0, 1, 0.94))
    out.parent.mkdir(parents=True, exist_ok=True)
    paths = [out.with_suffix(".svg"), out.with_suffix(".pdf")]
    figure.savefig(paths[0], format="svg", metadata={"Date": None}, facecolor=SURFACE)
    figure.savefig(paths[1], format="pdf", metadata={"CreationDate": None, "ModDate": None}, facecolor=SURFACE)
    plt.close(figure)
    return paths


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, required=True, help="figure_data.csv written by the analysis")
    parser.add_argument("--out", type=Path, required=True, help="output stem; .svg and .pdf are written")
    args = parser.parse_args(argv)
    try:
        if args.out.with_suffix(".csv").resolve() == args.data.resolve():
            raise AnalysisError("output_is_input", "the output stem would overwrite the figure data")
        paths = render(read_figure_data(args.data), args.out)
    except ImportError:
        print("Figure failed: matplotlib is missing; run with the uv 'figures' group", file=sys.stderr)
        return 1
    except (AnalysisError, OSError) as error:
        print(f"Figure failed: {error}", file=sys.stderr)
        return 1
    print("figure -> " + ", ".join(p.as_posix() for p in paths))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
