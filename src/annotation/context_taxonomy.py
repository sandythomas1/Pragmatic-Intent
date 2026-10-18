"""The versioned intent taxonomy and slot checks for the context pass (spec 003 FR3, FR6).

``data/annotations/intent_taxonomy.csv`` is committed and append-only by version: one row per
(``taxonomy_version``, ``intent_id``) with its required and optional slot names. A context label
records the version it used and is checked against that version's slots, so adding ``ctx-tax-v1``
never invalidates labels made under ``ctx-tax-v0``. Deleting a version that a label references is
an error. A version is frozen once labels use it; a change means a new version.

``out_of_taxonomy`` is reserved: always valid, never listed in the file, and it takes no slots
(an unrepresented request is still a request; its details go in local notes).

Slots are written ``name=value;name=value``. ``name=?`` records a required slot that the source
leaves unstated (review R2), so no annotator ever has to invent a value. Values are typed in the
source's own words; normalization belongs to the scorer (spec 005).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from src.annotation import context_schema as cs
from src.annotation.levels import AnnotationError, read_csv

TAXONOMY_FILE = "intent_taxonomy.csv"
TAXONOMY_FIELDS = ("taxonomy_version", "intent_id", "stratum", "required_slots", "optional_slots", "description")
INTENT_STRATA = ("dialogue", "literary", "both")
MAX_DESCRIPTION_CHARS = 200
_FORMULA_PREFIXES = ("=", "+", "-", "@")


class TaxonomyError(Exception):
    """The taxonomy file is invalid; ``problems`` lists every reason."""

    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__(f"{len(problems)} problem(s):\n  " + "\n  ".join(problems))
        self.problems = list(problems)


@dataclass(frozen=True)
class Intent:
    version: str
    intent_id: str
    stratum: str
    required: tuple[str, ...]
    optional: tuple[str, ...]

    def allows(self, item_stratum: str) -> bool:
        return self.stratum in ("both", item_stratum)


OUT_OF_TAXONOMY = Intent("", cs.OUT_OF_TAXONOMY, "both", (), ())


@dataclass(frozen=True)
class Taxonomy:
    intents: Mapping[str, Mapping[str, Intent]]  # version → intent_id → Intent

    @property
    def versions(self) -> tuple[str, ...]:
        return tuple(sorted(self.intents))

    @property
    def latest(self) -> str:
        """The newest version by number (``ctx-tax-v10`` is newer than ``ctx-tax-v9``)."""
        return max(self.intents, key=lambda version: int(version.rsplit("v", 1)[1]))

    def sha256(self, version: str) -> str:
        """Canonical hash of one version's intents and slots (descriptions excluded).

        Context rows record it (FR8), so editing a version in place after labels use it is
        detectable: "append-only" protects against deletion, this protects against redefinition.
        """
        intents = self.intents.get(version)
        if not intents:
            raise cs.SchemaError(f"taxonomy_version {version!r} has no intents")
        canonical = {
            intent_id: f"{intent.stratum}|{';'.join(sorted(intent.required))}|{';'.join(sorted(intent.optional))}"
            for intent_id, intent in intents.items()
        }
        return cs.canonical_hash(canonical, exclude=())

    def intent(self, version: str, intent_id: str) -> Intent:
        if version not in self.intents:
            raise cs.SchemaError(f"taxonomy_version {version!r} is not in {TAXONOMY_FILE}")
        if intent_id == cs.OUT_OF_TAXONOMY:
            return OUT_OF_TAXONOMY
        intent = self.intents[version].get(intent_id)
        if intent is None:
            raise cs.SchemaError(f"intent {intent_id!r} is not defined in {version}")
        return intent


# --------------------------------------------------------------------------- loading


def load_taxonomy(path: Path) -> Taxonomy:
    """Read and validate the taxonomy file; a missing file is an error (labels need a version)."""
    if not path.exists():
        raise TaxonomyError([f"no taxonomy at {path}"])
    try:
        rows = read_csv(path)
    except AnnotationError as error:
        raise TaxonomyError([str(error)]) from None
    if rows and tuple(rows[0]) != TAXONOMY_FIELDS:
        raise TaxonomyError([f"{path}: columns {list(rows[0])} do not match {list(TAXONOMY_FIELDS)}"])
    problems = validate_rows(rows)
    if problems:
        raise TaxonomyError(problems)
    return build(rows)


def build(rows: Iterable[Mapping[str, str]]) -> Taxonomy:
    intents: dict[str, dict[str, Intent]] = defaultdict(dict)
    for row in rows:
        intents[row["taxonomy_version"]][row["intent_id"]] = Intent(
            row["taxonomy_version"],
            row["intent_id"],
            row["stratum"],
            split_names(row["required_slots"]),
            split_names(row["optional_slots"]),
        )
    return Taxonomy(dict(intents))


def split_names(value: str) -> tuple[str, ...]:
    return tuple(name.strip() for name in value.split(";") if name.strip())


def validate_rows(rows: Sequence[Mapping[str, str]]) -> list[str]:
    """Every problem in the taxonomy rows, each naming its version, intent and rule."""
    problems: list[str] = []
    seen: set[tuple[str, str]] = set()
    for line, row in enumerate(rows, start=2):
        if set(row) != set(TAXONOMY_FIELDS) or any(value is None for value in row.values()):
            problems.append(f"line {line}: columns do not match the taxonomy header")
            continue
        label = f"{row['taxonomy_version'] or '?'}/{row['intent_id'] or '?'}"
        key = (row["taxonomy_version"], row["intent_id"])
        if key in seen:
            problems.append(f"{label}: duplicate intent within its version")
        seen.add(key)
        problems.extend(f"{label}: {problem}" for problem in _row_problems(row))
    return problems


def _row_problems(row: Mapping[str, str]) -> list[str]:
    problems: list[str] = []
    for check in (
        lambda: cs.require_match(cs.TAXONOMY_VERSION_RE, row["taxonomy_version"], "taxonomy_version"),
        lambda: cs.require_match(cs.NAME_RE, row["intent_id"], "intent_id"),
        lambda: cs.require_enum(row["stratum"], INTENT_STRATA, "stratum"),
        lambda: cs.free_text(row["description"], "description", limit=MAX_DESCRIPTION_CHARS),
    ):
        try:
            check()
        except cs.SchemaError as error:
            problems.append(str(error))
    if row["intent_id"] == cs.OUT_OF_TAXONOMY:
        problems.append(f"{cs.OUT_OF_TAXONOMY} is reserved and must not be listed")
    if not row["description"].strip():
        problems.append("description is empty")
    elif row["description"].startswith(_FORMULA_PREFIXES):
        problems.append("description starts with a spreadsheet formula character")
    required, optional = split_names(row["required_slots"]), split_names(row["optional_slots"])
    for field, names in (("required_slots", required), ("optional_slots", optional)):
        for name in names:
            if cs.NAME_RE.fullmatch(name) is None:
                problems.append(f"{field}: slot name {name!r} does not match {cs.NAME_RE.pattern}")
        if len(set(names)) != len(names):
            problems.append(f"{field}: a slot is listed twice")
    overlap = sorted(set(required) & set(optional))
    if overlap:
        problems.append(f"slot(s) {overlap} are both required and optional")
    return problems


def missing_versions(taxonomy: Taxonomy, referenced: Iterable[str]) -> list[str]:
    """Problems for label versions the taxonomy no longer contains (FR3: versions are append-only)."""
    return [f"taxonomy_version {version!r} is used by committed labels but missing from {TAXONOMY_FILE}"
            for version in sorted(set(referenced)) if version not in taxonomy.intents]  # fmt: skip


def version_sha256(rows: Iterable[Mapping[str, str]], version: str) -> str:
    """``Taxonomy.sha256`` straight from file rows."""
    return build(row for row in rows if row["taxonomy_version"] == version).sha256(version)


# --------------------------------------------------------------------------- slots


def parse_slots(text: str) -> list[tuple[str, str]]:
    """``"area=north; food=?"`` → ``[("area", "north"), ("food", "?")]``; raise on a malformed pair.

    Empty segments (e.g. a trailing ``;``) are ignored. A value may contain ``=``; it may not be
    empty (write ``?`` when the source leaves it unstated). A slot name may appear once.
    """
    cs.free_text(text, "slots")
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for part in (segment.strip() for segment in text.split(";")):
        if not part:
            continue
        name, separator, value = part.partition("=")
        name, value = name.strip(), value.strip()
        if not separator:
            raise cs.SchemaError(f"slot {part!r} is not name=value (use name=? when the source doesn't say)")
        cs.require_match(cs.NAME_RE, name, "slot name")
        if not value:
            raise cs.SchemaError(f"slot {name!r} has no value (use {name}=? when the source doesn't say)")
        if name in seen:
            raise cs.SchemaError(f"slot {name!r} appears twice")
        seen.add(name)
        pairs.append((name, value))
    return pairs


def slot_problems(intent: Intent, pairs: Sequence[tuple[str, str]]) -> list[str]:
    """Rule violations of ``pairs`` against ``intent``: missing required or undefined slots."""
    names = [name for name, _ in pairs]
    if intent.intent_id == cs.OUT_OF_TAXONOMY:
        return [f"{cs.OUT_OF_TAXONOMY} takes no slots; put details in notes"] if names else []
    problems = [f"required slot {name!r} is missing (write {name}=? if the source doesn't say)"
                for name in intent.required if name not in names]  # fmt: skip
    allowed = set(intent.required) | set(intent.optional)
    problems += [f"slot {name!r} is not defined for {intent.intent_id} in {intent.version}" for name in names if name not in allowed]
    return problems


def canonical_slots(pairs: Sequence[tuple[str, str]]) -> str:
    """One canonical string for hashing: pairs sorted by name, ``name=value`` joined by ``;``."""
    return ";".join(f"{name}={value}" for name, value in sorted(pairs))


def unstated(pairs: Sequence[tuple[str, str]]) -> list[str]:
    """Slot names recorded as ``?`` (unstated in the source)."""
    return [name for name, value in pairs if value == cs.UNSTATED_SLOT_VALUE]
