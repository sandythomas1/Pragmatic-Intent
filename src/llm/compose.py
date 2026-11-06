"""Hybrid composer: router predictions × interpreter interpretations (spec 009 T9, FR11, FR12).

    python -E -s -m src.llm.compose compose --split dev \\
        --router-root outputs/stage1/deberta-v3-large \\
        --interpreter outputs/stage2/qwen2.5-7b-instruct/dev

**Inputs.** Every check below runs before anything is written.
- *Router runs.* Every ``<router-root>/train-<c>/seed<s>/`` for c in ``none``/``one``/``full``;
  ``-smoke`` directories are skipped. All three train conditions must be present with the same
  seeds. Each run must record the router's name, its directory's train condition and seed, this
  split as ``eval_split`` and ``smoke = false``, in both ``config.resolved.json`` and
  ``metrics.json``. Its ``predictions.jsonl`` must hash to the value its metrics recorded (FR12).
- *Interpreter.* The complete main-task run of the recipe's selected prompt on this split: a
  ``provenance.main.json`` for all conditions, plus the ``interpretation.jsonl`` and
  ``oracle.jsonl`` files whose hashes it records.

**Composition (FR11).** For each ``(example_id, condition)`` that a router run predicted:
- router ``no_request`` gives the ``no_request`` row (null category, empty slots), whatever the
  interpreter returned, including ``invalid``;
- router ``direct``/``indirect`` with a valid interpretation gives the router's route plus the
  interpretation's ``category``, ``slots`` and ``requested_slots``;
- router ``direct``/``indirect`` with an invalid interpretation gives ``{"invalid": true}``.

The router and the interpreter must cover exactly the same ``(example_id, condition)`` set.

**Output.** ``outputs/stage2/hybrid/<split>/train-<c>/seed<s>/{routed,oracle}.jsonl``, with
``provenance.compose.json`` (both sides' input hashes) beside the run directories.
- Each routed file covers every condition its router run predicted. The analysis then takes
  matched condition c from the train-c file and mismatch conditions from the train-full file
  (spec 007 FR6); ``router_train_condition`` encodes the same rule for prompt selection (T11).
- Each oracle file is a byte copy of the interpreter's oracle file.
- Rows keep the router's order and are serialized with sorted keys, so the outputs are
  byte-deterministic.

**The test split (FR15b).** The freeze is verified before any input is read. Before anything is
written, every router run must then belong to the frozen ``deberta-v3-large`` grid (recipe hash,
seed and train condition), and the interpreter's provenance must name the frozen files, rendered
prompt and model.

Errors name files, codes and counts, never an example ID or corpus text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.analysis.files import AnalysisError, parse_json, parse_jsonl, read_bounded
from src.data.contexts import MISMATCH_CONDITIONS
from src.data.direct_dataset import CONDITIONS
from src.data.freeze import (FreezeError, FreezeRecord, RunIdentity, check_llm_run, check_run, recipe_sha256,
                             require_freeze)
from src.evaluation.interpretation import validate_predictions
from src.llm import streams
from src.llm.paths import REPO_ROOT, under_outputs
from src.llm.recipe import SPLITS
from src.stage1.data import STAGE1_LABELS
from src.stage1.provenance import git_state, source_sha256

COMPOSE_VERSION = "llm-compose-v1"
RUN_PROVENANCE_VERSION = "llm-run-v1"
ROUTER_NAME = "deberta-v3-large"
HYBRID_SYSTEM = "hybrid"
NO_REQUEST = "no_request"
ROUTER_TRAIN_CONDITIONS = tuple(c for c in CONDITIONS if c not in MISMATCH_CONDITIONS)
MAX_CONFIG_BYTES = 1 << 20
MAX_METRICS_BYTES = 64 << 20
MAX_PREDICTION_BYTES = 512 << 20
_SEED_DIR = re.compile(r"seed(0|[1-9][0-9]{0,8})\Z")
_INTERPRETATION_FIELDS = ("category", "slots", "requested_slots")


class ComposeError(ValueError):
    """A named composer refusal; ``code`` is stable for tests. Nothing has been written."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code


@dataclass(frozen=True)
class RouterRun:
    train_condition: str
    seed: int
    rows: tuple[Mapping[str, Any], ...]
    hashes: Mapping[str, str]  # config / metrics / predictions SHA-256
    recipe_sha256: str  # the freeze's identity of the run's Stage 1 recipe

    @property
    def label(self) -> str:
        return f"train-{self.train_condition}/seed{self.seed}"


@dataclass(frozen=True)
class Interpreter:
    system: str
    model: str
    variant: str
    interpretation: tuple[Mapping[str, Any], ...]
    oracle: bytes
    hashes: Mapping[str, str]  # provenance / interpretation / oracle SHA-256
    provenance: Mapping[str, Any]


# --- the composition rule (FR11) -----------------------------------------------------------------

def router_train_condition(condition: str) -> str:
    """The training condition of the router that fills ``condition``: matched c → c, mismatch → full."""
    if condition in ROUTER_TRAIN_CONDITIONS:
        return condition
    if condition in MISMATCH_CONDITIONS:
        return "full"
    raise ComposeError("unknown_condition", "not a DIRECT condition")


def compose_rows(router_rows: Sequence[Mapping[str, Any]], interpretation_rows: Sequence[Mapping[str, Any]],
                 conditions: Collection[str] | None = None) -> list[dict[str, Any]]:
    """The hybrid's routed rows, in router order (FR11, FR12).

    With ``conditions``, only the router rows under those conditions are composed. Prompt
    selection (T11) uses that over its ``none``/``full`` outputs. Either way the interpretation
    rows must cover exactly the composed ``(example_id, condition)`` set.
    """
    routes = _router_routes(router_rows, conditions)
    interpretations = _interpretations(interpretation_rows, routes)
    composed = []
    for (example_id, condition), route in routes.items():
        interpretation = interpretations[(example_id, condition)]
        if route == NO_REQUEST:
            composed.append({"example_id": example_id, "condition": condition, "prediction": NO_REQUEST,
                             "category": None, "slots": {}, "requested_slots": []})
        elif interpretation.get("invalid") is True:
            composed.append({"example_id": example_id, "condition": condition, "invalid": True})
        else:
            composed.append({"example_id": example_id, "condition": condition, "prediction": route,
                             **{field: interpretation[field] for field in _INTERPRETATION_FIELDS}})
    return composed


def _router_routes(rows: Sequence[Mapping[str, Any]], conditions: Collection[str] | None
                   ) -> dict[tuple[str, str], str]:
    if conditions is not None and (not conditions or set(conditions) - set(CONDITIONS)):
        raise ComposeError("unknown_condition", "conditions must be a non-empty subset of the DIRECT conditions")
    routes: dict[tuple[str, str], str] = {}
    for number, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise ComposeError("router_row", f"router row {number} is not an object")
        example_id, condition, label = row.get("example_id"), row.get("condition"), row.get("prediction")
        if not isinstance(example_id, str) or not example_id or len(example_id) > 150:
            raise ComposeError("router_row", f"router row {number} has no valid example_id")
        if condition not in CONDITIONS or label not in STAGE1_LABELS:
            raise ComposeError("router_row", f"router row {number} has an unknown condition or label")
        if conditions is not None and condition not in conditions:
            continue
        if (example_id, condition) in routes:
            raise ComposeError("router_row", f"router row {number} duplicates an earlier (example, condition)")
        routes[(example_id, condition)] = label
    if not routes:
        raise ComposeError("router_row", "the router predicts nothing under the requested conditions")
    return routes


def _interpretations(rows: Sequence[Mapping[str, Any]], routes: Mapping[tuple[str, str], str]
                     ) -> dict[tuple[str, str], Mapping[str, Any]]:
    keys = []
    for number, row in enumerate(rows, start=1):
        key = (row.get("example_id"), row.get("condition")) if isinstance(row, Mapping) else None
        if key is None or not all(isinstance(part, str) for part in key):
            raise ComposeError("interpretation_row", f"interpretation row {number} has no example_id or condition")
        keys.append(key)
    expected = set(routes)
    if len(keys) != len(set(keys)) or set(keys) != expected:
        provided = set(keys)
        raise ComposeError("coverage", f"router and interpreter cover different (example, condition) sets: "
                                       f"{len(expected - provided)} without an interpretation, "
                                       f"{len(provided - expected)} without a router prediction, "
                                       f"{len(keys) - len(provided)} duplicated")
    by_condition: dict[str, set[str]] = {}
    for example_id, condition in expected:
        by_condition.setdefault(condition, set()).add(example_id)
    try:
        validate_predictions(list(rows), by_condition)
    except ValueError as error:
        raise ComposeError("interpretation_row", str(error)) from None
    for row in rows:
        if row.get("invalid") is not True and row["category"] in (None, NO_REQUEST):
            raise ComposeError("interpretation_row", "a valid interpretation must carry a request category (FR3)")
    return dict(zip(keys, rows))


# --- inputs (FR12) -------------------------------------------------------------------------------

def load_router_runs(router_root: Path, split: str, name: str = ROUTER_NAME) -> list[RouterRun]:
    """Every non-smoke run under ``router_root``, checked against its directory's declared role."""
    seeds_by_condition = {}
    for condition in ROUTER_TRAIN_CONDITIONS:
        directory = router_root / f"train-{condition}"
        seeds = sorted(int(match[1]) for child in directory.iterdir() if child.is_dir()
                       and (match := _SEED_DIR.fullmatch(child.name))) if directory.is_dir() else []
        if not seeds:
            raise ComposeError("missing_train_condition", f"no train-{condition} router runs under {router_root.name}")
        seeds_by_condition[condition] = seeds
    if len({tuple(seeds) for seeds in seeds_by_condition.values()}) != 1:
        raise ComposeError("seed_sets_differ", "the train-none/one/full router runs have different seeds")
    return [load_router_run(router_root / f"train-{condition}" / f"seed{seed}", split=split, name=name,
                            train_condition=condition, seed=seed)
            for condition, seeds in seeds_by_condition.items() for seed in seeds]


def load_router_run(run_dir: Path, *, split: str, name: str, train_condition: str, seed: int) -> RouterRun:
    """One router run, refused if what it recorded differs from its declared role (FR12)."""
    where = f"train-{train_condition}/seed{seed}"
    config_bytes = _read(run_dir / "config.resolved.json", MAX_CONFIG_BYTES)
    metrics_bytes = _read(run_dir / "metrics.json", MAX_METRICS_BYTES)
    predictions = _read(run_dir / "predictions.jsonl", MAX_PREDICTION_BYTES)
    config, metrics = _json(config_bytes, f"{where} config"), _json(metrics_bytes, f"{where} metrics")
    try:
        data, run = config["data"], metrics["run"]
        recorded = {"name": config["name"], "config_train": data["train_condition"], "config_split": data["eval_split"],
                    "run_train": run["train_condition"], "run_split": run["eval_split"], "seed": run["seed"],
                    "smoke": run["smoke"], "predictions_sha256": run["predictions_sha256"]}
    except (KeyError, TypeError):
        raise ComposeError("malformed_run", f"{where}: config or metrics lack the run fields") from None
    if recorded["name"] != name:
        raise ComposeError("run_name_mismatch", f"{where}: not a {name} run")
    if (recorded["config_train"], recorded["run_train"]) != (train_condition, train_condition):
        raise ComposeError("train_condition_mismatch", f"{where}: the run recorded another train condition")
    if (recorded["config_split"], recorded["run_split"]) != (split, split):
        raise ComposeError("run_split_mismatch", f"{where}: the run did not evaluate {split}")
    if isinstance(recorded["seed"], bool) or recorded["seed"] != seed:
        raise ComposeError("seed_mismatch", f"{where}: the run recorded another seed")
    if recorded["smoke"] is not False:
        raise ComposeError("smoke_run", f"{where}: a smoke run is a pipeline check, not a result")
    predictions_sha256 = _sha256(predictions)
    if recorded["predictions_sha256"] != predictions_sha256:
        raise ComposeError("predictions_changed", f"{where}: predictions.jsonl differs from what the run recorded")
    rows = _jsonl(predictions, f"{where} predictions")
    return RouterRun(train_condition, seed, tuple(rows),
                     {"config_sha256": _sha256(config_bytes), "metrics_sha256": _sha256(metrics_bytes),
                      "predictions_sha256": predictions_sha256},
                     recipe_sha256(config))


def load_interpreter(directory: Path, split: str) -> Interpreter:
    """The interpreter's complete, selected-prompt main run on ``split``, verified against its provenance."""
    provenance_bytes = _read(directory / "provenance.main.json", MAX_CONFIG_BYTES)
    provenance = _json(provenance_bytes, "interpreter provenance")
    try:
        identity = (provenance["version"], provenance["task"], provenance["split"])
        selected, conditions, outputs = provenance["selected_variant"], provenance["conditions"], provenance["outputs"]
        system, model, variant = provenance["system"], provenance["model"], provenance["variant"]
    except (KeyError, TypeError):
        raise ComposeError("malformed_interpreter", "the interpreter provenance lacks the run fields") from None
    if identity != (RUN_PROVENANCE_VERSION, "main", split):
        raise ComposeError("interpreter_mismatch", f"not a main-task {RUN_PROVENANCE_VERSION} run on {split}")
    if selected is not True or conditions is not None:
        raise ComposeError("interpreter_partial", "a prompt-selection or condition-subset run is not the interpreter")
    if not all(isinstance(value, str) for value in (system, model, variant)) or not isinstance(outputs, dict):
        raise ComposeError("malformed_interpreter", "the interpreter provenance has wrongly typed fields")
    files = {}
    for kind in ("interpretation", "oracle"):
        data = _read(directory / f"{kind}.jsonl", MAX_PREDICTION_BYTES)
        if outputs.get(f"{kind}.jsonl") != _sha256(data):
            raise ComposeError("interpreter_changed", f"{kind}.jsonl differs from what the interpreter run recorded")
        files[kind] = data
    return Interpreter(system, model, variant, tuple(_jsonl(files["interpretation"], "interpretation")),
                       files["oracle"],
                       {"provenance_sha256": _sha256(provenance_bytes),
                        "interpretation_sha256": _sha256(files["interpretation"]),
                        "oracle_sha256": _sha256(files["oracle"])},
                       provenance)


def check_frozen(frozen: FreezeRecord, runs: Sequence[RouterRun], interpreter: Interpreter) -> None:
    """FR15b: every router run is in the frozen router grid, and the interpreter is the frozen one."""
    for run in runs:
        check_run(frozen, RunIdentity(ROUTER_NAME, run.recipe_sha256, run.seed, run.train_condition))
    try:
        recipe, rendered = interpreter.provenance["recipe"], interpreter.provenance["prompt"]["rendered_sha256"]
        files = {recipe["path"]: recipe["text_sha256"]}
    except (KeyError, TypeError):
        raise ComposeError("malformed_interpreter", "the interpreter provenance lacks its recipe or prompt") from None
    check_llm_run(frozen, interpreter.system, files, rendered, interpreter.model)


# --- the command ---------------------------------------------------------------------------------

def compose(*, split: str, router_root: Path, interpreter_dir: Path, root: Path = REPO_ROOT,
            router_name: str = ROUTER_NAME) -> dict[str, Any]:
    """Check every input, compose every router run, then write all files and the provenance last."""
    if split not in SPLITS:
        raise ComposeError("unknown_split", f"split must be one of {list(SPLITS)}")
    frozen = require_freeze(root) if split == "test" else None
    router_root, interpreter_dir = (path if path.is_absolute() else root / path for path in (router_root, interpreter_dir))
    out_root = under_outputs(Path("outputs/stage2") / HYBRID_SYSTEM / split, root)
    runs = load_router_runs(router_root, split, router_name)
    interpreter = load_interpreter(interpreter_dir, split)
    if frozen is not None:
        check_frozen(frozen, runs, interpreter)

    pending: dict[str, bytes] = {}
    counts: dict[str, dict[str, int]] = {}
    for run in runs:
        rows = compose_rows(run.rows, interpreter.interpretation)
        validate_predictions(rows, _expected(rows))
        pending[f"{run.label}/routed.jsonl"] = streams.jsonl_bytes(rows)
        pending[f"{run.label}/oracle.jsonl"] = interpreter.oracle
        counts[run.label] = {"rows": len(rows),
                             "router_no_request": sum(row.get("prediction") == NO_REQUEST for row in rows),
                             "invalid": sum(row.get("invalid") is True for row in rows)}

    for relative, data in pending.items():
        streams.write_atomic(out_root / relative, data, root)
    provenance = {
        "version": COMPOSE_VERSION, "spec": "009", "system": HYBRID_SYSTEM, "split": split,
        "freeze_content_sha256": frozen.content_sha256 if frozen else None,
        "router": {"name": router_name, "root": _relative(router_root, root),
                   "runs": [{"train_condition": run.train_condition, "seed": run.seed, **run.hashes} for run in runs]},
        "interpreter": {"system": interpreter.system, "model": interpreter.model, "variant": interpreter.variant,
                        "dir": _relative(interpreter_dir, root), **interpreter.hashes},
        "code": {"source_sha256": source_sha256(), **git_state(cwd=REPO_ROOT)},
        "counts": counts,
        "outputs": {relative: _sha256(data) for relative, data in pending.items()},
    }
    streams.write_atomic(out_root / "provenance.compose.json", streams.json_bytes(provenance), root)
    return provenance


def _expected(rows: Sequence[Mapping[str, Any]]) -> dict[str, set[str]]:
    expected: dict[str, set[str]] = {}
    for row in rows:
        expected.setdefault(row["condition"], set()).add(row["example_id"])
    return expected


def _read(path: Path, limit: int) -> bytes:
    try:
        return read_bounded(path, limit)
    except AnalysisError as error:
        raise ComposeError(error.code, f"{path.parent.name}/{path.name} is missing or too large") from None


def _json(data: bytes, label: str) -> Any:
    try:
        return parse_json(data, label)
    except AnalysisError as error:
        raise ComposeError(error.code, str(error)) from None


def _jsonl(data: bytes, label: str) -> list[Any]:
    try:
        return parse_jsonl(data, label)
    except AnalysisError as error:
        raise ComposeError(error.code, str(error)) from None


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _relative(path: Path, root: Path) -> str:
    resolved = path.resolve()
    return resolved.relative_to(root.resolve()).as_posix() if resolved.is_relative_to(root.resolve()) else path.name


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    compose_parser = commands.add_parser("compose", help="compose the hybrid's routed and oracle files")
    compose_parser.add_argument("--split", choices=SPLITS, required=True)
    compose_parser.add_argument("--router-root", type=Path, required=True,
                                help=f"e.g. outputs/stage1/{ROUTER_NAME}")
    compose_parser.add_argument("--interpreter", type=Path, required=True,
                                help="the interpreter's stream directory, e.g. outputs/stage2/<llm>/<split>")
    args = parser.parse_args(argv)
    try:
        provenance = compose(split=args.split, router_root=args.router_root, interpreter_dir=args.interpreter,
                             root=REPO_ROOT)
    except (ComposeError, FreezeError) as error:
        print(f"Compose stopped: {error}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as error:
        print(f"Compose failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    counts = provenance["counts"]
    print(f"Composed {len(counts)} hybrid runs on {args.split}: "
          f"{sum(c['rows'] for c in counts.values())} rows, {sum(c['invalid'] for c in counts.values())} invalid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
