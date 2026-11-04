"""Stream rows and atomic writers for LLM runs (spec 009 T8, FR4).

There is one row per input record, in input-file order:
- routed: the model's route, or the ``no_request`` nulls;
- oracle: the interpretation;
- transfer: ``request``/``value``.

A content failure becomes the contract's ``invalid`` record (``src.llm.schema``). Rows are
serialized with sorted keys and ``\\n`` line ends, so the same answers always give the same
bytes (AC-009-4).

Files are written to a temporary sibling, fsynced and renamed into place. A killed run therefore
leaves the previous file or none, never a partial stream that a scorer could read. Every target
must lie under git-ignored ``outputs/``, because rows and provenance sit next to cached text.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from src.llm import schema
from src.llm.paths import REPO_ROOT, under_outputs

Outcome = schema.MainAnswer | schema.TransferAnswer | schema.Invalid
RowBuilder = Callable[[str, str, Any], dict[str, Any]]
ROW_BUILDERS: Mapping[str, RowBuilder] = {"routed": schema.routed_row, "oracle": schema.oracle_row,
                                          "transfer": schema.transfer_row}


def build_rows(kind: str, records: Iterable[Mapping[str, Any]], outcomes: Mapping[str, Outcome]
               ) -> tuple[list[dict[str, Any]], Counter[str]]:
    """Rows in record order, plus invalid counts by reason; every record's hash must have an outcome."""
    build = ROW_BUILDERS[kind]
    rows: list[dict[str, Any]] = []
    invalid: Counter[str] = Counter()
    for record in records:
        outcome = outcomes[record["input_sha256"]]
        if isinstance(outcome, schema.Invalid):
            invalid[outcome.reason] += 1
        rows.append(build(record["example_id"], record["condition"], outcome))
    return rows, invalid


def jsonl_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode("utf-8")


def json_bytes(document: Mapping[str, Any]) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_atomic(path: Path, data: bytes, root: Path = REPO_ROOT) -> Path:
    """Write ``data`` to ``path`` (under ``outputs/``) via a temporary file and an atomic rename."""
    target = under_outputs(path, root)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(handle, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, target)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return target
