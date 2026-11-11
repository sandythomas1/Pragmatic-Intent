"""Diagnose a dev-time prompt change: which interpretations changed, and how (roadmap, spec 009).

Written for the open roadmap question: P1's selection mean fell from 0.1399 to 0.1275 after the
2026-11-05 slot-definition fix (aea7d53), although its invalid rate improved. The router is the
same in both selection runs, so every change in the hybrid score comes from the interpreter's
exactness. This script compares two interpretation runs of one variant item by item.

    python -E -s -m scripts.diagnose_prompt_change \\
        --before outputs/archive/run1-2026-11-05/llm/selection/qwen2.5-7b-instruct/p1/dev/interpretation.jsonl \\
        --after outputs/llm/selection/qwen2.5-7b-instruct/p1/dev/interpretation.jsonl \\
        --out outputs/research/p1-prompt-change.json

**Population.** The ``request_interpretation`` population of each condition: gold requests with a
mapped category (spec 007). The interpreter rows are scored alone, without the router.

**Each row gets one status.** ``exact``, ``invalid``, ``category_wrong``, ``slots_extra`` (every
gold slot plus more), ``slots_missing`` (a strict subset of gold), ``slots_value`` (the same slot
names with another value) or ``slots_mixed``.

**Output.** Aggregates only: counts, rates, status transitions, and the slot *names* (from the
recipe's slot-key list) that were predicted beyond gold. No example ID, text or slot value is
written or printed. Dev only: the test split is never read.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from src.analysis.files import AnalysisError, parse_jsonl, read_bounded
from src.analysis.outcomes import OutcomeTable, load_evaluation_set
from src.evaluation import interpretation as ip

VERSION = "prompt-change-diagnosis-v1"
SPLIT = "dev"
ENDPOINT = "request_interpretation"
RULES_VERSION = "auto-v1"
DEFAULT_CONDITIONS = ("none", "full")
STATUSES = ("exact", "invalid", "category_wrong", "slots_extra", "slots_missing", "slots_value", "slots_mixed")
TRIP_DOMAINS = frozenset({"train", "taxi"})
UNLISTED_KEY = "(unlisted)"
TOP_KEYS = 15
MAX_STREAM_BYTES = 512 << 20


def slot_sets(gold: ip.Reference, row: Mapping[str, Any]) -> tuple[set[tuple[str, str, str]], set[tuple[str, str, str]]]:
    """The predicted and required slot sets, built exactly as ``interpretation.outcome`` builds them."""
    predicted: set[tuple[str, str, str]] = set()
    if not row.get("invalid"):
        predicted = {("value", key, ip.normalize_value(key, value)) for key, value in row["slots"].items()}
        predicted |= {("request", key, "") for key in row["requested_slots"]}
    required = {("value", key, value) for key, value in gold.slots.items()}
    required |= {("request", key, "") for key in gold.requested_slots}
    return predicted, required


def status(gold: ip.Reference, row: Mapping[str, Any]) -> str:
    """One status per row; ``exact`` agrees with ``interpretation.outcome``."""
    if row.get("invalid"):
        return "invalid"
    result = ip.outcome(gold, dict(row))
    if result["exact"]:
        return "exact"
    if not result["category"]:
        return "category_wrong"
    predicted, required = slot_sets(gold, row)
    if predicted > required:
        return "slots_extra"
    if predicted < required:
        return "slots_missing"
    if {(kind, key) for kind, key, _ in predicted} == {(kind, key) for kind, key, _ in required}:
        return "slots_value"
    return "slots_mixed"


def group(gold: ip.Reference) -> str:
    """``trip`` if gold names a train or taxi slot (the slots the fix defined), else ``other``."""
    keys = {*gold.slots, *gold.requested_slots}
    return "trip" if any(key.split(".", 1)[0] in TRIP_DOMAINS for key in keys) else "other"


def extra_keys(gold: ip.Reference, row: Mapping[str, Any], allowed: frozenset[str]) -> list[str]:
    """Slot names predicted beyond gold; names outside the recipe's list are pooled."""
    predicted, required = slot_sets(gold, row)
    return [key if key in allowed else UNLISTED_KEY for _, key, _ in sorted(predicted - required)]


def _rate(hits: int, n: int) -> float | None:
    return hits / n if n else None


def compare_condition(ids: Sequence[str], gold: Mapping[str, ip.Reference], before: Mapping[str, Mapping[str, Any]],
                      after: Mapping[str, Mapping[str, Any]], allowed: frozenset[str]) -> dict[str, Any]:
    """Aggregate the paired before/after statuses of one condition's population."""
    transitions = {name: collections.Counter() for name in STATUSES}
    groups = {name: collections.Counter() for name in ("trip", "other")}
    extras = {"before": collections.Counter(), "after": collections.Counter()}
    predicted_slots = {"before": 0, "after": 0}
    for example_id in ids:
        reference = gold[example_id]
        old, new = status(reference, before[example_id]), status(reference, after[example_id])
        transitions[old][new] += 1
        counts = groups[group(reference)]
        counts["n"] += 1
        counts["exact_before"] += old == "exact"
        counts["exact_after"] += new == "exact"
        counts["lost"] += old == "exact" and new != "exact"
        counts["gained"] += old != "exact" and new == "exact"
        for label, row in (("before", before[example_id]), ("after", after[example_id])):
            extras[label].update(extra_keys(reference, row, allowed))
            predicted_slots[label] += len(slot_sets(reference, row)[0])
    n = len(ids)
    exact_before = sum(transitions["exact"].values())
    exact_after = sum(row["exact"] for row in transitions.values())
    lost = collections.Counter({new: count for new, count in transitions["exact"].items() if new != "exact"})
    gained = collections.Counter({old: row["exact"] for old, row in transitions.items() if old != "exact" and row["exact"]})
    return {
        "n": n,
        "exact_before": _rate(exact_before, n), "exact_after": _rate(exact_after, n),
        "delta": (exact_after - exact_before) / n if n else None,
        "lost": sum(lost.values()), "gained": sum(gained.values()),
        "lost_to": dict(lost.most_common()), "gained_from": dict(gained.most_common()),
        "status_before": {name: sum(transitions[name].values()) for name in STATUSES},
        "status_after": {name: sum(row[name] for row in transitions.values()) for name in STATUSES},
        "transitions": {old: dict(row) for old, row in transitions.items() if row},
        "by_group": {name: {**dict(counts), "exact_before": _rate(counts["exact_before"], counts["n"]),
                            "exact_after": _rate(counts["exact_after"], counts["n"])}
                     for name, counts in groups.items()},
        "mean_predicted_slots": {label: _rate(total, n) for label, total in predicted_slots.items()},
        "extra_slot_names": {label: [[key, count] for key, count in counter.most_common(TOP_KEYS)]
                             for label, counter in extras.items()},
        "extra_slot_total": {label: sum(counter.values()) for label, counter in extras.items()},
    }


def compare(populations: Mapping[str, Sequence[str]], gold: Mapping[str, ip.Reference],
            before: Mapping[str, Mapping[str, Mapping[str, Any]]], after: Mapping[str, Mapping[str, Mapping[str, Any]]],
            allowed: frozenset[str]) -> dict[str, Any]:
    """Per condition, then pooled: the counts that explain the change in exactness."""
    conditions = {condition: compare_condition(ids, gold, before[condition], after[condition], allowed)
                  for condition, ids in populations.items()}
    n = sum(entry["n"] for entry in conditions.values())
    lost = sum(entry["lost"] for entry in conditions.values())
    gained = sum(entry["gained"] for entry in conditions.values())
    return {"conditions": conditions,
            "pooled": {"n": n, "lost": lost, "gained": gained, "delta": (gained - lost) / n if n else None}}


# --- files ---------------------------------------------------------------------------------------

def _rows_by_condition(path: Path, expected: Mapping[str, set[str]]) -> dict[str, dict[str, dict]]:
    """Keep the compared conditions' rows; ``validate_predictions`` refuses any ID outside dev."""
    data = read_bounded(path, MAX_STREAM_BYTES)
    rows = [row for row in parse_jsonl(data, path.name) if isinstance(row, dict) and row.get("condition") in expected]
    try:
        return ip.validate_predictions(rows, expected)
    except ValueError as error:
        raise AnalysisError("not_a_dev_run", f"{path.name}: {error}") from None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def diagnose(before_path: Path, after_path: Path, items: Path, dialogues: Path, slot_keys: Path,
             conditions: Iterable[str] = DEFAULT_CONDITIONS) -> dict[str, Any]:
    """Load the dev evaluation set and both runs, then compare them."""
    evaluation = load_evaluation_set(items, dialogues, SPLIT, RULES_VERSION)
    table = OutcomeTable(evaluation, {})
    conditions = tuple(conditions)
    members = {c: {e.example_id for e in evaluation.members(c)} for c in conditions}
    populations = {c: sorted(e.example_id for e in table.population(ENDPOINT, c)) for c in conditions}
    allowed = frozenset(json.loads(slot_keys.read_text(encoding="utf-8"))["slot_keys"])
    report = compare(populations, evaluation.gold, _rows_by_condition(before_path, members),
                     _rows_by_condition(after_path, members), allowed)
    return {"version": VERSION, "split": SPLIT, "endpoint": ENDPOINT,
            "scope": "interpreter rows alone; the hybrid's router is the same in both runs",
            "inputs": {"before_sha256": _sha256(before_path), "after_sha256": _sha256(after_path),
                       "items_sha256": _sha256(items)},
            **report}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--before", type=Path, required=True, help="interpretation.jsonl of the earlier run")
    parser.add_argument("--after", type=Path, required=True, help="interpretation.jsonl of the later run")
    parser.add_argument("--out", type=Path, required=True, help="report path under outputs/")
    parser.add_argument("--items", type=Path, default=Path("data/interim/direct/items.jsonl"))
    parser.add_argument("--dialogues", type=Path, default=Path("data/interim/direct/dialogues.jsonl"))
    parser.add_argument("--slot-keys", type=Path, default=Path("configs/llm/slot_keys.json"))
    parser.add_argument("--conditions", nargs="+", default=list(DEFAULT_CONDITIONS))
    args = parser.parse_args(argv)
    try:
        ip.require_local_text_output(args.out)
        report = diagnose(args.before, args.after, args.items, args.dialogues, args.slot_keys, args.conditions)
    except (AnalysisError, ValueError, OSError, KeyError) as error:
        print(f"Diagnosis stopped: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = {c: {k: entry[k] for k in ("n", "exact_before", "exact_after", "lost", "gained", "lost_to")}
               for c, entry in report["conditions"].items()}
    print(json.dumps({"pooled": report["pooled"], "conditions": summary}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
