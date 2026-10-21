"""Post-scoring error audit: a seeded, stratified sample, registered before anyone reads it (FR23–FR26).

Spec 001 §13's error audit is human inspection of test outputs, so it must neither be
cherry-picked nor move the frozen test set. Each subcommand enforces part of that.

``sample`` runs only after the frozen test analysis. In order, it:

- **gates:** requires the WP-08 freeze record (its date is the only date floor; there is no
  override), ``--on`` between that date and today, a human annotator ID, and the
  ``frozen_test`` report of the frozen config;
- **finds the errors:** recomputes the primary system's ``request_interpretation`` outcomes on
  its primary line under ``full`` (all checks of T3–T5 apply). An example is an error when its
  seed-averaged value is below 0.5;
- **draws the sample:** uniformly at random within each rule level, with the config's seed and
  quota, over sorted IDs. A short stratum is taken whole and never backfilled;
- **registers before writing:** every sampled dialogue is registered ``manual`` /
  ``error_audit`` / ``post_scoring`` in the spec 006 registry before the sheet exists.
  Registration and sheet are all-or-nothing, and ``post_scoring`` rows never move the audit's
  content hash or ``primary`` (spec 006).

The sheet (rendered input, prediction, gold acts, blank ``code`` and ``gold_questionable``)
lives only under git-ignored ``data/interim/error_audit/``. A summary beside it records the
design and a hash of every row's locked columns.

``export`` validates the filled sheet and writes the committed, text-free
``results/error_audit/codes.csv``. ``report`` counts codes by level and writes no IDs.

The console only ever shows counts and paths.
"""

from __future__ import annotations

import csv
import datetime
import hashlib
import io
import json
import os
import random
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.analysis.config import AnalysisConfig
from src.analysis.files import AnalysisError, parse_json, parse_jsonl, read_bounded, read_verified
from src.analysis.freeze import freeze_date, require_frozen_config
from src.analysis.inputs import AnalysisInputs
from src.analysis.outcomes import EvaluationSet, OutcomeTable
from src.analysis.report import escape_cell
from src.data import split_audit as sa
from src.data.contexts import render
from src.data.direct_dataset import Item, Turn

SHEET_DIR = Path("data/interim/error_audit")
SHEET_NAME = "error_audit_sheet.csv"
SUMMARY_NAME = "error_audit_sample.json"
CODES_PATH = Path("results/error_audit/codes.csv")
REPORT_STEM = Path("results/error_audit/summary")
ERROR_CODES = ("literal_reading", "wrong_intent_or_slot", "missed_cue", "unsupported_addition", "source_mismatch",
               "malformed_response", "routing_failure")
ENDPOINT, CONDITION, ERROR_BELOW = "request_interpretation", "full", 0.5
LOCKED_FIELDS = ("example_id", "dialogue_id", "level", "seed_shown", "context", "target", "predicted_type",
                 "predicted_category", "predicted_slots", "predicted_requested_slots", "predicted_paraphrase",
                 "invalid_output", "gold_acts")
EDITABLE_FIELDS = ("code", "gold_questionable")
SHEET_FIELDS = (*LOCKED_FIELDS, *EDITABLE_FIELDS)
CODES_FIELDS = ("example_id", "level", "code", "gold_questionable")
MAX_CELL_CHARS = 20_000
_ANNOTATOR_RE = re.compile(r"A[0-9]{1,3}")  # a human annotator; Claude never inspects test outputs
_FORMULA_LEADS = ("=", "+", "-", "@", "\t", "\r")


@dataclass(frozen=True)
class SampleGate:
    freeze_date: datetime.date
    on: datetime.date
    inspector: str
    report_sha256: str


def check_gate(*, freeze_path: Path, on: str, inspector: str, report_path: Path, config: AnalysisConfig,
               today: datetime.date) -> SampleGate:
    """FR23: every precondition, before anything is read from test outputs or written."""
    frozen = freeze_date(freeze_path)
    try:
        day = datetime.date.fromisoformat(on)
    except ValueError:
        day = None
    if day is None or day.isoformat() != on:
        raise AnalysisError("bad_date", "--on must be YYYY-MM-DD")
    if day < frozen:
        raise AnalysisError("before_freeze", f"--on {on} is before the freeze date {frozen.isoformat()}")
    if day > today:
        raise AnalysisError("future_date", f"--on {on} is after today")
    if _ANNOTATOR_RE.fullmatch(inspector) is None:
        raise AnalysisError("bad_inspector", "--inspector must be a pseudonymous annotator ID such as A1")
    require_frozen_config(freeze_path, config.sha256)
    if not report_path.is_file():
        raise AnalysisError("report_missing", f"{report_path} does not exist; run the frozen test analysis first")
    data = read_bounded(report_path, 256 << 20)
    report = parse_json(data, report_path.name)
    if not isinstance(report, dict) or report.get("stamp") != "frozen_test":
        raise AnalysisError("not_frozen_test", f"{report_path.name} is not a frozen_test analysis report")
    recorded = report.get("config", {}).get("sha256") if isinstance(report.get("config"), dict) else None
    if recorded != config.sha256:
        raise AnalysisError("report_config_mismatch", "the report was made under another analysis config")
    return SampleGate(frozen, day, inspector, hashlib.sha256(data).hexdigest())


def find_errors(table: OutcomeTable, config: AnalysisConfig) -> tuple[dict[str, float], dict[int, dict[str, float]], str]:
    """Seed-averaged ``request_interpretation`` under ``full`` on the primary line, and the per-seed values."""
    system = config.primary.system
    inputs = table.systems[system]
    if inputs.status == "not_run":
        raise AnalysisError("primary_not_run", f"the primary system {system} has no test outputs")
    line = inputs.primary_line
    per_seed = table.seed_values(system, line, CONDITION, ENDPOINT)
    averaged = table.average(system, line, CONDITION, ENDPOINT)
    return averaged, per_seed, line


def draw(errors: Sequence[str], levels: Mapping[str, str], config: AnalysisConfig) -> tuple[list[str], list[dict[str, Any]]]:
    """Seeded uniform draw within each level stratum, in config order; short strata are taken whole."""
    design = config.error_audit
    rng = random.Random(design.seed)
    sampled, strata = [], []
    for level in design.levels:
        pool = sorted(i for i in errors if levels.get(i) == level)
        chosen = sorted(rng.sample(pool, min(design.per_level, len(pool))))
        sampled.extend(chosen)
        strata.append({"level": level, "errors": len(pool), "quota": design.per_level, "drawn": len(chosen),
                       "shortfall": design.per_level - len(chosen)})
    return sampled, strata


def sheet_rows(sampled: Sequence[str], evaluation: EvaluationSet, per_seed: Mapping[int, Mapping[str, float]],
               routed_rows: Mapping[int, Mapping[str, Mapping[str, Any]]], items: Mapping[str, Item],
               dialogues: Mapping[str, list[Turn]]) -> list[dict[str, str]]:
    """One row per sampled example, showing the output of the lowest seed that got it wrong."""
    by_id = {e.example_id: e for e in evaluation.examples}
    rows = []
    for example_id in sampled:
        example = by_id[example_id]
        seed = min(s for s, values in per_seed.items() if values[example_id] < 1.0)
        output = routed_rows[seed][example_id]
        rendered = render(items[example.item_id], example.text, dialogues, CONDITION)
        invalid = bool(output.get("invalid"))
        row = {"example_id": example_id, "dialogue_id": example.dialogue_id,
               "level": evaluation.slices["rule_level"][example_id], "seed_shown": str(seed),
               "context": rendered.context if rendered else "", "target": rendered.target if rendered else example.text,
               "predicted_type": "" if invalid else output["prediction"],
               "predicted_category": "" if invalid else str(output["category"]),
               "predicted_slots": "" if invalid else json.dumps(output["slots"], sort_keys=True, ensure_ascii=False),
               "predicted_requested_slots": "" if invalid else "; ".join(output["requested_slots"]),
               "predicted_paraphrase": "" if invalid else output.get("paraphrase", ""),
               "invalid_output": "yes" if invalid else "no",
               "gold_acts": json.dumps(items[example.item_id].get("user_acts") or {}, sort_keys=True, ensure_ascii=False),
               "code": "", "gold_questionable": ""}
        rows.append({k: escape_cell(v) if k in LOCKED_FIELDS else v for k, v in row.items()})
    return rows


def locked_sha256(row: Mapping[str, str]) -> str:
    return hashlib.sha256(json.dumps([row[f] for f in LOCKED_FIELDS], ensure_ascii=False).encode("utf-8")).hexdigest()


def sheet_bytes(rows: Sequence[Mapping[str, str]], fields: Sequence[str] = SHEET_FIELDS) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(fields), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def routed_outputs(table: OutcomeTable, inputs: AnalysisInputs, system: str, line: str,
                   evaluation: EvaluationSet) -> dict[int, dict[str, dict[str, Any]]]:
    """The primary system's routed rows under ``full``, per seed, re-read through their hashes."""
    system_inputs = inputs.systems[system]
    train = system_inputs.train_condition(line, CONDITION)
    out = {}
    for run in system_inputs.runs("stage2", train):
        rows = parse_jsonl(read_verified(run.routed), f"{system} routed")
        out[run.seed] = {row["example_id"]: row for row in rows
                         if isinstance(row, dict) and row.get("condition") == CONDITION
                         and isinstance(row.get("example_id"), str) and row["example_id"] not in evaluation.excluded_ids}
    return out


def register_and_write(*, root: Path, registry_path: Path, items_path: Path, rows: Sequence[Mapping[str, str]],
                       summary: Mapping[str, Any], gate: SampleGate) -> tuple[Path, Path, int]:
    """Registry rows first in effect, sheet last; on any failure no sheet and no new registry rows remain."""
    sheet_dir = root / SHEET_DIR
    sheet, summary_path = sheet_dir / SHEET_NAME, sheet_dir / SUMMARY_NAME
    if sheet.exists() or summary_path.exists():
        raise AnalysisError("sheet_exists", f"{SHEET_DIR.as_posix()} already holds an error-audit sample; "
                                            "a second draw would be a re-sample")
    index = sa.load_corpus_index(items_path)
    registry = sa.load_registry(registry_path, index.dialogue_split)
    dialogues = sorted({row["dialogue_id"] for row in rows})
    new = [sa.manual_row(d, "error_audit", gate.inspector, gate.on.isoformat(), gate.freeze_date.isoformat())
           for d in dialogues]
    merged, added = sa.merge_rows(registry, new, gate.freeze_date.isoformat())
    problems = sa.validate_registry(merged, index.dialogue_split)
    if problems:
        raise sa.RegistryError(problems)
    sheet_dir.mkdir(parents=True, exist_ok=True)
    temporary = [sheet.with_name(sheet.name + ".tmp"), summary_path.with_name(summary_path.name + ".tmp")]
    original = registry_path.read_bytes() if registry_path.exists() else None
    try:
        temporary[0].write_bytes(sheet_bytes(rows))
        temporary[1].write_bytes((json.dumps(summary, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        sa.write_registry(registry_path, merged, index.dialogue_split)
        os.replace(temporary[1], summary_path)
        os.replace(temporary[0], sheet)
    except BaseException:
        for path in (*temporary, sheet, summary_path):
            path.unlink(missing_ok=True)
        if original is None:
            registry_path.unlink(missing_ok=True)
        else:
            registry_path.write_bytes(original)
        raise
    return sheet, summary_path, added


# ---------------------------------------------------------------------------------------- export and report (T13)


def read_sheet(path: Path) -> list[dict[str, str]]:
    try:
        text = read_bounded(path, sa.MAX_SHEET_BYTES).decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        if tuple(reader.fieldnames or ()) != SHEET_FIELDS:
            raise AnalysisError("sheet_columns", f"{path.name}: columns must be exactly {list(SHEET_FIELDS)}")
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error):
        raise AnalysisError("invalid_csv", f"{path.name} is not UTF-8 CSV") from None
    for line, row in enumerate(rows, start=2):
        if None in row or any(v is None for v in row.values()):
            raise AnalysisError("ragged_row", f"{path.name} line {line} has the wrong number of cells")
        if any(len(v) > MAX_CELL_CHARS for v in row.values()):
            raise AnalysisError("cell_too_long", f"{path.name} line {line} has an oversized cell")
    return rows


def validate_sheet(rows: Sequence[Mapping[str, str]], summary: Mapping[str, Any]) -> list[dict[str, str]]:
    """FR26: coded rows from the enum, the sampled row set, untouched locked columns, no formulas."""
    expected: Mapping[str, str] = summary["locked_sha256"]
    seen: set[str] = set()
    codes = []
    for line, row in enumerate(rows, start=2):
        example_id = row["example_id"]
        if example_id not in expected or example_id in seen:
            raise AnalysisError("row_set_changed", f"sheet line {line} is not a sampled row, or repeats one")
        seen.add(example_id)
        if locked_sha256(row) != expected[example_id]:
            raise AnalysisError("locked_column_edited", f"sheet line {line}: a locked column was edited")
        code, flag = row["code"].strip(), row["gold_questionable"].strip()
        if any(value.startswith(_FORMULA_LEADS) for value in (row["code"], row["gold_questionable"])):
            raise AnalysisError("formula_cell", f"sheet line {line}: a cell starts like a spreadsheet formula")
        if not code:
            raise AnalysisError("uncoded_row", f"sheet line {line} has no error code")
        if code not in ERROR_CODES:
            raise AnalysisError("unknown_code", f"sheet line {line}: the code must be one of {list(ERROR_CODES)}")
        if flag not in ("", "yes"):
            raise AnalysisError("bad_flag", f"sheet line {line}: gold_questionable must be empty or yes")
        codes.append({"example_id": example_id, "level": row["level"], "code": code, "gold_questionable": flag})
    missing = len(set(expected) - seen)
    if missing:
        raise AnalysisError("row_set_changed", f"{missing} sampled row(s) were removed from the sheet")
    return sorted(codes, key=lambda r: r["example_id"])


def read_codes(path: Path, summary: Mapping[str, Any]) -> list[dict[str, str]]:
    """The committed codes file, re-validated against the sample before it is counted."""
    try:
        text = read_bounded(path, sa.MAX_SHEET_BYTES).decode("utf-8")
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        if tuple(reader.fieldnames or ()) != CODES_FIELDS:
            raise AnalysisError("codes_columns", f"{path.name}: columns must be exactly {list(CODES_FIELDS)}")
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error):
        raise AnalysisError("invalid_csv", f"{path.name} is not UTF-8 CSV") from None
    sampled = summary["locked_sha256"]
    if sorted(r["example_id"] for r in rows) != sorted(sampled) or any(
            r["code"] not in ERROR_CODES or r["gold_questionable"] not in ("", "yes") for r in rows):
        raise AnalysisError("codes_mismatch", f"{path.name} does not match the sample; re-run error-audit export")
    return rows


def code_counts(codes: Sequence[Mapping[str, str]], summary: Mapping[str, Any]) -> dict[str, Any]:
    """Counts by level x code with the design, quotas and shortfalls; no IDs."""
    by_level = {s["level"]: Counter() for s in summary["strata"]}
    for row in codes:
        by_level[row["level"]][row["code"]] += 1
    return {"design": {k: summary[k] for k in ("seed", "per_level", "levels", "system", "line", "condition",
                                               "endpoint", "error_definition")},
            "strata": summary["strata"],
            "counts": {level: {code: counts.get(code, 0) for code in ERROR_CODES} for level, counts in by_level.items()},
            "totals": {code: sum(1 for r in codes if r["code"] == code) for code in ERROR_CODES},
            "gold_questionable": sum(r["gold_questionable"] == "yes" for r in codes),
            "n": len(codes),
            "over_inference": "not audited; reported as the non-request false-positive rate (spec 007 FR25)"}


def counts_markdown(counts: Mapping[str, Any]) -> bytes:
    header = ["level", *ERROR_CODES, "drawn", "shortfall"]
    strata = {s["level"]: s for s in counts["strata"]}
    lines = ["# Error audit: codes by rule level", "",
             f"> Primary system {counts['design']['system']}, {counts['design']['line']} line, condition "
             f"{counts['design']['condition']}; errors are {counts['design']['error_definition']}. Seeded draw "
             f"(seed {counts['design']['seed']}), {counts['design']['per_level']} per level; short strata taken whole.",
             f"> gold_questionable flags: {counts['gold_questionable']} (recorded, never removing an error). "
             f"Over-inference: {counts['over_inference']}.", "",
             "| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for level, row in counts["counts"].items():
        lines.append("| " + " | ".join([level, *(str(row[c]) for c in ERROR_CODES),
                                         str(strata[level]["drawn"]), str(strata[level]["shortfall"])]) + " |")
    return ("\n".join(lines) + "\n").encode("utf-8")
