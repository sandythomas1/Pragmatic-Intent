"""Closed answer schemas and strict, non-repairing parsing of LLM output (spec 009 FR3, FR3b, FR5).

The JSON Schemas built here are the canonical output contract. A backend may give its provider
an equivalent projection, because some structured-output modes drop length bounds. The parser
therefore re-checks every bound itself, and it is the only path by which model output becomes a
prediction row. It never repairs or re-asks: a content failure becomes an ``Invalid`` with one
reason code, and the example stays in the scoring denominator as the contract's invalid record.

The slot-key vocabulary is a closed enum of the MultiWOZ ``domain.slot`` names seen in train
``Inform``/``Request`` reference acts (spec 005 ``acts-v1``). It is committed as names only.

    python -m src.llm.schema slot-keys --out configs/llm/slot_keys.json [--check-dev]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.data.direct_dataset import Item, load_items
from src.data.indirect_requests import AMBIGUOUS
from src.data.intent_categories import CATEGORIES, DEFAULT_ITEMS
from src.evaluation.interpretation import REFERENCE_VERSION, SLOT_KEY, checked_text, reference
from src.stage1.data import STAGE1_LABELS, build_examples

SCHEMA_VERSION = "llm-answer-v1"
SLOT_KEYS_VERSION = "slot-keys-v1"
REQUEST_CATEGORIES = tuple(category for category in CATEGORIES if category != "no_request")
FINISH_REASONS = ("stop", "length", "refusal")
REASONS = ("empty", "refusal", "truncated", "too_long", "parse", "schema", "category",
           "slot_key", "slot_duplicate", "transfer_value")
MAX_RAW_CHARS = 8192      # far above max_tokens=256; bounds parsing work on any backend
MAX_SLOTS = 20
MAX_REQUESTED = 20
MAX_VALUE_CHARS = 100
MAX_CANDIDATES = 100
MAX_SLOT_KEYS = 1000
MAX_VOCABULARY_BYTES = 1_000_000
_MAIN_FIELDS = frozenset({"route", "category", "slots", "requested_slots"})
_TRANSFER_FIELDS = frozenset({"request", "value"})
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class MainAnswer:
    """A schema-valid main-benchmark answer; the interpretation is given as if a request (FR3)."""

    route: str
    category: str
    slots: tuple[tuple[str, str], ...]
    requested_slots: tuple[str, ...]


@dataclass(frozen=True)
class TransferAnswer:
    """A schema-valid IndirectRequests answer (FR3b)."""

    request: bool
    value: str


@dataclass(frozen=True)
class Invalid:
    """A content failure: the call happened and its answer is unusable (FR5)."""

    reason: str

    def __post_init__(self) -> None:
        if self.reason not in REASONS:
            raise ValueError("unknown invalid-output reason")


# --- slot-key vocabulary -------------------------------------------------------------------------

def build_slot_keys(items: Iterable[Item]) -> list[str]:
    """Sorted ``domain.slot`` names from the reference acts of train examples only."""
    items = list(items)
    examples, _ = build_examples(items, "train")
    by_id = {item["item_id"]: item for item in items}
    keys: set[str] = set()
    for item_id in sorted({example.item_id for example in examples}):
        gold = reference(by_id[item_id])
        keys.update(gold.slots)
        keys.update(gold.requested_slots)
    if not keys:
        raise ValueError("no train reference slot keys found")
    return sorted(keys)


def slot_keys_document(keys: Sequence[str], items_sha256: str) -> dict[str, Any]:
    """The committed vocabulary file: names, versions and the source hash; no corpus text."""
    document = {"version": SLOT_KEYS_VERSION, "reference_version": REFERENCE_VERSION, "split": "train",
                "items_sha256": items_sha256, "slot_keys": list(keys)}
    _validate_vocabulary(document)
    return document


def load_slot_keys(path: Path) -> tuple[str, ...]:
    """Read and strictly validate a committed vocabulary file."""
    if path.stat().st_size > MAX_VOCABULARY_BYTES:
        raise ValueError("slot-key vocabulary file is too large")
    document = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    return _validate_vocabulary(document)


def _validate_vocabulary(document: Any) -> tuple[str, ...]:
    expected = {"version", "reference_version", "split", "items_sha256", "slot_keys"}
    if not isinstance(document, dict) or set(document) != expected:
        raise ValueError("slot-key vocabulary: unknown or missing fields")
    if (document["version"], document["reference_version"], document["split"]) != (
            SLOT_KEYS_VERSION, REFERENCE_VERSION, "train"):
        raise ValueError("slot-key vocabulary: unsupported version, reference version or split")
    if not isinstance(document["items_sha256"], str) or not _SHA256.fullmatch(document["items_sha256"]):
        raise ValueError("slot-key vocabulary: items_sha256 must be a lowercase SHA-256")
    return _checked_keys(document["slot_keys"])


def _checked_keys(keys: Any) -> tuple[str, ...]:
    if not isinstance(keys, (list, tuple)) or not keys or len(keys) > MAX_SLOT_KEYS:
        raise ValueError(f"slot keys must be a non-empty list of at most {MAX_SLOT_KEYS} names")
    if any(not isinstance(key, str) or not SLOT_KEY.fullmatch(key) for key in keys):
        raise ValueError("slot keys must be lowercase domain.slot names")
    if any(left >= right for left, right in zip(keys, keys[1:])):
        raise ValueError("slot keys must be sorted and unique")
    return tuple(keys)


# --- schemas -------------------------------------------------------------------------------------

def main_schema(slot_keys: Sequence[str]) -> dict[str, Any]:
    """Route plus a request interpretation; no ``paraphrase`` field (R12)."""
    keys = list(_checked_keys(list(slot_keys)))
    slot_pair = {"type": "object", "additionalProperties": False, "required": ["slot", "value"],
                 "properties": {"slot": {"type": "string", "enum": keys},
                                "value": {"type": "string", "minLength": 1, "maxLength": MAX_VALUE_CHARS}}}
    return {"type": "object", "additionalProperties": False,
            "required": ["route", "category", "slots", "requested_slots"],
            "properties": {
                "route": {"type": "string", "enum": list(STAGE1_LABELS)},
                "category": {"type": "string", "enum": list(REQUEST_CATEGORIES)},
                "slots": {"type": "array", "maxItems": MAX_SLOTS, "items": slot_pair},
                "requested_slots": {"type": "array", "maxItems": MAX_REQUESTED,
                                    "items": {"type": "string", "enum": keys}}}}


def transfer_values(candidates: Sequence[str]) -> tuple[str, ...]:
    """The record's closed value set: its candidates plus ``<ambiguous>``, order preserved."""
    if not isinstance(candidates, (list, tuple)) or not candidates or len(candidates) > MAX_CANDIDATES:
        raise ValueError(f"candidates must be a non-empty list of at most {MAX_CANDIDATES} values")
    for candidate in candidates:
        checked_text(candidate, "candidate")
    values = tuple(candidates) if AMBIGUOUS in candidates else (*candidates, AMBIGUOUS)
    if len(set(values)) != len(values):
        raise ValueError("duplicate transfer candidates")
    return values


def transfer_schema(candidates: Sequence[str]) -> dict[str, Any]:
    """Per-record schema ``{request: bool, value: enum(candidates ∪ {<ambiguous>})}`` (FR3b)."""
    return {"type": "object", "additionalProperties": False, "required": ["request", "value"],
            "properties": {"request": {"type": "boolean"},
                           "value": {"type": "string", "enum": list(transfer_values(candidates))}}}


def schema_sha256(schema: dict[str, Any]) -> str:
    """Hash of the schema's canonical JSON; part of the cache key and provenance (FR6, FR8)."""
    canonical = json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --- strict parsing ------------------------------------------------------------------------------

def parse_main(raw: str, finish_reason: str, slot_keys: Collection[str]) -> MainAnswer | Invalid:
    """Validate one main-benchmark answer against the closed schema, without repair."""
    data = _decode(raw, finish_reason)
    if isinstance(data, Invalid):
        return data
    if not isinstance(data, dict) or set(data) != _MAIN_FIELDS:
        return Invalid("schema")
    route, category, slots, requested = (data[name] for name in ("route", "category", "slots", "requested_slots"))
    if not isinstance(route, str) or route not in STAGE1_LABELS:
        return Invalid("schema")
    if not isinstance(category, str) or category not in REQUEST_CATEGORIES:
        return Invalid("category")
    if not isinstance(slots, list) or not isinstance(requested, list):
        return Invalid("schema")
    if len(slots) > MAX_SLOTS or len(requested) > MAX_REQUESTED:
        return Invalid("too_long")
    pairs = []
    for entry in slots:
        if not isinstance(entry, dict) or set(entry) != {"slot", "value"}:
            return Invalid("schema")
        slot, value = entry["slot"], entry["value"]
        if not isinstance(slot, str) or not isinstance(value, str):
            return Invalid("schema")
        if slot not in slot_keys:
            return Invalid("slot_key")
        if len(value) > MAX_VALUE_CHARS:
            return Invalid("too_long")
        if not _scorable_text(value, MAX_VALUE_CHARS):
            return Invalid("schema")
        pairs.append((slot, value))
    if any(not isinstance(name, str) for name in requested):
        return Invalid("schema")
    if any(name not in slot_keys for name in requested):
        return Invalid("slot_key")
    names = [slot for slot, _ in pairs]
    if len(set(names)) != len(names) or len(set(requested)) != len(requested):
        return Invalid("slot_duplicate")
    return MainAnswer(route, category, tuple(pairs), tuple(requested))


def parse_transfer(raw: str, finish_reason: str, candidates: Sequence[str]) -> TransferAnswer | Invalid:
    """Validate one transfer answer; the value must exactly equal an allowed value."""
    allowed = transfer_values(candidates)
    data = _decode(raw, finish_reason)
    if isinstance(data, Invalid):
        return data
    if not isinstance(data, dict) or set(data) != _TRANSFER_FIELDS:
        return Invalid("schema")
    request, value = data["request"], data["value"]
    if type(request) is not bool or not isinstance(value, str):
        return Invalid("schema")
    if value not in allowed:
        return Invalid("transfer_value")
    return TransferAnswer(request, value)


def _decode(raw: str, finish_reason: str) -> Any:
    """Map stop reasons and raw text to parsed JSON or an ``Invalid``; order is fixed."""
    if finish_reason not in FINISH_REASONS:
        raise ValueError("backend reported an unknown finish reason")
    if not isinstance(raw, str):
        raise TypeError("raw model output must be a string")
    if finish_reason == "refusal":
        return Invalid("refusal")
    if finish_reason == "length":
        return Invalid("truncated")
    if not raw.strip():
        return Invalid("empty")
    if len(raw) > MAX_RAW_CHARS:
        return Invalid("too_long")
    try:
        return json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except (ValueError, RecursionError):
        return Invalid("parse")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate JSON object key")
    return dict(pairs)


def _reject_constant(name: str) -> Any:
    raise ValueError("non-standard JSON constant")


def _scorable_text(value: str, limit: int) -> bool:
    """The scorer's own text rule (non-blank, bounded, no control characters)."""
    try:
        checked_text(value, "slot value", limit=limit)
    except ValueError:
        return False
    return True


# --- contract rows (docs/stage2_scoring.md) -----------------------------------------------------

def invalid_row(example_id: str, condition: str) -> dict[str, Any]:
    return {"example_id": example_id, "condition": condition, "invalid": True}


def routed_row(example_id: str, condition: str, outcome: MainAnswer | Invalid) -> dict[str, Any]:
    """LLM standalone routed row: the model's route; a ``no_request`` route carries no interpretation."""
    if isinstance(outcome, Invalid):
        return invalid_row(example_id, condition)
    if outcome.route == "no_request":
        return {"example_id": example_id, "condition": condition, "prediction": "no_request",
                "category": None, "slots": {}, "requested_slots": []}
    return _interpretation_row(example_id, condition, outcome)


def oracle_row(example_id: str, condition: str, outcome: MainAnswer | Invalid) -> dict[str, Any]:
    """Oracle row: the interpretation for every record (the scorer ignores ``prediction``)."""
    if isinstance(outcome, Invalid):
        return invalid_row(example_id, condition)
    return _interpretation_row(example_id, condition, outcome)


def transfer_row(example_id: str, condition: str, outcome: TransferAnswer | Invalid) -> dict[str, Any]:
    if isinstance(outcome, Invalid):
        return invalid_row(example_id, condition)
    return {"example_id": example_id, "condition": condition, "request": outcome.request, "value": outcome.value}


def _interpretation_row(example_id: str, condition: str, answer: MainAnswer) -> dict[str, Any]:
    return {"example_id": example_id, "condition": condition, "prediction": answer.route,
            "category": answer.category, "slots": dict(answer.slots),
            "requested_slots": list(answer.requested_slots)}


# --- CLI -----------------------------------------------------------------------------------------

def dev_coverage(items: Sequence[Item], keys: Collection[str]) -> dict[str, int]:
    """Counts only: dev reference keys the train vocabulary can't express (a ceiling to disclose)."""
    examples, _ = build_examples(items, "dev", require_context=True)
    by_id = {item["item_id"]: item for item in items}
    seen: set[str] = set()
    affected = 0
    for example in examples:
        gold = reference(by_id[example.item_id])
        gold_keys = set(gold.slots) | set(gold.requested_slots)
        seen |= gold_keys
        affected += bool(gold_keys - set(keys))
    return {"dev_examples": len(examples), "dev_keys": len(seen),
            "dev_keys_outside": len(seen - set(keys)), "dev_examples_affected": affected}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("slot-keys",))
    parser.add_argument("--items", type=Path, default=DEFAULT_ITEMS)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--check-dev", action="store_true",
                        help="also print dev coverage counts (never test)")
    args = parser.parse_args(argv)
    try:
        if args.out.resolve() == args.items.resolve():
            raise ValueError("output must not overwrite the items file")
        items = load_items(args.items)
        items_sha256 = hashlib.sha256(args.items.read_bytes()).hexdigest()
        document = slot_keys_document(build_slot_keys(items), items_sha256)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        print(f"Slot keys: {len(document['slot_keys'])} train names -> {args.out}")
        if args.check_dev:
            counts = dev_coverage(items, document["slot_keys"])
            print("Dev coverage: " + ", ".join(f"{name}={value}" for name, value in counts.items()))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f"Slot keys failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
