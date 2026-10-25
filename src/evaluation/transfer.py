"""Separate IndirectRequests detection/value recovery; no model calls or training."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from src.data import indirect_requests as ir
from src.data.freeze import require_freeze
from src.evaluation.interpretation import checked_text, require_local_text_output

SCORER_VERSION = "transfer-v1"
FREEZE_ROOT = Path(".")  # the scorers run from the repository root, like their default paths


def build_report(items: Sequence[ir.TransferItem], predictions: Sequence[dict], *, model_family: str) -> dict:
    """Request recall, oracle value recovery and routed success on all transfer items."""
    checked_text(model_family, "model_family", limit=80)
    expected = {item.example_id for item in items}
    if not items or len(expected) != len(items) or len({item.split for item in items}) != 1:
        raise ValueError("empty, duplicate or mixed-split transfer items")
    predicted: dict[str, dict] = {}
    for row in predictions:
        if not isinstance(row, dict):
            raise ValueError("transfer prediction must be an object")
        example_id = checked_text(row.get("example_id"), "example_id", limit=150)
        if example_id not in expected or example_id in predicted or row.get("condition") != "none":
            raise ValueError("foreign, duplicate or non-none transfer prediction")
        if row.get("invalid") is True:
            if set(row) != {"example_id", "condition", "invalid"}:
                raise ValueError("invalid marker carries unexpected fields")
        else:
            if set(row) != {"example_id", "condition", "request", "value"} or type(row["request"]) is not bool:
                raise ValueError("invalid transfer prediction fields or request type")
            if row["value"] is not None:
                checked_text(row["value"], "predicted candidate")
        predicted[example_id] = row
    if set(predicted) != expected:
        raise ValueError("missing transfer predictions")

    def summary(group):
        n = len(group)
        detected = recovered = success = invalid = 0
        for item in group:
            row = predicted[item.example_id]
            if row.get("invalid"):
                invalid += 1
                continue
            detected += row["request"]
            correct = item.resolve(row["value"]) == item.target
            recovered += correct
            success += correct and row["request"]
        return {"n": n, "invalid_outputs": invalid, "detected_requests": detected,
                "recovered_values": recovered, "end_to_end_successes": success,
                "request_recall": detected / n if n else None, "value_accuracy": recovered / n if n else None,
                "end_to_end": success / n if n else None}

    family = model_family.strip().casefold()
    return {"scorer_version": SCORER_VERSION, "adapter_version": ir.ADAPTER_VERSION,
            "data_kind": "llm_generated_transfer", "generator_family": "GPT-3.5/GPT-4",
            "model_family": model_family, "gpt_family": family.startswith(("gpt", "openai", "chatgpt")),
            "split": items[0].split, "condition": "none", **summary(items),
            "by_ambiguity": {name: summary([item for item in items if (item.target == ir.AMBIGUOUS) == ambiguous])
                             for name, ambiguous in (("ambiguous", True), ("unambiguous", False))},
            "limits": "all items are requests; no precision/specificity estimate; never pooled with the human-authored benchmark"}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inputs", "score"))
    parser.add_argument("--split", choices=ir.SPLITS, default="validation")
    parser.add_argument("--source-dir", type=Path, default=Path("data/raw/indirect_requests"))
    parser.add_argument("--manifest", type=Path, default=Path("data/sources.toml"))
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--model-family")
    parser.add_argument("--allow-test", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.split == "test" and not args.allow_test:
            raise ValueError("test use requires --allow-test after the study freeze")
        frozen = require_freeze(FREEZE_ROOT) if args.split == "test" else None  # spec 008 FR16
        sources = (args.source_dir / f"{args.split}.jsonl", args.manifest, args.predictions)
        if any(path is not None and path.resolve() == args.out.resolve() for path in sources):
            raise ValueError("output must not overwrite a source, manifest or predictions file")
        items = ir.load_pinned(args.source_dir, args.split, args.manifest)
        if args.command == "inputs":
            require_local_text_output(args.out)
            text = "".join(json.dumps(ir.input_record(item), ensure_ascii=False, sort_keys=True) + "\n" for item in items)
        else:
            if args.predictions is None or args.model_family is None:
                raise ValueError("score requires --predictions and explicit --model-family")
            predictions = [json.loads(line) for line in args.predictions.read_text(encoding="utf-8").splitlines() if line.strip()]
            report = build_report(items, predictions, model_family=args.model_family)
            report["source_sha256"] = hashlib.sha256((args.source_dir / f"{args.split}.jsonl").read_bytes()).hexdigest()
            report["predictions_sha256"] = hashlib.sha256(args.predictions.read_bytes()).hexdigest()
            if frozen:
                report["freeze_content_sha256"] = frozen.content_sha256
            text = json.dumps(report, indent=2, sort_keys=True) + "\n"
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8", newline="\n")
        print(f"Transfer {args.command}: {len(items)} {args.split} items -> {args.out}")
        return 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f"Transfer failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
