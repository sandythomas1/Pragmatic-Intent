"""Score level predictions or run a majority-class development pilot.

The pilot fits on all labeled dialogues except the held-out dialogue. It does
not use the utterance or context, so its predictions are identical across context
conditions. Calibration scores are diagnostics, not final benchmark results.
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from src.annotation.levels import normalize_label
from src.data.direct_dataset import CONDITIONS
from src.evaluation.metrics import bootstrap_accuracy_ci, classification_metrics

LEVELS = ("L0", "L1", "L2", "L3", "INF", "NR")


@dataclass(frozen=True)
class Example:
    item_id: str
    dialogue_id: str
    label: str
    variant: str
    split: str
    intent: str  # domain proxy, not an adjudicated Stage 2 intent


def load_examples(
    annotations: Path, items: Path, annotator: str, split: str
) -> tuple[list[Example], dict[str, int]]:
    """Join labels to source metadata; reject duplicates and split mismatches."""
    with annotations.open(encoding="utf-8-sig", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["annotator"] == annotator]
    if not rows:
        raise ValueError(f"no labels for annotator {annotator}")
    if len({row["item_id"] for row in rows}) != len(rows):
        raise ValueError("duplicate annotation item IDs")
    wanted = {(row["dialogue_id"], int(row["turn_index"])) for row in rows}
    metadata: dict[tuple[str, int], dict[str, Any]] = {}
    with items.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            key = (record["dialogue_id"], record["turn_index"])
            if key in wanted:
                if key in metadata:
                    raise ValueError(f"duplicate source turn {key}")
                metadata[key] = record
    examples: list[Example] = []
    excluded: collections.Counter[str] = collections.Counter()
    seen_variants: set[tuple[str, int, str]] = set()
    for row in rows:
        key = (row["dialogue_id"], int(row["turn_index"]))
        if key not in metadata:
            raise ValueError(f"no source metadata for {row['item_id']}")
        record = metadata[key]
        if record["split"] != split:
            raise ValueError(f"{row['item_id']} belongs to {record['split']}, expected {split}")
        variant = row["variant"]
        if variant not in ("target", "direct", "indirect"):
            raise ValueError(f"invalid variant for {row['item_id']}")
        variant_key = (*key, variant)
        if variant_key in seen_variants:
            raise ValueError(f"duplicate annotated turn variant {variant_key}")
        seen_variants.add(variant_key)
        label = normalize_label(row["label_final"])
        if label is None:
            raise ValueError(f"invalid final label for {row['item_id']}")
        if label == "?":
            excluded["undecidable"] += 1
            continue
        domains = sorted(record["turn_domains"])
        examples.append(Example(row["item_id"], row["dialogue_id"], label, variant,
                                split, "+".join(domains) or "(none)"))
    if not examples:
        raise ValueError("no scorable annotations")
    return sorted(examples, key=lambda e: e.item_id), dict(excluded)


def majority_predictions(examples: Sequence[Example]) -> list[dict[str, str]]:
    """Leave out entire dialogues; break majority ties by fixed LEVELS order."""
    if len({e.dialogue_id for e in examples}) < 2:
        raise ValueError("leave-one-dialogue-out requires at least two dialogues")
    choices = {}
    total = collections.Counter(e.label for e in examples)
    for dialogue in sorted({e.dialogue_id for e in examples}):
        held_out = collections.Counter(e.label for e in examples if e.dialogue_id == dialogue)
        training_counts = total - held_out
        choices[dialogue] = max(LEVELS, key=lambda label: training_counts[label])
    return [{"item_id": e.item_id, "condition": condition,
             "prediction": choices[e.dialogue_id]}
            for condition in CONDITIONS for e in examples]


def _metrics(pairs: Sequence[tuple[Example, str]]) -> dict[str, Any]:
    return classification_metrics([(e.label, prediction) for e, prediction in pairs], LEVELS)


def _accuracy_ci(pairs: Sequence[tuple[Example, str]], samples: int, seed: int) -> list[float]:
    """Percentile bootstrap of whole dialogues, preserving correlated variants."""
    return bootstrap_accuracy_ci([(e.dialogue_id, e.label == prediction) for e, prediction in pairs],
                                 samples, seed)


def build_report(
    examples: Sequence[Example], predictions: Sequence[dict[str, str]],
    bootstrap_samples: int = 1000, seed: int = 20261006,
) -> dict[str, Any]:
    """Require complete predictions for every supplied context; score each separately."""
    if not examples or bootstrap_samples < 1:
        raise ValueError("examples and positive bootstrap sample count required")
    expected = {e.item_id: e for e in examples}
    if len(expected) != len(examples):
        raise ValueError("duplicate example IDs")
    if any(e.label not in LEVELS for e in examples):
        raise ValueError("invalid gold label")
    by_condition: dict[str, dict[str, str]] = collections.defaultdict(dict)
    for row in predictions:
        item_id, condition = row["item_id"], row["condition"]
        prediction = normalize_label(row["prediction"])
        if condition not in CONDITIONS or prediction not in LEVELS:
            raise ValueError(f"invalid prediction or condition for {item_id}")
        if item_id not in expected or item_id in by_condition[condition]:
            raise ValueError(f"extra or duplicate prediction: {item_id}/{condition}")
        by_condition[condition][item_id] = prediction
    if not by_condition:
        raise ValueError("no predictions")
    report: dict[str, Any] = {"labels": list(LEVELS), "macro_f1_policy": "fixed_six_labels",
                            "n_items": len(examples),
                            "n_dialogues": len({e.dialogue_id for e in examples}),
                            "bootstrap": {"unit": "dialogue", "samples": bootstrap_samples,
                                          "seed": seed, "confidence": 0.95}, "conditions": {}}
    for condition in CONDITIONS:
        if condition not in by_condition:
            continue
        values = by_condition[condition]
        if set(values) != set(expected):
            raise ValueError(f"missing predictions under {condition}")
        pairs = [(expected[key], values[key]) for key in sorted(expected)]
        metrics = _metrics(pairs)
        metrics["accuracy_ci95"] = _accuracy_ci(pairs, bootstrap_samples, seed)
        for field in ("label", "variant", "intent"):
            slices = {}
            for value in sorted({getattr(e, field) for e in examples}):
                slices[value] = _metrics([pair for pair in pairs if getattr(pair[0], field) == value])
            metrics[{"label": "by_level", "variant": "by_variant", "intent": "by_domain"}[field]] = slices
        report["conditions"][condition] = metrics
    return report


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--items", type=Path, default=Path("data/interim/direct/items.jsonl"))
    parser.add_argument("--annotator", default="A1")
    parser.add_argument("--split", choices=("train", "dev", "test"), default="dev")
    parser.add_argument("--predictions", type=Path, help="JSONL with item_id, condition, prediction; otherwise run majority pilot")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20261006)
    args = parser.parse_args(argv)
    try:
        if args.predictions is None and args.split != "dev":
            raise ValueError("majority development pilot is restricted to dev; use separate training data for final experiments")
        examples, excluded = load_examples(args.annotations, args.items, args.annotator, args.split)
        if args.predictions:
            with args.predictions.open(encoding="utf-8") as handle:
                predictions = [json.loads(line) for line in handle if line.strip()]
        else:
            predictions = majority_predictions(examples)
        report = build_report(examples, predictions, args.bootstrap_samples, args.seed)
        git = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
        dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=False)
        report.update(status="development_pilot" if not args.predictions else "scored_predictions",
                      validation="leave_one_dialogue_out" if not args.predictions else "external_predictions",
                      model="majority_class" if not args.predictions else "external",
                      split=args.split, annotator=args.annotator, excluded=excluded,
                      git_commit=git.stdout.strip() if git.returncode == 0 else None,
                      git_dirty=bool(dirty.stdout.strip()) if dirty.returncode == 0 else None,
                      python_version=sys.version.split()[0],
                      source_sha256=_sha256(Path(__file__)),
                      annotations_sha256=_sha256(args.annotations), items_sha256=_sha256(args.items))
        if args.predictions:
            report["predictions_sha256"] = _sha256(args.predictions)
        args.out_dir.mkdir(parents=True, exist_ok=True)
        # Only identifiers/labels in artifacts; never copy restricted utterance text.
        (args.out_dir / "predictions.jsonl").write_text(
            "".join(json.dumps({field: row[field] for field in ("item_id", "condition", "prediction")},
                               sort_keys=True) + "\n" for row in predictions), encoding="utf-8")
        (args.out_dir / "metrics.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Scored {len(examples)} items across {len(report['conditions'])} conditions; results in {args.out_dir}")
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"Evaluation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
