"""Versioned weak MultiWOZ act references and strict structured predictions (spec 005)."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from src.data.direct_dataset import Item, SOCIAL_ACTS
from src.data.intent_categories import CATEGORIES, primary_category
from src.stage1.data import STAGE1_LABELS

REFERENCE_VERSION = "acts-v1"
NORMALIZER_VERSION = "slot-norm-v1"
SLOT_KEY = re.compile(r"[a-z][a-z0-9_]{0,39}\.[a-z][a-z0-9_]{0,39}\Z")
_NUMBERS = dict(zip(("zero one two three four five six seven eight nine ten eleven twelve").split(), map(str, range(13))))
_APOSTROPHES = str.maketrans({"’": "'", "‘": "'"})
_REGULAR = {"example_id", "condition", "prediction", "category", "slots", "requested_slots"}


def checked_text(value: Any, label: str, *, blank: bool = False, limit: int = 500) -> str:
    """Bound and validate external strings without echoing their content in errors."""
    if not isinstance(value, str) or len(value) > limit or (not blank and not value.strip()):
        raise ValueError(f"{label}: expected {'possibly empty ' if blank else ''}string of at most {limit} characters")
    if any(unicodedata.category(c) in {"Cc", "Cf", "Cs", "Zl", "Zp"} for c in value):
        raise ValueError(f"{label}: control or invisible characters are forbidden")
    return value


def normalize_value(key: str, value: str) -> str:
    """Conservative slot-specific aliases; no fuzzy matching or invented values."""
    normalized = " ".join(value.casefold().translate(_APOSTROPHES).split())
    slot = key.split(".")[-1]
    if slot in {"people", "stay", "stars"}:
        return _NUMBERS.get(normalized, normalized)
    if slot == "area":
        return {"center": "centre", "city centre": "centre", "city center": "centre"}.get(normalized, normalized)
    if slot in {"price", "pricerange"}:
        return {"inexpensive": "cheap", "moderately priced": "moderate", "moderately": "moderate"}.get(normalized, normalized)
    if slot in {"time", "leave", "arrive", "leaveat", "arriveby", "leave_at", "arrive_by"}:
        match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", normalized)
        if match:
            hour, minute, period = int(match[1]), int(match[2] or 0), match[3]
            if minute < 60 and ((period and 1 <= hour <= 12) or (not period and hour < 24)):
                hour = hour % 12 + (12 if period == "pm" else 0) if period else hour
                return f"{hour:02d}:{minute:02d}"
    return normalized


@dataclass(frozen=True)
class Reference:
    """An observed act reference, not a claim that all execution slots are present."""

    category: str | None
    slots: dict[str, str]
    requested_slots: frozenset[str]
    exclusion: str | None = None


def reference(item: Item) -> Reference:
    """Extract explicit Inform values and Request slot names, rejecting conflicting values."""
    slots: dict[str, str] = {}
    requested: set[str] = set()
    conflicting = False
    acts = item.get("user_acts") or {}
    if not isinstance(acts, dict):
        raise ValueError("user_acts must be an object")
    for act, pairs in acts.items():
        if act in SOCIAL_ACTS:
            continue
        if not isinstance(act, str) or "-" not in act or not isinstance(pairs, list):
            raise ValueError("invalid act reference")
        domain, kind = act.split("-", 1)
        for pair in pairs:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise ValueError("invalid act slot pair")
            slot, value = pair
            checked_text(slot, "reference slot")
            checked_text(value, "reference value", blank=True)
            if slot.casefold() == "none":
                continue
            key = f"{domain.lower()}.{slot.lower()}"
            if not SLOT_KEY.fullmatch(key):
                raise ValueError("invalid reference slot name")
            if kind == "Request":
                requested.add(key)
            elif kind == "Inform" and value.strip().casefold() not in {"", "?", "none", "not mentioned"}:
                normalized = normalize_value(key, value)
                if key in slots and slots[key] != normalized:
                    conflicting = True
                slots[key] = normalized
    if conflicting:
        return Reference(None, {}, frozenset(), "conflicting_act_values")
    return Reference(primary_category(item), slots, frozenset(requested))


def require_local_text_output(path) -> None:
    """Keep reconstructed corpus/model inputs within the repo's ignored text directories."""
    from pathlib import Path
    target = path.resolve()
    root = Path(__file__).resolve().parents[2]
    if not any(target.is_relative_to((root / folder).resolve()) for folder in ("data/interim", "outputs")):
        raise ValueError("text exports must stay under git-ignored data/interim/ or outputs/")


def validate_predictions(rows: Sequence[dict[str, Any]], expected: Mapping[str, set[str]]) -> dict[str, dict[str, dict]]:
    """Require exactly one typed record for every requested (condition, example)."""
    out: dict[str, dict[str, dict]] = {condition: {} for condition in expected}
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f"prediction row {index}: expected object")
        example_id = checked_text(row.get("example_id"), "example_id", limit=150)
        condition = checked_text(row.get("condition"), "condition", limit=30)
        if condition not in expected or example_id not in expected[condition] or example_id in out[condition]:
            raise ValueError(f"extra, duplicate or unavailable prediction row {index}")
        if row.get("invalid") is True:
            if set(row) != {"example_id", "condition", "invalid"}:
                raise ValueError("invalid-output marker must not carry interpretation fields")
        else:
            if set(row) - (_REGULAR | {"paraphrase"}) or _REGULAR - set(row):
                raise ValueError("unknown or missing structured prediction fields")
            if row["prediction"] not in STAGE1_LABELS or row["category"] not in (*CATEGORIES, None):
                raise ValueError("unknown prediction label or category")
            if not isinstance(row["slots"], dict) or len(row["slots"]) > 100:
                raise ValueError("slots must be an object with at most 100 entries")
            for key, value in row["slots"].items():
                if not isinstance(key, str) or not SLOT_KEY.fullmatch(key):
                    raise ValueError("invalid predicted slot name")
                checked_text(value, "slot value")
            requested = row["requested_slots"]
            if not isinstance(requested, list) or len(requested) > 100:
                raise ValueError("requested_slots must be a list of at most 100 names")
            if any(not isinstance(k, str) or not SLOT_KEY.fullmatch(k) for k in requested) or len(set(requested)) != len(requested):
                raise ValueError("invalid or duplicate requested slot names")
            if "paraphrase" in row:
                checked_text(row["paraphrase"], "paraphrase", blank=True)
        out[condition][example_id] = row
    for condition, ids in expected.items():
        if set(out[condition]) != ids:
            raise ValueError(f"missing {len(ids - set(out[condition]))} predictions under {condition}")
    return out


def outcome(gold: Reference, row: dict) -> dict[str, Any]:
    """Count stated and requested slots together, retaining exact-set correctness."""
    predicted = set()
    if not row.get("invalid"):
        predicted = {("value", key, normalize_value(key, value)) for key, value in row["slots"].items()}
        predicted |= {("request", key, "") for key in row["requested_slots"]}
    required = {("value", key, value) for key, value in gold.slots.items()}
    required |= {("request", key, "") for key in gold.requested_slots}
    category = not row.get("invalid") and gold.category is not None and row["category"] == gold.category
    if gold.category == "no_request" and not row.get("invalid"):
        category = row["category"] in {None, "no_request"}
    return {"category": bool(category), "exact": bool(category and predicted == required),
            "slots": {"correct": len(predicted & required), "gold": len(required), "predicted": len(predicted)}}
