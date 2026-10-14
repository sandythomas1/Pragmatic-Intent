"""Score Stage 1 (direct / indirect / no_request) predictions under each context condition.

Every scored condition must cover exactly the same examples, so differences
between conditions are paired. Context contrasts (e.g. ``full - none``) use a
paired bootstrap over dialogues; the ``by_variant`` and ``by_rule_level`` contrasts
are descriptive proxies for the context x indirectness interaction (H2), not its test.

Option A (spec 001 v1.2) slices every condition and contrast by the ``auto-v1``
rule level of each example's own paraphrase and by the ``cat-v1`` primary category
of its turn. Both are mechanical and reported as evaluation slices only; gold
labels always come from the weak-supervision policy.

Re-score a predictions file from the repository root::

    python -m src.evaluation.stage1 --predictions outputs/stage1/<run>/predictions.jsonl \\
        --out outputs/stage1/<run>/metrics.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from src.data.audit_fact_drift import build_vocabulary
from src.data.auto_levels import RULES_VERSION, level_item
from src.data.direct_dataset import CONDITIONS, Item, load_items
from src.data.intent_categories import MAPPING_VERSION, primary_category
from src.evaluation.metrics import bootstrap_accuracy_ci, classification_metrics, paired_bootstrap_difference
from src.stage1.data import POLICIES, STAGE1_LABELS, Stage1Example, build_examples

CONTRASTS = (("one", "none"), ("full", "none"), ("full", "one"),
             ("full", "mismatched"), ("one", "mismatched_one"))
SLICE_VERSIONS = {"rule_level": RULES_VERSION, "category": MAPPING_VERSION}
Slices = dict[str, dict[str, str]]  # slice name -> example_id -> value


def rule_slices(examples: Sequence[Stage1Example], items: Sequence[Item]) -> Slices:
    """``auto-v1`` level of each example's paraphrase and ``cat-v1`` primary category of its turn.

    Pass every item, not just the scored split: the place/food vocabulary is built from all of
    them, as in ``python -m src.data.auto_levels``, so the levels match its outputs.
    """
    vocab = build_vocabulary(items)
    by_id = {item["item_id"]: item for item in items}
    levels: dict[str, str] = {}
    categories: dict[str, str] = {}
    for e in examples:
        item = by_id[e.item_id]
        levels[e.example_id] = level_item(item, e.variant, vocab).level
        category = primary_category(item)
        if category is not None:
            categories[e.example_id] = category
    return {"rule_level": levels, "category": categories}


def _check_predictions(
    examples: Sequence[Stage1Example], predictions: Sequence[dict[str, Any]]
) -> dict[str, dict[str, str]]:
    expected = {e.example_id for e in examples}
    by_condition: dict[str, dict[str, str]] = {}
    for row in predictions:
        example_id, condition, prediction = row["example_id"], row["condition"], row["prediction"]
        if condition not in CONDITIONS or prediction not in STAGE1_LABELS:
            raise ValueError(f"invalid prediction or condition for {example_id}")
        scored = by_condition.setdefault(condition, {})
        if example_id not in expected or example_id in scored:
            raise ValueError(f"extra or duplicate prediction: {example_id}/{condition}")
        scored[example_id] = prediction
    if not by_condition:
        raise ValueError("no predictions")
    for condition, scored in by_condition.items():
        if len(scored) != len(expected):
            raise ValueError(f"missing predictions under {condition}")
    return by_condition


def _slices(examples: Sequence[Stage1Example], predicted: dict[str, str], key) -> dict[str, Any]:
    groups: dict[str, list[tuple[str, str]]] = {}
    for e in examples:
        value = key(e)
        if value is not None:
            groups.setdefault(value, []).append((e.label, predicted[e.example_id]))
    return {value: classification_metrics(groups[value], STAGE1_LABELS) for value in sorted(groups)}


def build_report(
    examples: Sequence[Stage1Example], predictions: Sequence[dict[str, Any]],
    slices: Slices | None = None, bootstrap_samples: int = 1000, seed: int = 20261006,
) -> dict[str, Any]:
    """Metrics per condition plus paired context contrasts; rejects partial prediction sets.

    ``slices`` (from ``rule_slices``) add a ``by_<name>`` breakdown to every condition and
    contrast; examples missing from a slice are left out of that breakdown only.
    """
    if not examples or bootstrap_samples < 1:
        raise ValueError("examples and a positive bootstrap sample count are required")
    by_condition = _check_predictions(examples, predictions)
    slices = slices or {}
    if set(slices) - set(SLICE_VERSIONS):
        raise ValueError(f"unknown slices: {sorted(set(slices) - set(SLICE_VERSIONS))}")
    groupings = {"variant": lambda e: e.variant,
                 **{name: (lambda e, values=values: values.get(e.example_id)) for name, values in slices.items()}}

    report: dict[str, Any] = {
        "labels": list(STAGE1_LABELS), "n_examples": len(examples),
        "n_dialogues": len({e.dialogue_id for e in examples}),
        "slices": {name: {"version": SLICE_VERSIONS[name], "n": len(values)} for name, values in slices.items()},
        "bootstrap": {"unit": "dialogue", "samples": bootstrap_samples, "seed": seed, "confidence": 0.95},
        "conditions": {}, "contrasts": {},
    }
    for condition in CONDITIONS:
        if condition not in by_condition:
            continue
        predicted = by_condition[condition]
        metrics = classification_metrics([(e.label, predicted[e.example_id]) for e in examples], STAGE1_LABELS)
        metrics["accuracy_ci95"] = bootstrap_accuracy_ci(
            [(e.dialogue_id, e.label == predicted[e.example_id]) for e in examples], bootstrap_samples, seed)
        metrics["by_variant"] = _slices(examples, predicted, lambda e: e.variant)
        metrics["by_gold"] = _slices(examples, predicted, lambda e: e.label)
        metrics["by_domain"] = _slices(examples, predicted, lambda e: e.domain)
        for name, values in slices.items():
            metrics[f"by_{name}"] = _slices(examples, predicted, groupings[name])
        report["conditions"][condition] = metrics
    for a, b in CONTRASTS:
        if a not in by_condition or b not in by_condition:
            continue

        def paired(subset: Sequence[Stage1Example]) -> dict[str, Any]:
            return paired_bootstrap_difference(
                [(e.dialogue_id, e.label == by_condition[a][e.example_id],
                  e.label == by_condition[b][e.example_id]) for e in subset], bootstrap_samples, seed)

        contrast = paired(examples)
        for name, key in groupings.items():
            values = sorted({key(e) for e in examples} - {None})
            contrast[f"by_{name}"] = {value: paired([e for e in examples if key(e) == value]) for value in values}
        report["contrasts"][f"{a}-{b}"] = contrast
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--predictions", type=Path, required=True,
                        help="JSONL with example_id, condition, prediction")
    parser.add_argument("--out", type=Path, required=True, help="metrics JSON to write")
    parser.add_argument("--items", type=Path, default=Path("data/interim/direct/items.jsonl"))
    parser.add_argument("--split", choices=("dev", "test"), default="dev")
    parser.add_argument("--policy", choices=POLICIES, default="direct_variants_v1")
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20261006)
    args = parser.parse_args(argv)
    try:
        items = load_items(args.items)
        examples, excluded = build_examples(items, args.split, args.policy, require_comparable=True)
        with args.predictions.open(encoding="utf-8") as handle:
            predictions = [json.loads(line) for line in handle if line.strip()]
        report = build_report(examples, predictions, rule_slices(examples, items),
                              args.bootstrap_samples, args.seed)
        report.update(split=args.split, policy=args.policy, excluded=excluded)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Scored {len(examples)} examples across {len(report['conditions'])} conditions -> {args.out}")
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"Stage 1 scoring failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
