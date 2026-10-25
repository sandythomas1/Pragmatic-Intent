"""The WP-08 freeze record (spec 008): what a reported test number was computed from.

The freeze inputs (``configs/freeze/freeze-v1.toml``) declare what to pin: the analysis config,
the code that renders, labels, scores and analyzes, and each panel system's recipe files and
seeds. Each system's training conditions are not declared; they follow from its design in the
frozen analysis config (spec 007's rule), so the two files cannot disagree.

Every path in the inputs is untrusted: it must be a repository-relative POSIX path, without
``..`` or a drive, and nothing on the way to it may be a symlink. Failures are ``FreezeError``
with a stable ``code`` and the keys involved; messages name keys, files and systems, never
dialogue or item IDs (spec 006: a printed test ID becomes an exclusion).
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from src.analysis.config import AnalysisConfig, PanelSystem, canonical_sha256
from src.analysis.config import load_config as load_analysis_config
from src.analysis.files import AnalysisError, read_bounded, read_toml
from src.analysis.inputs import needed_train_conditions
from src.data import auto_levels_v2
from src.data import split_audit as sa
from src.evaluation.test_audit import TestAuditError, require_test_audit
from src.stage1 import provenance
from src.stage1.config import load_config as load_stage1_config

INPUTS_VERSION = "freeze-inputs-v1"
DEFAULT_INPUTS = Path("configs/freeze/freeze-v1.toml")
MAX_INPUTS_BYTES = 1 << 16
MAX_PATH_CHARS = 512
MAX_SEEDS = 16
MAX_RECIPE_FILES = 16
MAX_CODE_FILES = 512
MAX_TEXT_BYTES = 16 << 20  # code, locks and summaries; generated data is hashed in chunks instead

SOURCES_TOML = Path("data/sources.toml")
UV_LOCK = Path("uv.lock")
CONTEXT_SUMMARY = Path("data/manifests/contexts_test_summary.json")
AUTO_V2_FREEZE = Path("specs/005-scoring/auto_v2_freeze.json")  # committed copy of the spec 005 seal
AUTO_LEVEL_MODULES = (Path("src/data/auto_levels.py"), Path("src/data/auto_levels_v2.py"))  # rules_sha256 order
STAGE1_FAMILIES = ("majority", "tfidf", "encoder")
GIT_IGNORED = (Path("results"), Path("outputs"))  # run outputs never make the tree dirty (spec 006 retro)
_COMMIT_RE = re.compile(r"[0-9a-f]{40}")
# Defense in depth for printed lines: anything shaped like a DIRECT/MultiWOZ dialogue ID is masked.
_ID_RE = re.compile(r"(?<![A-Za-z0-9])(?:PMUL|MUL|SNG|SSNG|WOZ)[0-9]{4,5}(?![0-9])")

_SHA256_RE = re.compile(r"[0-9a-f]{64}")

RECORD_VERSION = "freeze-record-v1"
MAX_RECORD_BYTES = 1 << 16  # src.analysis.freeze reads at most this much
BASE_KEYS = ("schema_version", "freeze_date", "original_pins", "written_at_commit", "inputs_path")
RECORD_KEYS = (*BASE_KEYS, "pins", "amendments", "analysis_config_sha256", "content_sha256")
AMENDMENT_KEYS = ("on", "reason", "changes", "commit", "previous_content_sha256")
IMMUTABLE_PREFIXES = ("membership.", "data.")  # the frozen test set never moves (spec 006; review R6)
MAX_REASON_CHARS = 500

GitProbe = Callable[[Path], Mapping[str, Any]]

# Recipe fields a run chooses for itself (FR8): never part of the recipe's identity.
RUNTIME_FIELDS = (("data", "eval_split"), ("data", "train_condition"),
                  ("encoder", "micro_batch_size"), ("encoder", "gradient_checkpointing"))

_TOP_KEYS = ("version", "analysis_config", "code", "systems")
_SYSTEM_KEYS = ("stage1", "files", "seeds", "llm_model")
_GLOB_RE = re.compile(r"[A-Za-z0-9_./*?-]+")
_NAME_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
_LLM_MODEL_RE = re.compile(r"[A-Za-z0-9._:@/-]{0,128}")


class FreezeError(AnalysisError):
    """A named freeze failure; ``keys`` lists the pins, systems or inputs entries involved."""

    def __init__(self, code: str, detail: str, keys: Sequence[str] = ()) -> None:
        super().__init__(code, detail)
        self.keys = tuple(keys)


@dataclass(frozen=True)
class SystemRecipe:
    name: str
    stage1: Path | None  # repository-relative
    files: tuple[Path, ...]
    seeds: tuple[int, ...]
    llm_model: str | None


@dataclass(frozen=True)
class FreezeInputs:
    path: Path
    analysis_config: Path
    code: tuple[Path, ...]  # sorted, deduplicated, repository-relative
    systems: Mapping[str, SystemRecipe]


def load_inputs(path: Path, *, root: Path) -> FreezeInputs:
    """Validate the freeze inputs; every path must resolve to a regular file inside ``root``."""
    raw = read_toml(root / path, MAX_INPUTS_BYTES, FreezeError)
    _keys(raw, "inputs", _TOP_KEYS)
    if raw["version"] != INPUTS_VERSION:
        raise FreezeError("unknown_version", f"inputs version must be {INPUTS_VERSION!r}", ["version"])
    systems = raw["systems"]
    if not isinstance(systems, dict) or not systems:
        raise FreezeError("wrong_type", "[systems] must be a non-empty table", ["systems"])
    return FreezeInputs(
        path=path,
        analysis_config=repo_file(raw["analysis_config"], "analysis_config", root),
        code=_code_files(raw["code"], root),
        systems={_name(name): _system(name, table, root) for name, table in sorted(systems.items())},
    )


def match_panel(inputs: FreezeInputs, config: AnalysisConfig) -> None:
    """The inputs must name exactly the analysis config's panel (FR2)."""
    panel = {system.name for system in config.panel}
    missing, extra = sorted(panel - set(inputs.systems)), sorted(set(inputs.systems) - panel)
    if missing or extra:
        raise FreezeError("panel_mismatch", f"freeze inputs lack {missing} and add {extra} relative to the panel",
                          [*missing, *extra])


def conditions_for(system: PanelSystem) -> tuple[str, ...]:
    """The training conditions a system's frozen grid may use, by spec 007's design rule."""
    return needed_train_conditions(system)


def recipe_sha256(config: Mapping[str, Any]) -> str:
    """The hash that identifies a Stage 1 recipe across dev, test and machines (FR8).

    ``config`` is ``RunConfig.to_dict()`` or a run's ``config.resolved.json``; the JSON round trip
    makes both the same shape (tuples become lists). Fields chosen per run are dropped: the split
    and train condition (the grid varies them) and the memory knobs that leave the effective batch
    unchanged.
    """
    content = json.loads(json.dumps(config, allow_nan=False))
    if not isinstance(content, dict):
        raise FreezeError("malformed_recipe", "a recipe must be a JSON object")
    for table, key in RUNTIME_FIELDS:
        section = content.get(table)
        if isinstance(section, dict):
            section.pop(key, None)
    return canonical_sha256(content)


def stage1_recipe(root: Path, relative: Path) -> dict[str, Any]:
    """A Stage 1 recipe TOML resolved exactly as the runner resolves it (defaults filled in)."""
    try:
        return load_stage1_config(root / relative).to_dict()
    except (OSError, ValueError) as error:  # tomllib's TOMLDecodeError is a ValueError
        shown = relative.as_posix()
        raise FreezeError("invalid_recipe", f"{shown}: {str(error)[:200]}", [shown]) from None


@dataclass(frozen=True)
class Finding:
    """Something that keeps the freeze from being written: ``missing`` (not supplied yet) or ``problem``."""

    status: str
    code: str
    key: str
    detail: str = ""


@dataclass
class PinState:
    """The repository's current pins, and what stops them from being frozen."""

    pins: dict[str, str] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    config: AnalysisConfig | None = None
    registry: list[dict[str, str]] | None = None
    index: sa.CorpusIndex | None = None
    git_commit: str | None = None

    def missing(self, code: str, key: str, detail: str = "") -> None:
        self.findings.append(Finding("missing", code, key, detail))

    def problem(self, code: str, key: str, detail: str = "") -> None:
        self.findings.append(Finding("problem", code, key, detail))


def compute_pins(inputs: FreezeInputs, root: Path) -> PinState:
    """Every FR3–FR8 pin of the repository at ``root``; nothing here writes or prints."""
    state = PinState()
    _data_pins(state, root)
    _membership_pins(state, root)
    _analysis_pins(state, inputs, root)
    for path in inputs.code:
        _pin_file(state, f"code.{path.as_posix()}", root, path, text_sha256)
    for recipe in inputs.systems.values():
        _recipe_pins(state, recipe, root)
    return state


def check_state(inputs: FreezeInputs, root: Path, *, on: datetime.date, today: datetime.date,
                git: GitProbe | None = None, record_may_exist: bool = False) -> PinState:
    """The pins plus every ``write`` precondition (FR11); ``check`` prints this, ``write`` needs it empty."""
    state = compute_pins(inputs, root)
    if not record_may_exist and (root / sa.FREEZE_FILE).exists():
        state.problem("freeze_exists", "freeze", "the record is written once; use amend")
    _test_audit_precondition(state, root)
    _scan_precondition(state, root)
    _git_precondition(state, root, git or git_probe)
    _date_preconditions(state, on, today)
    return state


def git_probe(root: Path) -> Mapping[str, Any]:
    """Commit and dirty flag of ``root``'s worktree, ignoring the run outputs (``results/``, ``outputs/``)."""
    return provenance.git_state(ignore=tuple(root / path for path in GIT_IGNORED), cwd=root)


def _test_audit_precondition(state: PinState, root: Path) -> None:
    if any(f.key in ("data.items", "data.dialogues", "membership.split_audit") for f in state.findings):
        return  # already reported as missing
    try:
        require_test_audit(root / sa.DEFAULT_ITEMS, root / sa.DEFAULT_DIALOGUES, registry_path=root / sa.DEFAULT_REGISTRY,
                           audit_path=root / sa.DEFAULT_AUDIT, summary_path=root / sa.DEFAULT_AUDIT_SUMMARY)
    except (TestAuditError, OSError, ValueError, KeyError, TypeError):
        # Its messages can quote registry rows, so only the fact is reported (FR15).
        state.problem("test_audit_failed", "membership.split_audit",
                      "run python -m src.data.split_audit audit --verify for details")


def _scan_precondition(state: PinState, root: Path) -> None:
    """Every human-facing sheet's test dialogues are registered; reported as counts and files only."""
    if state.registry is None or state.index is None:
        return
    try:
        report = sa.scan_sheets(root, state.registry, state.index, registry_path=sa.DEFAULT_REGISTRY)
    except (OSError, ValueError):
        state.problem("scan_failed", "membership.sheets", "run python -m src.data.split_audit scan")
        return
    unregistered = [failure for failure in report.failures if ": test dialogue " in failure]
    others = [failure for failure in report.failures if failure not in unregistered]
    files = sorted({failure.split(": ", 1)[0] for failure in report.failures})
    if unregistered:
        state.problem("scan_unregistered", "membership.sheets",
                      f"{len(unregistered)} unregistered test dialogue(s) in {len(files)} file(s): {', '.join(files)}; "
                      "run python -m src.data.split_audit scan")
    elif others:
        state.problem("scan_failed", "membership.sheets",
                      f"{len(others)} unreadable sheet(s): {', '.join(files)}; run python -m src.data.split_audit scan")


def _git_precondition(state: PinState, root: Path, git: GitProbe) -> None:
    info = git(root)
    commit, dirty = info.get("git_commit"), info.get("git_dirty")
    if not isinstance(commit, str) or not isinstance(dirty, bool):
        state.problem("git_unavailable", "git", "git is not on PATH or this is not a repository; never assumed clean")
        return
    state.git_commit = commit
    if dirty:
        state.problem("tree_dirty", "git", "commit everything outside results/ and outputs/ first")


def _date_preconditions(state: PinState, on: datetime.date, today: datetime.date) -> None:
    if on > today:
        state.problem("date_in_future", "freeze_date", f"{on.isoformat()} is after today ({today.isoformat()})")
    latest = max((row["inspected_on"] for row in state.registry or () if row["phase"] == "pre_freeze"), default=None)
    if latest is not None and on.isoformat() <= latest:
        # sa.phase_for is strict (inspected_on < freeze_date), so a same-day row would re-derive as
        # post_scoring and the registry could never be updated again (review R1).
        state.problem("date_not_after_inspection", "freeze_date",
                      f"the latest pre_freeze inspection is {latest}; freeze on a later day")


def text_sha256(path: Path) -> str:
    """SHA-256 of UTF-8 text with CRLF normalized to LF, so Windows and WSL checkouts agree."""
    try:
        text = read_bounded(path, MAX_TEXT_BYTES, FreezeError).decode("utf-8")
    except UnicodeDecodeError:
        raise FreezeError("not_utf8", f"{path.name} is not UTF-8 text") from None
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def bytes_sha256(path: Path) -> str:
    """Byte-exact SHA-256 for generated data and ``-text`` manifests, as spec 006 hashes them."""
    if not path.is_file():
        raise FreezeError("not_a_file", f"{path.name} is not a regular file")
    return sa.file_sha256(path)


def _pin_file(state: PinState, key: str, root: Path, relative: Path, hasher: Any) -> str | None:
    try:
        state.pins[key] = hasher(root / relative)
    except FreezeError as error:
        if error.code == "not_a_file":
            state.missing("file_missing", key, relative.as_posix())
        else:
            state.problem(error.code, key, relative.as_posix())
        return None
    return state.pins[key]


def _data_pins(state: PinState, root: Path) -> None:
    _pin_file(state, "data.sources_toml", root, SOURCES_TOML, text_sha256)
    _pin_file(state, "env.uv_lock", root, UV_LOCK, text_sha256)  # amendable, unlike data.* (FR13)
    _pin_file(state, "data.items", root, sa.DEFAULT_ITEMS, bytes_sha256)
    _pin_file(state, "data.dialogues", root, sa.DEFAULT_DIALOGUES, bytes_sha256)


def _membership_pins(state: PinState, root: Path) -> None:
    """The frozen test set: split audit, registry pre-freeze rows and the context manifest."""
    audit_csv = _pin_file(state, "membership.split_audit", root, sa.DEFAULT_AUDIT, bytes_sha256)
    summary = _json_file(state, "membership.split_audit_content", root, sa.DEFAULT_AUDIT_SUMMARY)
    if summary is not None:
        # The content hash leaves out ``disclosure``, which grows after scoring by design (spec 006).
        content = sa.audit_content_sha256(summary)
        if content != summary.get("content_sha256") or (audit_csv and audit_csv != summary.get("audit_sha256")):
            state.problem("split_audit_stale", "membership.split_audit_content",
                          "the summary does not match itself or its CSV; rebuild with split_audit audit")
        else:
            state.pins["membership.split_audit_content"] = content
            primary = summary.get("primary", {})
            state.pins["membership.primary"] = f"genuine={primary.get('genuine')};mismatch={primary.get('mismatch')}"
    manifest = _pin_file(state, "membership.context_manifest", root, sa.DEFAULT_CONTEXT_MANIFEST, bytes_sha256)
    context = _json_file(state, "membership.context_manifest", root, CONTEXT_SUMMARY)
    if context is not None:
        state.pins["membership.renderer_version"] = str(context.get("renderer_version"))
        state.pins["membership.budget_words"] = str(context.get("budget_words"))
        audited = (summary or {}).get("inputs", {}).get("context_manifest_sha256")
        if manifest is not None and (context.get("manifest_sha256") != manifest or audited != manifest):
            state.problem("manifest_mismatch", "membership.context_manifest",
                          "the context manifest, its summary and the split audit disagree")
    _registry_pins(state, root)


def _registry_pins(state: PinState, root: Path) -> None:
    items, registry = root / sa.DEFAULT_ITEMS, root / sa.DEFAULT_REGISTRY
    key = "membership.registry_pre_freeze"
    if not items.is_file() or not registry.is_file():
        state.missing("file_missing", key, "items.jsonl and the registry are both needed")
        return
    try:
        index = sa.load_corpus_index(items)
        rows = sa.load_registry(registry, index.dialogue_split)
    except (sa.RegistryError, OSError, ValueError, KeyError, TypeError):
        # Registry and corpus messages can name dialogues, so only the fact is reported (FR15).
        state.problem("registry_invalid", key, "run python -m src.data.split_audit check for details")
        return
    state.registry, state.index = rows, index
    state.pins[key] = sa.pre_freeze_sha256(rows)


def _analysis_pins(state: PinState, inputs: FreezeInputs, root: Path) -> None:
    try:
        config = load_analysis_config(root / inputs.analysis_config)
    except AnalysisError as error:
        state.problem("analysis_config_invalid", "analysis.config", error.code)
        return
    state.config = config
    state.pins["analysis.config"] = config.sha256
    state.pins["analysis.version"] = config.version
    state.pins["labels.rules_version"] = config.rules_version
    if config.draft:
        state.missing("analysis_draft", "analysis.config", "set draft = false once the primary system is named")
    if config.rules_version == auto_levels_v2.RULES_VERSION:
        _auto_v2_pin(state, root)
    try:
        match_panel(inputs, config)
    except FreezeError as error:
        state.problem("panel_mismatch", "analysis.panel", ", ".join(error.keys))


def _auto_v2_pin(state: PinState, root: Path) -> None:
    """``auto-v2`` must still match its spec 005 freeze, recomputed from this checkout's source."""
    key = "labels.auto_v2_rules"
    record = _json_file(state, key, root, AUTO_V2_FREEZE)
    digest = hashlib.sha256()
    for module in AUTO_LEVEL_MODULES:
        try:
            digest.update((root / module).read_text(encoding="utf-8").encode("utf-8"))  # newline-normalized
        except (OSError, UnicodeDecodeError):
            state.missing("file_missing", key, module.as_posix())
            return
    if record is not None:
        if record.get("rules_sha256") != digest.hexdigest() or record.get("rules_version") != auto_levels_v2.RULES_VERSION:
            state.problem("auto_v2_unfrozen", key, "auto-v2 source differs from its spec 005 freeze")
        else:
            state.pins[key] = digest.hexdigest()


def _recipe_pins(state: PinState, recipe: SystemRecipe, root: Path) -> None:
    prefix = f"recipe.{recipe.name}"
    state.pins[f"{prefix}.seeds"] = ",".join(str(seed) for seed in recipe.seeds)
    system = _panel_system(state.config, recipe.name)
    if recipe.stage1 is None and not recipe.files:
        state.missing("recipe_missing", prefix, "no stage1 config or recipe files yet")
    elif system is not None and system.family in STAGE1_FAMILIES and recipe.stage1 is None:
        state.missing("recipe_missing", f"{prefix}.stage1", f"a {system.family} system needs a stage1 config")
    if recipe.stage1 is not None:
        _stage1_pins(state, recipe.name, recipe.stage1, root)
    for path in recipe.files:
        _pin_file(state, f"{prefix}.file.{path.as_posix()}", root, path, text_sha256)
    if recipe.llm_model is not None:
        state.pins[f"{prefix}.llm_model"] = recipe.llm_model
        if not recipe.llm_model or recipe.llm_model.lower().endswith("latest"):
            state.problem("llm_model_floating", f"{prefix}.llm_model", "name a dated snapshot, not an alias")
    elif system is not None and system.family == "llm":
        state.missing("llm_model_missing", f"{prefix}.llm_model", "an llm system needs its model snapshot")


def _stage1_pins(state: PinState, name: str, path: Path, root: Path) -> None:
    prefix = f"recipe.{name}"
    try:
        config = stage1_recipe(root, path)
    except FreezeError as error:
        state.problem(error.code, f"{prefix}.stage1", path.as_posix())
        return
    state.pins[f"{prefix}.stage1"] = recipe_sha256(config)
    if config["name"] != name:
        state.problem("recipe_name_mismatch", f"{prefix}.stage1", f"[run] name must be {name!r}")
    encoder = config.get("encoder")
    if config["kind"] == "encoder" and isinstance(encoder, dict):
        state.pins[f"{prefix}.pretrained"] = str(encoder["pretrained"])
        state.pins[f"{prefix}.revision"] = str(encoder["revision"])
        if _COMMIT_RE.fullmatch(str(encoder["revision"])) is None:
            state.problem("revision_unpinned", f"{prefix}.revision", "pin a 40-hex Hugging Face commit, not a branch or tag")


def _panel_system(config: AnalysisConfig | None, name: str) -> PanelSystem | None:
    if config is None:
        return None
    return next((system for system in config.panel if system.name == name), None)


def _json_file(state: PinState, key: str, root: Path, relative: Path) -> dict[str, Any] | None:
    path = root / relative
    if not path.is_file():
        state.missing("file_missing", key, relative.as_posix())
        return None
    try:
        record = json.loads(read_bounded(path, MAX_TEXT_BYTES, FreezeError).decode("utf-8"))
    except (FreezeError, UnicodeDecodeError, ValueError, RecursionError):
        record = None
    if not isinstance(record, dict):
        state.problem("malformed_json", key, relative.as_posix())
        return None
    return record


def repo_file(value: Any, where: str, root: Path) -> Path:
    """A repository-relative path to a regular file, with no symlink anywhere on the way."""
    relative = _relative(value, where)
    _require_no_symlinks(root, relative, where)
    if not (root / relative).is_file():
        raise FreezeError("missing_path", f"{where}: {relative.as_posix()} is not a regular file", [where])
    return relative


def _system(name: str, table: Any, root: Path) -> SystemRecipe:
    where = f"systems.{name}"
    _keys(table, where, _SYSTEM_KEYS, required=("seeds",))
    stage1 = repo_file(table["stage1"], f"{where}.stage1", root) if "stage1" in table else None
    files = tuple(repo_file(v, f"{where}.files[{i}]", root)
                  for i, v in enumerate(_list(table.get("files", []), f"{where}.files", MAX_RECIPE_FILES)))
    if len(set(files)) != len(files) or (stage1 is not None and stage1 in files):
        raise FreezeError("duplicate_file", f"{where} lists a recipe file twice", [where])
    return SystemRecipe(name=name, stage1=stage1, files=files, seeds=_seeds(table["seeds"], f"{where}.seeds"),
                        llm_model=_llm_model(table["llm_model"], f"{where}.llm_model") if "llm_model" in table else None)


def _code_files(value: Any, root: Path) -> tuple[Path, ...]:
    """Expand the code globs; a glob that matches no file is an error, so nothing drops out silently."""
    found: set[Path] = set()
    for i, pattern in enumerate(_list(value, "code", MAX_CODE_FILES)):
        where = f"code[{i}]"
        if not isinstance(pattern, str) or _GLOB_RE.fullmatch(pattern) is None:
            raise FreezeError("bad_glob", f"{where} must be a POSIX glob of [A-Za-z0-9_./*?-]", [where])
        _relative(pattern, where)
        matches = sorted(p for p in root.glob(pattern) if p.is_file() or p.is_symlink())
        if not matches:
            raise FreezeError("glob_empty", f"{where} = {pattern!r} matches no file", [where])
        found.update(repo_file(p.relative_to(root).as_posix(), where, root) for p in matches)
    if not found:
        raise FreezeError("glob_empty", "code lists no globs", ["code"])
    if len(found) > MAX_CODE_FILES:
        raise FreezeError("too_many_entries", f"code matches more than {MAX_CODE_FILES} files", ["code"])
    return tuple(sorted(found, key=lambda p: p.as_posix()))


def _relative(value: Any, where: str) -> Path:
    if not isinstance(value, str) or not value or len(value) > MAX_PATH_CHARS or "\x00" in value:
        raise FreezeError("wrong_type", f"{where} must be a non-empty path string", [where])
    # A colon is a drive or, mid-path on Windows, an NTFS alternate data stream ("x.toml:s").
    if "\\" in value or ":" in value or PureWindowsPath(value).drive or PurePosixPath(value).is_absolute():
        raise FreezeError("path_not_relative", f"{where} must be a repository-relative POSIX path", [where])
    segments = value.split("/")  # raw segments: PurePosixPath would silently drop '.' and '//'
    if any(segment in ("", ".", "..") for segment in segments):
        raise FreezeError("path_escape", f"{where} must not contain empty, '.' or '..' segments", [where])
    return Path(*segments)


def _require_no_symlinks(root: Path, relative: Path, where: str) -> None:
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise FreezeError("symlink", f"{where}: {relative.as_posix()} goes through a symlink", [where])


def _seeds(value: Any, where: str) -> tuple[int, ...]:
    seeds = _list(value, where, MAX_SEEDS)
    if not seeds:
        raise FreezeError("empty_seeds", f"{where} is empty", [where])
    if any(isinstance(s, bool) or not isinstance(s, int) or s < 0 for s in seeds):
        raise FreezeError("wrong_type", f"{where} must hold non-negative integers", [where])
    if len(set(seeds)) != len(seeds):
        raise FreezeError("duplicate_seed", f"{where} repeats a seed", [where])
    return tuple(seeds)


def _llm_model(value: Any, where: str) -> str:
    if not isinstance(value, str) or _LLM_MODEL_RE.fullmatch(value) is None:
        raise FreezeError("wrong_type", f"{where} must be a model ID string of [A-Za-z0-9._:@/-]", [where])
    return value


def _name(value: str) -> str:
    if _NAME_RE.fullmatch(value) is None:
        raise FreezeError("bad_name", f"system names must match {_NAME_RE.pattern}", ["systems"])
    return value


def _keys(table: Any, where: str, allowed: Sequence[str], required: Sequence[str] | None = None) -> Mapping[str, Any]:
    if not isinstance(table, dict):
        raise FreezeError("wrong_type", f"{where} must be a table", [where])
    unknown = sorted(set(table) - set(allowed))
    if unknown:
        raise FreezeError("unknown_key", f"{where}: {[key[:40] for key in unknown]}", [where])
    missing = [key for key in (allowed if required is None else required) if key not in table]
    if missing:
        raise FreezeError("missing_key", f"{where}: {missing}", [where])
    return table


def _list(value: Any, where: str, limit: int) -> list[Any]:
    if not isinstance(value, list):
        raise FreezeError("wrong_type", f"{where} must be an array", [where])
    if len(value) > limit:
        raise FreezeError("too_many_entries", f"{where} has more than {limit} entries", [where])
    return value


# --------------------------------------------------------------------------- the record


@dataclass(frozen=True)
class RunIdentity:
    """What a Stage 1 test run is: checked against the frozen grid (FR17)."""

    system: str
    recipe_sha256: str
    seed: int
    train_condition: str


@dataclass(frozen=True)
class FreezeRecord:
    record: Mapping[str, Any]
    content_sha256: str
    freeze_date: datetime.date
    pins: Mapping[str, str]
    config: AnalysisConfig


def build_record(state: PinState, *, on: datetime.date, inputs_path: Path) -> dict[str, Any]:
    """The record as ``write`` stores it; ``state`` must have no findings."""
    record = _record(base={"schema_version": RECORD_VERSION, "freeze_date": on.isoformat(),
                           "original_pins": dict(sorted(state.pins.items())),
                           "written_at_commit": state.git_commit, "inputs_path": inputs_path.as_posix()},
                     pins=state.pins, amendments=[])
    return record


def serialize(record: Mapping[str, Any]) -> bytes:
    data = (json.dumps(record, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")
    if len(data) > MAX_RECORD_BYTES:
        raise FreezeError("record_too_large", f"the record would exceed {MAX_RECORD_BYTES} bytes")
    return data


def write_freeze(inputs: FreezeInputs, root: Path, *, on: datetime.date, today: datetime.date,
                 git: GitProbe | None = None) -> dict[str, Any]:
    """Freeze once (FR11): every precondition must pass, and nothing is written otherwise."""
    state = check_state(inputs, root, on=on, today=today, git=git)
    if state.findings:
        codes = sorted({finding.code for finding in state.findings})
        raise FreezeError("not_ready", f"{len(state.findings)} precondition(s) fail; run check", codes)
    record = build_record(state, on=on, inputs_path=inputs.path)
    _write_atomically(root / sa.FREEZE_FILE, serialize(record), exclusive=True)
    return record


def require_freeze(root: Path, *, run: RunIdentity | None = None, path: Path = sa.FREEZE_FILE) -> FreezeRecord:
    """Fail closed unless the record is intact and every pin still holds (FR12, FR17)."""
    record = read_record(root / path)
    _check_integrity(record)
    inputs = load_inputs(_relative(record["inputs_path"], "inputs_path"), root=root)
    state = compute_pins(inputs, root)
    pins = record["pins"]
    moved = sorted(key for key in pins.keys() | state.pins.keys() if pins.get(key) != state.pins.get(key))
    if moved:
        raise FreezeError("freeze_mismatch", f"{len(moved)} pin(s) differ from the freeze: {', '.join(moved)}", moved)
    if state.config is None:  # unreachable while analysis.config verified, kept so the type is exact
        raise FreezeError("freeze_mismatch", "the analysis config did not load", ["analysis.config"])
    frozen = FreezeRecord(record, record["content_sha256"], datetime.date.fromisoformat(record["freeze_date"]),
                          pins, state.config)
    if run is not None:
        check_run(frozen, run)
    return frozen


def amend_freeze(root: Path, *, on: datetime.date, reason: str, today: datetime.date,
                 git: GitProbe | None = None) -> dict[str, Any]:
    """Append one dated, reasoned, chained amendment for every pin that moved (FR13)."""
    record = read_record(root / sa.FREEZE_FILE)
    _check_integrity(record)
    _check_reason(reason)
    frozen_on = datetime.date.fromisoformat(record["freeze_date"])
    if on < frozen_on:
        raise FreezeError("amend_before_freeze", f"{on.isoformat()} is before the freeze ({frozen_on.isoformat()})",
                          ["freeze_date"])
    last = record["amendments"][-1]["on"] if record["amendments"] else None
    if last is not None and on.isoformat() < last:
        raise FreezeError("amend_out_of_order", f"{on.isoformat()} is before the last amendment ({last})", ["amendments"])
    inputs = load_inputs(_relative(record["inputs_path"], "inputs_path"), root=root)
    state = check_state(inputs, root, on=on, today=today, git=git, record_may_exist=True)
    if state.findings:
        codes = sorted({finding.code for finding in state.findings})
        raise FreezeError("not_ready", f"{len(state.findings)} precondition(s) fail; run check --on", codes)
    pins = record["pins"]
    changes = {key: {"old": pins.get(key), "new": state.pins.get(key)}
               for key in sorted(pins.keys() | state.pins.keys()) if pins.get(key) != state.pins.get(key)}
    if not changes:
        raise FreezeError("nothing_changed", "every pin still holds; there is nothing to amend", ["pins"])
    immutable = [key for key in changes if key.startswith(IMMUTABLE_PREFIXES)]
    if immutable:
        raise FreezeError("frozen_set_immutable", "the frozen test set and its data cannot be amended; "
                                                  "that needs a new freeze version", immutable)
    amendment = {"on": on.isoformat(), "reason": reason, "changes": changes, "commit": state.git_commit,
                 "previous_content_sha256": record["content_sha256"]}
    amended = _record({key: record[key] for key in BASE_KEYS}, state.pins, [*record["amendments"], amendment])
    _write_atomically(root / sa.FREEZE_FILE, serialize(amended), exclusive=False)
    return amended


def _check_reason(reason: str) -> None:
    """Printable ASCII, bounded, and nothing shaped like a test ID: the reason is committed (FR13)."""
    if not reason.strip() or len(reason) > MAX_REASON_CHARS:
        raise FreezeError("bad_reason", f"the reason must be 1-{MAX_REASON_CHARS} characters", ["reason"])
    if any(not " " <= char <= "~" for char in reason):
        raise FreezeError("bad_reason", "the reason must be printable ASCII on one line", ["reason"])
    if re.search(_ID_RE.pattern, reason, re.IGNORECASE):  # dialogue and item IDs (PMUL1234, PMUL1234_t5)
        raise FreezeError("bad_reason", "the reason must not name a dialogue or item", ["reason"])


def check_run(frozen: FreezeRecord, run: RunIdentity) -> None:
    """A Stage 1 run belongs to the frozen grid: pinned recipe, frozen seed, a design condition."""
    prefix = f"recipe.{run.system}"
    system = _panel_system(frozen.config, run.system)
    if system is None or f"{prefix}.seeds" not in frozen.pins:
        raise FreezeError("system_not_frozen", f"{run.system[:64]!r} is not a frozen panel system", [prefix])
    if frozen.pins.get(f"{prefix}.stage1") != run.recipe_sha256:
        raise FreezeError("recipe_not_frozen", f"the run's recipe is not the frozen {run.system} recipe", [f"{prefix}.stage1"])
    if str(run.seed) not in frozen.pins[f"{prefix}.seeds"].split(","):
        raise FreezeError("seed_not_frozen", f"seed {run.seed} is not in the frozen {run.system} seeds", [f"{prefix}.seeds"])
    if run.train_condition not in conditions_for(system):
        raise FreezeError("condition_not_frozen", f"a {system.design} {system.family} system does not train on "
                                                  f"{run.train_condition[:20]!r}", [prefix])


def read_record(path: Path) -> dict[str, Any]:
    """The record's JSON object, bounded; any structural problem is ``freeze_malformed``."""
    if not path.is_file():
        raise FreezeError("freeze_missing", f"{path.name} does not exist; run the WP-08 freeze first", ["freeze"])
    try:
        record = json.loads(read_bounded(path, MAX_RECORD_BYTES, FreezeError).decode("utf-8"))
    except FreezeError:
        raise
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise FreezeError("freeze_malformed", f"{path.name} is not valid UTF-8 JSON", ["freeze"]) from None
    _check_shape(record)
    return record


def _check_shape(record: Any) -> None:
    def bad(what: str) -> FreezeError:
        return FreezeError("freeze_malformed", f"freeze record: {what}", ["freeze"])

    if not isinstance(record, dict) or set(record) != set(RECORD_KEYS):
        raise bad(f"must be an object with exactly {list(RECORD_KEYS)}")
    if record["schema_version"] != RECORD_VERSION:
        raise bad(f"schema_version must be {RECORD_VERSION!r}")
    if not isinstance(record["freeze_date"], str) or not _is_date(record["freeze_date"]):
        raise bad("freeze_date must be YYYY-MM-DD")
    for name in ("pins", "original_pins"):
        if not isinstance(record[name], dict) or not all(isinstance(k, str) and isinstance(v, str)
                                                         for k, v in record[name].items()):
            raise bad(f"{name} must map strings to strings")
    for name in ("content_sha256", "analysis_config_sha256"):
        if not isinstance(record[name], str) or _SHA256_RE.fullmatch(record[name]) is None:
            raise bad(f"{name} must be a SHA-256 hex digest")
    if not isinstance(record["amendments"], list) or not all(isinstance(a, dict) for a in record["amendments"]):
        raise bad("amendments must be a list of objects")
    if record["written_at_commit"] is not None and not isinstance(record["written_at_commit"], str):
        raise bad("written_at_commit must be a string")
    if not isinstance(record["inputs_path"], str):
        raise bad("inputs_path must be a path string")


def _check_integrity(record: Mapping[str, Any]) -> None:
    """Content hash, amendment chain and overlay, and the top-level analysis hash (FR12)."""
    if canonical_sha256(_without_content(record)) != record["content_sha256"]:
        raise FreezeError("freeze_tampered", "the record's content hash does not match; it was edited by hand", ["freeze"])
    base = {key: record[key] for key in BASE_KEYS}
    pins = dict(record["original_pins"])
    dates = [record["freeze_date"]]
    for number, amendment in enumerate(record["amendments"]):
        if set(amendment) != set(AMENDMENT_KEYS) or not isinstance(amendment["on"], str) \
                or not _is_date(amendment["on"]) or amendment["on"] < dates[-1]:
            raise FreezeError("freeze_malformed", f"amendment {number + 1} lacks fields or is out of date order", ["freeze"])
        dates.append(amendment["on"])
        previous = _record(base, pins, record["amendments"][:number])
        if amendment.get("previous_content_sha256") != previous["content_sha256"]:
            raise FreezeError("freeze_tampered", f"amendment {number + 1} does not chain to the record before it",
                              ["freeze"])
        pins = _apply(pins, amendment, number)
    if pins != record["pins"]:
        raise FreezeError("freeze_tampered", "the original pins and amendments do not give the current pins", ["freeze"])
    if record["analysis_config_sha256"] != pins.get("analysis.config"):
        raise FreezeError("freeze_tampered", "analysis_config_sha256 is not the analysis.config pin", ["freeze"])


def _apply(pins: Mapping[str, str], amendment: Mapping[str, Any], number: int) -> dict[str, str]:
    changes = amendment.get("changes")
    if not isinstance(changes, dict) or not changes:
        raise FreezeError("freeze_malformed", f"amendment {number + 1} has no changes", ["freeze"])
    result = dict(pins)
    for key, change in changes.items():
        if not isinstance(change, dict) or set(change) != {"old", "new"} or pins.get(key) != change["old"] \
                or not (change["new"] is None or isinstance(change["new"], str)):
            raise FreezeError("freeze_tampered", f"amendment {number + 1} change to {key[:80]} is inconsistent", ["freeze"])
        if change["new"] is None:
            result.pop(key, None)
        else:
            result[key] = change["new"]
    return result


def _record(base: Mapping[str, Any], pins: Mapping[str, str], amendments: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    record = {**base, "pins": dict(sorted(pins.items())), "amendments": list(amendments),
              "analysis_config_sha256": pins.get("analysis.config")}
    record["content_sha256"] = canonical_sha256(record)
    return record


def _without_content(record: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key != "content_sha256"}


def _write_atomically(path: Path, data: bytes, *, exclusive: bool) -> None:
    if exclusive and path.exists():
        raise FreezeError("freeze_exists", f"{path.name} already exists; the record is written once", ["freeze"])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _is_date(value: str) -> bool:
    try:
        return datetime.date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


# --------------------------------------------------------------------------- command line


def mask_ids(text: str) -> str:
    return _ID_RE.sub("<id>", text)


def _say(line: str) -> None:
    print(mask_ids(line))


def _report(state: PinState, verbose: bool) -> None:
    for finding in sorted(state.findings, key=lambda f: (f.status != "problem", f.key, f.code)):
        _say(f"{finding.status:8} {finding.code:26} {finding.key}  {finding.detail}".rstrip())
    families = Counter(key.split(".", 1)[0] for key in state.pins)
    _say(f"ready    {len(state.pins)} pins ({', '.join(f'{name} {n}' for name, n in sorted(families.items()))})")
    if verbose:
        for key in sorted(state.pins):
            _say(f"ready    {key}")


def _show(record: Mapping[str, Any]) -> None:
    """The disclosure view (FR14): freeze date, effective pins and every amendment."""
    _check_integrity(record)
    _say(f"freeze_date {record['freeze_date']}  content {record['content_sha256'][:12]}  "
         f"written at {str(record['written_at_commit'])[:12]}  {len(record['pins'])} pins")
    for key, value in sorted(record["pins"].items()):
        _say(f"  {key} = {value}")
    _say(f"{len(record['amendments'])} amendment(s)")
    for number, amendment in enumerate(record["amendments"], start=1):
        _say(f"  {number}. {amendment['on']}: {amendment['reason']}")
        _say(f"     changed: {', '.join(amendment['changes'])}")


def _date(value: str) -> datetime.date:
    try:
        parsed = datetime.date.fromisoformat(value)
    except ValueError:
        parsed = None
    if parsed is None or parsed.isoformat() != value:
        raise argparse.ArgumentTypeError("must be YYYY-MM-DD")
    return parsed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("check", "write", "verify", "amend", "show"))
    parser.add_argument("--inputs", type=Path, default=DEFAULT_INPUTS, help="freeze inputs, repository-relative")
    parser.add_argument("--root", type=Path, default=Path("."), help="repository root")
    parser.add_argument("--on", type=_date, help="freeze/amendment date (check: default today; write, amend: required)")
    parser.add_argument("--reason", help="amend: why, in one line of ASCII; no corpus quotes or IDs")
    parser.add_argument("--verbose", action="store_true", help="check: also list every ready pin key")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    today = datetime.date.today()
    if args.command in ("write", "amend") and args.on is None:
        parser.error(f"{args.command} needs --on YYYY-MM-DD")
    if args.command == "amend" and args.reason is None:
        parser.error("amend needs --reason")
    try:
        if args.command == "verify":
            frozen = require_freeze(root)
            _say(f"verified: {len(frozen.pins)} pins hold; frozen {frozen.freeze_date.isoformat()}, "
                 f"{len(frozen.record['amendments'])} amendment(s), content {frozen.content_sha256[:12]}")
            return 0
        if args.command == "show":
            _show(read_record(root / sa.FREEZE_FILE))
            return 0
        if args.command == "amend":
            amended = amend_freeze(root, on=args.on, reason=args.reason, today=today)
            changed = amended["amendments"][-1]["changes"]
            _say(f"amended {sa.FREEZE_FILE.as_posix()} on {args.on.isoformat()}: {', '.join(changed)}; "
                 "commit it and disclose the amendment in the paper")
            return 0
        inputs = load_inputs(args.inputs, root=root)
        if args.command == "write":
            record = write_freeze(inputs, root, on=args.on, today=today)
            _say(f"wrote {sa.FREEZE_FILE.as_posix()}: {len(record['pins'])} pins, freeze_date {record['freeze_date']}, "
                 f"content {record['content_sha256'][:12]}; commit it before the test grid")
            return 0
        state = check_state(inputs, root, on=args.on or today, today=today)
    except FreezeError as error:
        _say(f"problem  {error.code:26} {', '.join(error.keys) or 'inputs'}  {error}")
        return 1
    _report(state, args.verbose)
    if state.findings:
        _say(f"not ready: {len(state.findings)} item(s) to settle before `write`")
        return 1
    _say("ready to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
