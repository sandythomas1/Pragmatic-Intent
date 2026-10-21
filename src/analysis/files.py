"""Bounded, hashed reads of the analysis's untrusted inputs, and its named error.

Every file the analysis uses is hashed when the inputs are resolved (``hash_file``) and read
again only through ``read_verified``, which rejects a file whose bytes changed in between. The
bytes that are parsed are therefore exactly the bytes recorded in the report's provenance.
Error messages name files and rules, never example or dialogue IDs: on test, a printed ID
would become an inspection exclusion (spec 006).
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class AnalysisError(ValueError):
    """A named analysis failure; ``code`` is stable for tests and logs."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code


@dataclass(frozen=True)
class FileRef:
    path: Path
    sha256: str
    size: int
    limit: int


def read_bounded(path: Path, limit: int, error: type[AnalysisError] = AnalysisError) -> bytes:
    """A regular file's bytes, refusing anything over ``limit`` without reading it all."""
    if not path.is_file():
        raise error("not_a_file", f"{path} is not a regular file")
    # Chunked: read(limit + 1) would allocate the whole limit up front, even for a tiny file.
    chunks, total = [], 0
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            total += len(chunk)
            if total > limit:
                raise error("file_too_large", f"{path.name} exceeds {limit} bytes")
            chunks.append(chunk)
    return b"".join(chunks)


def hash_file(path: Path, limit: int) -> FileRef:
    data = read_bounded(path, limit)
    return FileRef(path=path, sha256=hashlib.sha256(data).hexdigest(), size=len(data), limit=limit)


def read_verified(ref: FileRef) -> bytes:
    """The file's bytes, provided they still hash to what the inputs recorded."""
    data = read_bounded(ref.path, ref.limit)
    if hashlib.sha256(data).hexdigest() != ref.sha256:
        raise AnalysisError("file_changed", f"{ref.path.name} changed after its hash was recorded")
    return data


def read_toml(path: Path, limit: int, error: type[AnalysisError] = AnalysisError) -> dict[str, Any]:
    data = read_bounded(path, limit, error)
    try:
        return tomllib.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError, RecursionError) as exc:
        # tomllib recurses on nested arrays, so a crafted file can exhaust the stack.
        raise error("invalid_toml", f"{path.name}: {str(exc)[:200]}") from None


def parse_json(data: bytes, label: str) -> Any:
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise AnalysisError("invalid_json", f"{label} is not valid UTF-8 JSON") from None


def parse_jsonl(data: bytes, label: str) -> list[Any]:
    """One JSON value per non-blank line; the line number is reported, never its content."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise AnalysisError("invalid_json", f"{label} is not valid UTF-8") from None
    rows = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except (ValueError, RecursionError):
            raise AnalysisError("invalid_json", f"{label} line {number} is not valid JSON") from None
    return rows
