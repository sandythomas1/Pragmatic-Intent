"""Append-only, resumable response cache (spec 009 T5, FR6).

One JSONL line per answered call. The key is the SHA-256 of the canonical JSON of everything that
determines the answer: task, backend, model ID, rendered-prompt hash, decoding parameters, schema
hash and input hash. Changing any one of them is a miss, so an answer is never reused under a
different prompt, schema, model or input.

Durability rules:
- lines are flushed and fsynced once per appended batch;
- a final line without its newline is a write torn by a kill: it is dropped with a warning on
  load, and cut off before the next append, so the next line starts cleanly;
- any other malformed line is a hard error (the cache is corrupt, not merely interrupted);
- a key that appears twice must carry identical content (raw text, finish reason, usage), else
  loading fails: two writers disagreeing means the run is not reproducible from its cache.

Raw responses may echo corpus text, so the file must live under git-ignored ``outputs/``. Errors
name line numbers only, never content.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO

from src.llm.paths import REPO_ROOT, under_outputs
from src.llm.schema import FINISH_REASONS, MAX_RAW_CHARS

CACHE_VERSION = "llm-cache-v1"
TASKS = ("main", "transfer")
MAX_LINE_BYTES = 1_000_000
MAX_USAGE_FIELDS = 16
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_NAME = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_MODEL = re.compile(r"[A-Za-z0-9._:/@\-]{1,200}\Z")
_FIELDS = frozenset({"v", "key", "raw", "finish_reason", "usage", "created"})
log = logging.getLogger(__name__)


class CacheError(ValueError):
    """The cache file is corrupt or inconsistent; the message names lines, never content."""


@dataclass(frozen=True)
class KeyParts:
    """Everything that determines an answer (FR2, FR6)."""

    task: str
    backend: str
    model_id: str
    prompt_sha256: str
    decoding: Mapping[str, Any]
    schema_sha256: str
    input_sha256: str

    def __post_init__(self) -> None:
        if self.task not in TASKS:
            raise ValueError("unknown task")
        if not _NAME.fullmatch(self.backend) or not _MODEL.fullmatch(self.model_id):
            raise ValueError("malformed backend name or model ID")
        if not all(_SHA256.fullmatch(value) for value in (self.prompt_sha256, self.schema_sha256, self.input_sha256)):
            raise ValueError("prompt, schema and input hashes must be lowercase SHA-256")
        if not isinstance(self.decoding, Mapping) or not self.decoding:
            raise ValueError("decoding parameters are required")

    @property
    def key(self) -> str:
        payload = {"task": self.task, "backend": self.backend, "model_id": self.model_id,
                   "prompt_sha256": self.prompt_sha256, "decoding": dict(self.decoding),
                   "schema_sha256": self.schema_sha256, "input_sha256": self.input_sha256}
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Entry:
    """One cached answer. ``created`` is metadata and not part of the content comparison."""

    key: str
    raw: str
    finish_reason: str
    usage: Mapping[str, int] = field(default_factory=dict)
    created: str = ""

    def __post_init__(self) -> None:
        problem = _entry_problem(self.key, self.raw, self.finish_reason, self.usage, self.created)
        if problem:
            raise ValueError(problem)

    @property
    def content(self) -> tuple[str, str, tuple[tuple[str, int], ...]]:
        return self.raw, self.finish_reason, tuple(sorted(self.usage.items()))

    def line(self) -> bytes:
        record = {"v": CACHE_VERSION, "key": self.key, "raw": self.raw, "finish_reason": self.finish_reason,
                  "usage": dict(sorted(self.usage.items())), "created": self.created}
        return (json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


class ResponseCache:
    """The append-only cache file; ``load`` once, then ``get`` and ``append`` batches."""

    def __init__(self, path: Path, root: Path = REPO_ROOT) -> None:
        self.path = under_outputs(path, root)
        self._entries: dict[str, Entry] = {}
        self._valid_bytes = 0
        self._torn = False
        self._loaded = False

    def load(self) -> ResponseCache:
        self._entries.clear()
        self._valid_bytes, self._torn = 0, False
        if self.path.exists():
            self._read()
        self._loaded = True
        return self

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, key: str) -> bool:
        return key in self._entries

    def get(self, key: str) -> Entry | None:
        self._require_loaded()
        return self._entries.get(key)

    def append(self, entries: Iterable[Entry]) -> int:
        """Append new entries in one durable write; returns how many were new. An entry whose key is
        already cached must carry identical content (it is then skipped)."""
        self._require_loaded()
        fresh: list[Entry] = []
        pending: dict[str, Entry] = {}
        for entry in entries:
            known = self._entries.get(entry.key) or pending.get(entry.key)
            if known is not None:
                if known.content != entry.content:
                    raise CacheError("a cached key was answered again with different content")
                continue
            pending[entry.key] = entry
            fresh.append(entry)
        if not fresh:
            return 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("ab") as handle:
            if self._torn:
                handle.truncate(self._valid_bytes)
                self._torn = False
            data = b"".join(entry.line() for entry in fresh)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        self._valid_bytes += len(data)
        self._entries.update(pending)
        return len(fresh)

    def _read(self) -> None:
        with self.path.open("rb") as handle:
            number = 0
            while True:
                line = handle.readline(MAX_LINE_BYTES + 1)
                if not line:
                    break
                number += 1
                if not line.endswith(b"\n"):
                    if len(line) > MAX_LINE_BYTES:
                        raise CacheError(f"cache line {number} is longer than {MAX_LINE_BYTES} bytes")
                    if handle.read(1):
                        raise CacheError(f"cache line {number} is malformed")
                    log.warning("cache: dropped a torn final line (line %d) left by an interrupted write", number)
                    self._torn = True
                    break
                entry = _parse_line(line, number)
                known = self._entries.get(entry.key)
                if known is not None and known.content != entry.content:
                    raise CacheError(f"cache line {number} repeats a key with different content")
                self._entries.setdefault(entry.key, entry)
                self._valid_bytes += len(line)

    def _require_loaded(self) -> None:
        if not self._loaded:
            raise RuntimeError("load() the cache before using it")


@contextmanager
def exclusive_lock(cache_path: Path) -> Iterator[None]:
    """Hold an OS lock on ``<cache>.lock`` for one run, so two runs can't interleave appends.

    The OS lock (``fcntl.flock`` on POSIX, ``msvcrt.locking`` on Windows) dies with the process,
    so a killed run never leaves a stale lock to clear by hand before the resume.
    """
    lock_path = cache_path.with_name(cache_path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        try:
            _lock(handle)
        except OSError:
            raise CacheError("another run holds this cache's lock; wait for it to finish") from None
        try:
            yield
        finally:
            _unlock(handle)


def _lock(handle: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(handle: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def new_entry(key: str, raw: str, finish_reason: str, usage: Mapping[str, int] | None = None) -> Entry:
    """An entry stamped with the current UTC time."""
    return Entry(key, raw, finish_reason, dict(usage or {}), datetime.now(timezone.utc).isoformat(timespec="seconds"))


def _parse_line(line: bytes, number: int) -> Entry:
    try:
        record = json.loads(line.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise CacheError(f"cache line {number} is malformed") from None
    if not isinstance(record, dict) or set(record) != _FIELDS or record["v"] != CACHE_VERSION:
        raise CacheError(f"cache line {number} has unknown fields or version")
    problem = _entry_problem(record["key"], record["raw"], record["finish_reason"], record["usage"], record["created"])
    if problem:
        raise CacheError(f"cache line {number}: {problem}")
    return Entry(record["key"], record["raw"], record["finish_reason"], record["usage"], record["created"])


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """A repeated JSON key would let two readers see different values; refuse it."""
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate JSON key")
    return dict(pairs)


def _entry_problem(key: Any, raw: Any, finish_reason: Any, usage: Any, created: Any) -> str | None:
    if not isinstance(key, str) or not _SHA256.fullmatch(key):
        return "cache key must be a lowercase SHA-256"
    if not isinstance(raw, str) or len(raw) > MAX_RAW_CHARS + 1:
        return "raw output must be a string clipped to the parser's bound"
    if finish_reason not in FINISH_REASONS:
        return "unknown finish reason"
    if (not isinstance(usage, Mapping) or len(usage) > MAX_USAGE_FIELDS
            or any(not isinstance(k, str) or not _NAME.fullmatch(k) for k in usage)
            or any(type(v) is not int or v < 0 for v in usage.values())):
        return "usage must map short names to non-negative integers"
    if not isinstance(created, str) or len(created) > 40:
        return "created must be a short timestamp string"
    return None
