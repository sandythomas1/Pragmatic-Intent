"""The analysis plan (spec 007 FR1–FR4): D-07 statistics and the model panel in one hashed file.

The plan is fixed before test. WP-08's ``data/manifests/freeze.json`` records ``sha256`` of
the validated config, and a test analysis refuses to run under any other hash. Validation is
strict: every key is required and unknown keys are errors, so a typo cannot fall back to a
default and an invalid plan cannot be frozen. Each failure is an ``AnalysisConfigError`` with a
stable ``code``.

The hash is the SHA-256 of the parsed TOML as sorted-key, compact JSON, computed only after
validation. Comments, key order and formatting do not move it; any value (``draft`` included)
does. Anyone can recompute it with ``tomllib`` and ``json`` alone.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.analysis.files import AnalysisError, read_toml
from src.data import auto_levels, auto_levels_v2
from src.data.contexts import MISMATCH_CONDITIONS
from src.data.direct_dataset import CONDITIONS
from src.evaluation.stage1 import CONTRASTS

CONFIG_VERSION = "analysis-v1"
DEFAULT_CONFIG = Path("configs/analysis/analysis-v1.toml")
MAX_CONFIG_BYTES = 1 << 20
MAX_ENTRIES = 64

RULES_VERSIONS = (auto_levels.RULES_VERSION, auto_levels_v2.RULES_VERSION)
ANALYSIS_LEVELS = ("L0", "L1", "L2", "L3", "INF")  # request levels in order; NR rows are non-requests
FAMILIES = ("majority", "tfidf", "encoder", "llm", "hybrid")
DESIGNS = ("matched", "test_time")
STREAMS = ("stage1", "routed", "oracle", "transfer")
GENUINE_CONDITIONS = tuple(c for c in CONDITIONS if c not in MISMATCH_CONDITIONS)
GENUINE_CONTRASTS = tuple(f"{a}_minus_{b}" for a, b in CONTRASTS if b not in MISMATCH_CONDITIONS)
MISMATCH_CONTRASTS = tuple(f"{a}_minus_{b}" for a, b in CONTRASTS if b in MISMATCH_CONDITIONS)
TREND_WEIGHTS = {"linear": (-1, 0, 1), "quadratic": (1, -2, 1)}

# The stream sets that can compute each endpoint (FR3); any one set suffices. The Stage 2
# endpoints need oracle as well as routed, because their component check runs stage2.build_report.
_STAGE2 = frozenset({"routed", "oracle"})
ENDPOINT_STREAMS = {
    "request_interpretation": (_STAGE2,),
    "type_exact": (_STAGE2,),
    "stage1_correct": (frozenset({"stage1"}), _STAGE2),
    "request_detected": (_STAGE2,),
}
ENDPOINTS = tuple(ENDPOINT_STREAMS)

# Holm family member kinds and the keys each needs beyond name, kind and system.
MEMBER_KEYS = {
    "h1_trend": ("endpoint", "condition"),
    "h2_trend": ("endpoint", "contrast"),
    "h3_difference": ("endpoint", "contrast", "reference"),
    "h4_contrast": (),
    "mismatch_control": ("endpoint", "contrast"),
}
MEMBER_CONTRASTS = {"h2_trend": GENUINE_CONTRASTS, "h3_difference": GENUINE_CONTRASTS,
                    "mismatch_control": MISMATCH_CONTRASTS}

_TOP_KEYS = ("version", "rules_version", "draft", "alpha", "bootstrap", "cells", "primary",
             "exploratory", "error_audit", "panel", "family")
_NAME_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")


class AnalysisConfigError(AnalysisError):
    """A named validation failure in the analysis config."""


@dataclass(frozen=True)
class PanelSystem:
    name: str
    family: str
    design: str
    streams: tuple[str, ...]

    def provides(self, endpoint: str) -> bool:
        return any(needed <= set(self.streams) for needed in ENDPOINT_STREAMS[endpoint])


@dataclass(frozen=True)
class PrimaryTest:
    system: str
    endpoint: str
    contrast: str
    trend: str
    levels: tuple[str, ...]

    @property
    def weights(self) -> tuple[int, ...]:
        return TREND_WEIGHTS[self.trend]


@dataclass(frozen=True)
class FamilyMember:
    """One Holm-corrected secondary test; fields a kind does not use are None."""

    name: str
    kind: str
    system: str
    endpoint: str | None = None
    contrast: str | None = None
    condition: str | None = None
    reference: str | None = None


@dataclass(frozen=True)
class BootstrapSettings:
    samples: int
    seed: int
    confidence: float


@dataclass(frozen=True)
class CellRules:
    min_dialogues: int
    max_excluded_share: float


@dataclass(frozen=True)
class ErrorAuditDesign:
    levels: tuple[str, ...]
    per_level: int
    seed: int


@dataclass(frozen=True)
class AnalysisConfig:
    version: str
    rules_version: str
    draft: bool
    alpha: float
    bootstrap: BootstrapSettings
    cells: CellRules
    primary: PrimaryTest
    exploratory_levels: tuple[str, ...]
    error_audit: ErrorAuditDesign
    panel: tuple[PanelSystem, ...]
    family: tuple[FamilyMember, ...]
    sha256: str

    def system(self, name: str) -> PanelSystem:
        for system in self.panel:
            if system.name == name:
                return system
        raise KeyError(name)


def canonical_sha256(content: Mapping[str, Any]) -> str:
    """SHA-256 of sorted-key, compact JSON: the hash ``freeze.json`` pins."""
    text = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def load_config(path: Path) -> AnalysisConfig:
    """Read, validate and hash an analysis config; raise ``AnalysisConfigError`` on any problem."""
    return parse_config(read_toml(path, MAX_CONFIG_BYTES, AnalysisConfigError))


def parse_config(raw: Mapping[str, Any]) -> AnalysisConfig:
    """Validate parsed TOML content; the hash is taken only once every check has passed."""
    _keys(raw, "config", _TOP_KEYS)
    version = _enum(raw["version"], "version", (CONFIG_VERSION,), "unknown_version")
    panel = _panel(raw["panel"])
    by_name = {system.name: system for system in panel}
    primary = _primary(raw["primary"], by_name)
    exploratory = _keys(raw["exploratory"], "[exploratory]", ("levels",))
    exploratory_levels = _levels(exploratory["levels"], "[exploratory].levels")
    if set(exploratory_levels) & set(primary.levels):
        raise AnalysisConfigError("overlapping_levels", "a level cannot be both primary and exploratory")
    bootstrap = _bootstrap(raw["bootstrap"])
    alpha = _fraction(raw["alpha"], "alpha")
    if abs(alpha - (1 - bootstrap.confidence)) > 1e-9:
        raise AnalysisConfigError("alpha_confidence_mismatch",
                                  "alpha must equal 1 - confidence, since the interval decides the primary test")
    return AnalysisConfig(
        version=version,
        rules_version=_enum(raw["rules_version"], "rules_version", RULES_VERSIONS, "unknown_rules_version"),
        draft=_bool(raw["draft"], "draft"),
        alpha=alpha,
        bootstrap=bootstrap,
        cells=_cells(raw["cells"]),
        primary=primary,
        exploratory_levels=exploratory_levels,
        error_audit=_error_audit(raw["error_audit"]),
        panel=panel,
        family=_family(raw["family"], by_name, primary),
        sha256=canonical_sha256(raw),
    )


def _panel(entries: Any) -> tuple[PanelSystem, ...]:
    systems = tuple(_system_entry(table, f"panel[{i}]") for i, table in enumerate(_list(entries, "panel")))
    if not systems:
        raise AnalysisConfigError("empty_panel", "the panel names no systems")
    _no_duplicates([s.name for s in systems], "duplicate_system", "panel")
    return systems


def _system_entry(table: Any, where: str) -> PanelSystem:
    _keys(table, where, ("name", "family", "design", "streams"))
    streams = tuple(_enum(s, f"{where}.streams", STREAMS, "unknown_stream")
                    for s in _list(table["streams"], f"{where}.streams"))
    if not streams:
        raise AnalysisConfigError("empty_streams", f"{where} declares no streams")
    _no_duplicates(streams, "duplicate_stream", where)
    system = PanelSystem(
        name=_name(table["name"], f"{where}.name"),
        family=_enum(table["family"], f"{where}.family", FAMILIES, "unknown_family"),
        design=_enum(table["design"], f"{where}.design", DESIGNS, "unknown_design"),
        streams=streams,
    )
    if system.family == "llm" and system.design != "test_time":
        raise AnalysisConfigError("design_not_allowed", f"{where}: an untrained llm system has only a test_time line")
    return system


def _primary(table: Any, panel: Mapping[str, PanelSystem]) -> PrimaryTest:
    _keys(table, "[primary]", ("system", "endpoint", "contrast", "trend", "levels"))
    primary = PrimaryTest(
        system=_panel_system(table["system"], "[primary].system", panel),
        endpoint=_enum(table["endpoint"], "[primary].endpoint", ENDPOINTS, "unknown_endpoint"),
        contrast=_contrast(table["contrast"], "[primary].contrast", GENUINE_CONTRASTS),
        trend=_enum(table["trend"], "[primary].trend", tuple(TREND_WEIGHTS), "unknown_trend"),
        levels=_levels(table["levels"], "[primary].levels"),
    )
    if len(primary.levels) != len(primary.weights):
        raise AnalysisConfigError("primary_levels_count",
                                  f"a {primary.trend} trend needs exactly {len(primary.weights)} levels")
    _require_streams(panel[primary.system], primary.endpoint, "[primary]")
    return primary


def _family(entries: Any, panel: Mapping[str, PanelSystem], primary: PrimaryTest) -> tuple[FamilyMember, ...]:
    members = tuple(_member(table, f"family[{i}]", panel, primary) for i, table in enumerate(_list(entries, "family")))
    if not members:
        raise AnalysisConfigError("empty_family", "the secondary family has no members")
    _no_duplicates([m.name for m in members], "duplicate_member", "family names")
    _no_duplicates([(m.kind, m.system, m.endpoint, m.contrast, m.condition, m.reference) for m in members],
                   "duplicate_member", "family tests")
    return members


def _member(table: Any, where: str, panel: Mapping[str, PanelSystem], primary: PrimaryTest) -> FamilyMember:
    if isinstance(table, dict) and not table:
        raise AnalysisConfigError("empty_member", f"{where} is empty")
    if not isinstance(table, dict) or "kind" not in table:
        raise AnalysisConfigError("missing_key", f"{where} needs a kind")
    kind = _enum(table["kind"], f"{where}.kind", tuple(MEMBER_KEYS), "unknown_kind")
    _keys(table, where, ("name", "kind", "system", *MEMBER_KEYS[kind]))
    member = FamilyMember(
        name=_name(table["name"], f"{where}.name"),
        kind=kind,
        system=_panel_system(table["system"], f"{where}.system", panel),
        endpoint=_enum(table["endpoint"], f"{where}.endpoint", ENDPOINTS, "unknown_endpoint")
        if "endpoint" in table else None,
        contrast=_contrast(table["contrast"], f"{where}.contrast", MEMBER_CONTRASTS[kind])
        if "contrast" in table else None,
        condition=_enum(table["condition"], f"{where}.condition", GENUINE_CONDITIONS, "unknown_condition")
        if "condition" in table else None,
        reference=_panel_system(table["reference"], f"{where}.reference", panel) if "reference" in table else None,
    )
    if member.kind == "h3_difference":
        if member.reference != primary.system:
            raise AnalysisConfigError("h3_reference", f"{where}: H3 differences are taken against the primary system")
        if member.system == member.reference:
            raise AnalysisConfigError("h3_reference", f"{where}: a system cannot be compared with itself")
    if member.kind == "h4_contrast":
        _require_streams(panel[member.system], "request_interpretation", where)
    else:
        for name in filter(None, (member.system, member.reference)):
            _require_streams(panel[name], member.endpoint, where)
    if (member.kind, member.system, member.endpoint, member.contrast) == \
            ("h2_trend", primary.system, primary.endpoint, primary.contrast):
        raise AnalysisConfigError("primary_in_family", f"{where} repeats the confirmatory primary test")
    return member


def _bootstrap(table: Any) -> BootstrapSettings:
    _keys(table, "[bootstrap]", ("samples", "seed", "confidence"))
    return BootstrapSettings(samples=_int(table["samples"], "[bootstrap].samples", minimum=1),
                             seed=_int(table["seed"], "[bootstrap].seed", minimum=0),
                             confidence=_fraction(table["confidence"], "[bootstrap].confidence"))


def _cells(table: Any) -> CellRules:
    _keys(table, "[cells]", ("min_dialogues", "max_excluded_share"))
    return CellRules(min_dialogues=_int(table["min_dialogues"], "[cells].min_dialogues", minimum=1),
                     max_excluded_share=_fraction(table["max_excluded_share"], "[cells].max_excluded_share"))


def _error_audit(table: Any) -> ErrorAuditDesign:
    _keys(table, "[error_audit]", ("levels", "per_level", "seed"))
    return ErrorAuditDesign(levels=_levels(table["levels"], "[error_audit].levels"),
                            per_level=_int(table["per_level"], "[error_audit].per_level", minimum=1),
                            seed=_int(table["seed"], "[error_audit].seed", minimum=0))


def _require_streams(system: PanelSystem, endpoint: str, where: str) -> None:
    if not system.provides(endpoint):
        options = " or ".join("+".join(sorted(s)) for s in ENDPOINT_STREAMS[endpoint])
        raise AnalysisConfigError("missing_streams", f"{where}: {system.name} lacks {options} for {endpoint}")


def _keys(table: Any, where: str, allowed: Sequence[str]) -> Mapping[str, Any]:
    if not isinstance(table, dict):
        raise AnalysisConfigError("wrong_type", f"{where} must be a table")
    unknown = sorted(set(table) - set(allowed))
    if unknown:
        raise AnalysisConfigError("unknown_key", f"{where}: {unknown}")
    missing = [key for key in allowed if key not in table]
    if missing:
        raise AnalysisConfigError("missing_key", f"{where}: {missing}")
    return table


def _list(value: Any, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise AnalysisConfigError("wrong_type", f"{where} must be an array")
    if len(value) > MAX_ENTRIES:
        raise AnalysisConfigError("too_many_entries", f"{where} has more than {MAX_ENTRIES} entries")
    return value


def _enum(value: Any, where: str, allowed: Collection[str], code: str) -> str:
    if not isinstance(value, str):
        raise AnalysisConfigError("wrong_type", f"{where} must be a string")
    if value not in allowed:
        raise AnalysisConfigError(code, f"{where} = {value[:64]!r}; expected one of {sorted(allowed)}")
    return value


def _name(value: Any, where: str) -> str:
    if not isinstance(value, str) or _NAME_RE.fullmatch(value) is None:
        raise AnalysisConfigError("bad_name", f"{where} must match {_NAME_RE.pattern}")
    return value


def _panel_system(value: Any, where: str, panel: Mapping[str, PanelSystem]) -> str:
    if not isinstance(value, str):
        raise AnalysisConfigError("wrong_type", f"{where} must be a string")
    if value not in panel:
        raise AnalysisConfigError("system_outside_panel", f"{where} = {value[:64]!r} is not a panel system")
    return value


def _contrast(value: Any, where: str, allowed: Collection[str]) -> str:
    _enum(value, where, (*GENUINE_CONTRASTS, *MISMATCH_CONTRASTS), "unknown_contrast")
    return _enum(value, where, allowed, "wrong_contrast_kind")


def _levels(value: Any, where: str) -> tuple[str, ...]:
    levels = tuple(_enum(level, where, ANALYSIS_LEVELS, "unknown_level") for level in _list(value, where))
    if not levels:
        raise AnalysisConfigError("empty_levels", f"{where} is empty")
    _no_duplicates(levels, "duplicate_level", where)
    if list(levels) != sorted(levels, key=ANALYSIS_LEVELS.index):
        # A reordered list would silently flip the sign of a trend contrast.
        raise AnalysisConfigError("level_order", f"{where} must follow {ANALYSIS_LEVELS}")
    return levels


def _int(value: Any, where: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AnalysisConfigError("wrong_type", f"{where} must be an integer")
    if value < minimum:
        raise AnalysisConfigError("non_positive" if minimum == 1 else "out_of_range", f"{where} must be >= {minimum}")
    return value


def _fraction(value: Any, where: str) -> float:
    if not isinstance(value, float):
        raise AnalysisConfigError("wrong_type", f"{where} must be a float such as 0.05")
    if not 0.0 < value < 1.0:
        raise AnalysisConfigError("out_of_range", f"{where} must lie strictly between 0 and 1")
    return value


def _bool(value: Any, where: str) -> bool:
    if not isinstance(value, bool):
        raise AnalysisConfigError("wrong_type", f"{where} must be true or false")
    return value


def _no_duplicates(values: Sequence[Any], code: str, where: str) -> None:
    seen: set[Any] = set()
    for value in values:
        if value in seen:
            raise AnalysisConfigError(code, f"{where}: {value!r} appears twice")
        seen.add(value)
