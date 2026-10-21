"""Map the frozen panel's systems to their prediction files (spec 007 FR5–FR6).

The inputs file is written after the runs, so it may only *point* at files. The panel, the
Holm family and the designs come from the frozen analysis config. A system outside the panel
is an error, and a panel system the file does not mention is ``not_run``. Every file is hashed
here and re-verified when it is read (``files.read_verified``).

Format (``configs/analysis/inputs-<split>.toml``; paths relative to the repository root)::

    version = "analysis-inputs-v1"
    split = "dev"

    [systems.deberta-v3-large]
    stage1 = [
      { train_condition = "none", seed = 13, run_dir = "outputs/stage1/deberta-v3-large/train-none/seed13" },
    ]

    [systems.llm]
    stage2 = [{ train_condition = "untrained", seed = 0, routed = "...", oracle = "..." }]
    transfer = "outputs/transfer/llm.json"

**Design rules (FR6).** A ``matched`` system needs runs trained on each genuine condition
(``none``, ``one``, ``full``); its condition-c outcome comes from the train-c model. A
``test_time`` system needs only ``full``-trained runs, scored under every condition, and an
untrained ``llm`` declares ``untrained``. Mismatch conditions always use the full-trained (or
untrained) model. A run trained on any other condition is unused and therefore an error, so the
file cannot carry runs whose role is ambiguous.

**Stage 1 run directories** are checked against what the run recorded: ``config.resolved.json``
gives the run name, train condition and ``eval_split``, and ``metrics.json`` gives the seed and
smoke flag. Stage 2 provenance (which router fed a hybrid) can only be declared.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.analysis.config import GENUINE_CONDITIONS, AnalysisConfig, PanelSystem
from src.analysis.files import AnalysisError, FileRef, hash_file, parse_json, read_toml, read_verified
from src.data.contexts import MISMATCH_CONDITIONS

INPUTS_VERSION = "analysis-inputs-v1"
SPLITS = ("dev", "test")
LINES = ("matched", "test_time")
UNTRAINED = "untrained"
MAX_INPUTS_BYTES = 1 << 20
MAX_RUN_CONFIG_BYTES = 1 << 20
MAX_METRICS_BYTES = 64 << 20
MAX_PREDICTION_BYTES = 512 << 20
MAX_TRANSFER_BYTES = 64 << 20
MAX_PATH_CHARS = 1024
_SYSTEM_KEYS = ("stage1", "stage2", "transfer")
_STAGE1_KEYS = ("train_condition", "seed", "run_dir")
_STAGE2_KEYS = ("train_condition", "seed", "routed", "oracle")
_STREAMS_OF = {"stage1": ("stage1",), "stage2": ("routed", "oracle"), "transfer": ("transfer",)}


@dataclass(frozen=True)
class Stage1Run:
    train_condition: str
    seed: int
    run_dir: Path
    config: FileRef
    predictions: FileRef
    metrics: FileRef


@dataclass(frozen=True)
class Stage2Run:
    train_condition: str
    seed: int
    routed: FileRef
    oracle: FileRef


@dataclass(frozen=True)
class SystemInputs:
    system: PanelSystem
    stage1: tuple[Stage1Run, ...] = ()
    stage2: tuple[Stage2Run, ...] = ()
    transfer: FileRef | None = None

    @property
    def status(self) -> str:
        return "run" if self.stage1 or self.stage2 else "not_run"

    @property
    def lines(self) -> tuple[str, ...]:
        return LINES if self.system.design == "matched" else ("test_time",)

    @property
    def primary_line(self) -> str:
        return self.lines[0]

    def train_condition(self, line: str, condition: str) -> str:
        """The training condition of the model whose outputs fill ``condition`` on ``line``."""
        return train_condition_for(self.system, line, condition)

    def runs(self, stream: str, train_condition: str) -> tuple[Stage1Run, ...] | tuple[Stage2Run, ...]:
        runs = self.stage1 if stream == "stage1" else self.stage2
        return tuple(run for run in runs if run.train_condition == train_condition)


@dataclass(frozen=True)
class AnalysisInputs:
    split: str
    path: Path
    sha256: str
    systems: dict[str, SystemInputs] = field(default_factory=dict)

    def files(self, base: Path) -> dict[str, str]:
        """Every hashed input as display path -> SHA-256, for the report's provenance block."""
        refs: list[FileRef] = []
        for inputs in self.systems.values():
            for run in inputs.stage1:
                refs += [run.config, run.predictions, run.metrics]
            for run in inputs.stage2:
                refs += [run.routed, run.oracle]
            if inputs.transfer is not None:
                refs.append(inputs.transfer)
        return {_display(ref.path, base): ref.sha256 for ref in sorted(refs, key=lambda r: str(r.path))}


def train_condition_for(system: PanelSystem, line: str, condition: str) -> str:
    if line not in LINES or (line == "matched" and system.design != "matched"):
        raise AnalysisError("unknown_line", f"{system.name} has no {line} line")
    if system.family == "llm":
        return UNTRAINED
    if line == "matched" and condition in GENUINE_CONDITIONS:
        return condition
    return "full"


def needed_train_conditions(system: PanelSystem) -> tuple[str, ...]:
    if system.family == "llm":
        return (UNTRAINED,)
    return GENUINE_CONDITIONS if system.design == "matched" else ("full",)


def load_inputs(path: Path, config: AnalysisConfig, split: str, *, base: Path) -> AnalysisInputs:
    """Validate an inputs file against the panel and the split, hashing every file it names."""
    raw = read_toml(path, MAX_INPUTS_BYTES)
    _keys(raw, "inputs", ("version", "split", "systems"))
    if raw["version"] != INPUTS_VERSION:
        raise AnalysisError("unknown_version", f"inputs version must be {INPUTS_VERSION!r}")
    if split not in SPLITS or raw["split"] != split:
        raise AnalysisError("split_mismatch", f"the inputs file is for split {str(raw['split'])[:10]!r}, not {split!r}")
    systems = raw["systems"]
    if not isinstance(systems, dict):
        raise AnalysisError("wrong_type", "[systems] must be a table")
    panel = {system.name: system for system in config.panel}
    extra = sorted(set(systems) - set(panel))
    if extra:
        raise AnalysisError("system_outside_panel", f"not in the frozen panel: {[name[:64] for name in extra]}")
    resolved = {name: _system(panel[name], systems.get(name, {}), split, base) for name in panel}
    return AnalysisInputs(split=split, path=path, sha256=hash_file(path, MAX_INPUTS_BYTES).sha256, systems=resolved)


def _system(system: PanelSystem, table: Any, split: str, base: Path) -> SystemInputs:
    where = f"[systems.{system.name}]"
    _keys(table, where, _SYSTEM_KEYS, required=())
    provided = {stream for key in table for stream in _STREAMS_OF[key]}
    undeclared = sorted(provided - set(system.streams))
    if undeclared:
        raise AnalysisError("undeclared_stream", f"{where} gives {undeclared}, which the panel does not declare")
    if not provided:
        return SystemInputs(system)
    missing = sorted(set(system.streams) - provided - {"transfer"})
    if missing:
        raise AnalysisError("missing_stream", f"{where} lacks the panel's {missing} streams")
    stage1 = tuple(_stage1_run(system, entry, f"{where}.stage1[{i}]", split, base)
                   for i, entry in enumerate(_entries(table, "stage1", where)))
    stage2 = tuple(_stage2_run(system, entry, f"{where}.stage2[{i}]", base)
                   for i, entry in enumerate(_entries(table, "stage2", where)))
    for stream, runs in (("stage1", stage1), ("stage2", stage2)):
        if stream in table:
            _check_design(system, runs, f"{where}.{stream}")
    transfer = hash_file(_path(table["transfer"], f"{where}.transfer", base), MAX_TRANSFER_BYTES) \
        if "transfer" in table else None
    return SystemInputs(system, stage1, stage2, transfer)


def _check_design(system: PanelSystem, runs: Sequence[Stage1Run | Stage2Run], where: str) -> None:
    needed = needed_train_conditions(system)
    seen: set[tuple[str, int]] = set()
    for run in runs:
        if run.train_condition not in needed:
            raise AnalysisError("unused_train_condition",
                                f"{where}: a {system.design} {system.family} system uses only {list(needed)} "
                                f"training, not {run.train_condition!r}")
        if (run.train_condition, run.seed) in seen:
            raise AnalysisError("duplicate_run", f"{where}: train {run.train_condition} seed {run.seed} appears twice")
        seen.add((run.train_condition, run.seed))
    missing = [condition for condition in needed if not any(r.train_condition == condition for r in runs)]
    if missing:
        raise AnalysisError("missing_train_condition", f"{where}: no runs trained on {missing}")


def _stage1_run(system: PanelSystem, entry: Any, where: str, split: str, base: Path) -> Stage1Run:
    _keys(entry, where, _STAGE1_KEYS)
    train_condition, seed = _train_condition(entry["train_condition"], where), _seed(entry["seed"], where)
    run_dir = _path(entry["run_dir"], f"{where}.run_dir", base)
    if not run_dir.is_dir():
        raise AnalysisError("not_a_directory", f"{where}: {run_dir} is not a directory")
    config_ref = hash_file(run_dir / "config.resolved.json", MAX_RUN_CONFIG_BYTES)
    metrics_ref = hash_file(run_dir / "metrics.json", MAX_METRICS_BYTES)
    predictions_ref = hash_file(run_dir / "predictions.jsonl", MAX_PREDICTION_BYTES)
    resolved = parse_json(read_verified(config_ref), f"{where} config.resolved.json")
    metrics = parse_json(read_verified(metrics_ref), f"{where} metrics.json")
    try:
        name, data, run = resolved["name"], resolved["data"], metrics["run"]
        recorded = (data["train_condition"], data["eval_split"], run["train_condition"], run["eval_split"],
                    run["seed"], run["smoke"])
    except (KeyError, TypeError):
        raise AnalysisError("malformed_run", f"{where}: the run's config or metrics lack the run fields") from None
    if name != system.name:
        raise AnalysisError("run_name_mismatch", f"{where}: the run is named {str(name)[:64]!r}, not {system.name!r}")
    if recorded[0] != train_condition or recorded[2] != train_condition:
        raise AnalysisError("train_condition_mismatch",
                            f"{where}: declared train {train_condition!r}, the run recorded {str(recorded[0])[:20]!r}")
    if recorded[1] != split or recorded[3] != split:
        raise AnalysisError("run_split_mismatch", f"{where}: the run evaluated {str(recorded[1])[:10]!r}, not {split!r}")
    if recorded[4] != seed or isinstance(recorded[4], bool):
        raise AnalysisError("seed_mismatch", f"{where}: declared seed {seed}, the run recorded another")
    if recorded[5] is not False:
        raise AnalysisError("smoke_run", f"{where}: a smoke run is a pipeline check, not a result")
    return Stage1Run(train_condition, seed, run_dir, config_ref, predictions_ref, metrics_ref)


def _stage2_run(system: PanelSystem, entry: Any, where: str, base: Path) -> Stage2Run:
    _keys(entry, where, _STAGE2_KEYS)
    routed = _path(entry["routed"], f"{where}.routed", base)
    oracle = _path(entry["oracle"], f"{where}.oracle", base)
    if routed == oracle:
        raise AnalysisError("same_file", f"{where}: routed and oracle outputs must be separate files")
    return Stage2Run(_train_condition(entry["train_condition"], where), _seed(entry["seed"], where),
                     hash_file(routed, MAX_PREDICTION_BYTES), hash_file(oracle, MAX_PREDICTION_BYTES))


def _keys(table: Any, where: str, allowed: Sequence[str], required: Sequence[str] | None = None) -> Mapping[str, Any]:
    if not isinstance(table, dict):
        raise AnalysisError("wrong_type", f"{where} must be a table")
    unknown = sorted(set(table) - set(allowed))
    if unknown:
        raise AnalysisError("unknown_key", f"{where}: {[key[:40] for key in unknown]}")
    missing = [key for key in (allowed if required is None else required) if key not in table]
    if missing:
        raise AnalysisError("missing_key", f"{where}: {missing}")
    return table


def _entries(table: Mapping[str, Any], key: str, where: str) -> list[Any]:
    """A stream's run entries; an absent stream has none, a present one must list some."""
    if key not in table:
        return []
    value = table[key]
    if not isinstance(value, list) or not value:
        raise AnalysisError("wrong_type", f"{where}.{key} must be a non-empty array of tables")
    return value


def _train_condition(value: Any, where: str) -> str:
    allowed = (*GENUINE_CONDITIONS, *MISMATCH_CONDITIONS, UNTRAINED)
    if not isinstance(value, str) or value not in allowed:
        raise AnalysisError("unknown_train_condition", f"{where}.train_condition must be one of {list(allowed)}")
    return value


def _seed(value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AnalysisError("wrong_type", f"{where}.seed must be a non-negative integer")
    return value


def _path(value: Any, where: str, base: Path) -> Path:
    if not isinstance(value, str) or not value or len(value) > MAX_PATH_CHARS or "\x00" in value:
        raise AnalysisError("wrong_type", f"{where} must be a path string")
    path = Path(value)
    resolved = (path if path.is_absolute() else base / path).resolve()
    if not resolved.exists():
        raise AnalysisError("missing_path", f"{where}: {resolved} does not exist")
    return resolved


def _display(path: Path, base: Path) -> str:
    """Repository-relative where possible, so provenance does not record the user's home path."""
    root = base.resolve()
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix()
