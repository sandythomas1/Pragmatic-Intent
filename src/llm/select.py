"""Prompt selection (spec 009 T11, FR9, AC-009-6): which main-task prompt variant the study uses.

    python -E -s -m src.llm.select select-prompt --recipe configs/llm/qwen2.5-7b-instruct.toml \
        --split dev --router-root outputs/stage1/deberta-v3-large

**Inputs.** Every recipe variant must already have a complete dev selection run under
``none``/``full``, written by ``run --variant <v> --conditions none full`` to
``outputs/llm/selection/<system>/<variant>/dev/``.

**Scoring, per variant.**
- For each condition c in ``none``/``full`` and each seed, the variant's interpretations are
  composed with the train-c ``deberta-v3-large`` dev router through ``compose_rows``, the same
  rule as the hybrid (FR11).
- The composed rows are validated and checked against ``stage2.build_report`` by the spec 007
  analysis (``outcomes.stage2_outcomes``).
- The score is spec 007's ``request_interpretation``: a request is detected AND its
  interpretation is exact, over gold requests with a mapped category.
- The variant's score is the mean of its 2 conditions × N seeds rates.

**Decision.** The higher mean wins. If P1 is within ``TIE_MARGIN`` of the best, P1 wins, as
the simpler prompt.

**Sample.** If the variants ran on the FR9 sample (``run --sample``), every variant must record
the same sample. The sample is redrawn from the items and must match the recorded hash, and the
evaluation set is cut to it.

**Report.** ``outputs/llm/selection/<system>/report.json`` holds aggregates and hashes only, never
an example ID or text. Its presence also closes the sample fallback (``run`` refuses ``--sample``
afterwards). The recipe's ``prompts.main`` is not edited here: the report says whether it must
change, and the edit is committed like any recipe change.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.analysis.files import AnalysisError, parse_json, parse_jsonl, read_bounded
from src.analysis.outcomes import (EvaluationSet, OutcomeTable, load_evaluation_set, request_interpretation,
                                   stage2_outcomes)
from src.evaluation.stage1 import ScoringSets
from src.llm import prompt, schema, streams
from src.llm.compose import (ROUTER_NAME, ComposeError, RouterRun, compose_rows, load_router_runs,
                             router_train_condition)
from src.llm.paths import REPO_ROOT
from src.llm.recipe import SPLITS, Recipe, RecipeError, load_recipe
from src.llm.run import INVALID_RATE_LIMIT, PROVENANCE_VERSION, SELECTION_CONDITIONS, output_dir
from src.llm.sample import Sample, SampleError, draw, matches, report_path
from src.stage1.provenance import git_state, source_sha256

SELECT_VERSION = "llm-select-v1"
ENDPOINT = "request_interpretation"
TIE_MARGIN = 0.01  # FR9
TIE_PREFERENCE = "p1"  # FR9: the simpler prompt wins a tie
RULES_VERSION = "auto-v1"  # spec 001 option A; slices are not used by the selection metric
MAX_PROVENANCE_BYTES = 1 << 20
MAX_STREAM_BYTES = 512 << 20
DEV_ONLY = "prompt selection runs on dev only (FR9); the test split is never used to choose a prompt"


class SelectError(ValueError):
    """A named refusal; ``code`` is stable for tests. Nothing has been written."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code


@dataclass(frozen=True)
class VariantRun:
    """One variant's verified dev selection run under ``none``/``full``."""

    variant: str
    interpretation: tuple[Mapping[str, Any], ...]
    oracle: tuple[Mapping[str, Any], ...]
    sample: Any  # "all" or the run's recorded sample block
    invalid_calls: int
    distinct_inputs: int
    hashes: Mapping[str, str]


# --- the decision rule (FR9) ---------------------------------------------------------------------

def choose(means: Mapping[str, float]) -> tuple[str, str]:
    """The selected variant and why: the highest mean, unless P1 is within ``TIE_MARGIN`` of it."""
    if TIE_PREFERENCE not in means:
        raise SelectError("no_preferred_variant", f"the recipe must declare variant {TIE_PREFERENCE!r}")
    best = max(sorted(means), key=lambda name: means[name])
    if best == TIE_PREFERENCE:
        return best, "higher_mean"
    if means[best] - means[TIE_PREFERENCE] <= TIE_MARGIN + 1e-12:
        return TIE_PREFERENCE, "tie_within_margin"
    return best, "higher_mean"


# --- scoring -------------------------------------------------------------------------------------

def hybrid_rate(evaluation: EvaluationSet, router_rows: Sequence[Mapping[str, Any]],
                interpretation_rows: Sequence[Mapping[str, Any]], oracle_rows: Sequence[Mapping[str, Any]],
                condition: str, label: str) -> tuple[float, int]:
    """One router run × one condition: the hybrid's ``request_interpretation`` rate and its n."""
    try:
        composed = compose_rows(router_rows, interpretation_rows, conditions={condition})
        records, _ = stage2_outcomes(evaluation, composed, oracle_rows, label)
    except ComposeError as error:
        raise SelectError(error.code, f"{label}: {error}") from None
    except AnalysisError as error:
        raise SelectError(error.code, f"{label}: {error}") from None
    population = {e.example_id for e in OutcomeTable(evaluation, {}).population(ENDPOINT, condition)}
    hits = [request_interpretation(*record) for example, record in zip(evaluation.members(condition), records[condition])
            if example.example_id in population]
    if not hits:
        raise SelectError("empty_population", f"{label}: no gold requests with a mapped category to score")
    return sum(hits) / len(hits), len(hits)


def score_variant(evaluation: EvaluationSet, routers: Sequence[RouterRun], run: VariantRun,
                  sample_ids: frozenset[str] | None) -> dict[str, Any]:
    """Every (condition, seed) rate of one variant, their mean, and the per-condition n."""
    rates: dict[str, dict[str, float]] = {}
    scored: dict[str, int] = {}
    for condition in SELECTION_CONDITIONS:
        interpretation = [row for row in run.interpretation if row["condition"] == condition]
        oracle = [row for row in run.oracle if row["condition"] == condition]
        train = router_train_condition(condition)
        rates[condition] = {}
        for router in (r for r in routers if r.train_condition == train):
            rows = router.rows if sample_ids is None else [
                row for row in router.rows if isinstance(row, Mapping) and row.get("example_id") in sample_ids]
            rate, n = hybrid_rate(evaluation, rows, interpretation, oracle, condition,
                                  f"{run.variant} {condition} {router.label}")
            if scored.setdefault(condition, n) != n:
                raise SelectError("population_differs", f"{run.variant} {condition}: router runs scored different n")
            rates[condition][str(router.seed)] = rate
    values = [rate for per_seed in rates.values() for rate in per_seed.values()]
    return {"mean": statistics.fmean(values), "runs": len(values), "rates": rates, "scored_examples": scored}


# --- inputs --------------------------------------------------------------------------------------

def load_variant_run(recipe: Recipe, variant: str, split: str, root: Path) -> VariantRun:
    """The variant's selection run, checked against the current recipe, prompt and slot keys."""
    directory = output_dir(recipe, split, "main", variant, SELECTION_CONDITIONS, root)
    provenance_bytes = _read(directory / "provenance.main.json", MAX_PROVENANCE_BYTES, variant)
    provenance = _parse_json(provenance_bytes, f"{variant} provenance")
    rendered = prompt.main_instructions(recipe.prompt_path(variant), schema.load_slot_keys(recipe.slot_keys)).sha256
    try:
        recorded = (provenance["version"], provenance["task"], provenance["split"], provenance["system"],
                    provenance["variant"], provenance["conditions"], provenance["model"])
        prompt_sha, outputs, counts = provenance["prompt"]["rendered_sha256"], provenance["outputs"], provenance["counts"]
        sample = provenance["sample"]
        invalid_calls = sum(counts["invalid_calls_by_reason"].values())
        distinct_inputs = counts["distinct_inputs"]
    except (KeyError, TypeError, AttributeError):
        raise SelectError("malformed_run", f"{variant}: the provenance lacks the run fields") from None
    expected = (PROVENANCE_VERSION, "main", split, recipe.system, variant, list(SELECTION_CONDITIONS),
                recipe.model_ref)
    if recorded != expected:
        raise SelectError("not_a_selection_run",
                          f"{variant}: not a {split} main-task run of this recipe's model under "
                          f"{'/'.join(SELECTION_CONDITIONS)}")
    if prompt_sha != rendered:
        raise SelectError("prompt_changed", f"{variant}: the prompt or slot keys changed since the run")
    if type(invalid_calls) is not int or type(distinct_inputs) is not int or distinct_inputs < 1:
        raise SelectError("malformed_run", f"{variant}: the provenance counts are malformed")
    files = {}
    for kind in ("interpretation", "oracle"):
        data = _read(directory / f"{kind}.jsonl", MAX_STREAM_BYTES, variant)
        if not isinstance(outputs, dict) or outputs.get(f"{kind}.jsonl") != _sha256(data):
            raise SelectError("run_changed", f"{variant}: {kind}.jsonl differs from what the run recorded")
        files[kind] = _rows(data, f"{variant} {kind}")
    return VariantRun(variant, tuple(files["interpretation"]), tuple(files["oracle"]), sample,
                      invalid_calls, distinct_inputs,
                      {"provenance_sha256": _sha256(provenance_bytes),
                       "interpretation_sha256": outputs["interpretation.jsonl"],
                       "oracle_sha256": outputs["oracle.jsonl"], "rendered_prompt_sha256": rendered})


def resolve_sample(runs: Sequence[VariantRun], items: Path, split: str) -> Sample | None:
    """None if every variant ran on all inputs; else the one shared sample, redrawn and verified."""
    recorded = [run.sample for run in runs]
    if any(value != recorded[0] for value in recorded[1:]):
        raise SelectError("samples_differ", "the variants ran on different inputs (full set vs sample, or two samples)")
    if recorded[0] == "all":
        return None
    try:
        sample = draw(items, split, recorded[0]["dialogues"], recorded[0]["seed"])
    except (KeyError, TypeError):
        raise SelectError("malformed_run", "the recorded sample block is malformed") from None
    except SampleError as error:
        raise SelectError("sample_changed", str(error)) from None
    if not matches(recorded[0], sample):
        raise SelectError("sample_changed", "redrawing the sample from the items gives other examples than the runs used")
    return sample


def restrict(evaluation: EvaluationSet, ids: frozenset[str]) -> EvaluationSet:
    """The evaluation set cut to the sampled examples (sets, slices and gold alike)."""
    if not ids or not ids <= {e.example_id for e in evaluation.examples}:
        raise SelectError("sample_changed", "the sample names examples outside the evaluation set")
    sets = ScoringSets(evaluation.sets.mismatch_ids & ids,
                       {condition: values & ids for condition, values in evaluation.sets.cue_donor_ids.items()})
    return EvaluationSet(
        split=evaluation.split, examples=tuple(e for e in evaluation.examples if e.example_id in ids), sets=sets,
        slices={name: {i: v for i, v in values.items() if i in ids} for name, values in evaluation.slices.items()},
        rules_version=evaluation.rules_version, gold={i: evaluation.gold[i] for i in ids})


# --- the command ---------------------------------------------------------------------------------

def select_prompt(recipe: Recipe, *, split: str, router_root: Path, items: Path, dialogues: Path,
                  root: Path = REPO_ROOT, router_name: str = ROUTER_NAME) -> dict[str, Any]:
    """Score every variant, apply the FR9 rule, and write the aggregate report last."""
    if split not in SPLITS:
        raise SelectError("unknown_split", f"split must be one of {list(SPLITS)}")
    if split != "dev":
        raise SelectError("refused", DEV_ONLY)
    router_root, items, dialogues = (path if path.is_absolute() else root / path
                                     for path in (router_root, items, dialogues))
    runs = [load_variant_run(recipe, variant, split, root) for variant in recipe.variants]
    try:
        routers = [run for run in load_router_runs(router_root, split, router_name)
                   if run.train_condition in {router_train_condition(c) for c in SELECTION_CONDITIONS}]
        evaluation = load_evaluation_set(items, dialogues, split, RULES_VERSION)
    except ComposeError as error:
        raise SelectError(error.code, str(error)) from None
    except AnalysisError as error:
        raise SelectError(error.code, str(error)) from None
    sample = resolve_sample(runs, items, split)
    if sample is not None:
        evaluation = restrict(evaluation, sample.example_ids)

    variants = {}
    for run in runs:
        _check_conditions(run)
        scores = score_variant(evaluation, routers, run, sample.example_ids if sample else None)
        invalid_rate = run.invalid_calls / run.distinct_inputs
        variants[run.variant] = {**scores, "invalid_calls": run.invalid_calls, "distinct_inputs": run.distinct_inputs,
                                 "invalid_rate": invalid_rate, "invalid_rate_over_limit": invalid_rate > INVALID_RATE_LIMIT,
                                 **run.hashes}
    means = {name: entry["mean"] for name, entry in variants.items()}
    selected, reason = choose(means)
    report = {
        "version": SELECT_VERSION, "spec": "009", "split": split, "system": recipe.system, "model": recipe.model_ref,
        "metric": {"endpoint": ENDPOINT, "composition": "hybrid (FR11)", "router": router_name,
                   "conditions": list(SELECTION_CONDITIONS), "average": "mean over conditions x router seeds"},
        "rule": {"tie_margin": TIE_MARGIN, "tie_preference": TIE_PREFERENCE, "invalid_rate_limit": INVALID_RATE_LIMIT},
        "sample": sample.as_provenance() if sample else "all",
        "router": {"name": router_name, "root": _relative(router_root, root),
                   "runs": [{"train_condition": r.train_condition, "seed": r.seed, **r.hashes} for r in routers]},
        "recipe": {"path": _relative(recipe.path, root), "text_sha256": recipe.text_sha256,
                   "main_prompt": recipe.main_prompt},
        "variants": variants,
        "selected": selected, "reason": reason,
        "difference_best_minus_preference": max(means.values()) - means[TIE_PREFERENCE],
        "recipe_needs_update": selected != recipe.main_prompt,
        "code": {"source_sha256": source_sha256(), **git_state(cwd=REPO_ROOT)},
    }
    streams.write_atomic(report_path(recipe.system, root), streams.json_bytes(report), root)
    return report


def _check_conditions(run: VariantRun) -> None:
    for number, row in enumerate((*run.interpretation, *run.oracle), start=1):
        if not isinstance(row, Mapping) or row.get("condition") not in SELECTION_CONDITIONS:
            raise SelectError("malformed_run", f"{run.variant}: row {number} is not a {'/'.join(SELECTION_CONDITIONS)} row")


def _read(path: Path, limit: int, variant: str) -> bytes:
    try:
        return read_bounded(path, limit)
    except AnalysisError:
        raise SelectError("missing_run", f"{variant}: {path.name} is missing or too large; "
                                         f"run --variant {variant} --conditions {' '.join(SELECTION_CONDITIONS)}") from None


def _parse_json(data: bytes, label: str) -> Any:
    try:
        return parse_json(data, label)
    except AnalysisError as error:
        raise SelectError(error.code, str(error)) from None


def _rows(data: bytes, label: str) -> list[Any]:
    try:
        return parse_jsonl(data, label)
    except AnalysisError as error:
        raise SelectError(error.code, str(error)) from None


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _relative(path: Path, root: Path) -> str:
    resolved = path.resolve()
    return resolved.relative_to(root.resolve()).as_posix() if resolved.is_relative_to(root.resolve()) else path.name


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    select_parser = commands.add_parser("select-prompt", help="choose the main-task prompt variant on dev (FR9)")
    select_parser.add_argument("--recipe", type=Path, required=True)
    select_parser.add_argument("--split", choices=SPLITS, required=True)
    select_parser.add_argument("--router-root", type=Path, required=True, help=f"e.g. outputs/stage1/{ROUTER_NAME}")
    select_parser.add_argument("--items", type=Path, default=Path("data/interim/direct/items.jsonl"))
    select_parser.add_argument("--dialogues", type=Path, default=Path("data/interim/direct/dialogues.jsonl"))
    args = parser.parse_args(argv)
    try:
        if args.split != "dev":
            raise SelectError("refused", DEV_ONLY)  # before the recipe or any output is read
        report = select_prompt(load_recipe(args.recipe), split=args.split, router_root=args.router_root,
                               items=args.items, dialogues=args.dialogues)
    except (SelectError, RecipeError, SampleError) as error:
        print(f"Prompt selection stopped: {error}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as error:
        print(f"Prompt selection failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    summary = {"selected": report["selected"], "reason": report["reason"], "sample": report["sample"],
               "recipe_needs_update": report["recipe_needs_update"],
               "variants": {name: {key: entry[key] for key in ("mean", "runs", "invalid_rate", "invalid_rate_over_limit")}
                            for name, entry in report["variants"].items()}}
    print(json.dumps(summary, indent=2, sort_keys=True))
    if any(entry["invalid_rate_over_limit"] for entry in report["variants"].values()):
        print(f"Warning: a variant's invalid rate is above {INVALID_RATE_LIMIT}; fix the prompt or schema "
              "before relying on this selection (plan Risks).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
