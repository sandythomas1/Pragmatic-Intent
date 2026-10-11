"""The contextual-annotation item registry and the dialogue pilot draw (spec 003 FR1, FR2).

The registry, ``data/annotations/context_items.csv``, is committed and text-free. It lists every
item that enters the contextual passes, with the provenance needed to reconstruct and audit it:

* Dialogue items are original MultiWOZ user turns, ``d:<dialogue stem>:t<NN>``. Their target hash
  is taken from ``dialogues.jsonl`` (the original MultiWOZ text), not from DIRECT's copy, so that
  validation can recompute it from the same source.
* Literary items are screened-in spec 002 candidates, keyed by ``candidate_id`` (registered in T3).

Draw rule (FR1): dialogues are drawn uniformly without replacement from the dev pool, then one user
turn with ``turn_index > 0`` uniformly within each. The pool excludes every dialogue that any
``levels_round*.csv`` touched (Sandy has read them), every dialogue already registered, and
dialogues with no user turn after the first. Nothing about the turn's wording, acts or any model
output enters the draw, and unlike ``levels.eligible_items`` it does not filter on mismatch-donor
availability (spec 001 AC-06).
"""

from __future__ import annotations

import datetime
import hashlib
import random
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from src.annotation import context_schema as cs
from src.annotation.levels import AnnotationError, read_csv, write_csv
from src.data.direct_dataset import Turn

REGISTRY_FILE = "context_items.csv"
REGISTRY_FIELDS = (
    "item_id",
    "stratum",
    "batch",
    "split",
    "group_id",
    "source_ref",
    "target_sha256",
    "draw",
    "seed",
    "pool_size",
    "inputs_sha256",
    "registered_on",
    "protocol_version",
)
SPLITS = ("dev",)  # untouched test groups are collected under a later protocol (WP-04)
DRAW_FOR_STRATUM = {"dialogue": "drawn", "literary": "screened"}
DEFAULT_DRAW_SEED = 20261011

_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_DIGITS_RE = re.compile(r"[0-9]{1,12}")
_FAMILY_ID_RE = re.compile(r"[a-z0-9][a-z0-9:_-]{0,79}")  # the spec 002 family ID shape
# Dialogue stems start alphanumeric, so no committed value can begin with a spreadsheet formula prefix.
_SOURCE_REF_RE = re.compile(r"(?P<dialogue>[A-Za-z0-9][A-Za-z0-9_-]{0,39}\.json)#(?P<turn>[0-9]{1,3})")
_LITERARY_SOURCE_RE = re.compile(r"[a-z][a-z0-9_]{0,39}")  # a data/sources.toml source key


class RegistryError(Exception):
    """The registry is invalid or a draw can't proceed; ``problems`` lists every reason."""

    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__(f"{len(problems)} problem(s):\n  " + "\n  ".join(problems))
        self.problems = list(problems)


# --------------------------------------------------------------------------- registry I/O


def target_sha256(text: str) -> str:
    """Hash of a target exactly as it appears in its source (UTF-8, no normalization)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def load_registry(path: Path) -> list[dict[str, str]]:
    """Read and validate the registry; a missing file is an empty registry."""
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            header = handle.readline().strip().split(",")
    except UnicodeDecodeError:
        raise RegistryError([f"{path} is not UTF-8"]) from None
    if tuple(header) != REGISTRY_FIELDS:
        raise RegistryError([f"{path}: columns {header} do not match {list(REGISTRY_FIELDS)}"])
    try:
        rows = read_csv(path)
    except AnnotationError as error:
        raise RegistryError([str(error)]) from None
    problems = validate_registry(rows)
    if problems:
        raise RegistryError(problems)
    return rows


def write_registry(path: Path, rows: Sequence[Mapping[str, str]]) -> None:
    """Validate, sort by ``item_id`` and write atomically. Invalid rows never reach disk."""
    problems = validate_registry(rows)
    if problems:
        raise RegistryError(problems)
    write_csv(path, REGISTRY_FIELDS, sorted(rows, key=lambda row: row["item_id"]))


def validate_registry(rows: Sequence[Mapping[str, str]]) -> list[str]:
    """Every problem in the registry rows, each naming its item and rule."""
    problems: list[str] = []
    seen: set[str] = set()
    group_splits: dict[str, set[str]] = defaultdict(set)
    for index, row in enumerate(rows, start=2):  # line 1 is the header
        label = row.get("item_id") or f"line {index}"
        if set(row) != set(REGISTRY_FIELDS) or any(value is None for value in row.values()):
            problems.append(f"{label}: columns do not match the registry header")
            continue
        if row["item_id"] in seen:
            problems.append(f"{label}: duplicate item_id")
        seen.add(row["item_id"])
        problems.extend(f"{label}: {problem}" for problem in _row_problems(row))
        group_splits[row["group_id"]].add(row["split"])
    problems.extend(
        f"group {group}: spans splits {sorted(splits)}" for group, splits in sorted(group_splits.items()) if len(splits) > 1
    )
    return problems


def _row_problems(row: Mapping[str, str]) -> list[str]:
    problems: list[str] = []
    checks = (
        lambda: cs.item_id(row["item_id"]),
        lambda: cs.require_enum(row["stratum"], cs.STRATA, "stratum"),
        lambda: cs.batch_id(row["batch"]),
        lambda: cs.require_enum(row["split"], SPLITS, "split"),
        lambda: cs.require_match(_SHA256_RE, row["target_sha256"], "target_sha256"),
        lambda: cs.require_enum(row["protocol_version"], (cs.PROTOCOL_VERSION,), "protocol_version"),
        lambda: _check_date(row["registered_on"]),
    )
    for check in checks:
        try:
            check()
        except cs.SchemaError as error:
            problems.append(str(error))
    if row["stratum"] == "dialogue":
        problems.extend(_dialogue_row_problems(row))
    elif row["stratum"] == "literary":
        problems.extend(_literary_row_problems(row))
    return problems


def _dialogue_row_problems(row: Mapping[str, str]) -> list[str]:
    problems: list[str] = []
    match = _SOURCE_REF_RE.fullmatch(row["source_ref"])
    if match is None:
        problems.append(f"source_ref {row['source_ref']!r} is not <dialogue>.json#<turn>")
    else:
        dialogue_id, turn = match["dialogue"], int(match["turn"])
        expected_item = f"d:{dialogue_id.removesuffix('.json')}:t{turn:02d}"
        if row["item_id"] != expected_item:
            problems.append(f"item_id does not match source_ref (expected {expected_item})")
        if row["group_id"] != dialogue_id.removesuffix(".json"):
            problems.append("group_id is not the dialogue of source_ref")
        if turn == 0:
            problems.append("turn 0 has no prior context and is never drawn")
    if row["draw"] != "drawn":
        problems.append(f"draw {row['draw']!r} must be 'drawn' for a dialogue item")
    for field in ("seed", "pool_size"):
        if _DIGITS_RE.fullmatch(row[field]) is None:
            problems.append(f"{field} {row[field]!r} must be a non-negative integer")
    if _SHA256_RE.fullmatch(row["inputs_sha256"]) is None:
        problems.append("inputs_sha256 must be a SHA-256 of items.jsonl")
    return problems


def _literary_row_problems(row: Mapping[str, str]) -> list[str]:
    problems: list[str] = []
    if cs.LITERARY_ITEM_RE.fullmatch(row["item_id"]) is None:
        problems.append("a literary item_id must be its spec 002 candidate_id")
    if _FAMILY_ID_RE.fullmatch(row["group_id"]) is None:
        problems.append(f"group_id {row['group_id']!r} is not a spec 002 family ID")
    if _LITERARY_SOURCE_RE.fullmatch(row["source_ref"]) is None:
        problems.append(f"source_ref {row['source_ref']!r} is not a source key such as aesop_jones1912")
    if row["draw"] != "screened":
        problems.append(f"draw {row['draw']!r} must be 'screened' for a literary item")
    for field in ("seed", "pool_size", "inputs_sha256"):
        if row[field]:
            problems.append(f"{field} must be blank for a screened literary item")
    return problems


def _check_date(value: str) -> None:
    try:
        if datetime.date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except ValueError:
        raise cs.SchemaError(f"registered_on {value!r} is not YYYY-MM-DD") from None


def today(value: str | None = None) -> str:
    """``value`` validated as YYYY-MM-DD, or today's date. Injectable for deterministic tests."""
    if value is None:
        return datetime.date.today().isoformat()
    _check_date(value)
    return value


# --------------------------------------------------------------------------- dialogue draw


def dialogue_pool(
    items: Iterable[Mapping[str, Any]], excluded_dialogues: set[str], registered_dialogues: set[str]
) -> dict[str, list[int]]:
    """Map each eligible dev dialogue to its sorted user turns with ``turn_index > 0``."""
    turns: dict[str, list[int]] = defaultdict(list)
    for item in items:
        if item["split"] != "dev" or item["turn_index"] <= 0:
            continue
        dialogue_id = item["dialogue_id"]
        if dialogue_id in excluded_dialogues or dialogue_id in registered_dialogues:
            continue
        turns[dialogue_id].append(item["turn_index"])
    return {dialogue_id: sorted(indices) for dialogue_id, indices in sorted(turns.items())}


def draw_dialogues(
    pool: Mapping[str, Sequence[int]],
    dialogues: Mapping[str, Sequence[Turn]],
    *,
    count: int,
    seed: int,
    batch: str,
    inputs_sha256: str,
    registered_on: str,
) -> list[dict[str, str]]:
    """Draw ``count`` dialogues, then one turn in each; return registry rows sorted by item_id."""
    cs.batch_id(batch)
    if count < 1:
        raise RegistryError([f"count must be at least 1, not {count}"])
    if count > len(pool):
        raise RegistryError([f"asked for {count} dialogues but the eligible dev pool has only {len(pool)}"])

    rng = random.Random(f"{seed}:context-dialogue-draw")
    chosen = rng.sample(sorted(pool), count)
    rows = []
    for dialogue_id in chosen:
        turn_index = rng.choice(pool[dialogue_id])
        rows.append(
            {
                "item_id": cs.dialogue_item_id(dialogue_id, turn_index),
                "stratum": "dialogue",
                "batch": batch,
                "split": "dev",
                "group_id": dialogue_id.removesuffix(".json"),
                "source_ref": f"{dialogue_id}#{turn_index}",
                "target_sha256": target_sha256(_user_turn(dialogues, dialogue_id, turn_index).text),
                "draw": "drawn",
                "seed": str(seed),
                "pool_size": str(len(pool)),
                "inputs_sha256": inputs_sha256,
                "registered_on": registered_on,
                "protocol_version": cs.PROTOCOL_VERSION,
            }
        )
    return sorted(rows, key=lambda row: row["item_id"])


def _user_turn(dialogues: Mapping[str, Sequence[Turn]], dialogue_id: str, turn_index: int) -> Turn:
    """The drawn turn from the original dialogue; a mismatch with items.jsonl is a data error."""
    turns = dialogues.get(dialogue_id)
    if turns is None or turn_index >= len(turns):
        raise RegistryError([f"{dialogue_id} turn {turn_index} is missing from dialogues.jsonl; rebuild the DIRECT join"])
    turn = turns[turn_index]
    if turn.speaker != "user":
        raise RegistryError([f"{dialogue_id} turn {turn_index} is a {turn.speaker} turn, not a user turn"])
    return turn


def batch_has_drawn_items(registry: Iterable[Mapping[str, str]], batch: str) -> bool:
    return any(row["batch"] == batch and row["draw"] == "drawn" for row in registry)


# --------------------------------------------------------------------------- literary registration


def literary_rows(
    log: Sequence[Mapping[str, str]],
    families: Mapping[str, Mapping[str, str]],
    registry: Sequence[Mapping[str, str]],
    *,
    batch: str,
    registered_on: str,
) -> list[dict[str, str]]:
    """New registry rows for every ``include`` row of the spec 002 screening log not yet registered.

    ``pending`` and ``exclude`` rows never enter. Every problem is collected before raising, so a
    bad screening log is reported in full. An already-registered candidate whose target changed
    after registration (re-screened with a different ``target_text``) is an error, not a silent
    update: its earlier labels were made on the old span.
    """
    cs.batch_id(batch)
    registered = {row["item_id"]: row for row in registry}
    problems: list[str] = []
    rows: list[dict[str, str]] = []
    for entry in log:
        if entry["status"] != "include":
            continue
        candidate = entry["candidate_id"]
        label = f"candidate {candidate or '?'}"
        family = families.get(entry["family_id"])
        if cs.LITERARY_ITEM_RE.fullmatch(candidate) is None:
            problems.append(f"{label}: malformed candidate_id")
            continue
        if family is None:
            problems.append(f"{label}: family {entry['family_id']!r} is not in the families file")
            continue
        if family["split"] not in SPLITS or entry["split"] not in SPLITS:
            problems.append(f"{label}: family {entry['family_id']!r} is not a dev family")
            continue
        if _SHA256_RE.fullmatch(entry["target_sha256"]) is None:
            problems.append(f"{label}: malformed target_sha256")
            continue
        existing = registered.get(candidate)
        if existing is not None:
            if existing["target_sha256"] != entry["target_sha256"]:
                problems.append(f"{label}: target changed since registration; its labels refer to the old span")
            continue
        rows.append(
            {
                "item_id": candidate,
                "stratum": "literary",
                "batch": batch,
                "split": entry["split"],
                "group_id": entry["family_id"],
                "source_ref": entry["source"],
                "target_sha256": entry["target_sha256"],
                "draw": "screened",
                "seed": "",
                "pool_size": "",
                "inputs_sha256": "",
                "registered_on": registered_on,
                "protocol_version": cs.PROTOCOL_VERSION,
            }
        )
    problems.extend(f"{row['item_id']}: {problem}" for row in rows for problem in _row_problems(row))
    if problems:
        raise RegistryError(problems)
    return rows
