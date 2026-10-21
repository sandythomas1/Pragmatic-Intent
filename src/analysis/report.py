"""Analysis report, paper tables and figure data (FR19–FR22).

The JSON report carries a stamp, provenance, deterministic content, and rules for where outputs
may go.

A dev run is stamped ``dev_diagnostic_not_a_finding`` and writes only under
``outputs/analysis/dev/``. A test run is stamped ``frozen_test``. Its full JSON stays git-ignored
under ``outputs/analysis/test/``, and its text-free tables go to committed
``results/analysis/test/``. Outputs are byte-identical for the same inputs: sorted keys, LF,
and no clock fields. No output path may be an input path.

**Tables.** Each is written as CSV and Markdown. Every row names its denominators (examples and
dialogues) and points at the report's provenance block. CSV cells that a spreadsheet would run
as a formula are escaped. Committed tables are refused if anything resembling a dialogue ID
appears. The IndirectRequests transfer table is its own file, labelled LLM-generated and never
pooled.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from src.analysis.config import AnalysisConfig
from src.analysis.files import AnalysisError, parse_json
from src.evaluation.transfer import SCORER_VERSION as TRANSFER_SCORER

STAMPS = {"dev": "dev_diagnostic_not_a_finding", "test": "frozen_test"}
REPORT_NAME = "report.json"


def output_locations(root: Path, split: str) -> tuple[Path, Path]:
    """(directory for the full JSON report, directory for the tables and figure data)."""
    report_dir = root / "outputs" / "analysis" / split
    return report_dir, (root / "results" / "analysis" / "test" if split == "test" else report_dir)


def check_outputs(outputs: Iterable[Path], inputs: Iterable[Path]) -> None:
    taken = {path.resolve() for path in inputs}
    for path in outputs:
        if path.resolve() in taken:
            raise AnalysisError("output_is_input", f"{path.name} is also an input; refusing to overwrite it")


def config_summary(config: AnalysisConfig) -> dict[str, Any]:
    primary = config.primary
    return {"version": config.version, "sha256": config.sha256, "draft": config.draft,
            "rules_version": config.rules_version, "alpha": config.alpha,
            "bootstrap": {"unit": "dialogue", "samples": config.bootstrap.samples, "seed": config.bootstrap.seed,
                          "confidence": config.bootstrap.confidence, "shared": True},
            "cells": {"min_dialogues": config.cells.min_dialogues,
                      "max_excluded_share": config.cells.max_excluded_share},
            "primary": {"system": primary.system, "endpoint": primary.endpoint, "contrast": primary.contrast,
                        "trend": primary.trend, "levels": list(primary.levels), "weights": list(primary.weights)},
            "exploratory_levels": list(config.exploratory_levels),
            "panel": [{"name": s.name, "family": s.family, "design": s.design, "streams": list(s.streams)}
                      for s in config.panel]}


def assemble(body: Mapping[str, Any], *, split: str, config: AnalysisConfig,
             provenance: Mapping[str, Any]) -> dict[str, Any]:
    return {"stamp": STAMPS[split], "split": split, "config": config_summary(config),
            "provenance": dict(provenance), **body}


def json_bytes(data: Any) -> bytes:
    return (json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------------------- tables (T10)

STAT_COLUMNS = ("point", "ci_low", "ci_high", "p", "p_holm", "examples", "dialogues", "status")
BOOTSTRAP_NOTE = ("Intervals: 95% percentile, one shared dialogue bootstrap for every statistic of the run; "
                  "slice intervals therefore differ from the per-run by_rule_level intervals, which resample only "
                  "each slice's dialogues. Rates are seed-averaged per example before resampling. For a contrast, "
                  "examples and dialogues give its smallest cell.")
TRANSFER_LABEL = "LLM-generated (IndirectRequests); never pooled with the human-authored benchmark"
_FORMULA_LEADS = ("=", "+", "-", "@", "\t", "\r")
_ID_PATTERN = re.compile(r"(?<![A-Za-z0-9])(?:PMUL|MUL|SNG|SSNG|WOZ)[0-9]{4,5}(?![0-9])")

# name -> (title, report path, identifying columns)
TABLES: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    "h1_rates": ("H1: success by condition and level", ("h1", "rates"),
                 ("system", "line", "endpoint", "condition", "level")),
    "h1_trends": ("H1: L0–L2 linear trend of success", ("h1", "trends"),
                  ("system", "line", "endpoint", "condition", "trend", "levels")),
    "h2_benefits": ("H2: context benefit by level", ("h2", "benefits"),
                    ("system", "line", "endpoint", "contrast", "level")),
    "h2_trends": ("H2: benefit trends and level − L0 differences", ("h2", "trends"),
                  ("system", "line", "endpoint", "contrast", "trend", "levels")),
    "mismatch_controls": ("Corruption controls (test-time line, mismatch set)", ("mismatch_controls",),
                          ("system", "line", "endpoint", "contrast", "level")),
    "h3_tested": ("H3: benefit difference against the primary system (test-time lines)", ("h3", "tested"),
                  ("system", "reference", "line", "endpoint", "contrast", "level")),
    "h3_descriptive": ("H3 (descriptive): primary lines; design differs across families", ("h3", "descriptive"),
                       ("system", "reference", "line", "endpoint", "contrast", "level", "caption")),
    "h4_rates": ("H4: detection, oracle and routed success on identical gold indirect examples", ("h4", "rates"),
                 ("system", "line", "condition", "level", "measure")),
    "h4_contrasts": ("H4: drop(detection) − drop(oracle) under full", ("h4", "contrasts"),
                     ("system", "line", "condition", "definition")),
    "h5_rates": ("H5 (exploratory): success by intent category", ("h5", "rates"),
                 ("system", "line", "endpoint", "category", "condition")),
    "h5_benefits": ("H5 (exploratory): context benefit by intent category", ("h5", "benefits"),
                    ("system", "line", "endpoint", "category", "contrast")),
    "h5_standardized": ("H5 sensitivity: intent-standardized H2 line", ("h5", "standardized"),
                        ("system", "line", "endpoint", "level", "kind")),
    "holm": ("Secondary family (Holm-adjusted)", ("holm", "members"),
             ("name", "kind", "system", "reference", "endpoint", "contrast", "condition")),
    "sensitivity": ("Sensitivity lines (each alone, never crossed)", ("sensitivity",),
                    ("system", "line", "endpoint", "contrast", "statistic", "sensitivity")),
}


def escape_cell(value: Any) -> str:
    """One CSV cell. Text that a spreadsheet would run as a formula gets a leading quote; numbers never do."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (list, tuple)):
        if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value):
            return "; ".join(repr(v) for v in value)  # numbers only: nothing a spreadsheet would run
        value = "; ".join(str(v) for v in value)
    text = str(value)
    return "'" + text if text.startswith(_FORMULA_LEADS) else text


def flatten(row: Mapping[str, Any], columns: Sequence[str]) -> dict[str, Any]:
    ci = row.get("ci") or (None, None)
    values = {**row, "ci_low": ci[0], "ci_high": ci[1]}
    return {column: values.get(column) for column in columns}


def csv_bytes(columns: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([escape_cell(row.get(column)) for column in columns])
    return buffer.getvalue().encode("utf-8")


def markdown_bytes(title: str, columns: Sequence[str], rows: Iterable[Mapping[str, Any]], notes: Sequence[str]) -> bytes:
    def shown(value: Any) -> str:
        if isinstance(value, float):
            return f"{value:.3f}"
        return escape_cell(value).replace("|", "\\|")

    lines = [f"# {title}", "", *[f"> {note}" for note in notes], "", "| " + " | ".join(columns) + " |",
             "|" + "---|" * len(columns)]
    lines += ["| " + " | ".join(shown(row.get(column)) for column in columns) + " |" for row in rows]
    return ("\n".join(lines) + "\n").encode("utf-8")


def tables(report: Mapping[str, Any], transfer: Sequence[Mapping[str, Any]]) -> dict[str, tuple[str, Sequence[str], list[dict[str, Any]], list[str]]]:
    """Every table as (title, columns, rows, notes); rows carry denominators and a provenance reference."""
    stamp = report["stamp"]
    reference = f"report.json#provenance (config {report['config']['sha256'][:12]})"
    base_notes = [f"Stamp: {stamp}. Rows hold aggregates only; provenance: {reference}.", BOOTSTRAP_NOTE]
    out: dict[str, tuple[str, Sequence[str], list[dict[str, Any]], list[str]]] = {}
    out["primary_test"] = _primary_table(report, reference, base_notes)
    for name, (title, path, ids) in TABLES.items():
        rows: Any = report
        for key in path:
            rows = rows[key]
        columns = (*ids, *STAT_COLUMNS, "provenance")
        out[name] = (title, columns, [{**flatten(row, columns), "provenance": reference} for row in rows], base_notes)
    out["h2_labels"] = ("H2: main effects without an interaction (AC-09)", ("system", "line", "endpoint", "contrast", "label"),
                        list(report["h2"]["labels"]), base_notes)
    out["h5_exclusions"] = ("H5: categories excluded from the standardized line",
                            ("system", "endpoint", "included", "excluded", "excluded_share"),
                            list(report["h5"]["exclusions"]), base_notes)
    out["seed_variation"] = ("Seed variation (reported separately; seeds are never extra items)",
                             ("system", "line", "endpoint", "metric", "n_seeds", "mean", "sd", "min", "max", "per_seed"),
                             [{**row, "per_seed": [f"{s}={v!r}" for s, v in row["per_seed"].items()]}
                              for row in report["seed_variation"]], base_notes)
    out["status"] = ("Systems not run, and sparse, unstable or empty statistics",
                     ("table", "system", "detail", "status"), _status_rows(out, report), base_notes)
    if "precision" in report:
        out["precision"] = ("Dev precision report (D-07 evidence; not a finding)",
                            ("system", "line", "endpoint", "configured_primary", "point", "ci_low", "ci_high",
                             "half_width", "second_seed_ci", "monte_carlo_max_difference", "monte_carlo_ok"),
                            [{**row, "point": row["estimate"]["point"], "ci_low": (row["estimate"]["ci"] or [None])[0],
                              "ci_high": (row["estimate"]["ci"] or [None, None])[1],
                              "second_seed_ci": row["second_seed"]["ci"]} for row in report["precision"]], base_notes)
    out["figure_data"] = ("Figure data: full − none benefit by level", FIGURE_COLUMNS, figure_rows(report), base_notes)
    if transfer:
        out["transfer"] = ("Transfer: IndirectRequests (separate table)", TRANSFER_COLUMNS, list(transfer),
                           [TRANSFER_LABEL, f"Provenance: {reference}."])
    return out


FIGURE_COLUMNS = ("system", "line", "endpoint", "contrast", "level", "point", "ci_low", "ci_high", "examples",
                  "dialogues", "status")
TRANSFER_COLUMNS = ("system", "model_family", "gpt_family", "split", "n", "request_recall", "value_accuracy",
                    "end_to_end", "invalid_outputs", "data_kind", "label")


def figure_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    contrast = report["config"]["primary"]["contrast"]
    return [flatten(row, FIGURE_COLUMNS) for row in report["h2"]["benefits"]
            if row["contrast"] == contrast and row["level"] != "overall"]


def _primary_table(report: Mapping[str, Any], reference: str, notes: list[str]):
    primary = report["primary_test"]
    levels = primary["levels"]
    label = f"{levels[-1]} − {levels[0]} benefit difference ({primary['trend']} contrast)"
    columns = ("label", "system", "line", "endpoint", "contrast", "weights", "status", "point", "ci_low", "ci_high",
               "p", "decision", "quadratic_point", "quadratic_ci_low", "quadratic_ci_high", "examples", "dialogues",
               "provenance")
    row: dict[str, Any] = {"label": label, **{k: primary.get(k) for k in ("system", "line", "endpoint", "contrast",
                                                                         "weights", "status", "decision")},
                           "provenance": reference}
    if primary["status"] == "ok":
        estimate, quadratic = primary["estimate"], primary["quadratic"]
        row.update(point=estimate["point"], ci_low=estimate["ci"][0], ci_high=estimate["ci"][1], p=estimate["p"],
                   examples=estimate["examples"], dialogues=estimate["dialogues"], quadratic_point=quadratic["point"],
                   quadratic_ci_low=(quadratic["ci"] or [None])[0], quadratic_ci_high=(quadratic["ci"] or [None, None])[1])
    return ("Primary test (confirmatory H2)", columns, [row],
            [*notes, "The linear contrast weights L0 −1, L1 0, L2 +1: it is the L2 − L0 benefit difference; "
                     "the quadratic contrast is descriptive."])


def _status_rows(out: Mapping[str, Any], report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = [{"table": "systems", "system": name, "detail": "", "status": "not_run"}
            for name, status in sorted(report["systems"].items()) if status == "not_run"]
    for name, (_, columns, table_rows, _) in out.items():
        for row in table_rows:
            if row.get("status") in ("sparse", "unstable", "empty", "untestable"):
                detail = ", ".join(str(row.get(c)) for c in columns[:6] if c not in ("system", "status")
                                   and c in row and row.get(c) is not None and c not in STAT_COLUMNS)
                rows.append({"table": name, "system": row.get("system"), "detail": detail, "status": row["status"]})
    return rows


def transfer_rows(reports: Mapping[str, bytes]) -> list[dict[str, Any]]:
    """Spec 005 transfer reports by system; anything but a ``transfer-v1`` report is rejected (FR19)."""
    rows = []
    for system, data in sorted(reports.items()):
        report = parse_json(data, f"{system} transfer report")
        if not isinstance(report, dict) or report.get("scorer_version") != TRANSFER_SCORER \
                or report.get("data_kind") != "llm_generated_transfer":
            raise AnalysisError("not_a_transfer_report", f"{system}: the transfer input is not a {TRANSFER_SCORER} report")
        row = {"system": system, "label": TRANSFER_LABEL, **{k: report.get(k) for k in TRANSFER_COLUMNS[1:-1]}}
        if not isinstance(row["gpt_family"], bool) or not isinstance(row["n"], int):
            raise AnalysisError("not_a_transfer_report", f"{system}: the transfer report lacks gpt_family or n")
        row["model_family"] = str(row["model_family"])[:80]
        rows.append(row)
    return rows


def write_tables(tables_dir: Path, built: Mapping[str, tuple[str, Sequence[str], list[dict[str, Any]], list[str]]],
                 *, committed: bool) -> list[Path]:
    """CSV and Markdown per table. Committed tables are checked for anything that looks like an ID."""
    written = []
    for name, (title, columns, rows, notes) in sorted(built.items()):
        for path, data in ((tables_dir / f"{name}.csv", csv_bytes(columns, rows)),
                           (tables_dir / f"{name}.md", markdown_bytes(title, columns, rows, notes))):
            if committed and _ID_PATTERN.search(data.decode("utf-8")):
                raise AnalysisError("id_in_table", f"{path.name} would carry a dialogue ID; refusing to write it")
            write_atomic(path, data)
            written.append(path)
    return written


def table_paths(tables_dir: Path, names: Iterable[str]) -> list[Path]:
    return [tables_dir / f"{name}.{suffix}" for name in names for suffix in ("csv", "md")]
