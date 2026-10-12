"""Sealed annotation passes: snapshots, eligibility, sheets, immutable exports and corrections (spec 003 FR5–FR10).

A pass's sheet is built per item from the *committed* export of the previous pass, and every
exported row stores ``prior_sha256``, the canonical hash of the row it was built on:

    registry row ──hash──▶ form row ──hash──▶ context row ──hash──▶ reveal row

So the order "form before context before reveal" can be checked from committed files alone.

Each ``sheet`` call writes a snapshot (``<pass>_<annotator>_sheet_info.json``) next to the sheet.
It lists exactly which items the sheet covers, each with the prior hash it was built on, so items
registered later simply go into the next sheet and never block this one (review R3). Rows carry
opaque IDs (``f-001``, ``c-001``, ``r-001``) and the snapshot is the local key back to item IDs, so
no sheet shows an item ID that could be looked up in the source.

Exports are immutable: re-exporting a changed label for an already exported item fails and points
to ``correct``, which supersedes the old row (it stays in the file) and appends the fixed one.
Identical rows are a no-op. Free text (notes, slot values, paraphrases) goes to a git-ignored JSONL
keyed by the committed row it belongs to; committed rows hold IDs, enums and hashes only.

This module does no source reconstruction: callers pass in text they have already verified.
"""

from __future__ import annotations

import datetime
import json
import random
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.annotation import context_schema as cs
from src.annotation import context_taxonomy as ct
from src.annotation.levels import AnnotationError, normalize_fragment, normalize_label, read_csv, write_csv
from src.literary.screening import escape_cell, unescape_cell

PRIOR_PASS = {"form": None, "context": "form", "reveal": "context"}
LATER_PASSES = {"form": ("context", "reveal"), "context": ("reveal",), "reveal": ()}
IMPLEMENTED_PASSES = cs.PASSES
# Columns shown for reading only; export ignores whatever is in them.
DISPLAY_FIELDS = {"form": ("utterance",), "context": ("speakers", "context", "target"), "reveal": ("target", "reading", "continuation")}
LABEL_FIELDS = {
    "form": ("form", "fragment", "notes"),
    "context": ("function", "intent", "alt_intent", "slots", "paraphrase", "evidence", "confidence", "depth", "notes"),
    "reveal": ("future_dependence", "notes"),
}
SHEET_FIELDS = {name: ("row_id", *DISPLAY_FIELDS[name], *LABEL_FIELDS[name]) for name in cs.PASSES}
_COMMON_HEAD = ("item_id", "annotator")
COMMITTED_FIELDS = {
    "form": (*_COMMON_HEAD, "form", "fragment", "rubric_version", "protocol_version", "status", "prior_sha256"),
    "context": (
        *_COMMON_HEAD, "function", "request_status", "intent", "alt_intent", "slot_names", "unstated_slots",
        "evidence", "n_segments", "confidence", "depth", "taxonomy_version", "taxonomy_sha256",
        "segmenter_version", "protocol_version", "status", "text_sha256", "prior_sha256",
    ),
    "reveal": (
        *_COMMON_HEAD, "future_dependence", "confirmatory_eligible", "needs_adjudication", "protocol_version",
        "status", "prior_sha256",
    ),
}  # fmt: skip
CORRECTIONS_FILE = "context_corrections.csv"
CORRECTION_FIELDS = (
    "item_id", "pass", "annotator", "old_sha256", "new_sha256", "reason", "corrected_on", "later_passes_sealed",
)  # fmt: skip
NON_REQUEST_FUNCTIONS = ("inform", "decline", "social", "other")
ROW_STATUSES = ("", "superseded")
DEFAULT_SHEET_SEED = 20261011
RUBRIC_RE = re.compile(r"v[0-9]{1,3}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
_EVIDENCE_SPLIT = re.compile(r"[;,\s]+")


class PassError(Exception):
    """A sheet or export can't proceed; ``problems`` lists every reason, each naming its row or item."""

    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__(f"{len(problems)} problem(s):\n  " + "\n  ".join(problems))
        self.problems = list(problems)


@dataclass(frozen=True)
class PassPaths:
    """Where one annotator's files for one pass live. IDs are validated before any path is built.

    ``correction=True`` points the sheet and snapshot at the one-row correction sheet instead.
    """

    work_dir: Path
    annotations_dir: Path
    batch: str
    pass_name: str
    annotator: str
    correction: bool = False

    def __post_init__(self) -> None:
        cs.batch_id(self.batch)
        cs.annotator_id(self.annotator)
        cs.require_enum(self.pass_name, cs.PASSES, "pass")

    @property
    def stem(self) -> str:
        return f"{self.pass_name}_{self.annotator}"

    @property
    def _sheet_stem(self) -> str:
        return f"correct_{self.stem}" if self.correction else self.stem

    @property
    def sheet(self) -> Path:
        return self.work_dir / self.batch / f"{self._sheet_stem}.csv"

    @property
    def snapshot(self) -> Path:
        return self.work_dir / self.batch / f"{self._sheet_stem}_sheet_info.json"

    @property
    def text(self) -> Path:
        return self.work_dir / f"{self.stem}_text.jsonl"

    @property
    def committed(self) -> Path:
        return self.annotations_dir / f"context_{self.stem}.csv"

    def for_pass(self, pass_name: str) -> PassPaths:
        return PassPaths(self.work_dir, self.annotations_dir, self.batch, pass_name, self.annotator)


@dataclass(frozen=True)
class Display:
    """What a sheet shows for one item; built by the caller from hash-verified sources."""

    stratum: str
    target: str
    speakers: str = ""
    prior: str = ""  # rendered seg-v1 prior segments
    n_segments: int = 0
    continuation: str = ""
    reading: str = ""  # the annotator's own sealed context reading, shown in the reveal pass
    labels: Mapping[str, str] = field(default_factory=dict)  # prefilled label cells (corrections)


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
        problems.extend(f"{label}: {problem}" for problem in committed_row_problems(row, paths.pass_name, paths.annotator))
        if row.get("status") == "":
            if label in live:
                problems.append(f"{label}: more than one live (non-superseded) row")
            live.add(label)
    return problems


def committed_row_problems(row: Mapping[str, str], pass_name: str, annotator: str) -> list[str]:
    """Structural problems of one committed row; checks needing the taxonomy or sources are in ``validate``."""
    if set(row) != set(COMMITTED_FIELDS[pass_name]) or any(value is None for value in row.values()):
        return ["columns do not match the committed header"]
    checks: list[Callable[[], object]] = [
        lambda: cs.item_id(row["item_id"]),
        lambda: cs.require_enum(row["annotator"], (annotator,), "annotator"),
        lambda: cs.require_enum(row["status"], ROW_STATUSES, "status"),
        lambda: cs.require_match(SHA256_RE, row["prior_sha256"], "prior_sha256"),
        lambda: cs.require_enum(row["protocol_version"], (cs.PROTOCOL_VERSION,), "protocol_version"),
    ]
    checks += {"form": _form_checks, "context": _context_checks, "reveal": _reveal_checks}[pass_name](row)
    problems = []
    for check in checks:
        try:
            check()
        except cs.SchemaError as error:
            problems.append(str(error))
    if pass_name == "context" and not problems:
        problems += _context_row_rules(row)
    return problems


def _form_checks(row: Mapping[str, str]) -> list[Callable[[], object]]:
    return [
        lambda: cs.require_enum(row["form"], cs.FORM_LABELS, "form"),
        lambda: cs.require_enum(row["fragment"], cs.FRAGMENT_VALUES, "fragment"),
        lambda: cs.require_match(RUBRIC_RE, row["rubric_version"], "rubric_version"),
    ]


def _context_checks(row: Mapping[str, str]) -> list[Callable[[], object]]:
    return [
        lambda: cs.require_enum(row["function"], cs.FUNCTIONS, "function"),
        lambda: cs.require_enum(row["request_status"], (cs.request_status(row["function"]),), "request_status"),
        lambda: _intent_name(row["intent"], "intent"),
        lambda: _intent_name(row["alt_intent"], "alt_intent"),
        lambda: [cs.require_match(cs.NAME_RE, name, "slot name") for name in _names(row["slot_names"])],
        lambda: [cs.require_match(cs.NAME_RE, name, "unstated slot") for name in _names(row["unstated_slots"])],
        lambda: cs.require_match(re.compile(r"0|[1-9][0-9]{0,3}"), row["n_segments"], "n_segments"),
        lambda: cs.require_enum(row["confidence"], cs.CONFIDENCES, "confidence"),
        lambda: cs.require_enum(row["depth"], cs.DEPTHS, "depth"),
        lambda: cs.require_match(cs.TAXONOMY_VERSION_RE, row["taxonomy_version"], "taxonomy_version"),
        lambda: cs.require_match(SHA256_RE, row["taxonomy_sha256"], "taxonomy_sha256"),
        lambda: cs.require_enum(row["segmenter_version"], (cs.SEGMENTER_VERSION,), "segmenter_version"),
        lambda: cs.require_match(SHA256_RE, row["text_sha256"], "text_sha256"),
    ]


def _context_row_rules(row: Mapping[str, str]) -> list[str]:
    problems = function_rules(row["function"], row["intent"], row["alt_intent"], bool(row["slot_names"]))
    if not set(_names(row["unstated_slots"])) <= set(_names(row["slot_names"])):
        problems.append("unstated_slots lists a slot that is not in slot_names")
    try:
        if parse_evidence(row["evidence"], int(row["n_segments"])) != row["evidence"]:
            problems.append(f"evidence {row['evidence']!r} is not in canonical form (sorted, unique, ';'-separated)")
    except cs.SchemaError as error:
        problems.append(str(error))
    return problems


def _reveal_checks(row: Mapping[str, str]) -> list[Callable[[], object]]:
    return [
        lambda: cs.require_enum(row["future_dependence"], cs.FUTURE_DEPENDENCE, "future_dependence"),
        lambda: cs.require_enum(row["confirmatory_eligible"], (_flag(cs.confirmatory_eligible(row["future_dependence"])),), "confirmatory_eligible"),
        lambda: cs.require_enum(row["needs_adjudication"], (_flag(cs.needs_adjudication(row["future_dependence"])),), "needs_adjudication"),
    ]  # fmt: skip


def _intent_name(value: str, label: str) -> str:
    return value if value in ("", cs.OUT_OF_TAXONOMY) else cs.require_match(cs.NAME_RE, value, label)


def _names(value: str) -> list[str]:
    return value.split(";") if value else []


def _flag(value: bool) -> str:
    return "true" if value else "false"


def function_rules(function: str, intent: str, alt_intent: str, has_slots: bool) -> list[str]:
    """FR6 cross-field rules between the function and the intent columns.

    ``request`` needs an intent. ``inform``/``decline``/``social``/``other`` take no intent,
    alternative or slots. ``uncertain`` may record the candidate request it might be.
    """
    problems = []
    if function == "request" and not intent:
        problems.append(f"function 'request' needs an intent (use {cs.OUT_OF_TAXONOMY} if none fits)")
    if function in NON_REQUEST_FUNCTIONS:
        for name, present in (("intent", intent), ("alt_intent", alt_intent), ("slots", has_slots)):
            if present:
                problems.append(f"a {function!r} turn is not a request, so {name} must be blank")
    elif not intent and (alt_intent or has_slots):
        problems.append("alt_intent and slots need an intent")
    if intent and alt_intent == intent:
        problems.append("alt_intent repeats intent")
    return problems


def parse_evidence(text: str, n_segments: int) -> str:
    """``"3, 0;3"`` → ``"0;3"``: prior-segment indices, each in ``0..n_segments-1``."""
    indices: set[int] = set()
    for part in _EVIDENCE_SPLIT.split(text.strip()):
        if not part:
            continue
        if not part.isascii() or not part.isdigit() or len(part) > 4:
            raise cs.SchemaError(f"evidence {part[:12]!r} is not a segment number")
        index = int(part)
        if index >= n_segments:
            span = f"0-{n_segments - 1}" if n_segments else "none"
            raise cs.SchemaError(f"evidence segment {index} is out of range: this item has {n_segments} prior segment(s) ({span})")
        indices.add(index)
    return ";".join(str(index) for index in sorted(indices))


def live_rows(rows: Sequence[Mapping[str, str]]) -> dict[str, Mapping[str, str]]:
    """Item ID → its live (non-superseded) row: the sealed judgment later passes build on."""
    return {row["item_id"]: row for row in rows if row["status"] == ""}


def row_key(row: Mapping[str, str]) -> str:
    """Identity of one committed row for its free text: every field except ``status``.

    Unlike the FR10 chain hash it includes ``text_sha256``, so a correction that changes only a
    paraphrase still gets its own text record.
    """
    return cs.canonical_hash(row, exclude={"status"})


def merge_export(existing: Sequence[dict[str, str]], new: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    """Append new rows; identical re-exports are no-ops and changed labels are refused (FR8)."""
    live = live_rows(existing)
    problems: list[str] = []
    appended: list[dict[str, str]] = []
    for row in new:
        current = live.get(row["item_id"])
        if current is None:
            appended.append(row)
        elif row_key(current) != row_key(row):
            problems.append(f"{row['item_id']}: already exported with a different label; fix it with 'correct', not by re-exporting")
    if problems:
        raise PassError(problems)
    return sort_rows([*existing, *appended])


def sort_rows(rows: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    """Item order; for one item, superseded rows first, then the live row (stable for history)."""
    return sorted(rows, key=lambda row: (row["item_id"], row["status"] != "superseded"))


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


def snapshot_items(paths: PassPaths) -> set[str]:
    """Items an existing sheet showed the annotator (empty when there is no snapshot)."""
    return {entry["item_id"] for entry in load_snapshot(paths)["rows"]} if paths.snapshot.exists() else set()


def build_snapshot(
    paths: PassPaths,
    rows: Sequence[Mapping[str, Any]],
    *,
    seed: int,
    registry_sha256: str,
    built_at: str | None = None,
    extra: Mapping[str, str] | None = None,
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
        **(extra or {}),
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
    if not isinstance(snapshot, dict):
        raise PassError([f"{paths.snapshot} is not a snapshot object"])
    problems = []
    for key, expected in (("pass", paths.pass_name), ("annotator", paths.annotator), ("batch", paths.batch)):
        if snapshot.get(key) != expected:
            problems.append(f"snapshot {key} is {snapshot.get(key)!r}, expected {expected!r}")
    if paths.pass_name == "context":
        try:
            cs.require_match(cs.TAXONOMY_VERSION_RE, snapshot.get("taxonomy_version"), "snapshot taxonomy_version")
            cs.require_match(SHA256_RE, snapshot.get("taxonomy_sha256"), "snapshot taxonomy_sha256")
        except cs.SchemaError as error:
            problems.append(str(error))
    rows = snapshot.get("rows")
    if not isinstance(rows, list):
        problems.append("snapshot has no row list")
        rows = []
    for entry in rows:
        try:
            _check_snapshot_row(entry, paths.pass_name)
        except (cs.SchemaError, KeyError, TypeError) as error:
            problems.append(f"snapshot row {entry!r}: {error}")
    if problems:
        raise PassError(problems)
    return snapshot


def _check_snapshot_row(entry: Mapping[str, Any], pass_name: str) -> None:
    cs.item_id(entry["item_id"])
    cs.require_match(SHA256_RE, entry["prior_sha256"], "prior_sha256")
    cs.require_match(cs.ROW_ID_RES[pass_name], entry["row_id"], "row_id")
    if pass_name == "context":
        cs.require_enum(entry["stratum"], cs.STRATA, "stratum")
        if not isinstance(entry["n_segments"], int) or entry["n_segments"] < 0:
            raise cs.SchemaError(f"n_segments {entry['n_segments']!r} is not a count")
    if "old_row_key" in entry:  # correction sheets: the row being corrected
        cs.require_match(SHA256_RE, entry["old_row_key"], "old_row_key")


# --------------------------------------------------------------------------- building sheets


def build_rows(
    pass_name: str, items: Sequence[str], displays: Mapping[str, Display], prior: Mapping[str, str], seed: int
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Shuffle ``items`` with ``seed`` and return (sheet rows, snapshot rows) for any pass.

    Every display cell is formula-escaped; label cells are blank unless prefilled (corrections).
    """
    order = list(items)
    random.Random(seed).shuffle(order)
    width = max(3, len(str(len(order))))
    prefix = pass_name[0]
    sheet, snapshot_rows = [], []
    for index, item in enumerate(order, start=1):
        row_id = f"{prefix}-{index:0{width}d}"
        display = displays[item]
        shown = {
            "utterance": " ".join(display.target.split()),
            "target": " ".join(display.target.split()),
            "speakers": display.speakers,
            "context": display.prior,
            "reading": display.reading,
            "continuation": display.continuation,
        }
        row = {"row_id": row_id}
        row.update({name: escape_cell(shown[name]) for name in DISPLAY_FIELDS[pass_name]})
        row.update({name: escape_cell(display.labels.get(name, "")) for name in LABEL_FIELDS[pass_name]})
        sheet.append(row)
        entry: dict[str, Any] = {"row_id": row_id, "item_id": item, "prior_sha256": prior[item]}
        if pass_name == "context":
            entry.update(stratum=display.stratum, n_segments=display.n_segments)
        snapshot_rows.append(entry)
    return sheet, snapshot_rows


def form_sheet(
    items: Sequence[str], texts: Mapping[str, str], prior: Mapping[str, str], seed: int
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """The wording-only sheet: an opaque row ID and the utterance, whitespace collapsed (FR5)."""
    return build_rows("form", items, {item: Display("", texts[item]) for item in items}, prior, seed)


def label_cells(pass_name: str, row: Mapping[str, str], text: Mapping[str, str] | None) -> dict[str, str]:
    """A committed row turned back into sheet label cells, to prefill a correction sheet.

    Context rows need their local text (slot values and paraphrase exist nowhere else).
    """
    if pass_name == "context" and text is None:
        raise PassError([f"{row['item_id']}: its local text record is missing; restore data/interim/context/ from the Google Drive backup"])
    text = text or {}
    notes = text.get("notes", "")
    if pass_name == "form":
        return {"form": row["form"], "fragment": row["fragment"], "notes": notes}
    if pass_name == "reveal":
        return {"future_dependence": row["future_dependence"], "notes": notes}
    copied = ("function", "intent", "alt_intent", "evidence", "confidence", "depth")
    return {**{name: row[name] for name in copied}, "slots": text.get("slots", ""), "paraphrase": text.get("paraphrase", ""), "notes": notes}


def reading(context_row: Mapping[str, str], text: Mapping[str, str] | None) -> str:
    """The annotator's own sealed context reading, as one line for the reveal sheet."""
    parts = [context_row["function"]]
    if context_row["intent"]:
        parts.append(context_row["intent"] + (f" (or {context_row['alt_intent']})" if context_row["alt_intent"] else ""))
    if text and text.get("slots"):
        parts.append(text["slots"])
    if text and text.get("paraphrase"):
        parts.append(f'"{text["paraphrase"]}"')
    return " | ".join(parts)


# --------------------------------------------------------------------------- parsing filled sheets


class _RowInvalid(Exception):
    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = list(problems)


RowParser = Callable[[Mapping[str, str], Mapping[str, Any]], tuple[dict[str, str], dict[str, str]]]


def parse_sheet(
    pass_name: str,
    sheet: Sequence[Mapping[str, str]],
    snapshot: Mapping[str, Any],
    current_prior: Mapping[str, str],
    parse_row: RowParser,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Validate a filled sheet against its snapshot; return (committed rows, local text records).

    ``parse_row(cells, snapshot_entry)`` returns the pass-specific committed fields and free text,
    or raises ``_RowInvalid``. Every problem in the sheet is collected before anything is raised.
    """
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
        label = f"{label} [{entry['item_id']}]" if pass_name != "form" else label
        row_problems = []
        if current_prior.get(entry["item_id"]) != entry["prior_sha256"]:
            row_problems.append(f"its {PRIOR_PASS[pass_name] or 'registry'} row changed after the sheet was built; rebuild the sheet")
        try:
            fields, free = parse_row(cells, entry)
        except _RowInvalid as error:
            row_problems += error.problems
        if row_problems:
            problems.extend(f"{label}: {problem}" for problem in row_problems)
            continue
        row = {"item_id": entry["item_id"], "annotator": annotator, **fields}
        row.update(protocol_version=cs.PROTOCOL_VERSION, status="", prior_sha256=entry["prior_sha256"])
        row = {name: row[name] for name in COMMITTED_FIELDS[pass_name]}
        committed.append(row)
        texts.append({"item_id": entry["item_id"], "pass": pass_name, "annotator": annotator, "row_sha256": row_key(row), **free})
    problems.extend(f"{row_id}: row is missing from the sheet (rows must not be deleted)" for row_id in by_row if row_id not in seen)
    if problems:
        raise PassError(problems)
    return committed, texts


def _collect(problems: list[str], check: Callable[[], str], default: str = "") -> str:
    try:
        return check()
    except cs.SchemaError as error:
        problems.append(str(error))
        return default


def _choice(cells: Mapping[str, str], name: str, allowed: Sequence[str], problems: list[str], *, required: bool = True) -> str:
    value = cells.get(name, "").lower()
    if not value and required:
        problems.append(f"{name} is missing ({', '.join(choice for choice in allowed if choice)})")
        return ""
    return _collect(problems, lambda: cs.require_enum(value, allowed, name))


def parse_form_sheet(
    sheet: Sequence[Mapping[str, str]], snapshot: Mapping[str, Any], current_prior: Mapping[str, str], *, rubric: str
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Form pass: rubric labels, fragment flag and notes (FR5)."""
    cs.require_match(RUBRIC_RE, rubric, "rubric")

    def parse_row(cells: Mapping[str, str], entry: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
        problems: list[str] = []
        form = normalize_label(cells.get("form", ""))
        if form is None:
            problems.append(f"form {cells.get('form', '')!r} is missing or not a rubric v2 label ({' '.join(cs.FORM_LABELS)})")
        fragment = normalize_fragment(cells.get("fragment", ""))
        if fragment is None:
            problems.append(f"fragment {cells.get('fragment', '')!r} must be blank, 0 or 1")
        notes = _collect(problems, lambda: cs.free_text(cells.get("notes", ""), "notes"))
        if problems:
            raise _RowInvalid(problems)
        return {"form": form or "", "fragment": fragment or "", "rubric_version": rubric}, {"notes": notes}

    return parse_sheet("form", sheet, snapshot, current_prior, parse_row)


def parse_context_sheet(
    sheet: Sequence[Mapping[str, str]], snapshot: Mapping[str, Any], current_prior: Mapping[str, str], *, taxonomy: ct.Taxonomy
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Context pass: function, intent, slots, paraphrase, evidence, confidence, depth (FR6).

    Labels are checked against the taxonomy version recorded in the snapshot; the caller checks
    that version was not edited in place since the sheet was built.
    """
    version, version_sha = snapshot["taxonomy_version"], snapshot["taxonomy_sha256"]
    annotator = snapshot["annotator"]

    def lookup(intent_id: str, label: str, stratum: str, problems: list[str]) -> ct.Intent | None:
        try:
            intent = taxonomy.intent(version, intent_id)
        except cs.SchemaError as error:
            problems.append(f"{label}: {error}")
            return None
        if not intent.allows(stratum):
            problems.append(f"{label} {intent_id!r} is a {intent.stratum} intent; this is a {stratum} item")
        return intent

    def parse_row(cells: Mapping[str, str], entry: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
        problems: list[str] = []
        function = _choice(cells, "function", cs.FUNCTIONS, problems)
        confidence = _choice(cells, "confidence", cs.CONFIDENCES, problems)
        depth = _choice(cells, "depth", cs.DEPTHS, problems, required=False)
        intent_id, alt_id = cells.get("intent", "").lower(), cells.get("alt_intent", "").lower()
        paraphrase = _collect(problems, lambda: cs.free_text(cells.get("paraphrase", ""), "paraphrase"))
        notes = _collect(problems, lambda: cs.free_text(cells.get("notes", ""), "notes"))
        try:
            pairs = ct.parse_slots(cells.get("slots", ""))
        except cs.SchemaError as error:
            problems.append(str(error))
            pairs = []
        evidence = _collect(problems, lambda: parse_evidence(cells.get("evidence", ""), entry["n_segments"]))
        if function:
            problems += function_rules(function, intent_id, alt_id, bool(pairs or cells.get("slots", "")))
        if function == "request" and not paraphrase:
            problems.append("a request needs a paraphrase: what the speaker wants, said directly")
        if intent_id and function in ("request", "uncertain"):
            intent = lookup(intent_id, "intent", entry["stratum"], problems)
            if intent is not None:
                problems += ct.slot_problems(intent, pairs)
            if alt_id:
                lookup(alt_id, "alt_intent", entry["stratum"], problems)
        if problems:
            raise _RowInvalid(problems)
        slots = ct.canonical_slots(pairs)
        fields = {
            "function": function,
            "request_status": cs.request_status(function),
            "intent": intent_id,
            "alt_intent": alt_id,
            "slot_names": ";".join(sorted(name for name, _ in pairs)),
            "unstated_slots": ";".join(sorted(ct.unstated(pairs))),
            "evidence": evidence,
            "n_segments": str(entry["n_segments"]),
            "confidence": confidence,
            "depth": depth,
            "taxonomy_version": version,
            "taxonomy_sha256": version_sha,
            "segmenter_version": cs.SEGMENTER_VERSION,
            "text_sha256": cs.text_hash(entry["item_id"], "context", annotator, slots, paraphrase),
        }
        return fields, {"slots": slots, "paraphrase": paraphrase, "notes": notes}

    return parse_sheet("context", sheet, snapshot, current_prior, parse_row)


def parse_reveal_sheet(
    sheet: Sequence[Mapping[str, str]], snapshot: Mapping[str, Any], current_prior: Mapping[str, str]
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Reveal pass: does the continuation corroborate, conflict with or decide the reading (FR7)?"""

    def parse_row(cells: Mapping[str, str], entry: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
        problems: list[str] = []
        future = _choice(cells, "future_dependence", cs.FUTURE_DEPENDENCE, problems)
        notes = _collect(problems, lambda: cs.free_text(cells.get("notes", ""), "notes"))
        if problems:
            raise _RowInvalid(problems)
        fields = {
            "future_dependence": future,
            "confirmatory_eligible": _flag(cs.confirmatory_eligible(future)),
            "needs_adjudication": _flag(cs.needs_adjudication(future)),
        }
        return fields, {"notes": notes}

    return parse_sheet("reveal", sheet, snapshot, current_prior, parse_row)


# --------------------------------------------------------------------------- file helpers


def read_sheet(paths: PassPaths) -> list[dict[str, str]]:
    if not paths.sheet.exists():
        raise PassError([f"no sheet at {paths.sheet}; run 'sheet' first"])
    try:
        rows = read_csv(paths.sheet)
    except AnnotationError as error:
        raise PassError([str(error)]) from None
    fields = SHEET_FIELDS[paths.pass_name]
    header = set(rows[0]) if rows else set()
    earlier = sorted(
        {name for prior in cs.PASSES[: cs.PASSES.index(paths.pass_name)] for name in LABEL_FIELDS[prior]} & header - set(fields)
    )
    if earlier:
        raise PassError([f"{paths.sheet}: carries earlier-pass column(s) {earlier}; a {paths.pass_name} sheet must not"])
    if rows and header != set(fields):
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


def load_text_records(paths: PassPaths) -> dict[tuple[str, str], dict[str, str]]:
    """(item_id, row_sha256) → the free text of that committed row; a missing file is empty."""
    records: dict[tuple[str, str], dict[str, str]] = {}
    if not paths.text.exists():
        return records
    for number, line in enumerate(paths.text.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            if not isinstance(record, dict) or not all(isinstance(value, str) for value in record.values()):
                raise TypeError("expected an object of strings")
            records[(record["item_id"], record["row_sha256"])] = record
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            raise PassError([f"{paths.text} line {number} is not a text record: {error}"]) from None
    return records


def merge_text_records(paths: PassPaths, records: Sequence[Mapping[str, str]]) -> None:
    """Upsert free-text records by (item, row) into the local JSONL (sorted, atomic).

    Records of superseded rows are kept: agreement analyses may use first judgments.
    """
    merged = load_text_records(paths)
    merged.update({(record["item_id"], record["row_sha256"]): dict(record) for record in records})
    paths.text.parent.mkdir(parents=True, exist_ok=True)
    tmp = paths.text.with_suffix(".jsonl.tmp")
    tmp.write_text("".join(json.dumps(merged[key], ensure_ascii=False, sort_keys=True) + "\n" for key in sorted(merged)), encoding="utf-8")
    tmp.replace(paths.text)


# --------------------------------------------------------------------------- corrections log


def load_corrections(path: Path) -> list[dict[str, str]]:
    """The committed corrections log, validated; a missing file is empty."""
    if not path.exists():
        return []
    try:
        rows = read_csv(path)
    except AnnotationError as error:
        raise PassError([str(error)]) from None
    if rows and tuple(rows[0]) != CORRECTION_FIELDS:
        raise PassError([f"{path}: columns {list(rows[0])} do not match {list(CORRECTION_FIELDS)}"])
    problems = [f"{path.name} line {line} ({row.get('item_id') or '?'}): {problem}"
                for line, row in enumerate(rows, start=2) for problem in correction_problems(row)]  # fmt: skip
    if problems:
        raise PassError(problems)
    return rows


def correction_problems(row: Mapping[str, str]) -> list[str]:
    if set(row) != set(CORRECTION_FIELDS) or any(value is None for value in row.values()):
        return ["columns do not match the corrections header"]
    problems = []
    for check in (
        lambda: cs.item_id(row["item_id"]),
        lambda: cs.require_enum(row["pass"], cs.PASSES, "pass"),
        lambda: cs.annotator_id(row["annotator"]),
        lambda: cs.require_match(SHA256_RE, row["old_sha256"], "old_sha256"),
        lambda: cs.require_match(SHA256_RE, row["new_sha256"], "new_sha256"),
        lambda: cs.require_enum(row["reason"], cs.CORRECTION_REASONS, "reason"),
        lambda: cs.require_match(re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}"), row["corrected_on"], "corrected_on"),
        lambda: cs.require_enum(row["later_passes_sealed"], cs.BOOLEANS, "later_passes_sealed"),
    ):
        try:
            check()
        except cs.SchemaError as error:
            problems.append(str(error))
    return problems


def append_correction(path: Path, row: Mapping[str, str]) -> None:
    """Append one validated entry; the log is chronological and never rewritten."""
    problems = correction_problems(row)
    if problems:
        raise PassError(problems)
    write_csv(path, CORRECTION_FIELDS, [*load_corrections(path), dict(row)])
