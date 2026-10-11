"""Vocabulary, input checks, canonical hashing and derived fields for contextual annotation (spec 003).

Everything here is pure: no file or network access. The CLI (``src.annotation.context``) and the
registry, view and validation modules build on these definitions, so this module is the single
place where an enum value, an ID shape or the hash serialization is defined.

Annotation happens in three sealed passes per annotator (spec 003 FR5–FR7):

* ``form``: the target utterance alone, labeled with rubric v2 (``L0``–``L3``, ``INF``, ``NR``, ``?``).
* ``context``: prior context only. Function, intent, slots, paraphrase, evidence, confidence, depth.
* ``reveal``: the continuation. Whether later text corroborates, conflicts with or is required for
  the context-pass reading.

Request status and request type are *derived* from those labels and never typed by an annotator
(FR11). In particular, a wording-only ``INF`` that functions as a request in context is a request of
unknown form, never a non-request (spec 001 AC-03).
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Collection, Mapping

from src.annotation.levels import LABELS as FORM_LABELS

PROTOCOL_VERSION = "ctx-v0"
SEGMENTER_VERSION = "seg-v1"

PASSES = ("form", "context", "reveal")
STRATA = ("dialogue", "literary")
FUNCTIONS = ("request", "inform", "decline", "social", "other", "uncertain")
CONFIDENCES = ("certain", "probable", "uncertain")
DEPTHS = ("", "one_step", "multi_step", "uncertain")  # exploratory; blank means not judged
FUTURE_DEPENDENCE = ("none", "corroborates", "conflicts", "required")
CORRECTION_REASONS = ("typo", "wrong_sheet", "wrong_annotator", "rubric_misread", "other")
FRAGMENT_VALUES = ("0", "1")

REQUEST_STATUSES = ("present", "absent", "uncertain")
REQUEST_TYPES = ("direct", "indirect", "form_unknown", "uncertain", "none")
OUT_OF_TAXONOMY = "out_of_taxonomy"
UNSTATED_SLOT_VALUE = "?"

MAX_FREE_TEXT_CHARS = 500

# Fields left out of a row's canonical hash (FR10): the chain link itself, the free-text digest
# (hashed separately so local notes can change) and the superseded marker that `correct` sets.
HASH_EXCLUDED_FIELDS = frozenset({"prior_sha256", "text_sha256", "status"})

ANNOTATOR_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,15}")
BATCH_RE = re.compile(r"[a-z][a-z0-9_-]{0,31}")  # becomes a directory name: no dots, no separators
_WINDOWS_RESERVED_NAMES = frozenset(
    {"con", "prn", "aux", "nul"} | {f"com{n}" for n in range(1, 10)} | {f"lpt{n}" for n in range(1, 10)}
)
NAME_RE = re.compile(r"[a-z][a-z0-9_]{0,39}")  # intent IDs and slot names
TAXONOMY_VERSION_RE = re.compile(r"ctx-tax-v[0-9]{1,3}")
DIALOGUE_ITEM_RE = re.compile(r"d:[A-Za-z0-9][A-Za-z0-9_-]{0,39}:t[0-9]{2,3}")
LITERARY_ITEM_RE = re.compile(r"lit-[0-9a-f]{10}")  # the spec 002 candidate ID
FORM_ROW_RE = re.compile(r"f-[0-9]{3,5}")  # opaque form-sheet row IDs

# Characters that never belong in a single-line cell: controls (incl. newline/tab), invisible
# format characters (incl. bidi overrides), line/paragraph separators and lone surrogates.
_FORBIDDEN_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp", "Cs"})


class SchemaError(ValueError):
    """A value breaks the annotation schema; the message names the field and the rule."""


# --------------------------------------------------------------------------- input checks


def require_match(pattern: re.Pattern[str], value: str, label: str) -> str:
    """Return ``value`` if the *whole* string matches ``pattern``; otherwise raise.

    ``fullmatch`` is deliberate: ``re.match`` with ``$`` would accept a trailing newline.
    """
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise SchemaError(f"{label} {value!r} does not match {pattern.pattern}")
    return value


def require_enum(value: str, allowed: Collection[str], label: str) -> str:
    if value not in allowed:
        choices = ", ".join(repr(choice) for choice in allowed)
        raise SchemaError(f"{label} {value!r} is not one of {choices}")
    return value


def annotator_id(value: str) -> str:
    return require_match(ANNOTATOR_RE, value, "annotator")


def batch_id(value: str) -> str:
    require_match(BATCH_RE, value, "batch")
    if value in _WINDOWS_RESERVED_NAMES:
        raise SchemaError(f"batch {value!r} is a reserved device name on Windows")
    return value


def item_id(value: str) -> str:
    if DIALOGUE_ITEM_RE.fullmatch(value) or LITERARY_ITEM_RE.fullmatch(value):
        return value
    raise SchemaError(f"item_id {value!r} is neither d:<dialogue>:tNN nor lit-<10 hex>")


def dialogue_item_id(dialogue_id: str, turn_index: int) -> str:
    """``PMUL1234.json`` + 6 → ``d:PMUL1234:t06``; the result is validated."""
    if turn_index < 0:
        raise SchemaError(f"turn_index {turn_index} is negative")
    return item_id(f"d:{dialogue_id.removesuffix('.json')}:t{turn_index:02d}")


def free_text(value: str, label: str, limit: int = MAX_FREE_TEXT_CHARS) -> str:
    """Return a single-line annotator text of at most ``limit`` characters; otherwise raise.

    Unlike ``str.isprintable``, this allows non-breaking and other Unicode spaces, which Excel
    and pasted text often contain. It rejects only characters that break a line or hide content.
    """
    if len(value) > limit:
        raise SchemaError(f"{label} is longer than {limit} characters")
    for char in value:
        if unicodedata.category(char) in _FORBIDDEN_CATEGORIES:
            raise SchemaError(f"{label} contains a newline, tab or invisible control character (U+{ord(char):04X})")
    return value


# --------------------------------------------------------------------------- canonical hashing


def _sha256_json(obj: Mapping[str, str]) -> str:
    text = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_hash(row: Mapping[str, str], exclude: Collection[str] = HASH_EXCLUDED_FIELDS) -> str:
    """SHA-256 of a committed row in its canonical form (spec 003 FR10).

    Every value must already be a string, exactly as it is written to and read back from CSV.
    Hashing an int at export time and the same value as a string at validation time would give
    two different hashes, so non-strings are rejected rather than converted.
    """
    kept: dict[str, str] = {}
    for key, value in row.items():
        if key in exclude:
            continue
        if not isinstance(key, str) or not isinstance(value, str):
            raise TypeError(f"canonical_hash needs str keys and values; field {key!r} is {type(value).__name__}")
        kept[key] = value
    return _sha256_json(kept)


def text_hash(item: str, pass_name: str, annotator: str, slots: str, paraphrase: str) -> str:
    """Digest of the free-text gold kept in the local text file (FR10). Notes are excluded."""
    return canonical_hash(
        {"item_id": item, "pass": pass_name, "annotator": annotator, "slots": slots, "paraphrase": paraphrase},
        exclude=(),
    )


# --------------------------------------------------------------------------- derived fields


def request_status(function: str) -> str:
    """``present`` for a request, ``uncertain`` when presence can't be told, else ``absent``."""
    require_enum(function, FUNCTIONS, "function")
    if function == "request":
        return "present"
    if function == "uncertain":
        return "uncertain"
    return "absent"


def request_type(form: str, status: str) -> str:
    """Stage 1 target from a wording-only form label and a context request status (FR11).

    The form label never decides presence: ``INF``/``NR``/``?`` on a contextual request gives
    ``form_unknown`` (binary detection only), never ``none``.
    """
    require_enum(form, FORM_LABELS, "form")
    require_enum(status, REQUEST_STATUSES, "request_status")
    if status == "absent":
        return "none"
    if status == "uncertain":
        return "uncertain"
    if form == "L0":
        return "direct"
    if form in ("L1", "L2", "L3"):
        return "indirect"
    return "form_unknown"


def confirmatory_eligible(future_dependence: str) -> bool:
    """False when the reading is only recoverable from text after the target."""
    return require_enum(future_dependence, FUTURE_DEPENDENCE, "future_dependence") != "required"


def needs_adjudication(future_dependence: str) -> bool:
    """True when the story's own continuation contradicts the context-pass reading."""
    return require_enum(future_dependence, FUTURE_DEPENDENCE, "future_dependence") == "conflicts"
