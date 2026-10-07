"""Shared plumbing for Stage 1 trainers: arguments, data preparation, outputs, result log.

A trainer fits on ``train_split`` under ``train_condition`` and predicts the
comparable ``eval_split`` examples under every ``eval_conditions`` entry. Training
a ``full``-context model and scoring it under ``mismatched`` is the
relevant-context control; training under each condition separately gives the
context ablation.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.data.direct_dataset import load_dialogues, load_items
from src.evaluation.stage1 import build_report, load_levels
from src.stage1 import provenance
from src.stage1.config import RunConfig, load_config
from src.stage1.data import STAGE1_LABELS, Stage1Example, build_examples, contexts_defined, model_inputs

logger = logging.getLogger(__name__)
Pair = tuple[str, str]  # (context text, utterance); empty context means none


@dataclass
class Prepared:
    train: list[Stage1Example]
    train_inputs: list[Pair]
    eval: list[Stage1Example]
    eval_inputs: dict[str, list[Pair]]
    counts: dict[str, Any] = field(default_factory=dict)


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--train-condition", help="override [data] train_condition")
    parser.add_argument("--machine", default="unspecified",
                        help="label recorded with results, e.g. rtx5060-wsl or lab-4090")
    parser.add_argument("--out-root", type=Path, default=Path("outputs/stage1"))
    parser.add_argument("--results", type=Path, default=Path("results/stage1.jsonl"))
    parser.add_argument("--allow-test", action="store_true", help="permit eval_split = test")
    parser.add_argument("--smoke", action="store_true",
                        help="tiny pipeline check: 1,000 train / 300 eval examples, not logged to results")


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def load(args: argparse.Namespace, overrides: dict[str, dict[str, Any]]) -> RunConfig:
    overrides.setdefault("data", {})["train_condition"] = args.train_condition
    return load_config(args.config, overrides, allow_test=args.allow_test)


def prepare(config: RunConfig, smoke: bool = False) -> Prepared:
    data = config.data
    items = load_items(Path(data.items))
    dialogues = load_dialogues(Path(data.dialogues))
    items_by_id = {item["item_id"]: item for item in items}
    train, train_excluded = build_examples(items, data.train_split, data.policy)
    kept = [e for e in train if contexts_defined(items_by_id[e.item_id])]
    train_excluded["no_mismatch_donor"] = len(train) - len(kept)
    train = kept
    evaluation, eval_excluded = build_examples(items, data.eval_split, data.policy, require_comparable=True)
    if smoke:  # strided, so every class and many dialogues survive
        train = train[:: max(1, len(train) // 1000)][:1000]
        evaluation = evaluation[:: max(1, len(evaluation) // 300)][:300]

    def inputs(examples: list[Stage1Example], condition: str) -> list[Pair]:
        pairs = model_inputs(examples, items_by_id, dialogues, condition)
        if any(pair is None for pair in pairs):
            raise ValueError(f"an example lacks {condition} context despite filtering")
        return pairs  # type: ignore[return-value]

    prepared = Prepared(
        train=train, train_inputs=inputs(train, data.train_condition), eval=evaluation,
        eval_inputs={condition: inputs(evaluation, condition) for condition in data.eval_conditions},
        counts={"train_excluded": train_excluded, "eval_excluded": eval_excluded},
    )
    if not prepared.train or not prepared.eval:
        raise ValueError("no training or evaluation examples after applying the policy")
    if {e.label for e in prepared.train} != set(STAGE1_LABELS):
        raise ValueError("training data lacks a Stage 1 class")
    logger.info("train %d examples (%s), eval %d examples x %d conditions",
                len(prepared.train), data.train_condition, len(prepared.eval), len(prepared.eval_inputs))
    return prepared


def prediction_rows(examples: Sequence[Stage1Example], condition: str,
                    probabilities: Sequence[Sequence[float]]) -> list[dict[str, Any]]:
    """Rows in STAGE1_LABELS order; ties go to the earliest label."""
    rows = []
    for example, probs in zip(examples, probabilities, strict=True):
        best = max(range(len(STAGE1_LABELS)), key=lambda index: (probs[index], -index))
        rows.append({"example_id": example.example_id, "condition": condition,
                     "prediction": STAGE1_LABELS[best],
                     "probs": {label: round(float(p), 6) for label, p in zip(STAGE1_LABELS, probs)}})
    return rows


def output_dir(args: argparse.Namespace, config: RunConfig) -> Path:
    leaf = f"seed{args.seed}" + ("-smoke" if args.smoke else "")
    return args.out_root / config.name / f"train-{config.data.train_condition}" / leaf


def finish(args: argparse.Namespace, config: RunConfig, prepared: Prepared,
           predictions: list[dict[str, Any]], model_info: dict[str, Any], started: float) -> Path:
    """Score, write outputs (IDs and labels only), and append to the results log."""
    data = config.data
    levels = load_levels([Path(path) for path in data.levels])
    report = build_report(prepared.eval, predictions, levels, config.bootstrap_samples, config.bootstrap_seed)
    run = {
        "run": config.name, "kind": config.kind, "seed": args.seed, "machine": args.machine,
        "smoke": args.smoke, "policy": data.policy, "train_split": data.train_split,
        "eval_split": data.eval_split, "train_condition": data.train_condition,
        "n_train": len(prepared.train), "n_eval": len(prepared.eval),
        "config_sha256": config.sha256(), "items_sha256": provenance.sha256(Path(data.items)),
        "duration_s": round(time.time() - started, 1), "model": model_info,
        "gpu": provenance.gpu_info(), "environment": provenance.environment(), **provenance.git_state(),
    }
    out = output_dir(args, config)
    out.mkdir(parents=True, exist_ok=True)
    (out / "config.resolved.json").write_text(json.dumps(config.to_dict(), indent=2) + "\n", encoding="utf-8")
    (out / "predictions.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in predictions), encoding="utf-8")
    (out / "metrics.json").write_text(json.dumps(
        {**report, "run": run, "counts": prepared.counts, "local": provenance.local_details()},
        indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not args.smoke:
        provenance.append_result(args.results, {
            **run, "output_dir": str(out),
            "conditions": {condition: {key: metrics[key] for key in ("n", "accuracy", "macro_f1", "accuracy_ci95")}
                           for condition, metrics in report["conditions"].items()},
            "contrasts": {name: {"difference": c["difference"], "ci95": c["ci95"],
                                 "by_variant": {v: {"difference": s["difference"], "ci95": s["ci95"]}
                                                for v, s in c["by_variant"].items()}}
                          for name, c in report["contrasts"].items()},
        })
    for condition, metrics in report["conditions"].items():
        low, high = metrics["accuracy_ci95"]
        logger.info("%-15s acc %.4f [%.4f, %.4f]  macro-F1 %.4f",
                    condition, metrics["accuracy"], low, high, metrics["macro_f1"])
    logger.info("outputs in %s%s", out, "" if args.smoke else f"; result appended to {args.results}")
    return out
