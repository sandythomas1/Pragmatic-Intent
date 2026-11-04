"""Verified loading of the LLM runner's input streams (spec 009 T4, FR1, FR2).

The runner reads three kinds of file, all produced by committed exporters:
- ``routed`` and ``oracle``: spec 005 Stage 2 inputs (``context``, ``target``, ``render-v1``);
- ``transfer``: IndirectRequests inputs (``utterance``, ``slot_description``, closed candidates).

Every record's schema is checked and its ``input_sha256`` is recomputed from exactly the fields a
model is shown, so a hand-edited or stale file is refused before any backend exists. Reads are
bounded. Error messages carry line numbers and counts only, never an example ID or corpus text,
because these files may be test inputs (no-test-split-output rule).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.data.contexts import RENDERER_VERSION
from src.data.direct_dataset import CONDITIONS

KINDS = ("routed", "oracle", "transfer")
MAX_FILE_BYTES = 256 * 1024 * 1024   # dev routed is ~33 MB
MAX_LINE_BYTES = 256 * 1024          # a 350-word input is a few KB
MAX_RECORDS = 1_000_000
MAX_FIELD_CHARS = 20_000             # the renderer's own bound (src/llm/prompt.py)
MAX_CANDIDATES = 100
_MAIN_FIELDS = frozenset({"example_id", "condition", "context", "target", "renderer_version", "input_sha256"})
_TRANSFER_FIELDS = frozenset({"example_id", "condition", "utterance", "slot_description", "candidates",
                              "candidate_aliases", "input_sha256"})
_EXAMPLE_ID = re.compile(r"[A-Za-z0-9_.:\-]{1,128}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class InputError(ValueError):
    """An input file fails verification; the message holds no IDs or corpus text."""


@dataclass(frozen=True)
class InputStream:
    """One verified input file: its kind, records in file order, and the file's SHA-256."""

    kind: str
    records: tuple[dict[str, Any], ...]
    file_sha256: str

    @property
    def keys(self) -> dict[tuple[str, str], str]:
        """``(example_id, condition) -> input_sha256``."""
        return {(r["example_id"], r["condition"]): r["input_sha256"] for r in self.records}


def main_input_sha256(context: str, target: str) -> str:
    """Same canonical form as ``src.data.contexts.input_sha256`` (what the model is shown)."""
    payload = json.dumps({"context": context, "target": target}, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def transfer_input_sha256(record: Mapping[str, Any]) -> str:
    """Same canonical form as ``src.data.indirect_requests.input_record``: every field but the hash."""
    body = {name: value for name, value in record.items() if name != "input_sha256"}
    payload = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_stream(path: Path, kind: str) -> InputStream:
    """Read, bound and verify one input file; refuses duplicates and any hash mismatch."""
    if kind not in KINDS:
        raise InputError("unknown input kind")
    data = _bounded_read(path)
    if data and not data.endswith(b"\n"):
        raise InputError(f"{kind} inputs: file does not end with a newline (incomplete write?)")
    verify = _verify_transfer if kind == "transfer" else _verify_main
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for number, line in enumerate(data.split(b"\n")[:-1] if data else [], 1):
        if len(line) > MAX_LINE_BYTES:
            raise InputError(f"{kind} inputs line {number}: longer than {MAX_LINE_BYTES} bytes")
        if len(records) >= MAX_RECORDS:
            raise InputError(f"{kind} inputs: more than {MAX_RECORDS} records")
        try:
            record = json.loads(line.decode("utf-8"), object_pairs_hook=_unique_object)
        except (UnicodeDecodeError, ValueError, RecursionError):
            raise InputError(f"{kind} inputs line {number}: not one JSON object") from None
        problem = verify(record)
        if problem:
            raise InputError(f"{kind} inputs line {number}: {problem}")
        key = (record["example_id"], record["condition"])
        if key in seen:
            raise InputError(f"{kind} inputs line {number}: duplicate (example_id, condition)")
        seen.add(key)
        records.append(record)
    if not records:
        raise InputError(f"{kind} inputs: no records")
    return InputStream(kind, tuple(records), hashlib.sha256(data).hexdigest())


def check_oracle_subset(routed: InputStream, oracle: InputStream) -> None:
    """FR2: every oracle record is a routed record with the identical input hash."""
    if (routed.kind, oracle.kind) != ("routed", "oracle"):
        raise InputError("subset check needs a routed and an oracle stream")
    routed_keys = routed.keys
    missing = changed = 0
    for key, digest in oracle.keys.items():
        if key not in routed_keys:
            missing += 1
        elif routed_keys[key] != digest:
            changed += 1
    if missing or changed:
        raise InputError(f"oracle stream is not a subset of the routed stream: {missing} record(s) missing "
                         f"from routed, {changed} with a different input hash")


def distinct_inputs(streams: Iterable[InputStream]) -> dict[str, dict[str, Any]]:
    """One representative record per distinct ``input_sha256``, sorted by hash (one call each)."""
    distinct: dict[str, dict[str, Any]] = {}
    for stream in streams:
        for record in stream.records:
            distinct.setdefault(record["input_sha256"], record)
    return dict(sorted(distinct.items()))


def _verify_main(record: Any) -> str | None:
    if not isinstance(record, dict) or set(record) != _MAIN_FIELDS:
        return "unknown or missing fields"
    problem = _identity(record, allowed_conditions=CONDITIONS)
    if problem:
        return problem
    if record["renderer_version"] != RENDERER_VERSION:
        return f"renderer_version must be {RENDERER_VERSION}"
    if not _text(record["context"], blank=True) or not _text(record["target"]):
        return "context/target must be bounded strings and the target non-blank"
    if main_input_sha256(record["context"], record["target"]) != record["input_sha256"]:
        return "input_sha256 does not match the record's context and target"
    return None


def _verify_transfer(record: Any) -> str | None:
    if not isinstance(record, dict) or set(record) != _TRANSFER_FIELDS:
        return "unknown or missing fields"
    problem = _identity(record, allowed_conditions=("none",))
    if problem:
        return problem
    if not _text(record["utterance"]) or not _text(record["slot_description"]):
        return "utterance/slot_description must be non-blank bounded strings"
    candidates, aliases = record["candidates"], record["candidate_aliases"]
    if (not isinstance(candidates, list) or not candidates or len(candidates) > MAX_CANDIDATES
            or any(not _text(value) for value in candidates) or len(set(candidates)) != len(candidates)):
        return f"candidates must be 1-{MAX_CANDIDATES} unique non-blank strings"
    if (not isinstance(aliases, dict) or set(aliases) - set(candidates)
            or any(not _text(value, blank=True) for value in aliases.values())):
        return "candidate_aliases must map candidates to strings"
    if transfer_input_sha256(record) != record["input_sha256"]:
        return "input_sha256 does not match the record"
    return None


def _identity(record: Mapping[str, Any], *, allowed_conditions: Sequence[str]) -> str | None:
    example_id, condition, digest = record["example_id"], record["condition"], record["input_sha256"]
    if not isinstance(example_id, str) or not _EXAMPLE_ID.fullmatch(example_id):
        return "malformed example_id"
    if condition not in allowed_conditions:
        return "unknown condition"
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        return "input_sha256 must be a lowercase SHA-256"
    return None


def _text(value: Any, *, blank: bool = False) -> bool:
    return isinstance(value, str) and len(value) <= MAX_FIELD_CHARS and (blank or bool(value.strip()))


def _bounded_read(path: Path) -> bytes:
    with path.open("rb") as handle:
        data = handle.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise InputError(f"input file exceeds {MAX_FILE_BYTES} bytes")
    return data


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate JSON key")
    return dict(pairs)
