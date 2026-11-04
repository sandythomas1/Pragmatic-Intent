"""Backend interface, transport retry and error sanitizing (spec 009 T6, FR5, FR7, Security).

Every backend implements one method: a batch of ``Request(key, messages, schema)`` goes in and
one ``Response(key, raw, finish_reason, usage)`` per request comes out, in order.

Calls end in one of two classes (FR5):
- **content outcome**: a ``Response``, however bad its text. The parser turns it into a valid
  answer or a counted ``invalid``, after exactly one call;
- **transport failure**: the backend raises ``TransportError`` (connection, timeout, 429, 5xx,
  worker crash). ``generate_with_retry`` retries the batch with full-jitter exponential backoff,
  honouring ``retry-after``, and after the last attempt raises ``RunStopped``. No row is written,
  and a rerun resumes from the cache.

Any other exception is an unmapped failure: the run stops at once, without retry.

Exceptions never reach logs or stderr whole, because a provider error body can echo the prompt.
Only the class name, HTTP status, a charset-checked provider request ID and a hash of the batch's
cache keys are shown. The full text goes to a git-ignored raw error log under ``outputs/``.
``RunStopped`` is raised ``from None``, so a traceback can't print the original either.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from src.llm.paths import REPO_ROOT, under_outputs
from src.llm.preflight import TokenCounter
from src.llm.schema import FINISH_REASONS, MAX_RAW_CHARS

if TYPE_CHECKING:
    from src.llm.recipe import Recipe

ATTEMPTS = 5
BACKOFF_BASE = 2.0
BACKOFF_CAP = 60.0
MAX_RETRY_AFTER = 300.0
_REQUEST_ID = re.compile(r"[A-Za-z0-9_\-]{1,128}\Z")
log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Request:
    """One call: the cache key, rendered chat messages and the output schema to enforce."""

    key: str
    messages: tuple[Mapping[str, str], ...]
    schema: Mapping[str, Any]


@dataclass(frozen=True)
class Response:
    """One content outcome. ``raw`` is clipped to one char past the parser's bound, which keeps the
    parser's ``too_long`` outcome while bounding what is cached."""

    key: str
    raw: str
    finish_reason: str
    usage: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.raw, str):
            raise TypeError("backend raw output must be a string")
        if self.finish_reason not in FINISH_REASONS:
            raise ValueError("backend reported an unknown finish reason")
        object.__setattr__(self, "raw", self.raw[:MAX_RAW_CHARS + 1])


class TransportError(Exception):
    """A retryable failure to get any answer (FR5). Real backends map provider errors to this."""

    def __init__(self, message: str = "", *, status: int | None = None, request_id: str | None = None,
                 retry_after: float | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.request_id = request_id
        self.retry_after = retry_after


class RunStopped(RuntimeError):
    """The run stopped resumably; its message is sanitized and safe to print."""


class Backend(ABC):
    """A model behind one batch call. ``name`` is the recipe's ``backend``."""

    name: ClassVar[str]
    model_id: str
    paid: ClassVar[bool] = False

    @classmethod
    @abstractmethod
    def from_recipe(cls, recipe: Recipe) -> Backend:
        """Build the backend from a validated recipe; ``model_id`` must equal ``recipe.model_ref``."""

    def token_counter(self) -> TokenCounter | None:
        """The pinned tokenizer's prompt-length count for the FR5a preflight; ``None`` when the
        provider has no local context limit to check."""
        return None

    @classmethod
    def counter_from_recipe(cls, recipe: Recipe) -> TokenCounter | None:
        """The token counter alone, for sizing ``max_model_len``. A backend whose model is costly to
        load overrides this to load only its tokenizer."""
        return cls.from_recipe(recipe).token_counter()

    @abstractmethod
    def generate(self, batch: Sequence[Request]) -> list[Response]:
        """One ``Response`` per request, same order; raise ``TransportError`` for transport failures."""


@dataclass
class CallStats:
    """Counts for progress logs and provenance (FR8)."""

    batches: int = 0
    calls: int = 0
    retries: int = 0
    rate_limited: int = 0
    transport_errors: int = 0


class ErrorLog:
    """Append-only raw error log under git-ignored ``outputs/``; the only place full error text goes."""

    def __init__(self, path: Path, root: Path = REPO_ROOT) -> None:
        self.path = under_outputs(path, root)

    def write(self, error: BaseException, keys_hash: str, attempt: int) -> None:
        record = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "attempt": attempt,
                  "keys_hash": keys_hash, "class": type(error).__name__, "detail": repr(error)}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def keys_hash(batch: Sequence[Request]) -> str:
    """A short, content-free handle for a batch, to match a log line with the raw error log."""
    return hashlib.sha256("\n".join(request.key for request in batch).encode("ascii")).hexdigest()[:16]


def describe(error: BaseException, batch_hash: str) -> str:
    """The sanitized one-line form: class, status, request ID and batch hash only."""
    parts = [type(error).__name__]
    status = getattr(error, "status", None)
    if type(status) is int and 100 <= status <= 599:
        parts.append(f"status={status}")
    request_id = getattr(error, "request_id", None)
    if isinstance(request_id, str) and _REQUEST_ID.fullmatch(request_id):
        parts.append(f"request_id={request_id}")
    parts.append(f"keys={batch_hash}")
    return " ".join(parts)


def backoff_delay(failure: int, rng: random.Random, retry_after: float | None = None, *,
                  base: float = BACKOFF_BASE, cap: float = BACKOFF_CAP) -> float:
    """Full jitter: uniform in [0, min(cap, base * 2**(failure-1))], raised to a sane ``retry-after``."""
    if failure < 1:
        raise ValueError("failure counts from 1")
    delay = rng.uniform(0.0, min(cap, base * 2 ** (failure - 1)))
    if isinstance(retry_after, (int, float)) and not isinstance(retry_after, bool) and retry_after > 0:
        delay = max(delay, min(float(retry_after), MAX_RETRY_AFTER))
    return delay


def generate_with_retry(backend: Backend, batch: Sequence[Request], *, error_log: ErrorLog,
                        stats: CallStats, sleep: Callable[[float], None], rng: random.Random,
                        attempts: int = ATTEMPTS) -> list[Response]:
    """One batch, retried on transport failure only; returns one checked response per request."""
    if not batch:
        return []
    batch_hash = keys_hash(batch)
    for attempt in range(1, attempts + 1):
        try:
            stats.calls += len(batch)
            responses = backend.generate(batch)
        except TransportError as error:
            stats.transport_errors += 1
            stats.rate_limited += error.status == 429
            error_log.write(error, batch_hash, attempt)
            summary = describe(error, batch_hash)
            if attempt == attempts:
                raise RunStopped(f"transport failure after {attempts} attempts ({summary}); "
                                 "rerun to resume from the cache") from None
            delay = backoff_delay(attempt, rng, error.retry_after)
            log.warning("transport failure, attempt %d of %d (%s); retrying in %.1fs", attempt, attempts, summary, delay)
            stats.retries += 1
            sleep(delay)
            continue
        except Exception as error:  # noqa: BLE001 - unmapped failures stop the run, sanitized
            error_log.write(error, batch_hash, attempt)
            raise RunStopped(f"backend failed with an unmapped error ({describe(error, batch_hash)}); "
                             "see the raw error log under outputs/") from None
        stats.batches += 1
        return _checked(batch, responses)
    raise AssertionError("unreachable")


def _checked(batch: Sequence[Request], responses: Any) -> list[Response]:
    if (not isinstance(responses, list) or len(responses) != len(batch)
            or any(not isinstance(r, Response) or r.key != q.key for q, r in zip(batch, responses))):
        raise RunStopped("backend returned responses that do not match its batch (keys or order)")
    return responses
