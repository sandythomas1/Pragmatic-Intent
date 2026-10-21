"""Read the WP-08 freeze record (``data/manifests/freeze.json``) for the analysis gates.

Spec 007 needs two fields; the proposed spec 008 writer owns the rest of the record:

- ``analysis_config_sha256``: the canonical hash of the frozen analysis config. A test analysis
  refuses any other config (FR21).
- ``freeze_date``: YYYY-MM-DD. The error audit takes its date floor from here only, with no
  command-line override (FR23).
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import Any

from src.analysis.files import AnalysisError, parse_json, read_bounded
from src.data.split_audit import FREEZE_FILE

MAX_FREEZE_BYTES = 1 << 16
_SHA256_RE = re.compile(r"[0-9a-f]{64}")

__all__ = ["FREEZE_FILE", "freeze_date", "read_freeze", "require_frozen_config"]


def read_freeze(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise AnalysisError("freeze_missing", f"{path} does not exist; the WP-08 freeze record is required")
    record = parse_json(read_bounded(path, MAX_FREEZE_BYTES), path.name)
    if not isinstance(record, dict):
        raise AnalysisError("freeze_malformed", f"{path.name} must hold a JSON object")
    return record


def require_frozen_config(path: Path, config_sha256: str) -> str:
    """The recorded config hash, which must equal ``config_sha256``; returns it."""
    recorded = read_freeze(path).get("analysis_config_sha256")
    if not isinstance(recorded, str) or _SHA256_RE.fullmatch(recorded) is None:
        raise AnalysisError("freeze_malformed", f"{path.name}: analysis_config_sha256 must be a SHA-256 hex digest")
    if recorded != config_sha256:
        raise AnalysisError("config_not_frozen",
                            f"the analysis config hash {config_sha256[:12]}… is not the frozen {recorded[:12]}…")
    return recorded


def freeze_date(path: Path) -> datetime.date:
    value = read_freeze(path).get("freeze_date")
    try:
        parsed = datetime.date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        parsed = None
    if parsed is None or parsed.isoformat() != value:
        raise AnalysisError("freeze_malformed", f"{path.name}: freeze_date must be YYYY-MM-DD")
    return parsed
