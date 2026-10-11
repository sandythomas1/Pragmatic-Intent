"""Sealed annotation passes: snapshots, eligibility, sheets and immutable exports (spec 003 FR5–FR10).

A pass's sheet is built per item from the *committed* export of the previous pass, and every
exported row stores ``prior_sha256``, the canonical hash of the row it was built on:

    registry row ──hash──▶ form row ──hash──▶ context row ──hash──▶ reveal row

So the order "form before context before reveal" can be checked from committed files alone.

Each ``sheet`` call writes a snapshot (``<pass>_<annotator>_sheet_info.json``) next to the sheet.
It lists exactly which items the sheet covers, each with the prior hash it was built on, so items
registered later simply go into the next sheet and never block this one (review R3). For the form
pass, rows carry opaque IDs (``f-001``…) and the snapshot is the local key back to item IDs, so the
sheet itself never shows a stratum, source or item ID (FR5).

Exports are immutable: re-exporting a changed label for an already exported item fails and points
to ``correct``. Identical rows are a no-op. Free text (notes, and later slots and paraphrases) goes
to a git-ignored JSONL; committed rows hold IDs, enums and hashes only.

This module does no source reconstruction: callers pass in the target texts they have verified.
"""

from __future__ import annotations

import datetime
import json
import random
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.annotation import context_schema as cs
from src.annotation.levels import AnnotationError, normalize_fragment, normalize_label, read_csv, write_csv
from src.literary.screening import escape_cell, unescape_cell

PRIOR_PASS = {"form": None, "context": "form", "reveal": "context"}
IMPLEMENTED_PASSES = ("form",)
SHEET_FIELDS = {"form": ("row_id", "utterance", "form", "fragment", "notes")}
COMMITTED_FIELDS = {
    "form": ("item_id", "annotator", "form", "fragment", "rubric_version", "protocol_version", "status", "prior_sha256"),
}
ROW_STATUSES = ("", "superseded")
DEFAULT_SHEET_SEED = 20261011
RUBRIC_RE = re.compile(r"v[0-9]{1,3}")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


class PassError(Exception):
    """A sheet or export can't proceed; ``problems`` lists every reason, each naming its row or item."""

    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__(f"{len(problems)} problem(s):\n  " + "\n  ".join(problems))
        self.problems = list(problems)


@dataclass(frozen=True)
class PassPaths:
    """Where one annotator's files for one pass live. IDs are validated before any path is built."""

    work_dir: Path
    annotations_dir: Path
    batch: str
    pass_name: str
    annotator: str

    def __post_init__(self) -> None:
        cs.batch_id(self.batch)
        cs.annotator_id(self.annotator)
        cs.require_enum(self.pass_name, cs.PASSES, "pass")

    @property
    def stem(self) -> str:
        return f"{self.pass_name}_{self.annotator}"

    @property
    def sheet(self) -> Path:
        return self.work_dir / self.batch / f"{self.stem}.csv"

    @property
    def snapshot(self) -> Path:
        return self.work_dir / self.batch / f"{self.stem}_sheet_info.json"

    @property
    def text(self) -> Path:
        return self.work_dir / f"{self.stem}_text.jsonl"

    @property
    def committed(self) -> Path:
        return self.annotations_dir / f"context_{self.stem}.csv"

    def for_pass(self, pass_name: str) -> PassPaths:
        return PassPaths(self.work_dir, self.annotations_dir, self.batch, pass_name, self.annotator)


# --------------------------------------------------------------------------- committed pass files


def load_committed(paths: PassPaths) -> list[dict[str, str]]:
    """One annotator's committed rows for one pass, validated; a missing file is empty."""
    fields = COMMITTED_FIELDS[paths.pass_name]
    if not paths.committed.exists():
        return []
    try:
        rows = read_csv(paths.committed)
    except AnnotationError as error:
        raise PassError([str(error)]) from None
    problems = []
    if rows and tuple(rows[0]) != fields:
        problems.append(f"{paths.committed}: columns {list(rows[0])} do not match {list(fields)}")
    else:
        problems = validate_committed(rows, paths)
    if problems:
        raise PassError(problems)
    return rows


def validate_committed(rows: Sequence[Mapping[str, str]], paths: PassPaths) -> list[str]:
    problems: list[str] = []
    live: set[str] = set()
    for row in rows:
        label = row.get("item_id") or "?"
        problems.extend(f"{label}: {problem}" for problem in _committed_row_problems(row, paths))
        if row.get("status") == "":
            if label in live:
                problems.append(f"{label}: more than one live (non-superseded) row")
            live.add(label)
    return problems


def _committed_row_problems(row: Mapping[str, str], paths: PassPaths) -> list[str]:
    if set(row) != set(COMMITTED_FIELDS[paths.pass_name]) or any(value is None for value in row.values()):
        return ["columns do not match the committed header"]
    checks = [
        lambda: cs.item_id(row["item_id"]),
        lambda: cs.require_enum(row["annotator"], (paths.annotator,), "annotator"),
        lambda: cs.require_enum(row["status"], ROW_STATUSES, "status"),
        lambda: cs.require_match(_SHA256_RE, row["prior_sha256"], "prior_sha256"),
        lambda: cs.require_enum(row["protocol_version"], (cs.PROTOCOL_VERSION,), "protocol_version"),
    ]
    if paths.pass_name == "form":
        checks += [
            lambda: cs.require_enum(row["form"], cs.FORM_LABELS, "form"),
            lambda: cs.require_enum(row["fragment"], cs.FRAGMENT_VALUES, "fragment"),
            lambda: cs.require_match(RUBRIC_RE, row["rubric_version"], "rubric_version"),
        ]
    problems = []
    for check in checks:
        try:
            check()
        except cs.SchemaError as error:
            problems.append(str(error))
    return problems


def live_rows(rows: Sequence[Mapping[str, str]]) -> dict[str, Mapping[str, str]]:
    """Item ID → its live (non-superseded) row: the sealed judgment later passes build on."""
    return {row["item_id"]: row for row in rows if row["status"] == ""}


def merge_export(existing: Sequence[dict[str, str]], new: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    """Append new rows; identical re-exports are no-ops and changed labels are refused (FR8)."""
    live = live_rows(existing)
    problems: list[str] = []
    appended: list[dict[str, str]] = []
    for row in new:
        current = live.get(row["item_id"])
        if current is None:
            appended.append(row)
        elif cs.canonical_hash(current) != cs.canonical_hash(row) or current["prior_sha256"] != row["prior_sha256"]:
            problems.append(f"{row['item_id']}: already exported with a different label; fix it with 'correct', not by re-exporting")
    if problems:
        raise PassError(problems)
    return sorted([*existing, *appended], key=lambda row: (row["item_id"], row["status"] != "superseded"))


# --------------------------------------------------------------------------- eligibility and snapshots


def prior_hashes(
    pass_name: str, registry: Sequence[Mapping[str, str]], prior_live: Mapping[str, Mapping[str, str]]
) -> dict[str, str]:
    """Item ID → hash of the row this pass builds on: the registry row (form) or the prior pass row."""
    if PRIOR_PASS[pass_name] is None:
        return {row["item_id"]: cs.canonical_hash(row) for row in registry}
    return {item: cs.canonical_hash(row) for item, row in prior_live.items()}


def eligible_items(
    batch: str, registry: Sequence[Mapping[str, str]], prior: Mapping[str, str], done: Mapping[str, Any]
) -> list[str]:
    """Batch items, in registry order, whose prior pass is sealed and this pass is not yet exported."""
    return [row["item_id"] for row in registry if row["batch"] == batch and row["item_id"] in prior and row["item_id"] not in done]


def pending_snapshot_items(paths: PassPaths, done: Mapping[str, Any]) -> list[str]:
    """Items of an existing snapshot that are not exported yet: building a new sheet would lose them."""
    if not paths.snapshot.exists():
        return []
    return [entry["item_id"] for entry in load_snapshot(paths)["rows"] if entry["item_id"] not in done]


def build_snapshot(
    paths: PassPaths, rows: Sequence[Mapping[str, str]], *, seed: int, registry_sha256: str, built_at: str | None = None
) -> dict[str, Any]:
    return {
        "pass": paths.pass_name,
        "annotator": paths.annotator,
        "batch": paths.batch,
        "seed": seed,
        "protocol_version": cs.PROTOCOL_VERSION,
        "segmenter_version": cs.SEGMENTER_VERSION,
        "built_at": built_at or datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "registry_sha256": registry_sha256,
        "rows": [dict(row) for row in rows],
    }


def write_snapshot(paths: PassPaths, snapshot: Mapping[str, Any]) -> None:
    paths.snapshot.parent.mkdir(parents=True, exist_ok=True)
    tmp = paths.snapshot.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(paths.snapshot)


def load_snapshot(paths: PassPaths) -> dict[str, Any]:
    """Read and check a snapshot; it is local, but it decides which item a label belongs to."""
    if not paths.snapshot.exists():
        raise PassError([f"no sheet snapshot at {paths.snapshot}; run 'sheet' first"])
    try:
        snapshot = json.loads(paths.snapshot.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise PassError([f"{paths.snapshot} is not valid JSON: {error}"]) from None
    problems = []
    for key, expected in (("pass", paths.pass_name), ("annotator", paths.annotator), ("batch", paths.batch)):
        if snapshot.get(key) != expected:
            problems.append(f"snapshot {key} is {snapshot.get(key)!r}, expected {expected!r}")
    rows = snapshot.get("rows")
    if not isinstance(rows, list):
        problems.append("snapshot has no row list")
        rows = []
    for entry in rows:
        try:
            cs.item_id(entry["item_id"])
            cs.require_match(_SHA256_RE, entry["prior_sha256"], "prior_sha256")
            if paths.pass_name == "form":
                cs.require_match(cs.FORM_ROW_RE, entry["row_id"], "row_id")
        except (cs.SchemaError, KeyError, TypeError) as error:
            problems.append(f"snapshot row {entry!r}: {error}")
    if problems:
        raise PassError(problems)
    return snapshot


# --------------------------------------------------------------------------- form pass


def form_sheet(
    items: Sequence[str], texts: Mapping[str, str], prior: Mapping[str, str], seed: int
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Shuffle ``items`` with ``seed`` and return (sheet rows, snapshot rows).

    The sheet shows only an opaque row ID and the utterance with whitespace runs collapsed (a
    literary target can span line breaks). The snapshot rows map each row ID back to its item.
    """
    order = list(items)
    random.Random(seed).shuffle(order)
    width = max(3, len(str(len(order))))
    sheet, snapshot_rows = [], []
    for index, item in enumerate(order, start=1):
        row_id = f"f-{index:0{width}d}"
        sheet.append({"row_id": row_id, "utterance": escape_cell(" ".join(texts[item].split())), "form": "", "fragment": "", "notes": ""})
        snapshot_rows.append({"row_id": row_id, "item_id": item, "prior_sha256": prior[item]})
    return sheet, snapshot_rows


def parse_form_sheet(
    sheet: Sequence[Mapping[str, str]], snapshot: Mapping[str, Any], current_prior: Mapping[str, str], *, rubric: str
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Validate a filled form sheet against its snapshot; return (committed rows, local text records)."""
    cs.require_match(RUBRIC_RE, rubric, "rubric")
    annotator = snapshot["annotator"]
    by_row = {entry["row_id"]: entry for entry in snapshot["rows"]}
    problems: list[str] = []
    seen: dict[str, int] = {}
    committed, texts = [], []
    for line, raw in enumerate(sheet, start=2):
        cells = {key: unescape_cell((value or "").strip()) for key, value in raw.items() if key is not None}
        row_id = cells.get("row_id", "")
        label = f"sheet line {line} ({row_id or 'no row_id'})"
        entry = by_row.get(row_id)
        if entry is None:
            problems.append(f"{label}: row_id is not in this sheet's snapshot")
            continue
        if row_id in seen:
            problems.append(f"{label}: duplicates sheet line {seen[row_id]}")
            continue
        seen[row_id] = line
        row_problems = []
        form = normalize_label(cells.get("form", ""))
        if form is None:
            row_problems.append(f"form {cells.get('form', '')!r} is missing or not a rubric v2 label ({' '.join(cs.FORM_LABELS)})")
        fragment = normalize_fragment(cells.get("fragment", ""))
        if fragment is None:
            row_problems.append(f"fragment {cells.get('fragment', '')!r} must be blank, 0 or 1")
        try:
            notes = cs.free_text(cells.get("notes", ""), "notes")
        except cs.SchemaError as error:
            row_problems.append(str(error))
        if current_prior.get(entry["item_id"]) != entry["prior_sha256"]:
            row_problems.append("its registry row changed after the sheet was built; rebuild the sheet")
        if row_problems:
            problems.extend(f"{label}: {problem}" for problem in row_problems)
            continue
        committed.append(
            {
                "item_id": entry["item_id"],
                "annotator": annotator,
                "form": form,
                "fragment": fragment,
                "rubric_version": rubric,
                "protocol_version": cs.PROTOCOL_VERSION,
                "status": "",
                "prior_sha256": entry["prior_sha256"],
            }
        )
        texts.append({"item_id": entry["item_id"], "pass": "form", "annotator": annotator, "notes": notes})
    problems.extend(f"{row_id}: row is missing from the sheet (rows must not be deleted)" for row_id in by_row if row_id not in seen)
    if problems:
        raise PassError(problems)
    return committed, texts


# --------------------------------------------------------------------------- file helpers


def read_sheet(paths: PassPaths) -> list[dict[str, str]]:
    if not paths.sheet.exists():
        raise PassError([f"no sheet at {paths.sheet}; run 'sheet' first"])
    try:
        rows = read_csv(paths.sheet)
    except AnnotationError as error:
        raise PassError([str(error)]) from None
    fields = SHEET_FIELDS[paths.pass_name]
    if rows and set(rows[0]) != set(fields):
        raise PassError([f"{paths.sheet}: columns {list(rows[0])} do not match {list(fields)}"])
    return rows


def write_sheet(paths: PassPaths, rows: Sequence[Mapping[str, str]]) -> None:
    try:
        write_csv(paths.sheet, SHEET_FIELDS[paths.pass_name], rows, excel=True)
    except PermissionError:
        raise PassError([f"cannot write {paths.sheet}; close it in Excel and retry"]) from None


def write_committed(paths: PassPaths, rows: Sequence[Mapping[str, str]]) -> None:
    problems = validate_committed(rows, paths)
    if problems:
        raise PassError(problems)
    write_csv(paths.committed, COMMITTED_FIELDS[paths.pass_name], rows)


def merge_text_records(paths: PassPaths, records: Sequence[Mapping[str, str]]) -> None:
    """Upsert free-text records by item into the local JSONL (sorted, atomic)."""
    merged: dict[str, Mapping[str, str]] = {}
    if paths.text.exists():
        for line in paths.text.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                merged[record["item_id"]] = record
    merged.update({record["item_id"]: record for record in records})
    paths.text.parent.mkdir(parents=True, exist_ok=True)
    tmp = paths.text.with_suffix(".jsonl.tmp")
    tmp.write_text("".join(json.dumps(merged[key], ensure_ascii=False, sort_keys=True) + "\n" for key in sorted(merged)), encoding="utf-8")
    tmp.replace(paths.text)
