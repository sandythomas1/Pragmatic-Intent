"""The split and prior-inspection audit (spec 006, WP-04): registry of inspected test dialogues.

The registry, ``data/annotations/inspected_test_dialogues.csv``, is committed and text-free. It
lists every test-split dialogue a researcher or Claude has inspected, one row per (dialogue,
source), so the whole dialogue can be kept out of the primary test set (spec 001 FR-06, AC-04):

* ``source`` says where the inspection is recorded; its reason code is fixed per source, except
  for ``manual`` rows, which pick one from ``MANUAL_REASONS``.
* ``phase`` is ``pre_freeze`` or ``post_scoring``. Only ``pre_freeze`` rows define the primary set
  and its hash; ``post_scoring`` rows (the error audit) are disclosed and never move the freeze.
* A dialogue may have several rows. Its exclusion reason is the reason of its highest-precedence
  source, in the order of ``SOURCES``.

Every dialogue ID read anywhere passes through ``canonical_dialogue_id``, which accepts the bare
(``PMUL1762``) and the ``items.jsonl`` form (``PMUL1762.json``) and returns the latter.

Every committed value is a validated ID, enum or date, none of which can start with a spreadsheet
formula character, so the registry is safe to open in Excel without escaping.

Run from the repository root (Python 3.12, standard library only)::

    python -m src.data.split_audit register [--freeze-date YYYY-MM-DD]
    python -m src.data.split_audit register --add PMUL1234 --reason viewed_text --inspector A1 --on 2026-10-20
    python -m src.data.split_audit scan
    python -m src.data.split_audit scan --transcripts DIR [DIR ...] [--register --on YYYY-MM-DD]
    python -m src.data.split_audit check
    python -m src.data.split_audit audit [--verify]

``register`` derives rows from ``DERIVED_SOURCES``. Each source has a fixed inspection date, and
git-ignored files are pinned by the SHA-256 they had when they were inspected, so rerunning a tool
that rewrites them can't move the test set. A missing local file (a fresh clone) keeps its
committed rows. Committed rows never change or disappear through ``register``. Rows dated on or
after the freeze date are ``post_scoring``; once a freeze date exists, a new ``pre_freeze`` row
means an inspection went unrecorded before the freeze, which is an error, not something to fix
quietly.

``scan`` searches the human-facing sheet locations for test dialogue IDs and fails on any that the
registry doesn't hold. ``scan --transcripts`` searches assistant session logs once, before the
freeze. It prints IDs and counts only, never log content.

``check`` re-derives the split rules from ``items.jsonl`` and the pinned MultiWOZ list files,
independently of the dataset builder. It also finds cross-split duplicate dialogues: a test
dialogue (at least 2 user turns) whose ``dup-v1``-normalized user turns equal a train or dev
dialogue's. It exits 1 on any rule failure. Duplicates never fail it, but more than 1% of test
sets ``needs_decision``.

``audit`` writes the freeze object ``data/manifests/split_audit_test.csv``, one text-free row per
genuine test example of spec 004's manifest, giving ``primary``, the exclusion reason and the
``dup_exact`` and ``donor_inspected`` flags. Its summary pins the input hashes and has its own
content hash, which covers everything but the ``post_scoring`` disclosure. ``--verify`` rebuilds
and compares both files byte for byte. ``src.evaluation.test_audit`` loads it for test scoring.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import io
import itertools
import json
import logging
import os
import re
import sys
import unicodedata
from collections import Counter
from collections.abc import Collection, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.data.audit_fact_drift import build_vocabulary
from src.data.auto_levels import RULES_VERSION, VARIANTS, level_item
from src.data.contexts import in_mismatch_set
from src.data.direct_dataset import load_items
from src.stage1.data import build_examples

logger = logging.getLogger(__name__)

REGISTRY_VERSION = "inspected-v1"
REGISTRY_FIELDS = ("dialogue_id", "source", "reason", "inspector", "inspected_on", "phase", "registry_version")
DEFAULT_REGISTRY = Path("data/annotations/inspected_test_dialogues.csv")

# Highest precedence first (spec 006 FR1). Each derived source has exactly one reason.
SOURCES = ("levels_round1", "levels_round3", "obsolete_round3_sheet", "fact_drift_review", "claude_session", "manual")
SOURCE_REASONS = {
    "levels_round1": "calibration_labels",
    "levels_round3": "calibration_labels",
    "obsolete_round3_sheet": "sealed_labels",
    "fact_drift_review": "fact_drift_review_unrecorded",
    "claude_session": "session_output_unverified",
}
MANUAL_REASONS = ("viewed_text", "error_audit", "llm_judge_sample", "source_changed_since_inspection")
PHASES = ("pre_freeze", "post_scoring")
MAX_REGISTRY_BYTES = 1 << 20  # thousands of rows at most; anything larger is not a registry
MAX_SHEET_BYTES = 16 << 20  # human-facing sheets and inspection sources are kilobytes

DEFAULT_ITEMS = Path("data/interim/direct/items.jsonl")
FREEZE_FILE = Path("data/manifests/freeze.json")  # WP-08 writes {"freeze_date": "YYYY-MM-DD"}
PRE_FREEZE_SCAN_DIRS = (Path("data/interim/labeling"), Path("data/interim/auto_levels"), Path("data/interim/context"),
                        Path("data/interim/literary"), Path("data/annotations"))
# results/error_audit holds the committed spec 007 codes file (test example IDs, no text).
POST_SCORING_SCAN_DIRS = (Path("data/interim/error_audit"), Path("results/error_audit"))
TEXT_SUFFIXES = (".json", ".jsonl", ".txt")

_DIALOGUE_ID_RE = re.compile(r"(?P<stem>(?:PMUL|MUL|SNG|SSNG|WOZ)[0-9]{4,5})(?:\.json)?")
# An ID inside free text or a compound value (``PMUL1234_t02``, ``d:PMUL1234:t04``): no letter or
# digit before (so ``MUL`` inside ``PMUL`` doesn't match), no digit after.
_EMBEDDED_ID_RE = re.compile(r"(?<![A-Za-z0-9])((?:PMUL|MUL|SNG|SSNG|WOZ)[0-9]{4,5})(?![0-9])")
_INSPECTOR_RE = re.compile(r"A[0-9]{1,3}|claude")  # pseudonymous annotator IDs, as in levels_round*.csv


class RegistryError(Exception):
    """The registry is invalid; ``problems`` lists every reason."""

    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__(f"{len(problems)} problem(s):\n  " + "\n  ".join(problems))
        self.problems = list(problems)


# --------------------------------------------------------------------------- dialogue IDs


def canonical_dialogue_id(raw: str) -> str:
    """``raw`` in the ``items.jsonl`` form (``PMUL1762.json``); anything malformed raises ValueError.

    No whitespace is stripped: a padded ID in a hand-edited file is a data error to fix, not guess.
    """
    match = _DIALOGUE_ID_RE.fullmatch(raw) if isinstance(raw, str) else None
    if match is None:
        shown = raw[:40] if isinstance(raw, str) else type(raw).__name__
        raise ValueError(f"malformed dialogue ID {shown!r}")
    return f"{match['stem']}.json"


# --------------------------------------------------------------------------- validation


def validate_registry(rows: Sequence[Mapping[str, str]], dialogue_split: Mapping[str, str]) -> list[str]:
    """Every problem in the registry rows, each naming its line or dialogue and the rule.

    ``dialogue_split`` maps canonical dialogue IDs to their split; every row must name a known
    test dialogue in canonical form.
    """
    problems: list[str] = []
    seen: set[tuple[str, str]] = set()
    for line, row in enumerate(rows, start=2):  # line 1 is the header
        if set(row) != set(REGISTRY_FIELDS) or any(not isinstance(value, str) for value in row.values()):
            problems.append(f"line {line}: columns do not match {list(REGISTRY_FIELDS)}")
            continue
        label = f"line {line} ({row['dialogue_id'][:40]!r})"
        problems.extend(f"{label}: {problem}" for problem in row_problems(row, dialogue_split))
        key = (row["dialogue_id"], row["source"])
        if key in seen:
            problems.append(f"{label}: duplicate row for source {row['source']!r}")
        seen.add(key)
    return problems


def row_problems(row: Mapping[str, str], dialogue_split: Mapping[str, str]) -> list[str]:
    problems: list[str] = []
    try:
        canonical = canonical_dialogue_id(row["dialogue_id"])
    except ValueError as error:
        problems.append(str(error))
    else:
        if canonical != row["dialogue_id"]:
            problems.append(f"dialogue_id must be written as {canonical!r}")
        split = dialogue_split.get(canonical)
        if split is None:
            problems.append("dialogue is not in the corpus")
        elif split != "test":
            problems.append(f"dialogue is in the {split} split; only test dialogues are registered")
    problems.extend(_source_reason_problems(row["source"], row["reason"]))
    if _INSPECTOR_RE.fullmatch(row["inspector"]) is None:
        problems.append(f"inspector {row['inspector'][:20]!r} is not a pseudonymous annotator ID (A<n>) or 'claude'")
    if not _is_iso_date(row["inspected_on"]):
        problems.append(f"inspected_on {row['inspected_on'][:20]!r} is not YYYY-MM-DD")
    if row["phase"] not in PHASES:
        problems.append(f"phase {row['phase'][:20]!r} is not one of {list(PHASES)}")
    if row["registry_version"] != REGISTRY_VERSION:
        problems.append(f"registry_version {row['registry_version'][:20]!r} is not {REGISTRY_VERSION!r}")
    return problems


def _source_reason_problems(source: str, reason: str) -> list[str]:
    if source not in SOURCES:
        return [f"source {source[:30]!r} is not one of {list(SOURCES)}"]
    allowed = MANUAL_REASONS if source == "manual" else (SOURCE_REASONS[source],)
    if reason not in allowed:
        return [f"reason {reason[:40]!r} is not allowed for source {source!r} (allowed: {list(allowed)})"]
    return []


def _is_iso_date(value: str) -> bool:
    try:
        return datetime.date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


# --------------------------------------------------------------------------- registry I/O


def load_registry(path: Path, dialogue_split: Mapping[str, str]) -> list[dict[str, str]]:
    """Read and validate the registry; a missing file is an empty registry."""
    if not path.exists():
        return []
    if path.stat().st_size > MAX_REGISTRY_BYTES:
        raise RegistryError([f"{path} is larger than {MAX_REGISTRY_BYTES} bytes; not a registry"])
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, strict=True)
            header = tuple(reader.fieldnames or ())
            if header != REGISTRY_FIELDS:
                raise RegistryError([f"{path}: columns {list(header)} do not match {list(REGISTRY_FIELDS)}"])
            rows = list(reader)
    except UnicodeDecodeError:
        raise RegistryError([f"{path} is not UTF-8"]) from None
    except csv.Error as error:
        raise RegistryError([f"{path}: malformed CSV ({error})"]) from None
    problems = validate_registry(rows, dialogue_split)
    if problems:
        raise RegistryError(problems)
    return rows


def write_registry(path: Path, rows: Sequence[Mapping[str, str]], dialogue_split: Mapping[str, str]) -> None:
    """Validate, sort and write atomically (UTF-8, LF). Invalid rows never reach disk."""
    problems = validate_registry(rows, dialogue_split)
    if problems:
        raise RegistryError(problems)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(_serialize(rows).encode("utf-8"))
    os.replace(tmp, path)


def _serialize(rows: Iterable[Mapping[str, str]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(REGISTRY_FIELDS), lineterminator="\n")
    writer.writeheader()
    writer.writerows(sorted(rows, key=_sort_key))
    return buffer.getvalue()


def _sort_key(row: Mapping[str, str]) -> tuple[str, int]:
    return row["dialogue_id"], SOURCES.index(row["source"])


# --------------------------------------------------------------------------- derived views


def pre_freeze_sha256(rows: Iterable[Mapping[str, str]]) -> str:
    """SHA-256 of the serialized ``pre_freeze`` rows only, so ``post_scoring`` rows never move it."""
    return hashlib.sha256(_serialize(row for row in rows if row["phase"] == "pre_freeze").encode("utf-8")).hexdigest()


def exclusion_reasons(rows: Iterable[Mapping[str, str]]) -> dict[str, str]:
    """Map each dialogue with a ``pre_freeze`` row to the reason of its highest-precedence source."""
    best: dict[str, Mapping[str, str]] = {}
    for row in rows:
        if row["phase"] != "pre_freeze":
            continue
        current = best.get(row["dialogue_id"])
        if current is None or SOURCES.index(row["source"]) < SOURCES.index(current["source"]):
            best[row["dialogue_id"]] = row
    return {dialogue_id: row["reason"] for dialogue_id, row in sorted(best.items())}


# --------------------------------------------------------------------------- corpus index


@dataclass(frozen=True)
class CorpusIndex:
    dialogue_split: dict[str, str]  # canonical dialogue ID -> split
    item_dialogue: dict[str, str]  # DIRECT item_id -> canonical dialogue ID


def load_corpus_index(items_path: Path) -> CorpusIndex:
    """Splits and item-to-dialogue links from ``items.jsonl``, reading only the ID fields."""
    dialogue_split: dict[str, str] = {}
    item_dialogue: dict[str, str] = {}
    with items_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            try:
                dialogue_id = canonical_dialogue_id(record["dialogue_id"])
            except ValueError as error:
                raise ValueError(f"{items_path}:{line_number}: {error}") from None
            if dialogue_split.setdefault(dialogue_id, record["split"]) != record["split"]:
                raise ValueError(f"{items_path}:{line_number}: {dialogue_id} appears in two splits")
            item_dialogue[record["item_id"]] = dialogue_id
    return CorpusIndex(dialogue_split, item_dialogue)


# --------------------------------------------------------------------------- derived sources and register


@dataclass(frozen=True)
class DerivedSource:
    """One recorded inspection. ``sha256`` pins a git-ignored file to its state when inspected."""

    code: str
    path: Path
    kind: str  # "levels" (annotator column), "items_sheet" (dialogue_id column) or "fact_drift" (item_id JSONL)
    inspected_on: str
    inspector: str | None  # None: taken from the file's ``annotator`` column
    sha256: str | None  # None for committed files, which git already versions


# Dates are first exposure: when the items were drawn and Claude sealed its labels, or when Claude
# hand-checked fact-drift flags (spec 006 Problem; docs/data_sources.md "Fact drift in rewrites").
DERIVED_SOURCES = (
    DerivedSource("levels_round1", Path("data/annotations/levels_round1.csv"), "levels", "2026-09-25", None, None),
    DerivedSource("levels_round3", Path("data/annotations/levels_round3.csv"), "levels", "2026-09-26", None, None),
    DerivedSource("obsolete_round3_sheet", Path("data/interim/labeling/round3_items.csv"), "items_sheet",
                  "2026-10-01", "claude", "7a3b8cf94847aa3c1b08eb7471ac4d9e48c7b2eda97837a88dea9f813a478159"),
    DerivedSource("fact_drift_review", Path("data/interim/direct/fact_drift.jsonl"), "fact_drift",
                  "2026-10-01", "claude", "2948c3c1d62a44c2761415b3d3734f9b535cc5196597fd4651d32d15fa5e1acd"),
)


def phase_for(inspected_on: str, freeze_date: str | None) -> str:
    """``pre_freeze`` for inspections strictly before the freeze date (or while none is set)."""
    return "pre_freeze" if freeze_date is None or inspected_on < freeze_date else "post_scoring"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def derive_rows(source: DerivedSource, root: Path, index: CorpusIndex, freeze_date: str | None) -> list[dict[str, str]] | None:
    """Registry rows for the test dialogues in ``source``, or None when its file is absent."""
    path = root / source.path
    if not path.exists():
        return None
    if source.sha256 is not None and file_sha256(path) != source.sha256:
        raise RegistryError([f"{source.path} changed since inspection on {source.inspected_on}; register its dialogues "
                             "with --add and reason source_changed_since_inspection"])
    inspectors: dict[str, str] = {}
    for dialogue_id, inspector in _source_dialogues(source, path, index):
        if index.dialogue_split.get(dialogue_id) == "test":
            inspectors[dialogue_id] = min(inspector, inspectors.get(dialogue_id, inspector))
    return [{"dialogue_id": dialogue_id, "source": source.code, "reason": SOURCE_REASONS[source.code],
             "inspector": inspector, "inspected_on": source.inspected_on,
             "phase": phase_for(source.inspected_on, freeze_date), "registry_version": REGISTRY_VERSION}
            for dialogue_id, inspector in sorted(inspectors.items())]


def _source_dialogues(source: DerivedSource, path: Path, index: CorpusIndex) -> Iterator[tuple[str, str]]:
    if source.kind == "fact_drift":
        for line_number, line in enumerate(_read_text(path).splitlines(), start=1):
            if line.strip():
                record = json.loads(line)
                item_id = record.get("item_id") if isinstance(record, dict) else None
                if not isinstance(item_id, str) or item_id not in index.item_dialogue:
                    raise RegistryError([f"{source.path}:{line_number}: item_id is not in items.jsonl"])
                yield index.item_dialogue[item_id], source.inspector or ""
        return
    rows = _read_csv(path)
    for line_number, row in enumerate(rows, start=2):
        try:
            dialogue_id = canonical_dialogue_id(row.get("dialogue_id") or "")
        except ValueError as error:
            raise RegistryError([f"{source.path}:{line_number}: {error}"]) from None
        yield dialogue_id, source.inspector or row.get("annotator") or ""


def merge_rows(existing: Sequence[Mapping[str, str]], new: Iterable[Mapping[str, str]],
               freeze_date: str | None) -> tuple[list[dict[str, str]], int]:
    """``existing`` plus each new (dialogue, source) row. Committed rows never change.

    A new row identical to a committed one is a no-op, and a different one is an error. A new
    ``pre_freeze`` row after the freeze date is an error: it records an inspection that should
    have been registered before the freeze.
    """
    merged = {(row["dialogue_id"], row["source"]): dict(row) for row in existing}
    problems: list[str] = []
    added = 0
    for row in new:
        key = (row["dialogue_id"], row["source"])
        if key in merged:
            if merged[key] != dict(row):
                problems.append(f"{key[0]} ({key[1]}): differs from the committed row; registry rows never change")
            continue
        if freeze_date is not None and row["phase"] == "pre_freeze":
            problems.append(f"{key[0]} ({key[1]}): freeze recorded on {freeze_date}; "
                            f"an inspection on {row['inspected_on']} can no longer be added as pre_freeze")
            continue
        merged[key] = dict(row)
        added += 1
    if problems:
        raise RegistryError(problems)
    return list(merged.values()), added


def manual_row(raw_dialogue_id: str, reason: str, inspector: str, inspected_on: str,
               freeze_date: str | None) -> dict[str, str]:
    return {"dialogue_id": canonical_dialogue_id(raw_dialogue_id), "source": "manual", "reason": reason,
            "inspector": inspector, "inspected_on": inspected_on, "phase": phase_for(inspected_on, freeze_date),
            "registry_version": REGISTRY_VERSION}


def register(registry_path: Path, index: CorpusIndex, *, root: Path = Path("."),
             sources: Sequence[DerivedSource] = DERIVED_SOURCES, freeze_date: str | None = None,
             extra: Sequence[Mapping[str, str]] = ()) -> dict[str, int]:
    """Regenerate derived rows, add ``extra`` rows, validate and write. Returns counts per source.

    Derived rows that are committed but no longer derivable from a present source are an error,
    so a row can only leave the registry through a deliberate new registry version.
    """
    existing = load_registry(registry_path, index.dialogue_split)
    new: list[dict[str, str]] = []
    problems: list[str] = []
    for source in sources:
        rows = derive_rows(source, root, index, freeze_date)
        if rows is None:
            kept = sum(row["source"] == source.code for row in existing)
            logger.warning("%s is missing; keeping its %d committed row(s)", source.path, kept)
            continue
        derived = {row["dialogue_id"] for row in rows}
        problems.extend(f"{row['dialogue_id']} ({source.code}): committed but no longer derivable from {source.path}"
                        for row in existing if row["source"] == source.code and row["dialogue_id"] not in derived)
        new.extend(rows)
    if problems:
        raise RegistryError(problems)
    merged, added = merge_rows(existing, [*new, *extra], freeze_date)
    write_registry(registry_path, merged, index.dialogue_split)
    counts = Counter(row["source"] for row in merged)
    logger.info("registry: %d row(s), %d dialogue(s), %d added; by source %s", len(merged),
                len({row["dialogue_id"] for row in merged}), added, dict(sorted(counts.items())))
    return {"rows": len(merged), "added": added, **counts}


def resolve_freeze_date(flag: str | None, freeze_file: Path) -> str | None:
    """The freeze date from the WP-08 freeze file, or ``flag`` while none exists; they must agree."""
    recorded = None
    if freeze_file.exists():
        record = json.loads(_read_text(freeze_file))
        recorded = record.get("freeze_date") if isinstance(record, dict) else None
        if not isinstance(recorded, str) or not _is_iso_date(recorded):
            raise ValueError(f"{freeze_file}: freeze_date must be YYYY-MM-DD")
    if flag is not None and not _is_iso_date(flag):
        raise ValueError(f"--freeze-date {flag[:20]!r} is not YYYY-MM-DD")
    if recorded is not None and flag is not None and flag != recorded:
        raise ValueError(f"--freeze-date {flag} disagrees with {freeze_file} ({recorded})")
    return recorded or flag


# --------------------------------------------------------------------------- sheet scan


@dataclass
class ScanReport:
    files: int = 0
    skipped: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)  # "<path>: <problem>"
    test_dialogues: dict[str, int] = field(default_factory=dict)  # path -> distinct test dialogues found


def scan_sheets(root: Path, registry: Sequence[Mapping[str, str]], index: CorpusIndex, *,
                registry_path: Path = DEFAULT_REGISTRY, freeze_date: str | None = None,
                pre_freeze_dirs: Sequence[Path] = PRE_FREEZE_SCAN_DIRS,
                post_scoring_dirs: Sequence[Path] = POST_SCORING_SCAN_DIRS) -> ScanReport:
    """Check every human-facing sheet against the registry (FR4). Reads IDs only; prints no text.

    A sheet in a pre-freeze location needs a ``pre_freeze`` row for each test dialogue in it. A
    sheet in a post-scoring location, or modified on or after the freeze date, needs any row. The
    registry itself lists test IDs by design and is not scanned.
    """
    pre_freeze = {row["dialogue_id"] for row in registry if row["phase"] == "pre_freeze"}
    any_phase = {row["dialogue_id"] for row in registry}
    registry_file = (root / registry_path).resolve()
    report = ScanReport()
    locations = [(d, False) for d in pre_freeze_dirs] + [(d, True) for d in post_scoring_dirs]
    for directory, post_scoring in locations:
        for path in _files_under(root / directory):
            if path.resolve() == registry_file:
                continue
            shown = path.relative_to(root).as_posix()
            try:
                ids = _sheet_dialogue_ids(path)
            except _SkipFile as skip:
                report.skipped.append(f"{shown}: {skip}")
                continue
            except RegistryError as error:
                report.failures.extend(f"{shown}: {problem}" for problem in error.problems)
                continue
            report.files += 1
            tests = sorted(d for d in ids if index.dialogue_split.get(d) == "test")
            report.test_dialogues[shown] = len(tests)
            late = freeze_date is not None and _modified_on(path) >= freeze_date
            allowed = any_phase if post_scoring or late else pre_freeze
            report.failures.extend(f"{shown}: test dialogue {d} is not registered"
                                   f"{'' if post_scoring or late else ' as pre_freeze'}" for d in tests if d not in allowed)
    return report


class _SkipFile(Exception):
    """A file the scan deliberately doesn't parse (the reason is logged)."""


def _files_under(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    files = []
    for current, dirnames, filenames in os.walk(directory, followlinks=False):
        dirnames.sort()
        files.extend(Path(current) / name for name in sorted(filenames))
    return [path for path in files if not path.is_symlink() and not path.name.endswith(".tmp")]


def _sheet_dialogue_ids(path: Path) -> set[str]:
    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        prefix = path.stem.rsplit("_", 1)[0]
        if not (path.parent / f"{prefix}_items.csv").exists():
            raise RegistryError([f"no sibling {prefix}_items.csv; the scan can't read .xlsx, so export its IDs as CSV"])
        raise _SkipFile(f"covered by {prefix}_items.csv")
    if suffix == ".csv":
        # Every cell, including any beyond the header: a ragged row is still readable for IDs.
        try:
            rows = list(csv.reader(io.StringIO(_read_text(path), newline=""), strict=True))
        except csv.Error as error:
            raise RegistryError([f"malformed CSV ({error})"]) from None
        keys = (path.parent / "key.csv", path.parent / f"{path.stem}_sheet_info.json")  # the spec 003 key
        if rows and "row_id" in rows[0] and not any(key.exists() for key in keys):
            raise RegistryError(["a blind row_id sheet needs a sibling key.csv or "
                                 f"{path.stem}_sheet_info.json to resolve its dialogues"])
        return {canonical_dialogue_id(m) for row in rows for cell in row for m in _EMBEDDED_ID_RE.findall(cell)}
    if suffix in TEXT_SUFFIXES:
        return {canonical_dialogue_id(m) for m in _EMBEDDED_ID_RE.findall(_read_text(path))}
    raise _SkipFile(f"unscanned file type {suffix or '(none)'}")


def _modified_on(path: Path) -> str:
    return datetime.date.fromtimestamp(path.stat().st_mtime).isoformat()


def _read_text(path: Path) -> str:
    if path.stat().st_size > MAX_SHEET_BYTES:
        raise RegistryError([f"larger than {MAX_SHEET_BYTES} bytes"])
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        raise RegistryError(["not UTF-8"]) from None


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        rows = list(csv.DictReader(io.StringIO(_read_text(path), newline=""), strict=True))
    except csv.Error as error:
        raise RegistryError([f"malformed CSV ({error})"]) from None
    if any(None in row for row in rows):
        raise RegistryError(["a row has more cells than the header"])
    return rows


# --------------------------------------------------------------------------- transcript scan


TRANSCRIPT_SUFFIX = ".jsonl"
_CHUNK_BYTES = 1 << 20
_OVERLAP_BYTES = 32  # longer than any dialogue ID, so an ID split across chunks is still found


def scan_transcripts(directories: Sequence[Path], index: CorpusIndex) -> tuple[list[str], int]:
    """Canonical test dialogue IDs mentioned in session logs under ``directories``, and files read.

    Logs are read as raw bytes in overlapping chunks, so a multi-megabyte line is never held whole.
    Nothing but matched IDs leaves this function. Symlinks are not followed.
    """
    found: set[str] = set()
    files = 0
    for directory in directories:
        if not directory.is_dir():
            raise ValueError(f"{directory} is not a directory")
        for path in _files_under(directory):
            if path.suffix != TRANSCRIPT_SUFFIX:
                continue
            files += 1
            found.update(stem for stem in _ids_in_file(path))
    tests = sorted(d for d in map(canonical_dialogue_id, found) if index.dialogue_split.get(d) == "test")
    return tests, files


_EMBEDDED_ID_BYTES_RE = re.compile(_EMBEDDED_ID_RE.pattern.encode("ascii"))


def _ids_in_file(path: Path) -> Iterator[str]:
    """Every embedded ID in ``path``, read in windows of one chunk plus the previous window's tail.

    Two guards make the windows exact. A match touching the window's end may be a cut-off ID
    (``SNG0123`` from ``SNG01234``), so it is deferred to the next window, whose tail holds it
    whole; at end of file it is final. A match at the very start of a later window has lost the
    character before it (``MUL1234`` from ``PMUL1234``), and the previous window already judged it
    with that context, so it is skipped. Duplicates are harmless; the caller collects a set.
    """
    tail, tail_offset = b"", 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(_CHUNK_BYTES)
            at_eof = not chunk
            window = tail + chunk
            for match in _EMBEDDED_ID_BYTES_RE.finditer(window):
                lost_context = match.start() == 0 and tail_offset > 0
                maybe_cut = match.end() == len(window) and not at_eof
                if not (lost_context or maybe_cut):
                    yield match.group(1).decode("ascii")
            if at_eof:
                return
            tail_offset += len(window) - min(_OVERLAP_BYTES, len(window))
            tail = window[-_OVERLAP_BYTES:]


def transcript_rows(test_ids: Sequence[str], existing: Sequence[Mapping[str, str]], inspected_on: str,
                    freeze_date: str | None) -> list[dict[str, str]]:
    """New ``claude_session`` rows; a dialogue already registered from a session keeps its first date."""
    seen = {row["dialogue_id"] for row in existing if row["source"] == "claude_session"}
    return [{"dialogue_id": dialogue_id, "source": "claude_session", "reason": SOURCE_REASONS["claude_session"],
             "inspector": "claude", "inspected_on": inspected_on, "phase": phase_for(inspected_on, freeze_date),
             "registry_version": REGISTRY_VERSION}
            for dialogue_id in test_ids if dialogue_id not in seen]


# --------------------------------------------------------------------------- split checks and duplicate dialogues


DEFAULT_DIALOGUES = Path("data/interim/direct/dialogues.jsonl")
DEFAULT_MULTIWOZ_DIR = Path("data/raw/multiwoz/MultiWOZ_2.1")
# The official MultiWOZ 2.1 lists, pinned as in data/sources.toml.
LIST_FILES = {"test": ("testListFile.txt", "56fff5bf8c7b0a64fba8672241a7bdd947c3a58986bf06f46d37f33288f73ce0"),
              "dev": ("valListFile.txt", "8e19240b90576c3ed83a0d44ef5e7ca8916e47356662ed4621e6b39d8c327d80")}
SPLITS = ("train", "dev", "test")
CHECK_RULES = ("one_split_per_dialogue", "disjoint_splits", "test_in_test_list", "dev_in_val_list",
               "train_not_in_lists", "donor_same_split")
DUP_VERSION = "dup-v1"
DUP_MIN_USER_TURNS = 2  # one-turn dialogues are mostly templated openers, so equality says nothing
DUP_DECISION_RATE = 0.01  # above this share of test dialogues, Sandy decides before the freeze (FR8)
DUPLICATE_DIALOGUE_REASON = "cross_split_duplicate_dialogue"
_NON_ALNUM_RE = re.compile(r"[\W_]+")


def dup_v1(text: str) -> str:
    """``dup-v1``: NFKC, casefold, each run of non-alphanumeric characters to one space, strip."""
    return _NON_ALNUM_RE.sub(" ", unicodedata.normalize("NFKC", text).casefold()).strip()


@dataclass(frozen=True)
class SplitRecord:
    item_id: str
    dialogue_id: str  # canonical
    split: str
    donor_dialogue_id: str | None  # canonical; None without a mismatch donor


def split_records(items: Iterable[Mapping[str, Any]]) -> list[SplitRecord]:
    """The ID fields of every item. Unlike ``load_corpus_index`` this never stops at a split conflict,
    so ``check`` can count every failure."""
    records = []
    for number, item in enumerate(items, start=1):
        try:
            mismatch = item.get("mismatch")
            donor = canonical_dialogue_id(mismatch["donor_dialogue_id"]) if mismatch else None
            records.append(SplitRecord(item["item_id"], canonical_dialogue_id(item["dialogue_id"]), item["split"], donor))
        except ValueError as error:
            raise ValueError(f"item {number}: {error}") from None
        if item["split"] not in SPLITS:
            raise ValueError(f"item {number}: split {str(item['split'])[:20]!r} is not one of {list(SPLITS)}")
    return records


def read_list_file(path: Path, expected_sha256: str | None) -> set[str]:
    """Canonical IDs in a MultiWOZ list file; refuses a file that differs from its pin."""
    if expected_sha256 is not None and file_sha256(path) != expected_sha256:
        raise ValueError(f"{path} does not match its pinned SHA-256 (data/sources.toml)")
    ids = set()
    for number, token in enumerate(_read_text(path).split(), start=1):
        try:
            ids.add(canonical_dialogue_id(token))
        except ValueError as error:
            raise ValueError(f"{path}: entry {number}: {error}") from None
    return ids


def load_user_turns(dialogues_path: Path) -> dict[str, list[str]]:
    """Each dialogue's user turns, in order, from ``dialogues.jsonl``."""
    turns: dict[str, list[str]] = {}
    with dialogues_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            try:
                dialogue_id = canonical_dialogue_id(record["dialogue_id"])
            except ValueError as error:
                raise ValueError(f"{dialogues_path}:{line_number}: {error}") from None
            turns[dialogue_id] = [turn["text"] for turn in record["turns"] if turn["speaker"] == "user"]
    return turns


@dataclass
class CheckReport:
    failures: dict[str, int]  # every rule in CHECK_RULES -> offending IDs
    first: dict[str, str]  # failing rule -> its first offending ID in sorted order
    test_dialogues: int
    duplicate_test: dict[str, str]  # test dialogue -> the split it duplicates ("train" before "dev")
    duplicate_dev_train: int  # reported only

    @property
    def ok(self) -> bool:
        return not any(self.failures.values())

    @property
    def duplicate_test_rate(self) -> float:
        return len(self.duplicate_test) / self.test_dialogues if self.test_dialogues else 0.0

    @property
    def needs_decision(self) -> bool:
        return self.duplicate_test_rate > DUP_DECISION_RATE


def check_splits(records: Sequence[SplitRecord], test_list: Collection[str], val_list: Collection[str],
                 user_turns: Mapping[str, Sequence[str]]) -> CheckReport:
    """FR7 split rules and FR8 cross-split duplicate dialogues, independent of the dataset builder."""
    splits_of: dict[str, set[str]] = {}
    for record in records:
        splits_of.setdefault(record.dialogue_id, set()).add(record.split)
    by_split = {split: {d for d, splits in splits_of.items() if split in splits} for split in SPLITS}
    offenders = {
        "one_split_per_dialogue": {d for d, splits in splits_of.items() if len(splits) > 1},
        "disjoint_splits": set().union(*(by_split[a] & by_split[b] for a, b in itertools.combinations(SPLITS, 2))),
        "test_in_test_list": by_split["test"] - set(test_list),
        "dev_in_val_list": by_split["dev"] - set(val_list),
        "train_not_in_lists": by_split["train"] & (set(test_list) | set(val_list)),
        "donor_same_split": {r.item_id for r in records
                             if r.donor_dialogue_id is not None and splits_of.get(r.donor_dialogue_id) != {r.split}},
    }
    duplicate_test, duplicate_dev_train = _duplicate_dialogues(splits_of, user_turns)
    return CheckReport({rule: len(offenders[rule]) for rule in CHECK_RULES},
                       {rule: min(offenders[rule]) for rule in CHECK_RULES if offenders[rule]},
                       len(by_split["test"]), duplicate_test, duplicate_dev_train)


def _duplicate_dialogues(splits_of: Mapping[str, set[str]],
                         user_turns: Mapping[str, Sequence[str]]) -> tuple[dict[str, str], int]:
    """Dialogues whose ``dup-v1`` user-turn sequence equals one in another split (at least 2 user turns)."""
    split_of = {d: min(splits, key=SPLITS.index) for d, splits in splits_of.items()}
    keys: dict[str, str] = {}
    key_splits: dict[str, set[str]] = {}
    for dialogue_id, turns in user_turns.items():
        if dialogue_id not in split_of or len(turns) < DUP_MIN_USER_TURNS:
            continue
        key = hashlib.sha256("\n".join(map(dup_v1, turns)).encode("utf-8")).hexdigest()
        keys[dialogue_id] = key
        key_splits.setdefault(key, set()).add(split_of[dialogue_id])
    duplicate_test = {}
    for dialogue_id, key in sorted(keys.items()):
        if split_of[dialogue_id] == "test":
            other = next((split for split in ("train", "dev") if split in key_splits[key]), None)
            if other is not None:
                duplicate_test[dialogue_id] = other
    dev_train = sum(split_of[d] == "dev" and "train" in key_splits[key] for d, key in keys.items())
    return duplicate_test, dev_train


def run_check(items: Sequence[Mapping[str, Any]], dialogues_path: Path, multiwoz_dir: Path,
              *, pinned: bool = True) -> CheckReport:
    lists = {split: read_list_file(multiwoz_dir / name, sha if pinned else None)
             for split, (name, sha) in LIST_FILES.items()}
    return check_splits(split_records(items), lists["test"], lists["dev"], load_user_turns(dialogues_path))


def log_check(report: CheckReport) -> None:
    logger.info("check: %d test dialogue(s); failures by rule %s", report.test_dialogues, report.failures)
    for rule, first in report.first.items():
        logger.error("%s failed for %d ID(s); first %s", rule, report.failures[rule], first)
    logger.info("duplicate dialogues (%s, >= %d user turns): %d test (%.2f%%), %d dev-train (reported only)",
                DUP_VERSION, DUP_MIN_USER_TURNS, len(report.duplicate_test), 100 * report.duplicate_test_rate,
                report.duplicate_dev_train)
    if report.needs_decision:
        logger.warning("test duplicates exceed %.0f%%: needs_decision; Sandy decides before the freeze",
                       100 * DUP_DECISION_RATE)


# --------------------------------------------------------------------------- test audit


AUDIT_SCHEMA_VERSION = "split-audit-v1"
AUDIT_POLICY = "direct_variants_v1"
AUDIT_FIELDS = ("example_id", "item_id", "dialogue_id", "variant", "mismatch_set", "primary", "exclusion",
                "dup_exact", "donor_inspected")
DEFAULT_CONTEXT_MANIFEST = Path("data/manifests/contexts_test.csv")
DEFAULT_AUDIT = Path("data/manifests/split_audit_test.csv")
DEFAULT_AUDIT_SUMMARY = Path("data/manifests/split_audit_test_summary.json")
MAX_AUDIT_BYTES = 64 << 20  # the test manifests are a few megabytes
# Disclosed in the summary but outside its content hash, so post-scoring inspection never moves it.
_UNHASHED_SUMMARY_KEYS = ("content_sha256", "disclosure")


def exclusion_reason(dialogue_id: str, inspected: Mapping[str, str], duplicates: Collection[str]) -> str:
    """Why a test dialogue leaves the primary set ("" if it stays). Inspection outranks duplication."""
    if dialogue_id in inspected:
        return f"inspected:{inspected[dialogue_id]}"
    return DUPLICATE_DIALOGUE_REASON if dialogue_id in duplicates else ""


def exclusion_codes() -> frozenset[str]:
    """Every exclusion value an audit row may carry."""
    reasons = {*SOURCE_REASONS.values(), *MANUAL_REASONS}
    return frozenset({DUPLICATE_DIALOGUE_REASON, *(f"inspected:{reason}" for reason in reasons)})


def read_context_manifest(manifest_path: Path, items_sha256: str, dialogues_sha256: str) -> tuple[dict[str, int], str]:
    """``example_id -> mismatch_set`` from spec 004's committed test manifest, and the manifest's SHA-256.

    Refuses a manifest that its summary doesn't vouch for, or one built from other inputs.
    """
    summary_path = manifest_path.with_name(f"{manifest_path.stem}_summary.json")
    data = read_bounded(manifest_path)
    summary = json.loads(read_bounded(summary_path).decode("utf-8"))
    sha = hashlib.sha256(data).hexdigest()
    if not isinstance(summary, dict) or summary.get("manifest_sha256") != sha:
        raise ValueError(f"{manifest_path} does not match manifest_sha256 in {summary_path.name}")
    inputs = summary.get("inputs")
    if not isinstance(inputs, dict) or (inputs.get("items_sha256"), inputs.get("dialogues_sha256")) != (
            items_sha256, dialogues_sha256):
        raise ValueError(f"{manifest_path} was built from other items/dialogues; rebuild the spec 004 manifest first")
    try:
        rows = list(csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""), strict=True))
        return {row["example_id"]: int(row["mismatch_set"]) for row in rows}, sha
    except (csv.Error, KeyError, ValueError, UnicodeDecodeError):
        raise ValueError(f"{manifest_path} is not a spec 004 context manifest") from None


def read_bounded(path: Path) -> bytes:
    if path.stat().st_size > MAX_AUDIT_BYTES:
        raise ValueError(f"{path} is larger than {MAX_AUDIT_BYTES} bytes")
    return path.read_bytes()


def build_audit(items: Sequence[Mapping[str, Any]], registry: Sequence[Mapping[str, str]],
                duplicate_test: Collection[str], manifest: Mapping[str, int]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """One row per genuine test example (spec 004's set, checked against its manifest) and the counts.

    ``primary`` follows the ``pre_freeze`` registry rows and the duplicate dialogues; ``dup_exact`` and
    ``donor_inspected`` are flags that never change it. No text leaves this function.
    """
    examples, _ = build_examples(items, "test", AUDIT_POLICY, require_context=True)
    by_id = {item["item_id"]: item for item in items}
    mismatch = {e.example_id: int(in_mismatch_set(by_id[e.item_id])) for e in examples}
    if mismatch != dict(manifest):
        missing, extra = len(manifest.keys() - mismatch.keys()), len(mismatch.keys() - manifest.keys())
        differ = sum(manifest[k] != mismatch[k] for k in manifest.keys() & mismatch.keys())
        raise ValueError(f"test examples differ from the spec 004 manifest: {missing} missing, {extra} extra, "
                         f"{differ} with another mismatch_set")
    inspected = exclusion_reasons(registry)
    duplicates = frozenset(duplicate_test)
    train_utterances = {dup_v1(item[f"{variant}_utterance"]) for item in items if item["split"] == "train"
                        for variant in VARIANTS} - {""}
    vocab = build_vocabulary(items)
    rows, levels = [], {}
    for example in sorted(examples, key=lambda e: e.example_id):
        item = by_id[example.item_id]
        dialogue_id = canonical_dialogue_id(example.dialogue_id)
        reason = exclusion_reason(dialogue_id, inspected, duplicates)
        donor = item["mismatch"]["donor_dialogue_id"] if mismatch[example.example_id] else None
        normalized = dup_v1(example.text)
        rows.append({"example_id": example.example_id, "item_id": example.item_id, "dialogue_id": dialogue_id,
                     "variant": example.variant, "mismatch_set": mismatch[example.example_id],
                     "primary": int(not reason), "exclusion": reason,
                     "dup_exact": int(bool(normalized) and normalized in train_utterances),
                     "donor_inspected": int(donor is not None and canonical_dialogue_id(donor) in inspected)})
        levels[example.example_id] = level_item(item, example.variant, vocab).level
    test_items = [item for item in items if item["split"] == "test"]
    return rows, _audit_counts(rows, test_items, inspected, duplicates, levels)


def _audit_counts(rows: Sequence[Mapping[str, Any]], test_items: Sequence[Mapping[str, Any]],
                  inspected: Mapping[str, str], duplicates: Collection[str], levels: Mapping[str, str]) -> dict[str, Any]:
    def by_reason(values: Iterable[str]) -> dict[str, int]:
        return dict(sorted(Counter(value for value in values if value).items()))

    def flag_rate(group: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        flagged = sum(row["dup_exact"] for row in group)
        return {"flagged": flagged, "n": len(group), "rate": round(flagged / len(group), 4) if group else None}

    def reason_of(item: Mapping[str, Any]) -> str:
        return exclusion_reason(canonical_dialogue_id(item["dialogue_id"]), inspected, duplicates)

    primary = [row for row in rows if row["primary"]]
    dialogue_reasons = {canonical_dialogue_id(item["dialogue_id"]): reason_of(item) for item in test_items}
    return {
        "test": {"dialogues": len(dialogue_reasons), "items": len(test_items), "genuine_examples": len(rows),
                 "mismatch_examples": sum(row["mismatch_set"] for row in rows)},
        "excluded": {"dialogues": by_reason(dialogue_reasons.values()), "items": by_reason(map(reason_of, test_items)),
                     "examples": by_reason(row["exclusion"] for row in rows)},
        "primary": {"genuine": len(primary), "mismatch": sum(row["mismatch_set"] for row in primary)},
        "dup_exact": {
            "scope": "primary_genuine", "overall": flag_rate(primary),
            "by_variant": {v: flag_rate([r for r in primary if r["variant"] == v])
                           for v in sorted({r["variant"] for r in primary})},
            "by_rule_level": {level: flag_rate([r for r in primary if levels[r["example_id"]] == level])
                              for level in sorted({levels[r["example_id"]] for r in primary})},
        },
        "donor_inspected": {"primary_mismatch_examples": sum(row["donor_inspected"] for row in primary)},
    }


def audit_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    """CSV bytes, UTF-8 without BOM, LF line endings on every OS."""
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=AUDIT_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def audit_content_sha256(summary: Mapping[str, Any]) -> str:
    """Hash of the summary minus its unhashed keys; the summary holds ``audit_sha256``, so it covers the CSV."""
    content = {key: value for key, value in summary.items() if key not in _UNHASHED_SUMMARY_KEYS}
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def audit_summary(csv_bytes: bytes, counts: Mapping[str, Any], check: CheckReport,
                  registry: Sequence[Mapping[str, str]], inputs: Mapping[str, str]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "schema_version": AUDIT_SCHEMA_VERSION, "split": "test", "policy": AUDIT_POLICY,
        "registry_version": REGISTRY_VERSION, "dup_version": DUP_VERSION, "rules_version": RULES_VERSION,
        "inputs": dict(sorted(inputs.items())), "audit_file": DEFAULT_AUDIT.name,
        "audit_sha256": hashlib.sha256(csv_bytes).hexdigest(), **counts,
        "cross_split_duplicates": {"min_user_turns": DUP_MIN_USER_TURNS, "test_dialogues": len(check.duplicate_test),
                                   "test_rate": round(check.duplicate_test_rate, 4),
                                   "dev_train_dialogues": check.duplicate_dev_train,
                                   "decision_rate": DUP_DECISION_RATE},
        "needs_decision": check.needs_decision,
    }
    summary["content_sha256"] = audit_content_sha256(summary)
    summary["disclosure"] = {"post_scoring_dialogues": len({row["dialogue_id"] for row in registry
                                                            if row["phase"] == "post_scoring"})}
    return summary


def summary_bytes(summary: Mapping[str, Any]) -> bytes:
    return (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode("utf-8")


@dataclass(frozen=True)
class AuditPaths:
    items: Path = DEFAULT_ITEMS
    dialogues: Path = DEFAULT_DIALOGUES
    multiwoz_dir: Path = DEFAULT_MULTIWOZ_DIR
    registry: Path = DEFAULT_REGISTRY
    context_manifest: Path = DEFAULT_CONTEXT_MANIFEST
    audit: Path = DEFAULT_AUDIT
    summary: Path = DEFAULT_AUDIT_SUMMARY


def build_audit_files(paths: AuditPaths, *, pinned: bool = True) -> tuple[bytes, bytes, dict[str, Any]]:
    """The audit CSV and summary bytes from the pinned inputs; refuses when ``check`` fails."""
    items = load_items(paths.items)
    check = run_check(items, paths.dialogues, paths.multiwoz_dir, pinned=pinned)
    log_check(check)
    if not check.ok:
        raise ValueError("the split check failed, so the audit is not built")
    dialogue_split = {record.dialogue_id: record.split for record in split_records(items)}
    registry = load_registry(paths.registry, dialogue_split)
    items_sha, dialogues_sha = file_sha256(paths.items), file_sha256(paths.dialogues)
    manifest, manifest_sha = read_context_manifest(paths.context_manifest, items_sha, dialogues_sha)
    rows, counts = build_audit(items, registry, check.duplicate_test, manifest)
    data = audit_bytes(rows)
    inputs = {"items_sha256": items_sha, "dialogues_sha256": dialogues_sha,
              "test_list_sha256": file_sha256(paths.multiwoz_dir / LIST_FILES["test"][0]),
              "val_list_sha256": file_sha256(paths.multiwoz_dir / LIST_FILES["dev"][0]),
              "registry_pre_freeze_sha256": pre_freeze_sha256(registry), "context_manifest_sha256": manifest_sha}
    summary = audit_summary(data, counts, check, registry, inputs)
    return data, summary_bytes(summary), summary


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def run_audit(paths: AuditPaths, *, verify: bool = False, pinned: bool = True) -> int:
    data, summary_data, summary = build_audit_files(paths, pinned=pinned)
    if verify:
        stale = [path for path, expected in ((paths.audit, data), (paths.summary, summary_data))
                 if not path.exists() or path.read_bytes() != expected]
        for path in stale:
            logger.error("%s does not match a fresh build from the pinned inputs", path)
        if not stale:
            logger.info("%s and its summary match a fresh build (content %s)", paths.audit, summary["content_sha256"][:12])
        return 1 if stale else 0
    _write_atomic(paths.audit, data)
    _write_atomic(paths.summary, summary_data)
    logger.info("test audit: %d genuine examples, primary %s; excluded dialogues %s, examples %s",
                summary["test"]["genuine_examples"], summary["primary"], summary["excluded"]["dialogues"],
                summary["excluded"]["examples"])
    logger.info("dup_exact (primary) %s; donor_inspected %s; needs_decision %s; post-scoring dialogues %d",
                summary["dup_exact"]["overall"], summary["donor_inspected"]["primary_mismatch_examples"],
                summary["needs_decision"], summary["disclosure"]["post_scoring_dialogues"])
    logger.info("wrote %s and %s (content %s)", paths.audit, paths.summary, summary["content_sha256"][:12])
    return 0


# --------------------------------------------------------------------------- CLI


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.data.split_audit", description=__doc__.split("\n")[0])
    parser.add_argument("command", choices=("register", "scan", "check", "audit"))
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--items", type=Path, default=DEFAULT_ITEMS)
    parser.add_argument("--dialogues", type=Path, default=DEFAULT_DIALOGUES)
    parser.add_argument("--multiwoz-dir", type=Path, default=DEFAULT_MULTIWOZ_DIR,
                        help="holds the pinned testListFile.txt and valListFile.txt")
    parser.add_argument("--context-manifest", type=Path, default=DEFAULT_CONTEXT_MANIFEST,
                        help="spec 004's committed test manifest (its _summary.json sits beside it)")
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT.parent,
                        help="audit: where split_audit_test.csv and its summary are written")
    parser.add_argument("--verify", action="store_true", help="audit: rebuild and compare with the files on disk")
    parser.add_argument("--freeze-date", help="YYYY-MM-DD; only until the WP-08 freeze file records one")
    parser.add_argument("--add", metavar="DIALOGUE", help="register: add one manual row")
    parser.add_argument("--reason", choices=MANUAL_REASONS, help="register --add: the manual reason")
    parser.add_argument("--inspector", help="register --add: pseudonymous annotator ID (A<n>) or 'claude'")
    parser.add_argument("--on", help="register --add / scan --register: inspection date YYYY-MM-DD "
                                     "(transcripts default to today, written once)")
    parser.add_argument("--transcripts", type=Path, nargs="+", metavar="DIR",
                        help="scan: session-log directories instead of sheets (local, one-time, IDs only)")
    parser.add_argument("--register", action="store_true", help="scan --transcripts: add the hits to the registry")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        if args.command == "check":
            report = run_check(load_items(args.items), args.dialogues, args.multiwoz_dir)
            log_check(report)
            return 0 if report.ok else 1
        if args.command == "audit":
            return run_audit(AuditPaths(args.items, args.dialogues, args.multiwoz_dir, args.registry,
                                        args.context_manifest, args.audit_dir / DEFAULT_AUDIT.name,
                                        args.audit_dir / DEFAULT_AUDIT_SUMMARY.name), verify=args.verify)
        freeze_date = resolve_freeze_date(args.freeze_date, FREEZE_FILE)
        index = load_corpus_index(args.items)
        if args.command == "register":
            extra = []
            if args.add is not None:
                if not (args.reason and args.inspector and args.on):
                    parser.error("--add needs --reason, --inspector and --on")
                extra.append(manual_row(args.add, args.reason, args.inspector, args.on, freeze_date))
            register(args.registry, index, freeze_date=freeze_date, extra=extra)
            return 0
        registry = load_registry(args.registry, index.dialogue_split)
        if args.transcripts:
            return _run_transcript_scan(args, registry, index, freeze_date)
        report = scan_sheets(Path("."), registry, index, registry_path=args.registry, freeze_date=freeze_date)
        for skipped in report.skipped:
            logger.info("skipped %s", skipped)
        logger.info("scanned %d file(s); %d hold test dialogues", report.files,
                    sum(1 for n in report.test_dialogues.values() if n))
        for failure in report.failures:
            logger.error("%s", failure)
        return 1 if report.failures else 0
    except RegistryError as error:
        for problem in error.problems:
            logger.error("%s", problem)
        return 1
    except (OSError, ValueError, KeyError) as error:
        logger.error("%s", error)
        return 1


def _run_transcript_scan(args: argparse.Namespace, registry: Sequence[Mapping[str, str]], index: CorpusIndex,
                         freeze_date: str | None) -> int:
    tests, files = scan_transcripts(args.transcripts, index)
    unregistered = sorted(set(tests) - {row["dialogue_id"] for row in registry})
    logger.info("read %d log file(s): %d test dialogue(s) mentioned, %d not yet registered",
                files, len(tests), len(unregistered))
    for dialogue_id in unregistered:
        print(dialogue_id)
    if args.register:
        on = args.on or datetime.date.today().isoformat()
        if not _is_iso_date(on):
            raise ValueError(f"--on {on[:20]!r} is not YYYY-MM-DD")
        rows = transcript_rows(tests, registry, on, freeze_date)
        merged, added = merge_rows(registry, rows, freeze_date)
        write_registry(args.registry, merged, index.dialogue_split)
        logger.info("registered %d new claude_session row(s)", added)
    return 0


if __name__ == "__main__":
    sys.exit(main())
