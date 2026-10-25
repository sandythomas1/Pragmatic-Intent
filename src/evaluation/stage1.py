"""Score Stage 1 (direct / indirect / no_request) predictions under each context condition.

Spec 004 sets: none / one / full score the *genuine* set (every example with prior
context); the mismatch conditions score the *mismatch* set (those with a donor). A
contrast uses one set on both sides, so differences between conditions are paired;
contrasts touching a mismatch condition also report a ``without_cue_donors`` line
that drops examples whose donor mentions a target value. Context contrasts (e.g. ``full - none``) use a
paired bootstrap over dialogues; the ``by_variant`` and ``by_rule_level`` contrasts
are descriptive proxies for the context x indirectness interaction (H2), not its test.

Option A (spec 001 v1.2) slices every condition and contrast by the ``auto-v1``
rule level of each example's own paraphrase and by the ``cat-v1`` primary category
of its turn. Both are mechanical and reported as evaluation slices only; gold
labels always come from the weak-supervision policy.

On test, scoring first requires a verifying spec 008 freeze record, then the committed split audit
(spec 006 FR15), current against ``items.jsonl``, ``dialogues.jsonl`` and the registry's
``pre_freeze`` rows. Only primary examples are scored, and every contrast gains one
``primary_minus_dup`` sensitivity line. Dev is unchanged.

Re-score a predictions file from the repository root::

    python -m src.evaluation.stage1 --predictions outputs/stage1/<run>/predictions.jsonl \\
        --out outputs/stage1/<run>/metrics.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.data.audit_fact_drift import build_vocabulary
from src.data.auto_levels import RULES_VERSION, level_item
from src.data.contexts import MISMATCH_CONDITIONS, RENDERER_VERSION, cue_flags, in_mismatch_set, render_all
from src.data.direct_dataset import CONDITIONS, Item, Turn, load_dialogues, load_items
from src.data.intent_categories import MAPPING_VERSION, primary_category
from src.evaluation.metrics import bootstrap_accuracy_ci, classification_metrics, paired_bootstrap_difference
from src.evaluation.test_audit import audit_summary_path, require_test_audit
from src.stage1.data import POLICIES, STAGE1_LABELS, Stage1Example, build_examples

CONTRASTS = (("one", "none"), ("full", "none"), ("full", "one"),
             ("full", "mismatched"), ("one", "mismatched_one"))
SLICE_VERSIONS = {"rule_level": RULES_VERSION, "category": MAPPING_VERSION}
FREEZE_ROOT = Path(".")  # the scorers run from the repository root, like their default paths
Slices = dict[str, dict[str, str]]  # slice name -> example_id -> value


def rule_slices(examples: Sequence[Stage1Example], items: Sequence[Item], *, version: str = RULES_VERSION) -> Slices:
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
        levels[e.example_id] = level_item(item, e.variant, vocab, version=version).level
        category = primary_category(item)
        if category is not None:
            categories[e.example_id] = category
    return {"rule_level": levels, "category": categories}


@dataclass(frozen=True)
class ScoringSets:
    """Which examples each condition scores (spec 004).

    Examples outside ``mismatch_ids`` have no donor and are scored under none / one / full
    only. ``cue_donor_ids`` maps each mismatch condition to the examples whose donor context
    under that condition mentions a target value; they leave the sensitivity line only.
    """

    mismatch_ids: frozenset[str]
    cue_donor_ids: dict[str, frozenset[str]] = field(default_factory=dict)


def scoring_sets(examples: Sequence[Stage1Example], items: Sequence[Item],
                 dialogues: dict[str, list[Turn]]) -> ScoringSets:
    """Mismatch membership and per-condition cue donors; pass every item (shared vocabulary)."""
    by_id = {item["item_id"]: item for item in items}
    vocab = build_vocabulary(items)
    mismatch: set[str] = set()
    cue: dict[str, set[str]] = {condition: set() for condition in MISMATCH_CONDITIONS}
    for e in examples:
        item = by_id[e.item_id]
        if not in_mismatch_set(item):
            continue
        mismatch.add(e.example_id)
        flags = cue_flags(item, render_all(item, e.text, dialogues), dialogues, vocab)
        if flags.donor_cue:
            cue["mismatched"].add(e.example_id)
        if flags.donor_cue_one:
            cue["mismatched_one"].add(e.example_id)
    return ScoringSets(frozenset(mismatch), {condition: frozenset(ids) for condition, ids in cue.items()})


def set_name(*conditions: str) -> str:
    return "mismatch" if any(condition in MISMATCH_CONDITIONS for condition in conditions) else "genuine"


def check_predictions(
    members: dict[str, list[Stage1Example]], predictions: Sequence[dict[str, Any]]
) -> dict[str, dict[str, str]]:
    """Exactly one valid prediction per member example under each predicted condition.

    ``members`` maps ``genuine`` and ``mismatch`` to their examples. Public for the spec 007
    analysis, which re-validates saved predictions with the scorer's own rules.
    """
    expected = {name: {e.example_id for e in examples} for name, examples in members.items()}
    by_condition: dict[str, dict[str, str]] = {}
    for row in predictions:
        example_id, condition, prediction = row["example_id"], row["condition"], row["prediction"]
        if condition not in CONDITIONS or prediction not in STAGE1_LABELS:
            raise ValueError(f"invalid prediction or condition for {example_id}")
        scored = by_condition.setdefault(condition, {})
        if example_id not in expected[set_name(condition)] or example_id in scored:
            raise ValueError(f"extra or duplicate prediction: {example_id}/{condition}")
        scored[example_id] = prediction
    if not by_condition:
        raise ValueError("no predictions")
    for condition, scored in by_condition.items():
        if len(scored) != len(expected[set_name(condition)]):
            raise ValueError(f"missing predictions under {condition}")
    return by_condition


_check_predictions = check_predictions  # the historical private name


def _slices(examples: Sequence[Stage1Example], predicted: dict[str, str], key) -> dict[str, Any]:
    groups: dict[str, list[tuple[str, str]]] = {}
    for e in examples:
        value = key(e)
        if value is not None:
            groups.setdefault(value, []).append((e.label, predicted[e.example_id]))
    return {value: classification_metrics(groups[value], STAGE1_LABELS) for value in sorted(groups)}


def build_report(
    examples: Sequence[Stage1Example], predictions: Sequence[dict[str, Any]],
    slices: Slices | None = None, sets: ScoringSets | None = None,
    bootstrap_samples: int = 1000, seed: int = 20261006,
    *, rules_version: str = RULES_VERSION, dup_ids: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Metrics per condition plus paired context contrasts; rejects partial prediction sets.

    ``examples`` is the genuine set. ``sets`` (from ``scoring_sets``) says which of them the
    mismatch conditions score; ``None`` means all of them, with no cue donors. ``slices``
    (from ``rule_slices``) add a ``by_<name>`` breakdown to every condition and contrast;
    examples missing from a slice are left out of that breakdown only. ``dup_ids`` (test only,
    from the spec 006 audit) adds a ``primary_minus_dup`` line to every contrast, never crossed
    with ``without_cue_donors``.
    """
    if not examples or bootstrap_samples < 1:
        raise ValueError("examples and a positive bootstrap sample count are required")
    if rules_version not in {"auto-v1", "auto-v2"}:
        raise ValueError("unknown rules version")
    ids = {e.example_id for e in examples}
    sets = sets or ScoringSets(frozenset(ids))
    if not sets.mismatch_ids <= ids or set(sets.cue_donor_ids) - set(MISMATCH_CONDITIONS):
        raise ValueError("scoring sets name unknown examples or conditions")
    members = {"genuine": list(examples), "mismatch": [e for e in examples if e.example_id in sets.mismatch_ids]}
    by_condition = check_predictions(members, predictions)
    slices = slices or {}
    if set(slices) - set(SLICE_VERSIONS):
        raise ValueError(f"unknown slices: {sorted(set(slices) - set(SLICE_VERSIONS))}")
    groupings = {"variant": lambda e: e.variant,
                 **{name: (lambda e, values=values: values.get(e.example_id)) for name, values in slices.items()}}

    report: dict[str, Any] = {
        "labels": list(STAGE1_LABELS), "n_examples": len(examples),
        "n_dialogues": len({e.dialogue_id for e in examples}),
        "renderer_version": RENDERER_VERSION,
        "sets": {"genuine": len(members["genuine"]), "mismatch": len(members["mismatch"]),
                 "excluded_from_mismatch": {"no_donor": len(members["genuine"]) - len(members["mismatch"])},
                 "cue_donors": {condition: len(sets.cue_donor_ids.get(condition, frozenset()) & sets.mismatch_ids)
                                for condition in MISMATCH_CONDITIONS}},
        "slices": {name: {"version": rules_version if name == "rule_level" else SLICE_VERSIONS[name],
                          "n": len(values)} for name, values in slices.items()},
        "rule_level_status": "provisional_fresh_L3_check_pending" if rules_version == "auto-v2" else "historical_auto_v1",
        "bootstrap": {"unit": "dialogue", "samples": bootstrap_samples, "seed": seed, "confidence": 0.95},
        "conditions": {}, "contrasts": {},
    }
    if rules_version == "auto-v2":
        from src.data.auto_levels_v2 import rules_sha256
        report["rules_sha256"] = rules_sha256()
    for condition in CONDITIONS:
        if condition not in by_condition:
            continue
        predicted, scored = by_condition[condition], members[set_name(condition)]
        metrics = classification_metrics([(e.label, predicted[e.example_id]) for e in scored], STAGE1_LABELS)
        metrics["set"] = set_name(condition)
        metrics["accuracy_ci95"] = bootstrap_accuracy_ci(
            [(e.dialogue_id, e.label == predicted[e.example_id]) for e in scored], bootstrap_samples, seed)
        metrics["by_variant"] = _slices(scored, predicted, lambda e: e.variant)
        metrics["by_gold"] = _slices(scored, predicted, lambda e: e.label)
        metrics["by_domain"] = _slices(scored, predicted, lambda e: e.domain)
        for name in slices:
            metrics[f"by_{name}"] = _slices(scored, predicted, groupings[name])
        report["conditions"][condition] = metrics
    for a, b in CONTRASTS:
        if a not in by_condition or b not in by_condition:
            continue

        def paired(subset: Sequence[Stage1Example]) -> dict[str, Any]:
            return paired_bootstrap_difference(
                [(e.dialogue_id, e.label == by_condition[a][e.example_id],
                  e.label == by_condition[b][e.example_id]) for e in subset], bootstrap_samples, seed)

        name = set_name(a, b)
        scored = members[name]
        contrast = {**paired(scored), "set": name}
        for grouping, key in groupings.items():
            values = sorted({key(e) for e in scored} - {None})
            contrast[f"by_{grouping}"] = {value: paired([e for e in scored if key(e) == value]) for value in values}
        if name == "mismatch":
            flagged = frozenset().union(*(sets.cue_donor_ids.get(c, frozenset()) for c in (a, b)))
            kept = [e for e in scored if e.example_id not in flagged]
            contrast["without_cue_donors"] = (paired(kept) if kept
                                              else {"n": 0, "difference": None, "ci95": None})
        if dup_ids is not None:
            kept = [e for e in scored if e.example_id not in dup_ids]
            contrast["primary_minus_dup"] = (paired(kept) if kept
                                             else {"n": 0, "difference": None, "ci95": None})
        report["contrasts"][f"{a}-{b}"] = contrast
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--predictions", type=Path, required=True,
                        help="JSONL with example_id, condition, prediction")
    parser.add_argument("--out", type=Path, required=True, help="metrics JSON to write")
    parser.add_argument("--items", type=Path, default=Path("data/interim/direct/items.jsonl"))
    parser.add_argument("--dialogues", type=Path, default=Path("data/interim/direct/dialogues.jsonl"),
                        help="needed for the donor cue flags")
    parser.add_argument("--split", choices=("dev", "test"), default="dev")
    parser.add_argument("--policy", choices=POLICIES, default="direct_variants_v1")
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20261006)
    parser.add_argument("--rules-version", choices=("auto-v1", "auto-v2"), default=RULES_VERSION)
    parser.add_argument("--registry", type=Path, default=Path("data/annotations/inspected_test_dialogues.csv"),
                        help="test only: the spec 006 registry the audit is checked against")
    parser.add_argument("--audit", type=Path, default=Path("data/manifests/split_audit_test.csv"),
                        help="test only: the spec 006 audit (its _summary.json sits beside it)")
    args = parser.parse_args(argv)
    try:
        # Imported here: src.data.freeze imports the analysis config, which imports this module.
        from src.data.freeze import require_freeze

        frozen = require_freeze(FREEZE_ROOT) if args.split == "test" else None  # spec 008 FR16
        items = load_items(args.items)
        examples, excluded = build_examples(items, args.split, args.policy, require_context=True)
        with args.predictions.open(encoding="utf-8") as handle:
            predictions = [json.loads(line) for line in handle if line.strip()]
        audit = None
        if args.split == "test":  # spec 006 FR15: primary examples only, from a current audit
            audit = require_test_audit(args.items, args.dialogues, registry_path=args.registry,
                                       audit_path=args.audit, summary_path=audit_summary_path(args.audit))
            examples, predictions = audit.primary_examples(examples), audit.drop_excluded(predictions)
        report = build_report(examples, predictions, rule_slices(examples, items, version=args.rules_version),
                              scoring_sets(examples, items, load_dialogues(args.dialogues)),
                              args.bootstrap_samples, args.seed, rules_version=args.rules_version,
                              dup_ids=audit.dup_ids if audit else None)
        report.update(split=args.split, policy=args.policy, excluded=excluded)
        if audit:
            report["test_audit"] = audit.report(len(examples))
        if frozen:
            report["freeze_content_sha256"] = frozen.content_sha256
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Scored {len(examples)} examples across {len(report['conditions'])} conditions -> {args.out}")
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"Stage 1 scoring failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
