"""Validate every completed encoder run before a dev grid spends any GPU time.

Called by ``scripts/stage1_grid.sh`` with project Python and no optional dependencies.
Prints a tab-separated plan only after all requested runs have passed validation.
Older results without the new provenance are preserved, but cannot be skipped automatically.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from src.stage1 import provenance
from src.stage1.config import RunConfig, load_config


def _read_object(path: Path, limit: int) -> dict[str, Any]:
    if path.stat().st_size > limit:
        raise ValueError(f"completed output too large: {path.name}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"completed output is not an object: {path.name}")
    return value


def verify_completed(output: Path, config: RunConfig, seed: int, hashes: dict[str, str]) -> None:
    """Refuse incomplete, stale or edited artifacts without changing any output bytes."""
    resolved = _read_object(output / "config.resolved.json", 1 << 20)
    metrics = _read_object(output / "metrics.json", 16 << 20)
    if resolved != json.loads(json.dumps(config.to_dict())):
        raise ValueError("resolved recipe differs from the requested run")
    run = metrics.get("run")
    if not isinstance(run, dict):
        raise ValueError("completed output lacks run metadata")
    expected = {"run": config.name, "kind": config.kind, "seed": seed, "smoke": False,
                "train_split": config.data.train_split, "eval_split": config.data.eval_split,
                "train_condition": config.data.train_condition, "policy": config.data.policy,
                "config_sha256": config.sha256(), **hashes}
    mismatched = [key for key, value in expected.items()
                  if type(run.get(key)) is not type(value) or run[key] != value]
    if mismatched:
        raise ValueError(f"missing or mismatched run provenance: {', '.join(sorted(mismatched))}")
    predictions = output / "predictions.jsonl"
    if predictions.stat().st_size == 0 or run.get("predictions_sha256") != provenance.sha256(predictions):
        raise ValueError("predictions are empty, edited or missing their recorded hash")


def plan(config_path: Path, seeds: Sequence[int], conditions: Sequence[str], *,
         micro_batch_size: int | None = None, gradient_checkpointing: bool | None = None,
         out_root: Path = Path("outputs/stage1")) -> list[tuple[str, str, int, str]]:
    """Plan the whole dev grid; one bad completed run rejects the entire plan."""
    if not seeds or any(type(seed) is not int or seed < 0 for seed in seeds) or len(set(seeds)) != len(seeds):
        raise ValueError("seeds must be distinct non-negative integers")
    if not conditions or len(set(conditions)) != len(conditions):
        raise ValueError("training conditions must be nonempty and distinct")
    rows = []
    hashes = None
    for condition in conditions:
        config = load_config(config_path, {"data": {"train_condition": condition},
                             "encoder": {"micro_batch_size": micro_batch_size,
                                         "gradient_checkpointing": gradient_checkpointing}})
        if config.kind != "encoder" or config.encoder is None:
            raise ValueError("the grid requires an encoder config")
        if config.data.eval_split != "dev" or config.data.train_split != "train":
            raise ValueError("the grid requires train -> dev; test runs use the freeze procedure")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", config.name):
            raise ValueError("run name must be a single safe directory name")
        for seed in seeds:
            output = out_root / config.name / f"train-{condition}" / f"seed{seed}"
            status = "run"
            if (output / "metrics.json").exists():
                try:
                    if hashes is None:
                        hashes = provenance.run_hashes(Path(config.data.items), Path(config.data.dialogues))
                    verify_completed(output, config, seed, hashes)
                except (OSError, ValueError) as exc:
                    raise ValueError(f"cannot reuse {output}: {exc}; preserve it and use a separate checkout "
                                     "or archive its outputs before rerunning") from None
                status = "skip"
            rows.append((config.name, condition, seed, status))
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--seeds", required=True, help="space-separated seeds")
    parser.add_argument("--conditions", required=True, help="space-separated training conditions")
    parser.add_argument("--micro-batch-size", type=int)
    parser.add_argument("--gradient-checkpointing", action="store_const", const=True)
    args = parser.parse_args(argv)
    try:
        rows = plan(args.config, [int(value) for value in args.seeds.split()], args.conditions.split(),
                    micro_batch_size=args.micro_batch_size, gradient_checkpointing=args.gradient_checkpointing)
    except (OSError, ValueError) as exc:
        print(f"grid refused: {exc}", file=sys.stderr)
        return 1
    for row in rows:
        print("\t".join(map(str, row)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
