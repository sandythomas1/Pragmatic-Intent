"""Export leakage-safe inputs and score separate routed/oracle weak interpretations.

No model calls. Reports measure cat-v1/act recovery, not free-paraphrase adequacy.
On test, both commands require the current spec 006 split audit and use primary examples only.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from src.data.auto_levels import LEVELS, RULES_VERSION
from src.data.contexts import MISMATCH_CONDITIONS, RENDERER_VERSION, input_sha256, render
from src.data.direct_dataset import CONDITIONS, Item, Turn, load_dialogues, load_items
from src.data.intent_categories import CATEGORIES, MAPPING_VERSION
from src.evaluation import interpretation as ip
from src.evaluation.metrics import bootstrap_accuracy_ci, paired_bootstrap_difference
from src.evaluation.stage1 import CONTRASTS, ScoringSets, rule_slices, scoring_sets, set_name
from src.evaluation.test_audit import audit_summary_path, require_test_audit
from src.stage1.data import Stage1Example, build_examples

SCORER_VERSION = "stage2-v1"


def input_records(examples: Sequence[Stage1Example], items: Sequence[Item], dialogues: dict[str, list[Turn]],
                  conditions: Sequence[str]) -> list[dict]:
    """Export only shared-renderer inputs and IDs; reference acts never enter a record."""
    if not conditions or len(set(conditions)) != len(conditions) or set(conditions) - set(CONDITIONS):
        raise ValueError("unknown, duplicate or empty input conditions")
    by_id = {item["item_id"]: item for item in items}
    rows = []
    for example in sorted(examples, key=lambda e: e.example_id):
        for condition in conditions:
            rendered = render(by_id[example.item_id], example.text, dialogues, condition)
            if rendered is not None:
                rows.append({"example_id": example.example_id, "condition": condition,
                             "context": rendered.context, "target": rendered.target,
                             "renderer_version": RENDERER_VERSION, "input_sha256": input_sha256(rendered)})
    return rows


def _rate(outcomes: Sequence[tuple[str, bool]], samples: int, seed: int) -> dict:
    return {"n": len(outcomes), "success": sum(value for _, value in outcomes) / len(outcomes) if outcomes else None,
            "ci95": bootstrap_accuracy_ci(outcomes, samples, seed) if outcomes else None}


def _interpretation_summary(examples: Sequence[Stage1Example], gold: dict[str, ip.Reference], rows: dict,
                            samples: int, seed: int) -> dict:
    outcomes = [(e, ip.outcome(gold[e.example_id], rows[e.example_id])) for e in examples]
    counts = {name: sum(out["slots"][name] for _, out in outcomes) for name in ("correct", "gold", "predicted")}
    return {**_rate([(e.dialogue_id, out["exact"]) for e, out in outcomes], samples, seed),
            "category_accuracy": sum(out["category"] for _, out in outcomes) / len(outcomes) if outcomes else None,
            "invalid_outputs": sum(bool(rows[e.example_id].get("invalid")) for e in examples),
            "slot_recovery": {**counts,
                              "recall": counts["correct"] / counts["gold"] if counts["gold"] else None,
                              "precision": counts["correct"] / counts["predicted"] if counts["predicted"] else None,
                              "examples_with_gold_slots": sum(bool(out["slots"]["gold"]) for _, out in outcomes)}}


def build_report(examples: Sequence[Stage1Example], gold: dict[str, ip.Reference], predictions: Sequence[dict],
                 oracle_predictions: Sequence[dict], *, conditions: Sequence[str], sets: ScoringSets | None = None,
                 slices: dict[str, dict[str, str]] | None = None, rules_version: str = RULES_VERSION,
                 bootstrap_samples: int = 1000, seed: int = 20261018,
                 dup_ids: frozenset[str] | None = None) -> dict[str, Any]:
    """Complete, separate oracle/routed denominators; paired contrasts resample dialogues.

    ``dup_ids`` (test only, from the spec 006 audit) adds one ``primary_minus_dup`` line per
    contrast, never crossed with ``without_cue_donors``.
    """
    if not examples or bootstrap_samples < 1 or not conditions or len(set(conditions)) != len(conditions) or set(conditions) - set(CONDITIONS):
        raise ValueError("examples, positive bootstrap count and unique known conditions are required")
    ids = {e.example_id for e in examples}
    if len(ids) != len(examples) or set(gold) != ids:
        raise ValueError("duplicate examples or references do not match examples")
    if rules_version not in {"auto-v1", "auto-v2"}:
        raise ValueError("unknown rules version")
    sets = sets or ScoringSets(frozenset(ids))
    if not sets.mismatch_ids <= ids or set(sets.cue_donor_ids) - set(MISMATCH_CONDITIONS):
        raise ValueError("invalid scoring sets")
    if any(not values <= sets.mismatch_ids for values in sets.cue_donor_ids.values()):
        raise ValueError("cue flags name examples outside the mismatch set")
    for name, values in (slices or {}).items():
        allowed = {"rule_level": set(LEVELS), "category": set(CATEGORIES)}
        if name not in allowed or set(values) - ids or set(values.values()) - allowed[name]:
            raise ValueError("unknown slice name, ID or value")
    members = {c: [e for e in examples if c not in MISMATCH_CONDITIONS or e.example_id in sets.mismatch_ids] for c in conditions}
    oracle_members = {c: [e for e in group if e.label == "indirect" and gold[e.example_id].category is not None]
                      for c, group in members.items()}
    routed = ip.validate_predictions(predictions, {c: {e.example_id for e in group} for c, group in members.items()})
    oracle = ip.validate_predictions(oracle_predictions, {c: {e.example_id for e in group} for c, group in oracle_members.items()})
    eligible = [e for e in examples if gold[e.example_id].category is not None]
    correct: dict[str, dict[str, bool]] = {}
    report: dict[str, Any] = {"scorer_version": SCORER_VERSION, "reference_version": ip.REFERENCE_VERSION,
        "normalizer_version": ip.NORMALIZER_VERSION, "renderer_version": RENDERER_VERSION,
        "rules_version": rules_version, "category_version": MAPPING_VERSION,
        "rule_level_status": "provisional_fresh_L3_check_pending" if rules_version == "auto-v2" else "historical_auto_v1",
        "reference_kind": "weak_multiwoz_acts", "paraphrase_adequacy": "not_scored",
        "policy": "direct_variants_v1",
        "sets": {"genuine": len(examples), "mismatch": len(sets.mismatch_ids)},
        "bootstrap": {"unit": "dialogue", "samples": bootstrap_samples, "seed": seed},
        "conditions": {}, "contrasts": {}}
    if rules_version == "auto-v2":
        from src.data.auto_levels_v2 import rules_sha256
        report["rules_sha256"] = rules_sha256()
    for condition, group in members.items():
        scored = [e for e in group if gold[e.example_id].category is not None]
        interpretations = {e.example_id: ip.outcome(gold[e.example_id], routed[condition][e.example_id]) for e in scored}
        correct[condition] = {e.example_id: not routed[condition][e.example_id].get("invalid")
                              and routed[condition][e.example_id]["prediction"] == e.label
                              and interpretations[e.example_id]["exact"] for e in scored}
        requests = [e for e in group if e.label != "no_request"]
        tp = sum(not routed[condition][e.example_id].get("invalid") and routed[condition][e.example_id]["prediction"] != "no_request" for e in requests)
        fp = sum(not routed[condition][e.example_id].get("invalid") and routed[condition][e.example_id]["prediction"] != "no_request" for e in group if e.label == "no_request")
        unsupported = sum(not routed[condition][e.example_id].get("invalid") and (
            routed[condition][e.example_id]["category"] not in {None, "no_request"}
            or bool(routed[condition][e.example_id]["slots"] or routed[condition][e.example_id]["requested_slots"]))
            for e in group if e.label == "no_request")
        entry = {"n": len(group), "set": set_name(condition),
                 "invalid_outputs": sum(bool(row.get("invalid")) for row in routed[condition].values()),
                 "nonrequest_false_positives": fp, "unmapped_requests": sum(e.label != "no_request" and gold[e.example_id].category is None for e in group),
                 "nonrequest_unsupported_interpretations": unsupported,
                 "interpretation_exclusions": dict(collections.Counter(
                     gold[e.example_id].exclusion or "unmapped_category" for e in group if gold[e.example_id].category is None)),
                 "request_detection": {"n_requests": len(requests), "n_nonrequests": len(group) - len(requests),
                                       "true_positives": tp, "false_positives": fp,
                                       "recall": tp / len(requests) if requests else None,
                                       "precision": tp / (tp + fp) if tp + fp else None},
                 "routed_interpretation": _interpretation_summary([e for e in scored if e.label != "no_request"], gold, routed[condition], bootstrap_samples, seed),
                 "oracle": _interpretation_summary(oracle_members[condition], gold, oracle[condition], bootstrap_samples, seed),
                 "end_to_end": _rate([(e.dialogue_id, correct[condition][e.example_id]) for e in scored], bootstrap_samples, seed)}
        for name, values in (slices or {}).items():
            entry[f"by_{name}"] = {value: _rate([(e.dialogue_id, correct[condition][e.example_id]) for e in scored if values.get(e.example_id) == value], bootstrap_samples, seed)
                                   for value in sorted({values[e.example_id] for e in scored if e.example_id in values})}
        report["conditions"][condition] = entry
    for a, b in CONTRASTS:
        if a not in conditions or b not in conditions:
            continue
        common = [e for e in eligible if e.example_id in correct[a] and e.example_id in correct[b]]

        def paired(group):
            return paired_bootstrap_difference([(e.dialogue_id, correct[a][e.example_id], correct[b][e.example_id]) for e in group], bootstrap_samples, seed) if group else {"n": 0, "difference": None, "ci95": None}

        contrast = {"set": set_name(a, b), **paired(common)}
        if set_name(a, b) == "mismatch":
            flagged = frozenset().union(*(sets.cue_donor_ids.get(c, frozenset()) for c in (a, b)))
            contrast["without_cue_donors"] = paired([e for e in common if e.example_id not in flagged])
        if dup_ids is not None:
            contrast["primary_minus_dup"] = paired([e for e in common if e.example_id not in dup_ids])
        for name, values in (slices or {}).items():
            contrast[f"by_{name}"] = {value: paired([e for e in common if values.get(e.example_id) == value])
                                      for value in sorted({values[e.example_id] for e in common if e.example_id in values})}
        report["contrasts"][f"{a}-{b}"] = contrast
    return report


def _jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inputs", "score"))
    parser.add_argument("--items", type=Path, default=Path("data/interim/direct/items.jsonl"))
    parser.add_argument("--dialogues", type=Path, default=Path("data/interim/direct/dialogues.jsonl"))
    parser.add_argument("--split", choices=("dev", "test"), default="dev")
    parser.add_argument("--allow-test", action="store_true")
    parser.add_argument("--conditions", nargs="+", choices=CONDITIONS, default=list(CONDITIONS))
    parser.add_argument("--rules-version", choices=("auto-v1", "auto-v2"), default="auto-v1")
    parser.add_argument("--mode", choices=("routed", "oracle"), default="routed", help="inputs: which complete stream to prepare")
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--oracle-predictions", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    parser.add_argument("--registry", type=Path, default=Path("data/annotations/inspected_test_dialogues.csv"),
                        help="test only: the spec 006 registry the audit is checked against")
    parser.add_argument("--audit", type=Path, default=Path("data/manifests/split_audit_test.csv"),
                        help="test only: the spec 006 audit (its _summary.json sits beside it)")
    args = parser.parse_args(argv)
    try:
        if args.split == "test" and not args.allow_test:
            raise ValueError("test use requires --allow-test after the study freeze")
        sources = (args.items, args.dialogues, args.predictions, args.oracle_predictions)
        if any(path is not None and path.resolve() == args.out.resolve() for path in sources):
            raise ValueError("output must not overwrite a source or predictions file")
        items, dialogues = load_items(args.items), load_dialogues(args.dialogues)
        examples, excluded = build_examples(items, args.split, require_context=True)
        audit = None
        if args.split == "test":  # spec 006 FR15: primary examples only, from a current audit
            audit = require_test_audit(args.items, args.dialogues, registry_path=args.registry,
                                       audit_path=args.audit, summary_path=audit_summary_path(args.audit))
            examples = audit.primary_examples(examples)
        if args.command == "inputs":
            ip.require_local_text_output(args.out)
            selected = examples
            if args.mode == "oracle":
                by_id = {item["item_id"]: item for item in items}
                selected = [e for e in examples if e.label == "indirect" and ip.reference(by_id[e.item_id]).category is not None]
            records = input_records(selected, items, dialogues, args.conditions)
            data = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in records)
        else:
            if args.predictions is None or args.oracle_predictions is None:
                raise ValueError("score requires routed --predictions and separate --oracle-predictions")
            by_id = {item["item_id"]: item for item in items}
            gold = {e.example_id: ip.reference(by_id[e.item_id]) for e in examples}
            slices = rule_slices(examples, items, version=args.rules_version)
            predictions, oracle_predictions = _jsonl(args.predictions), _jsonl(args.oracle_predictions)
            if audit:
                predictions, oracle_predictions = audit.drop_excluded(predictions), audit.drop_excluded(oracle_predictions)
            report = build_report(examples, gold, predictions, oracle_predictions,
                                  conditions=args.conditions, sets=scoring_sets(examples, items, dialogues),
                                  slices=slices, rules_version=args.rules_version, bootstrap_samples=args.bootstrap_samples,
                                  dup_ids=audit.dup_ids if audit else None)
            if audit:
                report["test_audit"] = audit.report(len(examples))
            report.update(split=args.split, excluded=excluded,
                          inputs={"items_sha256": hashlib.sha256(args.items.read_bytes()).hexdigest(),
                                  "dialogues_sha256": hashlib.sha256(args.dialogues.read_bytes()).hexdigest(),
                                  "predictions_sha256": hashlib.sha256(args.predictions.read_bytes()).hexdigest(),
                                  "oracle_predictions_sha256": hashlib.sha256(args.oracle_predictions.read_bytes()).hexdigest()})
            data = json.dumps(report, indent=2, sort_keys=True) + "\n"
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(data, encoding="utf-8", newline="\n")
        count = f"{len(records)} {args.mode} input records" if args.command == "inputs" else f"{len(examples)} weak examples"
        print(f"Stage 2 {args.command}: {count} -> {args.out}")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Stage 2 failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
