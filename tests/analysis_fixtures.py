"""Invented panels, run directories and inputs files for the spec 007 analysis tests."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from src.analysis.config import AnalysisConfig, parse_config
from src.analysis.files import FileRef
from src.analysis.inputs import Stage1Run, Stage2Run, SystemInputs
from src.analysis.outcomes import EvaluationSet, OutcomeTable, RunKey
from src.data.direct_dataset import CONDITIONS
from src.evaluation import interpretation as ip
from src.evaluation import stage1
from src.evaluation.stage1 import ScoringSets
from src.stage1.data import Stage1Example

PANEL = [
    {"name": "enc", "family": "encoder", "design": "matched", "streams": ["stage1"]},
    {"name": "tfidf", "family": "tfidf", "design": "test_time", "streams": ["stage1"]},
    {"name": "llm", "family": "llm", "design": "test_time", "streams": ["routed", "oracle", "transfer"]},
    {"name": "pipe", "family": "hybrid", "design": "matched", "streams": ["routed", "oracle"]},
]


FULL_FAMILY = [
    {"name": "h1", "kind": "h1_trend", "system": "pipe", "endpoint": "request_interpretation", "condition": "none"},
    {"name": "h2-detection", "kind": "h2_trend", "system": "pipe", "endpoint": "stage1_correct",
     "contrast": "full_minus_none"},
    {"name": "h4", "kind": "h4_contrast", "system": "pipe"},
    {"name": "corruption", "kind": "mismatch_control", "system": "pipe", "endpoint": "request_interpretation",
     "contrast": "full_minus_mismatched"},
    {"name": "h3-enc", "kind": "h3_difference", "system": "enc", "reference": "pipe", "endpoint": "stage1_correct",
     "contrast": "full_minus_none"},
    {"name": "h3-tfidf", "kind": "h3_difference", "system": "tfidf", "reference": "pipe", "endpoint": "stage1_correct",
     "contrast": "full_minus_none"},
    {"name": "h3-llm", "kind": "h3_difference", "system": "llm", "reference": "pipe",
     "endpoint": "request_interpretation", "contrast": "full_minus_none"},
]


def analysis_config(panel: list[dict[str, Any]] | None = None, **options: Any) -> AnalysisConfig:
    return parse_config(config_dict(panel, **options))


def config_toml(raw: Mapping[str, Any]) -> str:
    """The config as TOML text (top-level keys with inline tables and arrays)."""
    return "".join(f"{key} = {toml_value(value)}\n" for key, value in raw.items())


def config_dict(panel: list[dict[str, Any]] | None = None, *, family: list[dict[str, Any]] | None = None,
                min_dialogues: int = 1, samples: int = 50, draft: bool = True,
                primary_levels: list[str] | None = None) -> dict[str, Any]:
    levels = primary_levels or ["L0", "L1", "L2"]
    return {
        "version": "analysis-v1", "rules_version": "auto-v1", "draft": draft, "alpha": 0.05,
        "bootstrap": {"samples": samples, "seed": 7, "confidence": 0.95},
        "cells": {"min_dialogues": min_dialogues, "max_excluded_share": 0.01},
        "primary": {"system": "pipe", "endpoint": "request_interpretation", "contrast": "full_minus_none",
                    "trend": "linear", "levels": levels},
        "exploratory": {"levels": [level for level in ("L0", "L3", "INF") if level not in levels]},
        "error_audit": {"levels": ["L0", "L1", "L2", "L3"], "per_level": 15, "seed": 7},
        "panel": panel or PANEL,
        "family": family or [{"name": "h3-enc", "kind": "h3_difference", "system": "enc", "reference": "pipe",
                              "endpoint": "stage1_correct", "contrast": "full_minus_none"}],
    }


def toml_value(value: Any) -> str:
    """Enough TOML for inputs files: strings, ints, inline tables and arrays (JSON-compatible)."""
    if isinstance(value, Mapping):
        return "{ " + ", ".join(f"{key} = {toml_value(v)}" for key, v in value.items()) + " }"
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(v) for v in value) + "]"
    return json.dumps(value)


class Workspace:
    """A temporary repository root holding run directories, prediction files and inputs."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()

    def cleanup(self) -> None:
        self._tmp.cleanup()

    def write(self, relative: str, text: str) -> str:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        return relative

    def write_jsonl(self, relative: str, rows: Iterable[Mapping[str, Any]]) -> str:
        return self.write(relative, "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))

    def stage1_run(self, name: str, train: str, seed: int, *, split: str = "dev", smoke: bool = False,
                   rows: Iterable[Mapping[str, Any]] = (), metrics: Mapping[str, Any] | None = None,
                   recorded_train: str | None = None, recorded_name: str | None = None) -> str:
        """A run directory laid out as ``src.stage1.runner.finish`` writes it."""
        leaf = f"outputs/stage1/{name}/train-{train}/seed{seed}"
        recorded = recorded_train or train
        self.write(f"{leaf}/config.resolved.json", json.dumps(
            {"name": recorded_name or name, "kind": "encoder", "data": {"train_condition": recorded, "eval_split": split}}))
        self.write_jsonl(f"{leaf}/predictions.jsonl", rows)
        run = {"seed": seed, "smoke": smoke, "train_condition": recorded, "eval_split": split}
        self.write(f"{leaf}/metrics.json", json.dumps({**(metrics or {}), "run": run}, sort_keys=True))
        return leaf

    def inputs(self, systems: Mapping[str, Mapping[str, Any]], *, split: str = "dev",
               name: str = "configs/analysis/inputs.toml") -> Path:
        lines = ['version = "analysis-inputs-v1"', f'split = "{split}"', "[systems]"]
        for system, table in systems.items():
            lines.append(f'"{system}" = {toml_value(dict(table))}')
        return self.root / self.write(name, "\n".join(lines) + "\n")


Decide = Callable[[Stage1Example, str, str, int], str]  # (example, condition, train, seed) -> label


def evaluation_set(split: str = "dev", **changes: Any) -> EvaluationSet:
    """Six invented dialogues, two turns each, direct and indirect paraphrases.

    Turn 2 of every dialogue has a mismatch donor; turn 4 has none. Turn 4 of every third
    dialogue is social-only, so its examples are ``no_request``.
    """
    examples, levels, categories, gold = [], {}, {}, {}
    for d in range(1, 7):
        for turn in (2, 4):
            social = turn == 4 and d % 3 == 0
            item_id = f"PMUL900{d}_t0{turn}"
            for variant in ("direct", "indirect"):
                example_id = f"{item_id}:{variant}"
                label = "no_request" if social else variant
                examples.append(Stage1Example(example_id, item_id, f"PMUL900{d}.json", turn, variant, "text", label, "hotel"))
                levels[example_id] = "NR" if social else ("L0" if variant == "direct" else ("L1", "L2", "L3")[d % 3])
                categories[example_id] = "no_request" if social else "booking"
                gold[example_id] = ip.Reference(categories[example_id], {}, frozenset())
    sets = ScoringSets(frozenset(e.example_id for e in examples if e.turn_index == 2),
                       {"mismatched": frozenset(), "mismatched_one": frozenset()})
    fields = dict(split=split, examples=tuple(examples), sets=sets,
                  slices={"rule_level": levels, "category": categories}, rules_version="auto-v1", gold=gold)
    return EvaluationSet(**{**fields, **changes})


def stage1_rows(evaluation: EvaluationSet, decide: Decide, train: str, seed: int,
                conditions: Iterable[str] = CONDITIONS) -> list[dict[str, Any]]:
    return [{"example_id": e.example_id, "condition": c, "prediction": decide(e, c, train, seed)}
            for c in conditions for e in evaluation.members(c)]


def write_stage1_grid(ws: Workspace, evaluation: EvaluationSet, name: str, trains: Iterable[str],
                      seeds: Iterable[int], decide: Decide) -> None:
    """Runs whose metrics.json comes from the real scorer, as ``runner.finish`` writes it."""
    for train in trains:
        for seed in seeds:
            rows = stage1_rows(evaluation, decide, train, seed)
            report = stage1.build_report(list(evaluation.examples), rows, None, evaluation.sets, 1, 0)
            ws.stage1_run(name, train, seed, split=evaluation.split, rows=rows, metrics=report)


# (example, condition, train, seed, oracle) -> overrides for the row, or None for an invalid output
Decide2 = Callable[[Stage1Example, str, str, int, bool], Mapping[str, Any] | None]


def exact_answer(example: Stage1Example, condition: str, train: str, seed: int, oracle: bool) -> Mapping[str, Any]:
    return {}


def stage2_rows(evaluation: EvaluationSet, decide: Decide2, train: str, seed: int, *, oracle: bool,
                conditions: Iterable[str] = CONDITIONS) -> list[dict[str, Any]]:
    """Structured rows; by default each predicts the gold type and category with no slots (exact)."""
    rows = []
    for condition in conditions:
        members = evaluation.oracle_members(condition) if oracle else evaluation.members(condition)
        for e in members:
            changes = decide(e, condition, train, seed, oracle)
            if changes is None:
                rows.append({"example_id": e.example_id, "condition": condition, "invalid": True})
                continue
            gold = evaluation.gold[e.example_id]
            rows.append({"example_id": e.example_id, "condition": condition, "prediction": e.label,
                         "category": gold.category, "slots": dict(gold.slots),
                         "requested_slots": sorted(gold.requested_slots), **changes})
    return rows


def write_stage2_grid(ws: Workspace, evaluation: EvaluationSet, name: str, trains: Iterable[str],
                      seeds: Iterable[int], decide: Decide2 = exact_answer) -> list[dict[str, Any]]:
    entries = []
    for train in trains:
        for seed in seeds:
            leaf = f"outputs/stage2/{name}/train-{train}/seed{seed}"
            routed = ws.write_jsonl(f"{leaf}/routed.jsonl", stage2_rows(evaluation, decide, train, seed, oracle=False))
            oracle = ws.write_jsonl(f"{leaf}/oracle.jsonl", stage2_rows(evaluation, decide, train, seed, oracle=True))
            entries.append({"train_condition": train, "seed": seed, "routed": routed, "oracle": oracle})
    return entries


Correct = Callable[[Stage1Example, str, str, int], bool]  # (example, condition, train, seed) -> correct?


def large_evaluation(dialogues: int = 60, *, split: str = "dev", dup_ids: frozenset[str] | None = None,
                     category_of: Callable[[int, str], str] | None = None) -> EvaluationSet:
    """Every dialogue holds L0 (direct), L1, L2 and L3 (indirect) examples; every fifth adds an NR item.

    Turn 2 has a mismatch donor; dialogue 1's turn 2 is a cue donor under both mismatch conditions.
    ``category_of(dialogue, level)`` sets the cat-v1 category (default: booking / info_seeking by
    dialogue parity).
    """
    examples, levels, categories, gold = [], {}, {}, {}
    for d in range(1, dialogues + 1):
        dialogue = f"PMUL{9000 + d}.json"
        for turn, indirect_level in ((2, "L1"), (4, "L2"), (6, "L3"), (8, "NR")):
            if indirect_level == "NR" and d % 5:
                continue
            item_id = f"PMUL{9000 + d}_t{turn:02d}"
            for variant in ("direct", "indirect"):
                example_id = f"{item_id}:{variant}"
                social = indirect_level == "NR"
                level = "NR" if social else ("L0" if variant == "direct" else indirect_level)
                label = "no_request" if social else variant
                category = "no_request" if social else (category_of(d, level) if category_of
                                                        else ("booking" if d % 2 else "info_seeking"))
                examples.append(Stage1Example(example_id, item_id, dialogue, turn, variant, "text", label, "hotel"))
                levels[example_id], categories[example_id] = level, category
                gold[example_id] = ip.Reference(category, {}, frozenset())
    mismatch = frozenset(e.example_id for e in examples if e.turn_index == 2)
    donors = frozenset(e.example_id for e in examples if e.item_id == "PMUL9001_t02")
    return EvaluationSet(split=split, examples=tuple(examples),
                         sets=ScoringSets(mismatch, {"mismatched": donors, "mismatched_one": donors}),
                         slices={"rule_level": levels, "category": categories}, rules_version="auto-v1",
                         gold=gold, dup_ids=dup_ids)


def synthetic_table(evaluation: EvaluationSet, config: AnalysisConfig,
                    runs: Mapping[str, Mapping[tuple[str, int], Correct]]) -> OutcomeTable:
    """An outcome table straight from decision functions, bypassing files (T3–T5 test those).

    A Stage 1 system records the label when correct and a wrong label otherwise. A Stage 2
    system always routes to the gold type; ``correct`` sets routed and oracle exactness.
    """
    ref = FileRef(Path("synthetic"), "0" * 64, 0, 0)
    systems = {}
    table_runs = []
    for system in config.panel:
        trains = runs.get(system.name, {})
        stage2 = "routed" in system.streams
        stage1_runs = tuple(Stage1Run(t, s, Path("synthetic"), ref, ref, ref) for t, s in trains) if not stage2 else ()
        stage2_runs = tuple(Stage2Run(t, s, ref, ref) for t, s in trains) if stage2 else ()
        systems[system.name] = SystemInputs(system, stage1_runs, stage2_runs)
        for (train, seed), correct in trains.items():
            table_runs.append((system.name, "stage2" if stage2 else "stage1", train, seed, correct))
    table = OutcomeTable(evaluation, systems)
    for name, source, train, seed, correct in table_runs:
        records, oracle = {}, {}
        for condition in CONDITIONS:
            members = evaluation.members(condition)
            if source == "stage1":
                records[condition] = tuple(e.label if correct(e, condition, train, seed) else
                                           ("indirect" if e.label == "direct" else "direct") for e in members)
            else:
                records[condition] = tuple((e.label, correct(e, condition, train, seed)) for e in members)
                oracle[condition] = tuple(correct(e, condition, train, seed) for e in evaluation.oracle_members(condition))
        table.add_run(RunKey(name, source, train, seed), records, oracle if source == "stage2" else None)
    return table


def grid(trains: Iterable[str], seeds: Iterable[int], correct: Correct) -> dict[tuple[str, int], Correct]:
    return {(t, s): correct for t in trains for s in seeds}


INDIRECT_TEXTS = {2: "Could you book the hotel?", 4: "A hotel would be nice."}  # auto-v1 L1 and L2
DIRECT_TEXT = "Book the hotel."  # auto-v1 L0


def write_corpus(ws: Workspace, dialogues: int = 12, *, split: str = "dev") -> tuple[Path, Path]:
    """Real ``items.jsonl`` / ``dialogues.jsonl`` (invented text) giving L0, L1 and L2 examples.

    Every dialogue has two target turns with prior context. Each item's mismatch donor is the
    next dialogue, so every example is in the mismatch set.
    """
    items, records = [], []
    for d in range(1, dialogues + 1):
        dialogue = f"PMUL{9100 + d}.json"
        donor = f"PMUL{9100 + d % dialogues + 1}.json"
        for turn, indirect in INDIRECT_TEXTS.items():
            items.append({"item_id": f"PMUL{9100 + d}_t{turn:02d}", "dialogue_id": dialogue, "turn_index": turn,
                          "split": split, "target_utterance": "original", "direct_utterance": DIRECT_TEXT,
                          "indirect_utterance": indirect, "turn_domains": ["hotel"],
                          "user_acts": {"Hotel-Inform": [["Area", "north"]]}, "quality_labels": None,
                          "mismatch": {"donor_dialogue_id": donor, "start": 0, "length": turn}})
        turns = [{"speaker": "user" if i % 2 == 0 else "system", "text": f"line {i} of the chat"} for i in range(6)]
        records.append({"dialogue_id": dialogue, "turns": turns})
    ws.write_jsonl("data/interim/direct/items.jsonl", items)
    ws.write_jsonl("data/interim/direct/dialogues.jsonl", records)
    return ws.root / "data/interim/direct/items.jsonl", ws.root / "data/interim/direct/dialogues.jsonl"


def stage1_entries(name: str, trains: Iterable[str], seeds: Iterable[int]) -> list[dict[str, Any]]:
    return [{"train_condition": t, "seed": s, "run_dir": f"outputs/stage1/{name}/train-{t}/seed{s}"}
            for t in trains for s in seeds]
