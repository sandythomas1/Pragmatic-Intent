"""Load the spec 006 test audit before any test score; every doubt fails closed.

Stage 1 and Stage 2 test scoring call ``require_test_audit``. It validates the committed audit
file and summary (schema, row fields, the summary's own content hash) and compares the recorded
hashes of ``items.jsonl``, ``dialogues.jsonl`` and the registry's ``pre_freeze`` rows with the
current files, so a stale or edited audit can't gate a reported number. Scorers then keep the
primary examples only and report one uncrossed ``primary_minus_dup`` line per contrast.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.data import split_audit as sa
from src.stage1.data import PARAPHRASE_VARIANTS, Stage1Example

_ITEM_ID_RE = re.compile(r"(?P<stem>(?:PMUL|MUL|SNG|SSNG|WOZ)[0-9]{4,5})_t[0-9]{1,3}")
_FLAGS = ("mismatch_set", "primary", "dup_exact", "donor_inspected")


class TestAuditError(ValueError):
    """The test audit is missing, malformed, tampered with or stale."""

    __test__ = False  # not a test case, despite the name


@dataclass(frozen=True)
class SplitAudit:
    primary_ids: frozenset[str]
    excluded: dict[str, str]  # example_id -> exclusion reason
    dup_ids: frozenset[str]  # primary examples flagged dup_exact
    content_sha256: str

    def primary_examples(self, examples: Sequence[Stage1Example]) -> list[Stage1Example]:
        """The primary examples; the audit must cover exactly the scoring set."""
        ids = {e.example_id for e in examples}
        audited = self.primary_ids | self.excluded.keys()
        if ids != audited:
            raise TestAuditError(f"the audit covers {len(audited)} examples but the test set has {len(ids)} "
                                 f"({len(ids - audited)} unaudited); rebuild it with split_audit audit")
        return [e for e in examples if e.example_id in self.primary_ids]

    def drop_excluded(self, predictions: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
        """Predictions for excluded examples are ignored, so a model may predict the whole test set."""
        return [row for row in predictions if not (isinstance(row, Mapping) and row.get("example_id") in self.excluded)]

    def report(self, scored: int) -> dict[str, Any]:
        return {"content_sha256": self.content_sha256, "primary_examples": scored,
                "excluded_examples": len(self.excluded),
                "excluded_by_reason": dict(sorted(Counter(self.excluded.values()).items())),
                "dup_exact_primary": len(self.dup_ids),
                "sensitivities": {"primary_minus_dup": "primary examples minus dup_exact, never crossed with "
                                                       "without_cue_donors"}}


def load_test_audit(audit_path: Path, summary_path: Path, *, items_sha256: str, dialogues_sha256: str,
                    registry_sha256: str) -> SplitAudit:
    """Validate the audit files against each other and against the current input hashes."""
    try:
        data = sa.read_bounded(audit_path)
        summary = json.loads(sa.read_bounded(summary_path).decode("utf-8"))
    except FileNotFoundError:
        raise TestAuditError("test scoring needs the spec 006 audit; run python -m src.data.split_audit audit") from None
    except (OSError, ValueError) as error:
        raise TestAuditError(f"unreadable test audit: {error}") from None
    _check_summary(summary, data)
    recorded = summary["inputs"]
    for name, current in (("items_sha256", items_sha256), ("dialogues_sha256", dialogues_sha256),
                          ("registry_pre_freeze_sha256", registry_sha256)):
        if recorded.get(name) != current:
            raise TestAuditError(f"stale test audit: {name} differs from the current file; rebuild the audit")
    primary, excluded, dup = _parse_rows(data)
    if (len(primary), len(dup)) != (summary["primary"]["genuine"], summary["dup_exact"]["overall"]["flagged"]):
        raise TestAuditError("test audit rows disagree with the summary counts")
    return SplitAudit(frozenset(primary), excluded, frozenset(dup), summary["content_sha256"])


def _check_summary(summary: Any, data: bytes) -> None:
    if not isinstance(summary, dict) or summary.get("schema_version") != sa.AUDIT_SCHEMA_VERSION \
            or summary.get("split") != "test":
        raise TestAuditError(f"the summary is not a {sa.AUDIT_SCHEMA_VERSION} test summary")
    if summary.get("content_sha256") != sa.audit_content_sha256(summary):
        raise TestAuditError("the summary's content hash does not match; it was edited after it was built")
    if summary.get("audit_sha256") != hashlib.sha256(data).hexdigest():
        raise TestAuditError("the audit CSV does not match audit_sha256 in its summary")
    try:
        if not isinstance(summary["inputs"], dict) or not isinstance(summary["primary"]["genuine"], int) \
                or not isinstance(summary["dup_exact"]["overall"]["flagged"], int):
            raise TypeError
    except (KeyError, TypeError):
        raise TestAuditError("the summary lacks inputs or counts") from None


def _parse_rows(data: bytes) -> tuple[set[str], dict[str, str], set[str]]:
    """Primary IDs, excluded ID -> reason, and primary IDs flagged ``dup_exact``."""
    try:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""), strict=True)
        if tuple(reader.fieldnames or ()) != sa.AUDIT_FIELDS:
            raise TestAuditError("the audit CSV columns are wrong")
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error):
        raise TestAuditError("the audit CSV is not valid UTF-8 CSV") from None
    codes = sa.exclusion_codes()
    primary, dup, excluded = set(), set(), {}
    for line, row in enumerate(rows, start=2):
        problem = _row_problem(row, codes)
        if problem or row["example_id"] in primary or row["example_id"] in excluded:
            raise TestAuditError(f"audit line {line}: {problem or 'duplicate example_id'}")
        if row["primary"] == "1":
            primary.add(row["example_id"])
            if row["dup_exact"] == "1":
                dup.add(row["example_id"])
        else:
            excluded[row["example_id"]] = row["exclusion"]
    return primary, excluded, dup


def _row_problem(row: Mapping[str, str | None], codes: frozenset[str]) -> str | None:
    if None in row or any(not isinstance(value, str) for value in row.values()):
        return "wrong number of cells"
    match = _ITEM_ID_RE.fullmatch(row["item_id"])
    if match is None or row["dialogue_id"] != f"{match['stem']}.json":
        return "malformed item or dialogue ID"
    if row["variant"] not in PARAPHRASE_VARIANTS or row["example_id"] != f"{row['item_id']}:{row['variant']}":
        return "malformed example ID"
    if any(row[flag] not in ("0", "1") for flag in _FLAGS):
        return "a flag is not 0 or 1"
    if (row["primary"] == "1") != (row["exclusion"] == "") or (row["exclusion"] and row["exclusion"] not in codes):
        return "primary and exclusion disagree, or the exclusion is unknown"
    return None


def audit_summary_path(audit_path: Path) -> Path:
    """``split_audit_test.csv`` -> ``split_audit_test_summary.json`` beside it."""
    return audit_path.with_name(f"{audit_path.stem}_summary.json")


def require_test_audit(items_path: Path, dialogues_path: Path, *, registry_path: Path = sa.DEFAULT_REGISTRY,
                       audit_path: Path = sa.DEFAULT_AUDIT, summary_path: Path = sa.DEFAULT_AUDIT_SUMMARY) -> SplitAudit:
    """``load_test_audit`` against the current items, dialogues and registry (FR15)."""
    index = sa.load_corpus_index(items_path)
    try:
        registry = sa.load_registry(registry_path, index.dialogue_split)
    except sa.RegistryError as error:
        raise TestAuditError(f"invalid registry: {error.problems[0]}") from None
    return load_test_audit(audit_path, summary_path, items_sha256=sa.file_sha256(items_path),
                           dialogues_sha256=sa.file_sha256(dialogues_path),
                           registry_sha256=sa.pre_freeze_sha256(registry))
