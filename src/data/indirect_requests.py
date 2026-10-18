"""Pinned, local-only IndirectRequests adapter; never mixed into DIRECT training."""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from src.data.download_sources import load_manifest
from src.evaluation.interpretation import checked_text

ADAPTER_VERSION = "indirect-requests-v1"
AMBIGUOUS = "<ambiguous>"
SPLITS = ("train", "validation", "test")
_FIELDS = {"utterance", "situation", "service", "slot_description", "possible_slot_values",
           "bool_rephrased_slot_values", "target_slot_value"}


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _list(value: str) -> tuple[str, ...]:
    if not isinstance(value, str) or len(value) > 10000:
        raise ValueError("candidate literal must be a bounded string")
    try:
        parsed = ast.literal_eval(value)
    except (ValueError, SyntaxError, RecursionError) as error:
        raise ValueError("invalid candidate list literal") from error
    if not isinstance(parsed, list) or not 1 <= len(parsed) <= 100:
        raise ValueError("candidates must be a nonempty list of at most 100 strings")
    for candidate in parsed:
        checked_text(candidate, "candidate")
    if len({_normalized(candidate) for candidate in parsed}) != len(parsed):
        raise ValueError("candidate labels collide after normalization")
    return tuple(parsed)


@dataclass(frozen=True)
class TransferItem:
    example_id: str
    split: str
    service: str
    utterance: str
    slot_description: str
    candidates: tuple[str, ...]
    aliases: tuple[str, ...]
    target: str

    def resolve(self, value: str | None) -> str | None:
        """Canonicalize one closed-set value, including boolean description aliases."""
        if value is None:
            return None
        if _normalized(value) == AMBIGUOUS:
            return AMBIGUOUS
        for candidate, alias in zip(self.candidates, self.aliases, strict=True):
            if _normalized(value) in {_normalized(candidate), _normalized(alias)}:
                return candidate
        return None


def load_records(path: Path, split: str) -> list[TransferItem]:
    """Validate bounded local source records; IDs are stable split/line locators."""
    if split not in SPLITS:
        raise ValueError("unknown IndirectRequests split")
    records = []
    with path.open(encoding="utf-8") as handle:
        for index, line in enumerate(handle, 1):
            if len(line) > 50000:
                raise ValueError(f"transfer row {index}: oversized record")
            if not line.strip():
                raise ValueError(f"transfer row {index}: blank record")
            try:
                row = json.loads(line)
                if not isinstance(row, dict) or _FIELDS - set(row) or set(row) - (_FIELDS | {"creation_date", "mean_world_understanding"}):
                    raise ValueError("unknown or missing source fields")
                for key in ("utterance", "situation", "service", "slot_description", "target_slot_value"):
                    checked_text(row[key], key, limit=5000 if key in {"utterance", "situation"} else 500)
                candidates, aliases = _list(row["possible_slot_values"]), _list(row["bool_rephrased_slot_values"])
                if len(candidates) != len(aliases) or AMBIGUOUS in {_normalized(x) for x in (*candidates, *aliases)}:
                    raise ValueError("candidate/alias length mismatch or reserved ambiguous label")
                owners: dict[str, str] = {}
                for candidate, alias in zip(candidates, aliases, strict=True):
                    for label in (candidate, alias):
                        key = _normalized(label)
                        if key in owners and owners[key] != candidate:
                            raise ValueError("candidate aliases collide")
                        owners[key] = candidate
                target = row["target_slot_value"]
                if target != AMBIGUOUS and target not in candidates:
                    raise ValueError("target not in the closed candidate set")
                records.append(TransferItem(f"ir:{split}:{index:04d}", split, row["service"], row["utterance"],
                                            row["slot_description"], candidates, aliases, target))
            except (ValueError, TypeError, KeyError) as error:
                raise ValueError(f"transfer row {index}: invalid source schema ({type(error).__name__})") from error
    if not records:
        raise ValueError("empty transfer split")
    return records


def verify_pin(path: Path, size: int, sha256: str) -> None:
    """Require exactly the pinned bytes before loading a real split."""
    data = path.read_bytes()
    if len(data) != size or hashlib.sha256(data).hexdigest() != sha256:
        raise ValueError("IndirectRequests file differs from its pinned source")


def load_pinned(root: Path, split: str, manifest: Path = Path("data/sources.toml")) -> list[TransferItem]:
    """Load a manifest-pinned split without any download or execution."""
    if split not in SPLITS:
        raise ValueError("unknown IndirectRequests split")
    sources = [source for source in load_manifest(manifest).sources if source.name == "indirect_requests"]
    if len(sources) != 1:
        raise ValueError("missing IndirectRequests manifest source")
    file = next((file for file in sources[0].files if file.path == f"{split}.jsonl"), None)
    if file is None:
        raise ValueError("missing pinned split")
    path = root / file.path
    verify_pin(path, file.size, file.sha256)
    return load_records(path, split)


def input_record(item: TransferItem) -> dict:
    """None context only: situation, ratings, dates and target never reach the model."""
    record = {"example_id": item.example_id, "condition": "none", "utterance": item.utterance,
              "slot_description": item.slot_description, "candidates": [*item.candidates, AMBIGUOUS],
              "candidate_aliases": dict(zip(item.candidates, item.aliases, strict=True))}
    record["input_sha256"] = hashlib.sha256(json.dumps(record, ensure_ascii=False, sort_keys=True,
                                                     separators=(",", ":")).encode("utf-8")).hexdigest()
    return record
