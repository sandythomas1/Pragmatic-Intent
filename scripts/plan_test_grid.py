"""Plan the WP-09 Stage 1 test grid against the freeze, before any GPU time is spent.

Called by ``scripts/stage1_test_grid.sh`` with project Python and no optional dependencies:

    python -m scripts.plan_test_grid --systems "tfidf-utterance deberta-v3-large"

It verifies the freeze once, then for each requested system takes the frozen recipe path and
seeds from the freeze and the training conditions from the system's design (spec 008 FR17).
Every planned run is checked against the frozen grid exactly as the trainer will check it, so a
refusal costs seconds here instead of a model load on the GPU.

A completed test run is skipped only if its artifacts verify (``grid_check.verify_completed``) and
it was written under the current freeze content. Anything else that is complete under the output
root refuses the whole plan, so one grid never mixes freezes. A run directory without
``metrics.json`` is an interrupted run: it is planned again, and the encoder resumes it from its
checkpoint, whose fingerprint refuses any other run.

Runs are ordered system by system, then seed by seed, then by condition (none, one, full), so a
session that stops early leaves whole seeds rather than every seed missing ``full``.

Output: one tab-separated row per run: system, trainer module, config path, condition, seed,
``run`` or ``skip``. Nothing here reads or prints test examples.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from src.data.freeze import (FreezeError, FreezeRecord, RunIdentity, check_run, conditions_for, load_inputs,
                             recipe_sha256, require_freeze)
from src.stage1 import provenance
from src.stage1.config import RunConfig, load_config
from src.stage1.grid_check import verify_completed

OUT_ROOT = Path("outputs/stage1-test")
TRAINERS = {"tfidf": "src.stage1.tfidf", "encoder": "src.stage1.encoder"}
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


class PlanError(ValueError):
    """The plan is refused; the message names a system, run directory or freeze code, never data."""


@dataclass(frozen=True)
class PlannedRun:
    system: str
    module: str
    config: Path
    condition: str
    seed: int
    status: str  # "run" or "skip"

    def row(self) -> str:
        return "\t".join((self.system, self.module, self.config.as_posix(), self.condition, str(self.seed),
                          self.status))


def load_frozen(root: Path) -> tuple[FreezeRecord, dict[str, Path]]:
    """Verify the freeze and return it with each Stage 1 system's frozen recipe path."""
    try:
        frozen = require_freeze(root)
        inputs = load_inputs(Path(frozen.record["inputs_path"]), root=root)
    except FreezeError as error:
        raise PlanError(f"freeze refused ({error.code}): {error}") from None
    return frozen, {name: recipe.stage1 for name, recipe in inputs.systems.items() if recipe.stage1 is not None}


def frozen_seeds(frozen: FreezeRecord, system: str) -> tuple[int, ...]:
    pin = frozen.pins.get(f"recipe.{system}.seeds")
    if not pin:
        raise PlanError(f"{system!r} has no frozen seeds")
    return tuple(int(seed) for seed in pin.split(","))


def resolve_test_config(path: Path, condition: str, *, micro_batch_size: int | None = None,
                gradient_checkpointing: bool | None = None) -> RunConfig:
    """The recipe as the trainer resolves it for a test run; memory knobs apply to encoders only."""
    overrides: dict[str, dict[str, object]] = {"data": {"train_condition": condition, "eval_split": "test"}}
    config = load_config(path, overrides, allow_test=True)
    if config.kind == "encoder" and (micro_batch_size is not None or gradient_checkpointing is not None):
        overrides["encoder"] = {"micro_batch_size": micro_batch_size, "gradient_checkpointing": gradient_checkpointing}
        config = load_config(path, overrides, allow_test=True)
    return config


def run_status(output: Path, config: RunConfig, seed: int, frozen: FreezeRecord,
               hashes: dict[str, str]) -> str:
    """``hashes`` caches the data and source hashes, computed only once a completed run needs them."""
    if not (output / "metrics.json").exists():
        return "run"
    try:
        if not hashes:
            hashes.update(provenance.run_hashes(Path(config.data.items), Path(config.data.dialogues)))
        verify_completed(output, config, seed, hashes)  # bounds and shapes metrics.json before it is read here
        written_under = json.loads((output / "metrics.json").read_text(encoding="utf-8"))["run"].get(
            "freeze_content_sha256")
    except (OSError, ValueError) as exc:
        raise PlanError(f"cannot reuse {output.as_posix()}: {exc}; archive it before rerunning") from None
    if written_under != frozen.content_sha256:
        raise PlanError(f"cannot reuse {output.as_posix()}: it was written under another freeze content; "
                        "archive it before rerunning")
    return "skip"


def plan(systems: Sequence[str], frozen: FreezeRecord, recipes: Mapping[str, Path], *,
         out_root: Path = OUT_ROOT, micro_batch_size: int | None = None,
         gradient_checkpointing: bool | None = None) -> list[PlannedRun]:
    """Plan every requested system's frozen test grid; one problem refuses the whole plan."""
    if not systems or len(set(systems)) != len(systems):
        raise PlanError("systems must be nonempty and distinct")
    panel = {system.name: system for system in frozen.config.panel}
    rows: list[PlannedRun] = []
    hashes: dict[str, str] = {}
    for name in systems:
        if name not in recipes or name not in panel:
            raise PlanError(f"{name[:64]!r} is not a frozen Stage 1 system")
        if not SAFE_NAME.fullmatch(name):
            raise PlanError(f"{name[:64]!r} is not a safe directory name")
        path = recipes[name]
        for seed in frozen_seeds(frozen, name):
            for condition in conditions_for(panel[name]):
                config = resolve_test_config(path, condition, micro_batch_size=micro_batch_size,
                                     gradient_checkpointing=gradient_checkpointing)
                if config.name != name or config.kind not in TRAINERS:
                    raise PlanError(f"{path.as_posix()} does not define the {name!r} Stage 1 run")
                try:
                    check_run(frozen, RunIdentity(name, recipe_sha256(config.to_dict()), seed, condition))
                except FreezeError as error:
                    raise PlanError(f"{name} train-{condition} seed {seed} refused ({error.code}): {error}") from None
                output = out_root / name / f"train-{condition}" / f"seed{seed}"
                rows.append(PlannedRun(name, TRAINERS[config.kind], path, condition, seed,
                                       run_status(output, config, seed, frozen, hashes)))
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--systems", required=True, help="space-separated panel system names, in run order")
    parser.add_argument("--micro-batch-size", type=int)
    parser.add_argument("--gradient-checkpointing", action="store_const", const=True)
    args = parser.parse_args(argv)
    try:
        frozen, recipes = load_frozen(Path("."))  # the launcher runs from the repository root
        rows = plan(args.systems.split(), frozen, recipes, out_root=OUT_ROOT, micro_batch_size=args.micro_batch_size,
                    gradient_checkpointing=args.gradient_checkpointing)
    except (OSError, ValueError) as exc:
        print(f"test grid refused: {exc}", file=sys.stderr)
        return 1
    for run in rows:
        print(run.row())
    return 0


if __name__ == "__main__":
    sys.exit(main())
