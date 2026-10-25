"""Per-example outcomes rebuilt from saved predictions and checked against the scorers (FR7–FR9).

Nothing here re-implements validation. Stage 1 rows go through ``stage1.check_predictions``,
and Stage 2 routed and oracle rows through ``interpretation.validate_predictions`` and
``outcome``. Each run's component counts are then compared with the scorer's ``build_report``
on the same rows, and Stage 1 runs also with the ``metrics.json`` they saved. Any difference
fails the analysis, so a wrong endpoint formula, or a predictions file swapped after scoring,
cannot pass silently.

**Endpoints and populations (FR3).** Only the combination of checked components is new:

- ``request_interpretation`` (primary): a request is detected AND exact. Scored on gold
  requests with a mapped category.
- ``type_exact``: spec 005's ``end_to_end``. Scored on its population, every example with a
  mapped gold category, non-requests included, so its totals equal the scorer's.
- ``stage1_correct``: three-way prediction equals the label. Scored on all members.
- ``request_detected``: scored on gold requests.
- ``oracle_exact``: scored on the oracle population (gold ``indirect`` with a mapped category).

An invalid output has no predicted type and is never exact, so it fails every endpoint.

Predictions are stored as tuples aligned to the evaluation set's per-condition member lists,
not as per-example dicts. A 5-seed, 3-training-condition grid then costs a few megabytes, not
hundreds. Endpoint values are computed on demand by the module-level endpoint functions.

**Lines and seeds.** ``average`` averages an endpoint over seeds within (system, line,
condition, example) before any resampling (FR9). The run that fills a condition depends on the
line (``inputs.train_condition_for``). Within a system, every training condition one line uses
must have the same seed set (FR7). Otherwise a contrast would compare different seeds.

Errors never quote an example or dialogue ID (the scorer's own messages do, so they are
replaced), because a printed test ID becomes an inspection exclusion.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.analysis.files import AnalysisError, parse_json, parse_jsonl, read_verified
from src.analysis.inputs import AnalysisInputs, Stage1Run, Stage2Run, SystemInputs
from src.data.direct_dataset import CONDITIONS, load_dialogues, load_items
from src.evaluation import interpretation as ip
from src.evaluation import stage1, stage2
from src.evaluation.stage1 import ScoringSets, Slices, rule_slices, scoring_sets, set_name
from src.evaluation.test_audit import SplitAudit
from src.stage1.data import STAGE1_LABELS, Stage1Example, build_examples

NO_REQUEST = "no_request"
RATE_TOLERANCE = 1e-12


# Endpoint formulas (spec FR3). Module-level so a test can corrupt one and see the check fail.
def stage1_correct(label: str, prediction: str | None) -> bool:
    return prediction is not None and prediction == label


def request_detected(prediction: str | None) -> bool:
    return prediction is not None and prediction != NO_REQUEST


def request_interpretation(prediction: str | None, exact: bool) -> bool:
    """The primary endpoint (spec 001 §5): a request is detected AND its interpretation is exact."""
    return request_detected(prediction) and exact


def type_exact(label: str, prediction: str | None, exact: bool) -> bool:
    """Spec 005's ``end_to_end``: the direct/indirect type matches the variant label AND exact."""
    return stage1_correct(label, prediction) and exact


STAGE1_ENDPOINTS = ("stage1_correct", "request_detected")
STAGE2_ENDPOINTS = ("request_interpretation", "type_exact", "oracle_exact")


@dataclass(frozen=True)
class EvaluationSet:
    """The scored examples of one split, with the spec 004 sets and the option-A slices.

    ``examples`` is the genuine set (on test, the spec 006 primary examples only).
    ``excluded_ids`` are audit-excluded test examples whose predictions are ignored, and
    ``dup_ids`` the primary examples flagged ``dup_exact`` (test only).
    """

    split: str
    examples: tuple[Stage1Example, ...]
    sets: ScoringSets
    slices: Slices
    rules_version: str
    gold: Mapping[str, ip.Reference] = field(default_factory=dict)
    excluded_ids: frozenset[str] = frozenset()
    dup_ids: frozenset[str] | None = None

    def __post_init__(self) -> None:
        ids = [e.example_id for e in self.examples]
        if not ids or len(set(ids)) != len(ids):
            raise AnalysisError("bad_evaluation_set", "the evaluation set is empty or repeats an example")
        if not self.sets.mismatch_ids <= set(ids):
            raise AnalysisError("bad_evaluation_set", "the mismatch set names examples outside the genuine set")
        if self.gold and set(self.gold) != set(ids):
            raise AnalysisError("bad_evaluation_set", "gold references do not match the examples")
        members = {"genuine": self.examples,
                   "mismatch": tuple(e for e in self.examples if e.example_id in self.sets.mismatch_ids)}
        object.__setattr__(self, "_members", members)

    def members(self, condition: str) -> tuple[Stage1Example, ...]:
        """Examples scored under ``condition``: the genuine set, or its mismatch subset."""
        return self._members[set_name(condition)]  # type: ignore[attr-defined]

    @property
    def member_lists(self) -> dict[str, list[Stage1Example]]:
        return {name: list(examples) for name, examples in self._members.items()}  # type: ignore[attr-defined]

    def oracle_members(self, condition: str) -> tuple[Stage1Example, ...]:
        """Spec 005's oracle population: gold ``indirect`` variants with a mapped category."""
        return tuple(e for e in self.members(condition) if e.label == "indirect" and self.mapped(e))

    def mapped(self, example: Stage1Example) -> bool:
        if not self.gold:
            raise AnalysisError("no_gold", "Stage 2 outcomes need the gold act references")
        return self.gold[example.example_id].category is not None


def load_evaluation_set(items_path: Path, dialogues_path: Path, split: str, rules_version: str,
                        audit: SplitAudit | None = None) -> EvaluationSet:
    """The set the scorers score: genuine examples, primary-only on test (needs the audit)."""
    if split == "test" and audit is None:
        raise AnalysisError("audit_required", "a test evaluation set needs the current spec 006 audit")
    items = load_items(items_path)
    examples, _ = build_examples(items, split, require_context=True)
    if audit is not None:
        examples = audit.primary_examples(examples)
    by_id = {item["item_id"]: item for item in items}
    return EvaluationSet(
        split=split, examples=tuple(examples),
        sets=scoring_sets(examples, items, load_dialogues(dialogues_path)),
        slices=rule_slices(examples, items, version=rules_version), rules_version=rules_version,
        gold={e.example_id: ip.reference(by_id[e.item_id]) for e in examples},
        excluded_ids=frozenset(audit.excluded) if audit else frozenset(),
        dup_ids=audit.dup_ids if audit else None)


@dataclass(frozen=True)
class RunKey:
    system: str
    source: str  # "stage1" or "stage2": which stream the outcomes came from
    train_condition: str
    seed: int


class OutcomeTable:
    """Validated per-condition predictions for every run, and seed-averaged endpoint values."""

    def __init__(self, evaluation: EvaluationSet, systems: Mapping[str, SystemInputs]) -> None:
        self.evaluation = evaluation
        self.systems = dict(systems)
        # Per run and condition, records aligned to evaluation.members(condition): a Stage 1
        # prediction, or a Stage 2 (routed prediction or None if invalid, routed exact) pair.
        self._records: dict[RunKey, dict[str, tuple[Any, ...]]] = {}
        # Stage 2 only: oracle exactness aligned to evaluation.oracle_members(condition).
        self._oracle: dict[RunKey, dict[str, tuple[bool, ...]]] = {}

    @property
    def not_run(self) -> list[str]:
        return [name for name, inputs in self.systems.items() if inputs.status == "not_run"]

    def add_run(self, key: RunKey, records: dict[str, tuple[Any, ...]],
                oracle: dict[str, tuple[bool, ...]] | None = None) -> None:
        self._records[key] = records
        if oracle is not None:
            self._oracle[key] = oracle

    def conditions(self, key: RunKey) -> frozenset[str]:
        return frozenset(self._records[key])

    def seeds(self, system: str, source: str, train_condition: str) -> tuple[int, ...]:
        return tuple(sorted(k.seed for k in self._records if (k.system, k.source, k.train_condition)
                            == (system, source, train_condition)))

    def population(self, endpoint: str, condition: str) -> tuple[Stage1Example, ...]:
        """The examples an endpoint is scored on (FR3); every system shares it per condition."""
        members = self.evaluation.members(condition)
        if endpoint == "stage1_correct":
            return members
        if endpoint == "request_detected":
            return tuple(e for e in members if e.label != NO_REQUEST)
        if endpoint == "request_interpretation":
            return tuple(e for e in members if e.label != NO_REQUEST and self.evaluation.mapped(e))
        if endpoint == "type_exact":  # spec 005's end_to_end population: mapped gold, non-requests included
            return tuple(e for e in members if self.evaluation.mapped(e))
        if endpoint == "oracle_exact":
            return self.evaluation.oracle_members(condition)
        raise AnalysisError("unknown_endpoint", f"unknown endpoint {endpoint[:40]!r}")

    def seed_values(self, system: str, line: str, condition: str, endpoint: str) -> dict[int, dict[str, float]]:
        """Per seed, the endpoint value of every population example under ``condition`` on ``line``."""
        inputs = self.systems[system]
        if inputs.status == "not_run":
            raise AnalysisError("not_run", f"{system} has no outputs")
        train = inputs.train_condition(line, condition)
        source = self.source(system, endpoint)
        population = self.population(endpoint, condition)
        aligned_to = (self.evaluation.oracle_members(condition) if endpoint == "oracle_exact"
                      else self.evaluation.members(condition))
        positions = {e.example_id: i for i, e in enumerate(aligned_to)}
        out = {}
        for seed in self.seeds(system, source, train):
            key = RunKey(system, source, train, seed)
            stored = (self._oracle if endpoint == "oracle_exact" else self._records)[key].get(condition)
            if stored is None:
                raise AnalysisError("missing_condition", f"{system} train-{train} seed {seed} lacks {condition}")
            out[seed] = {e.example_id: float(_endpoint_value(endpoint, e, stored[positions[e.example_id]]))
                         for e in population}
        if not out:
            raise AnalysisError("missing_runs", f"{system} has no {source} runs trained on {train}")
        return out

    def average(self, system: str, line: str, condition: str, endpoint: str) -> dict[str, float]:
        """Seed-averaged value in [0, 1] per example (FR9); seeds never count as extra items."""
        per_seed = self.seed_values(system, line, condition, endpoint)
        return {example_id: sum(values[example_id] for values in per_seed.values()) / len(per_seed)
                for example_id in next(iter(per_seed.values()))}

    def seed_rates(self, system: str, line: str, condition: str, endpoint: str) -> dict[int, float]:
        return {seed: sum(values.values()) / len(values)
                for seed, values in self.seed_values(system, line, condition, endpoint).items() if values}

    def seed_contrasts(self, system: str, line: str, a: str, b: str, endpoint: str) -> dict[int, float]:
        """Per seed, the a − b rate on the examples both conditions score (seed s paired with s)."""
        first = self.seed_values(system, line, a, endpoint)
        second = self.seed_values(system, line, b, endpoint)
        if set(first) != set(second):
            raise AnalysisError("seed_sets_differ", f"{system} {line}: {a} and {b} have different seed sets")
        out = {}
        for seed in sorted(first):
            common = [i for i in first[seed] if i in second[seed]]
            if common:
                out[seed] = sum(first[seed][i] - second[seed][i] for i in common) / len(common)
        return out

    def source(self, system: str, endpoint: str) -> str:
        """Detection endpoints come from a system's Stage 1 runs if it has them, else its routed file."""
        streams = self.systems[system].system.streams
        if endpoint in STAGE1_ENDPOINTS and "stage1" in streams:
            return "stage1"
        if "routed" not in streams:
            raise AnalysisError("missing_streams", f"{system} has no Stage 2 output for {endpoint}")
        return "stage2"


def seed_variation(estimates: Mapping[int, float]) -> dict[str, Any]:
    """Per-seed estimates and their mean, SD, min and max, reported beside every headline (FR9)."""
    if not estimates:
        raise AnalysisError("no_seeds", "no per-seed estimates to summarise")
    values = [estimates[seed] for seed in sorted(estimates)]
    return {"n_seeds": len(values), "per_seed": {str(seed): estimates[seed] for seed in sorted(estimates)},
            "mean": statistics.fmean(values), "sd": statistics.stdev(values) if len(values) > 1 else None,
            "min": min(values), "max": max(values)}


def build_outcomes(evaluation: EvaluationSet, inputs: AnalysisInputs) -> OutcomeTable:
    """Validate and check every run named by ``inputs``; fail on the first disagreement."""
    if inputs.split != evaluation.split:
        raise AnalysisError("split_mismatch", "the inputs and the evaluation set are for different splits")
    table = OutcomeTable(evaluation, inputs.systems)
    for name, system_inputs in inputs.systems.items():
        for run in system_inputs.stage1:
            table.add_run(RunKey(name, "stage1", run.train_condition, run.seed),
                          _stage1_run(evaluation, run, f"{name} train-{run.train_condition} seed {run.seed}"))
        for run in system_inputs.stage2:
            table.add_run(RunKey(name, "stage2", run.train_condition, run.seed),
                          *_stage2_run(evaluation, run, f"{name} train-{run.train_condition} seed {run.seed}"))
        for source in ("stage1", "stage2"):
            _check_coverage(table, system_inputs, source)
    return table


def _stage1_run(evaluation: EvaluationSet, run: Stage1Run, label: str) -> dict[str, tuple[str, ...]]:
    rows = _drop_excluded(parse_jsonl(read_verified(run.predictions), f"{label} predictions"), evaluation)
    try:
        by_condition = stage1.check_predictions(evaluation.member_lists, rows)
    except (ValueError, KeyError, TypeError):
        # The scorer's message names the example; on test that would print a test ID.
        raise AnalysisError("invalid_predictions",
                            f"{label}: predictions are missing, extra, duplicated or invalid for the "
                            f"{evaluation.split} evaluation set") from None
    aligned = {condition: tuple(predicted[e.example_id] for e in evaluation.members(condition))
               for condition, predicted in by_condition.items()}
    report = stage1.build_report(list(evaluation.examples), rows, None, evaluation.sets, 1, 0,
                                 rules_version=evaluation.rules_version)
    saved = parse_json(read_verified(run.metrics), f"{label} metrics.json")
    _check_stage1_components(evaluation, aligned, report, saved, label)
    return aligned


def _check_stage1_components(evaluation: EvaluationSet, aligned: Mapping[str, tuple[str, ...]],
                             report: Mapping[str, Any], saved: Any, label: str) -> None:
    """Outcome counts against build_report, and build_report against the run's saved metrics."""
    saved_conditions = saved.get("conditions") if isinstance(saved, dict) else None
    if not isinstance(saved_conditions, dict) or set(saved_conditions) != set(report["conditions"]):
        raise AnalysisError("metrics_mismatch", f"{label}: metrics.json covers other conditions than its predictions")
    for condition, predicted in aligned.items():
        members = evaluation.members(condition)
        scored = report["conditions"][condition]
        confusion = scored["confusion"]
        correct = sum(stage1_correct(e.label, p) for e, p in zip(members, predicted))
        detected = [sum(request_detected(p) for e, p in zip(members, predicted) if (e.label == NO_REQUEST) == nonrequest)
                    for nonrequest in (False, True)]
        expected_detected = [sum(confusion[gold][guess] for gold in STAGE1_LABELS for guess in STAGE1_LABELS
                                 if guess != NO_REQUEST and (gold == NO_REQUEST) == nonrequest)
                             for nonrequest in (False, True)]
        if (scored["n"], correct, detected) != (len(members), sum(confusion[x][x] for x in STAGE1_LABELS),
                                                 expected_detected) \
                or not math.isclose(correct / len(members), scored["accuracy"], rel_tol=0, abs_tol=RATE_TOLERANCE):
            raise AnalysisError("component_mismatch", f"{label} {condition}: outcomes disagree with stage1.build_report")
        recorded = saved_conditions[condition]
        try:
            agrees = (recorded["n"] == scored["n"] and recorded["confusion"] == confusion
                      and math.isclose(recorded["accuracy"], scored["accuracy"], rel_tol=0, abs_tol=RATE_TOLERANCE))
        except (KeyError, TypeError):
            agrees = False
        if not agrees:
            raise AnalysisError("metrics_mismatch",
                                f"{label} {condition}: the predictions no longer match the run's metrics.json")


def _stage2_run(evaluation: EvaluationSet, run: Stage2Run,
                label: str) -> tuple[dict[str, tuple[Any, ...]], dict[str, tuple[bool, ...]]]:
    """Routed and oracle rows through ``interpretation.validate_predictions``, then the component check."""
    routed_rows = _drop_excluded(parse_jsonl(read_verified(run.routed), f"{label} routed"), evaluation)
    oracle_rows = _drop_excluded(parse_jsonl(read_verified(run.oracle), f"{label} oracle"), evaluation)
    conditions = [c for c in CONDITIONS if any(isinstance(r, dict) and r.get("condition") == c for r in routed_rows)]
    if not conditions:
        raise AnalysisError("invalid_predictions", f"{label}: the routed file predicts no known condition")
    try:  # interpretation's messages carry row numbers and counts, never IDs or text
        routed = ip.validate_predictions(
            routed_rows, {c: {e.example_id for e in evaluation.members(c)} for c in conditions})
        oracle = ip.validate_predictions(
            oracle_rows, {c: {e.example_id for e in evaluation.oracle_members(c)} for c in conditions})
    except (ValueError, TypeError, KeyError) as exc:
        raise AnalysisError("invalid_predictions", f"{label}: {str(exc)[:200] if isinstance(exc, ValueError) else 'malformed row'}") from None
    gold = evaluation.gold
    records = {c: tuple(_routed_record(gold[e.example_id], routed[c][e.example_id]) for e in evaluation.members(c))
               for c in conditions}
    oracle_exact = {c: tuple(ip.outcome(gold[e.example_id], oracle[c][e.example_id])["exact"]
                             for e in evaluation.oracle_members(c)) for c in conditions}
    report = stage2.build_report(list(evaluation.examples), dict(gold), routed_rows, oracle_rows,
                                 conditions=conditions, sets=evaluation.sets, rules_version=evaluation.rules_version,
                                 bootstrap_samples=1, seed=0)
    _check_stage2_components(evaluation, records, oracle_exact, report, label)
    return records, oracle_exact


def _routed_record(gold: ip.Reference, row: Mapping[str, Any]) -> tuple[str | None, bool]:
    """(predicted type, exact interpretation); an invalid output has no type and is never exact."""
    if row.get("invalid"):
        return None, False
    return row["prediction"], ip.outcome(gold, row)["exact"]


def _check_stage2_components(evaluation: EvaluationSet, records: Mapping[str, tuple[Any, ...]],
                             oracle_exact: Mapping[str, tuple[bool, ...]], report: Mapping[str, Any],
                             label: str) -> None:
    """Request TP/FP, oracle and routed exactness, and end_to_end, against stage2.build_report (FR8)."""
    for condition, aligned in records.items():
        scored = report["conditions"][condition]
        members = evaluation.members(condition)
        pairs = list(zip(members, aligned))
        detection = scored["request_detection"]
        mapped_requests = [(e, r) for e, r in pairs if e.label != NO_REQUEST and evaluation.mapped(e)]
        mapped = [(e, r) for e, r in pairs if evaluation.mapped(e)]
        checks = (
            detection["true_positives"] == sum(request_detected(r[0]) for e, r in pairs if e.label != NO_REQUEST),
            detection["false_positives"] == sum(request_detected(r[0]) for e, r in pairs if e.label == NO_REQUEST),
            _same_rate(sum(oracle_exact[condition]), len(oracle_exact[condition]), scored["oracle"]),
            _same_rate(sum(r[1] for _, r in mapped_requests), len(mapped_requests), scored["routed_interpretation"]),
            _same_rate(sum(type_exact(e.label, *r) for e, r in mapped), len(mapped), scored["end_to_end"]),
        )
        if not all(checks):
            raise AnalysisError("component_mismatch", f"{label} {condition}: outcomes disagree with stage2.build_report")


def _same_rate(count: int, n: int, scored: Mapping[str, Any]) -> bool:
    if scored["n"] != n:
        return False
    if n == 0:
        return scored["success"] is None
    return math.isclose(count / n, scored["success"], rel_tol=0, abs_tol=RATE_TOLERANCE)


def _check_coverage(table: OutcomeTable, inputs: SystemInputs, source: str) -> None:
    """Every condition each line needs is predicted, and a line's training conditions share seeds (FR7)."""
    runs = inputs.stage1 if source == "stage1" else inputs.stage2
    if not runs:
        return
    name = inputs.system.name
    for line in inputs.lines:
        trains = {inputs.train_condition(line, condition) for condition in CONDITIONS}
        seed_sets = {train: table.seeds(name, source, train) for train in trains}
        if len(set(seed_sets.values())) != 1:
            raise AnalysisError("seed_sets_differ",
                                f"{name} {source} {line} line: training conditions have different seed sets "
                                f"{ {train: list(seeds) for train, seeds in sorted(seed_sets.items())} }")
        for condition in CONDITIONS:
            train = inputs.train_condition(line, condition)
            for seed in seed_sets[train]:
                if condition not in table.conditions(RunKey(name, source, train, seed)):
                    raise AnalysisError("missing_condition",
                                        f"{name} {source} train-{train} seed {seed} has no {condition} predictions")


def _drop_excluded(rows: Sequence[Any], evaluation: EvaluationSet) -> list[Any]:
    """Audit-excluded test examples may be predicted; their rows are ignored, as the scorers do."""
    if not evaluation.excluded_ids:
        return list(rows)
    return [row for row in rows if not (isinstance(row, dict) and isinstance(row.get("example_id"), str)
                                        and row["example_id"] in evaluation.excluded_ids)]


def _endpoint_value(endpoint: str, example: Stage1Example, record: Any) -> bool:
    """One example's endpoint from its stored record (FR3); an invalid output is never correct."""
    if endpoint == "oracle_exact":
        return record
    prediction, exact = record if isinstance(record, tuple) else (record, False)
    if endpoint == "stage1_correct":
        return stage1_correct(example.label, prediction)
    if endpoint == "request_detected":
        return request_detected(prediction)
    if endpoint == "request_interpretation":
        return request_interpretation(prediction, exact)
    return type_exact(example.label, prediction, exact)
