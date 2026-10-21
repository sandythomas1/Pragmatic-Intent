"""Outcome table, component check and seed averaging (spec 007 T4–T5)."""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any
from unittest import mock

from src.analysis import outcomes
from src.analysis.files import AnalysisError
from src.analysis.inputs import load_inputs
from src.analysis.outcomes import build_outcomes, load_evaluation_set, seed_variation
from src.data.direct_dataset import CONDITIONS
from src.evaluation import stage2
from src.stage1.data import Stage1Example
from tests.analysis_fixtures import (
    Workspace,
    analysis_config,
    evaluation_set,
    exact_answer,
    stage1_entries,
    stage1_rows,
    stage2_rows,
    write_stage1_grid,
    write_stage2_grid,
)

GENUINE = ("none", "one", "full")


def wrong(example: Stage1Example) -> str:
    return "indirect" if example.label == "direct" else "direct"


def varied(example: Stage1Example, condition: str, train: str, seed: int) -> str:
    """Right for some seeds and not others, so seed averages land on thirds."""
    dialogue = int(example.dialogue_id[7])
    return example.label if (dialogue * seed + CONDITIONS.index(condition)) % 3 == 1 else wrong(example)


def full_training_helps(example: Stage1Example, condition: str, train: str, seed: int) -> str:
    return example.label if train == "full" else wrong(example)


class OutcomeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.ws = Workspace()
        self.addCleanup(self.ws.cleanup)
        self.config = analysis_config()
        self.evaluation = evaluation_set()

    def table(self, systems: dict[str, Any], evaluation=None):
        evaluation = evaluation or self.evaluation
        path = self.ws.inputs(systems, split=evaluation.split)
        return build_outcomes(evaluation, load_inputs(path, self.config, evaluation.split, base=self.ws.root))

    def grid(self, decide=varied, seeds=(1, 2, 3)) -> dict[str, Any]:
        write_stage1_grid(self.ws, self.evaluation, "enc", GENUINE, seeds, decide)
        write_stage1_grid(self.ws, self.evaluation, "tfidf", ["full"], [1], decide)
        return {"enc": {"stage1": stage1_entries("enc", GENUINE, seeds)},
                "tfidf": {"stage1": stage1_entries("tfidf", ["full"], [1])}}

    def assert_code(self, code: str, call) -> AnalysisError:
        with self.assertRaises(AnalysisError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)
        return caught.exception


class SeedAveragingTest(OutcomeTestCase):
    """AC-007-2."""

    def test_three_seeds_average_to_thirds_and_vary_per_seed(self) -> None:
        table = self.table(self.grid())
        averaged = table.average("enc", "matched", "full", "stage1_correct")
        self.assertEqual(len(averaged), len(self.evaluation.examples))
        self.assertTrue(set(averaged.values()) <= {0.0, 1 / 3, 2 / 3, 1.0})
        self.assertGreater(len(set(averaged.values())), 1)
        rates = table.seed_rates("enc", "matched", "full", "stage1_correct")
        self.assertEqual(sorted(rates), [1, 2, 3])
        summary = seed_variation(rates)
        self.assertEqual(summary["n_seeds"], 3)
        self.assertEqual(set(summary["per_seed"]), {"1", "2", "3"})
        self.assertAlmostEqual(summary["mean"], sum(rates.values()) / 3)
        self.assertEqual((summary["min"], summary["max"]), (min(rates.values()), max(rates.values())))
        self.assertGreater(summary["sd"], 0)
        # The seed average of the example values equals the mean of the per-seed rates.
        self.assertAlmostEqual(sum(averaged.values()) / len(averaged), summary["mean"])

    def test_one_seed_has_no_sd(self) -> None:
        self.assertIsNone(seed_variation({4: 0.5})["sd"])
        self.assert_code("no_seeds", lambda: seed_variation({}))

    def test_removing_one_seed_under_one_condition_fails(self) -> None:
        systems = self.grid()
        systems["enc"]["stage1"] = [e for e in systems["enc"]["stage1"]
                                    if (e["train_condition"], e["seed"]) != ("none", 3)]
        error = self.assert_code("seed_sets_differ", lambda: self.table(systems))
        self.assertIn("matched", str(error))

    def test_lines_take_their_runs_from_the_design(self) -> None:
        # AC-007-3: the matched line's none outcomes come from train-none, the test-time line's from train-full.
        table = self.table(self.grid(full_training_helps))
        self.assertEqual(set(table.average("enc", "matched", "none", "stage1_correct").values()), {0.0})
        self.assertEqual(set(table.average("enc", "test_time", "none", "stage1_correct").values()), {1.0})
        self.assertEqual(set(table.average("enc", "matched", "mismatched", "stage1_correct").values()), {1.0})
        self.assertEqual(table.not_run, ["llm", "pipe"])
        with self.assertRaises(AnalysisError):
            table.average("llm", "test_time", "none", "stage1_correct")

    def test_seed_contrast_pairs_seeds_on_the_common_examples(self) -> None:
        table = self.table(self.grid(full_training_helps))
        self.assertEqual(table.seed_contrasts("enc", "matched", "full", "none", "stage1_correct"),
                         {1: 1.0, 2: 1.0, 3: 1.0})
        self.assertEqual(table.seed_contrasts("enc", "test_time", "full", "mismatched", "stage1_correct"),
                         {1: 0.0, 2: 0.0, 3: 0.0})

    def test_request_detected_is_scored_on_gold_requests_only(self) -> None:
        table = self.table(self.grid())
        detected = table.average("tfidf", "test_time", "full", "request_detected")
        labels = {e.example_id: e.label for e in self.evaluation.examples}
        self.assertTrue(detected)
        self.assertNotIn("no_request", {labels[i] for i in detected})
        self.assertEqual(len(table.average("tfidf", "test_time", "mismatched", "stage1_correct")),
                         len(self.evaluation.sets.mismatch_ids))


class ComponentCheckTest(OutcomeTestCase):
    """AC-007-4, Stage 1 part."""

    def test_valid_grid_passes_the_component_check(self) -> None:
        self.assertEqual(self.table(self.grid()).seeds("enc", "stage1", "none"), (1, 2, 3))

    def test_a_corrupted_endpoint_function_fails_the_run(self) -> None:
        systems = self.grid()
        with mock.patch.object(outcomes, "stage1_correct", lambda label, prediction: True):
            self.assert_code("component_mismatch", lambda: self.table(systems))
        with mock.patch.object(outcomes, "request_detected", lambda prediction: prediction is not None):
            self.assert_code("component_mismatch", lambda: self.table(systems))

    def test_predictions_that_no_longer_match_metrics_json_fail(self) -> None:
        systems = self.grid()
        swapped = stage1_rows(self.evaluation, full_training_helps, "full", 1)  # valid rows, other predictions
        self.ws.write_jsonl("outputs/stage1/tfidf/train-full/seed1/predictions.jsonl", swapped)
        self.assert_code("metrics_mismatch", lambda: self.table(systems))

    def test_metrics_json_for_other_conditions_fails(self) -> None:
        systems = self.grid()
        path = self.ws.root / "outputs/stage1/tfidf/train-full/seed1/metrics.json"
        metrics = json.loads(path.read_text(encoding="utf-8"))
        del metrics["conditions"]["one"]
        path.write_text(json.dumps(metrics), encoding="utf-8")
        self.assert_code("metrics_mismatch", lambda: self.table(systems))


class PredictionValidationTest(OutcomeTestCase):
    """FR7: a missing, extra or duplicate prediction is an error, and errors never name an example."""

    def rewrite(self, rows: list[dict[str, Any]]) -> None:
        self.ws.write_jsonl("outputs/stage1/tfidf/train-full/seed1/predictions.jsonl", rows)

    def test_missing_extra_duplicate_and_invalid_rows_fail_without_ids(self) -> None:
        systems = self.grid()
        rows = stage1_rows(self.evaluation, varied, "full", 1)
        cases = {
            "missing": rows[1:],
            "duplicate": [*rows, rows[0]],
            "extra": [*rows, {"example_id": "PMUL9999_t02:direct", "condition": "none", "prediction": "direct"}],
            "mismatch-only example under mismatched": [*rows, {**rows[-1], "example_id": "PMUL9001_t04:direct"}],
            "unknown label": [{**rows[0], "prediction": "maybe"}, *rows[1:]],
            "not an object": [["PMUL9001_t02:direct"], *rows[1:]],
            "missing field": [{"example_id": rows[0]["example_id"], "condition": "none"}, *rows[1:]],
        }
        for name, bad in cases.items():
            with self.subTest(name):
                self.rewrite(bad)
                error = self.assert_code("invalid_predictions", lambda: self.table(systems))
                self.assertNotIn("PMUL", str(error))

    def test_run_lacking_a_condition_its_line_needs_fails(self) -> None:
        systems = self.grid()
        rows = stage1_rows(self.evaluation, varied, "full", 1, conditions=("none", "one", "full", "mismatched"))
        self.rewrite(rows)
        report = outcomes.stage1.build_report(list(self.evaluation.examples), rows, None, self.evaluation.sets, 1, 0)
        self.ws.stage1_run("tfidf", "full", 1, rows=rows, metrics=report)
        self.assert_code("missing_condition", lambda: self.table(systems))

    def test_audit_excluded_test_examples_are_ignored(self) -> None:
        excluded = "PMUL9006_t02:direct"
        test_set = evaluation_set("test", excluded_ids=frozenset({"PMUL9999_t02:direct"}))
        self.evaluation = test_set
        systems = self.grid()
        rows = stage1_rows(test_set, varied, "full", 1)
        rows.append({"example_id": "PMUL9999_t02:direct", "condition": "none", "prediction": "direct"})
        self.rewrite(rows)
        self.assertEqual(len(self.table(systems, test_set).average("tfidf", "test_time", "none", "stage1_correct")),
                         len(test_set.examples))
        self.assertIn(excluded, {e.example_id for e in test_set.examples})

    def test_console_stays_silent(self) -> None:
        systems = self.grid()
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.table(systems)
        self.assertEqual((out.getvalue(), err.getvalue()), ("", ""))


class Stage2TestCase(OutcomeTestCase):
    TARGET = "PMUL9001_t02:indirect"  # gold indirect, booking

    def stage2(self, decide=exact_answer, seeds=(1, 2), llm: bool = False) -> dict[str, Any]:
        systems = {"pipe": {"stage2": write_stage2_grid(self.ws, self.evaluation, "pipe", GENUINE, seeds, decide)}}
        if llm:
            systems["llm"] = {"stage2": write_stage2_grid(self.ws, self.evaluation, "llm", ["untrained"], [0], decide)}
        return systems

    def values(self, table, endpoint: str, condition: str = "full", system: str = "pipe",
               line: str = "matched") -> dict[str, float]:
        return table.average(system, line, condition, endpoint)


class EndpointTest(Stage2TestCase):
    """AC-007-5 (first case) and FR3."""

    def test_direct_reading_of_an_indirect_request_counts_for_detection_not_type(self) -> None:
        self.evaluation = evaluation_set(slices={**self.evaluation.slices,
                                                 "rule_level": {**self.evaluation.slices["rule_level"], self.TARGET: "L0"}})

        def read_as_direct(e, condition, train, seed, oracle):
            return {"prediction": "direct"} if e.example_id == self.TARGET and not oracle else {}

        table = self.table(self.stage2(read_as_direct))
        self.assertEqual(self.values(table, "request_interpretation")[self.TARGET], 1.0)
        self.assertEqual(self.values(table, "type_exact")[self.TARGET], 0.0)
        self.assertEqual(self.values(table, "stage1_correct")[self.TARGET], 0.0)  # from the routed type
        self.assertEqual(self.values(table, "oracle_exact")[self.TARGET], 1.0)

    def test_invalid_output_fails_every_endpoint(self) -> None:
        def invalid(e, condition, train, seed, oracle):
            return None if e.example_id == self.TARGET else {}

        table = self.table(self.stage2(invalid))
        for endpoint in ("request_interpretation", "type_exact", "stage1_correct", "request_detected", "oracle_exact"):
            with self.subTest(endpoint):
                self.assertEqual(self.values(table, endpoint)[self.TARGET], 0.0)

    def test_no_request_prediction_on_a_gold_request_fails_the_primary_endpoint(self) -> None:
        def abstain(e, condition, train, seed, oracle):
            return {"prediction": "no_request"} if e.example_id == self.TARGET and not oracle else {}

        table = self.table(self.stage2(abstain))
        self.assertEqual(self.values(table, "request_interpretation")[self.TARGET], 0.0)
        self.assertEqual(self.values(table, "request_detected")[self.TARGET], 0.0)

    def test_populations_follow_fr3(self) -> None:
        table = self.table(self.stage2())
        labels = {e.example_id: e.label for e in self.evaluation.examples}
        primary = self.values(table, "request_interpretation")
        typed = self.values(table, "type_exact")
        oracle = self.values(table, "oracle_exact")
        self.assertNotIn("no_request", {labels[i] for i in primary})
        self.assertIn("no_request", {labels[i] for i in typed})  # spec 005's end_to_end population
        self.assertEqual({labels[i] for i in oracle}, {"indirect"})
        self.assertEqual(set(primary.values()) | set(typed.values()) | set(oracle.values()), {1.0})
        self.assertEqual(len(self.values(table, "oracle_exact", "mismatched")),
                         sum(e.label == "indirect" for e in self.evaluation.members("mismatched")))

    def test_stage1_only_system_has_no_stage2_endpoint(self) -> None:
        systems = {**self.grid(), **self.stage2()}
        table = self.table(systems)
        for endpoint in ("request_interpretation", "type_exact", "oracle_exact"):
            with self.subTest(endpoint), self.assertRaises(AnalysisError) as caught:
                table.average("enc", "matched", "full", endpoint)
            self.assertEqual(caught.exception.code, "missing_streams")
        # Detection endpoints of a Stage 1 system still come from its Stage 1 runs.
        self.assertEqual(table.source("enc", "stage1_correct"), "stage1")
        self.assertEqual(table.source("pipe", "stage1_correct"), "stage2")

    def test_untrained_llm_fills_every_condition_from_one_run(self) -> None:
        table = self.table(self.stage2(llm=True))
        for condition in CONDITIONS:
            self.assertEqual(set(self.values(table, "request_interpretation", condition, "llm", "test_time").values()),
                             {1.0})


class Stage2ComponentTest(Stage2TestCase):
    """AC-007-4, Stage 2 part."""

    @staticmethod
    def mixed(e, condition, train, seed, oracle):
        """Dialogue 2 is read as direct but interpreted exactly; dialogue 4 gets the wrong intent."""
        index = int(e.dialogue_id[7])
        if index == 2:
            return {"prediction": "direct"}
        return {"category": "travel"} if index == 4 else {}

    def test_type_exact_totals_equal_the_scorers_end_to_end(self) -> None:
        table = self.table(self.stage2(self.mixed, seeds=(1,)))
        routed = stage2_rows(self.evaluation, self.mixed, "full", 1, oracle=False)
        oracle = stage2_rows(self.evaluation, self.mixed, "full", 1, oracle=True)
        report = stage2.build_report(list(self.evaluation.examples), dict(self.evaluation.gold), routed, oracle,
                                     conditions=CONDITIONS, sets=self.evaluation.sets, bootstrap_samples=1)
        for condition in CONDITIONS:
            typed = self.values(table, "type_exact", condition)
            end_to_end = report["conditions"][condition]["end_to_end"]
            self.assertEqual(len(typed), end_to_end["n"])
            self.assertAlmostEqual(sum(typed.values()) / len(typed), end_to_end["success"])
            self.assertLess(end_to_end["success"], 1.0)

    def test_corrupted_endpoint_functions_fail_the_run(self) -> None:
        systems = self.stage2(self.mixed)
        patches = {"type_exact": lambda label, prediction, exact: exact,
                   "request_detected": lambda prediction: True}
        for name, replacement in patches.items():
            with self.subTest(name), mock.patch.object(outcomes, name, replacement):
                self.assert_code("component_mismatch", lambda: self.table(systems))


class OracleValidationTest(Stage2TestCase):
    def rewrite(self, rows: list[dict[str, Any]], stream: str = "oracle") -> None:
        self.ws.write_jsonl(f"outputs/stage2/pipe/train-full/seed1/{stream}.jsonl", rows)

    def test_each_oracle_example_needs_exactly_one_row_per_condition(self) -> None:
        systems = self.stage2()
        oracle = stage2_rows(self.evaluation, exact_answer, "full", 1, oracle=True)
        routed_only_some = stage2_rows(self.evaluation, exact_answer, "full", 1, oracle=False, conditions=("none",))
        cases = {
            "missing oracle row": ("oracle", oracle[1:]),
            "duplicate oracle row": ("oracle", [*oracle, oracle[0]]),
            "oracle row for a direct example": ("oracle", [*oracle, {**oracle[0], "example_id": "PMUL9001_t02:direct"}]),
            "oracle conditions beyond the routed file": ("routed", routed_only_some),
            "unknown routed condition": ("routed", [{"example_id": "x", "condition": "loud", "invalid": True}]),
            "slot name injection": ("oracle", [{**oracle[0], "slots": {"../etc": "x"}}, *oracle[1:]]),
        }
        for name, (stream, rows) in cases.items():
            with self.subTest(name):
                self.stage2()  # restore both files
                self.rewrite(rows, stream)
                error = self.assert_code("invalid_predictions", lambda: self.table(systems))
                self.assertNotIn("PMUL", str(error))

    def test_stage2_seed_sets_must_match_across_training_conditions(self) -> None:
        systems = self.stage2(seeds=(1, 2))
        systems["pipe"]["stage2"] = [e for e in systems["pipe"]["stage2"]
                                     if (e["train_condition"], e["seed"]) != ("one", 2)]
        self.assert_code("seed_sets_differ", lambda: self.table(systems))


class EvaluationSetTest(unittest.TestCase):
    def test_loader_builds_the_scorers_set_and_needs_the_audit_on_test(self) -> None:
        ws = Workspace()
        self.addCleanup(ws.cleanup)
        item = {"item_id": "PMUL9001_t02", "dialogue_id": "PMUL9001.json", "turn_index": 2, "split": "dev",
                "target_utterance": "o", "direct_utterance": "Book the hotel.", "indirect_utterance": "A bed would help.",
                "turn_domains": ["hotel"], "user_acts": {"Hotel-Inform": [["Area", "north"]]}, "quality_labels": None,
                "mismatch": None}
        ws.write("items.jsonl", json.dumps(item) + "\n")
        turns = [{"speaker": s, "text": t} for s, t in (("user", "u0"), ("system", "s1"), ("user", "u2"))]
        ws.write("dialogues.jsonl", json.dumps({"dialogue_id": "PMUL9001.json", "turns": turns}) + "\n")
        loaded = load_evaluation_set(ws.root / "items.jsonl", ws.root / "dialogues.jsonl", "dev", "auto-v1")
        self.assertEqual([e.example_id for e in loaded.examples], ["PMUL9001_t02:direct", "PMUL9001_t02:indirect"])
        self.assertEqual(set(loaded.gold), {e.example_id for e in loaded.examples})
        self.assertEqual(set(loaded.slices["rule_level"]), set(loaded.gold))
        self.assertEqual(loaded.members("mismatched"), ())
        with self.assertRaises(AnalysisError) as caught:
            load_evaluation_set(Path("absent.jsonl"), Path("absent.jsonl"), "test", "auto-v1")
        self.assertEqual(caught.exception.code, "audit_required")

    def test_invalid_evaluation_sets_fail(self) -> None:
        good = evaluation_set()
        with self.assertRaises(AnalysisError):
            evaluation_set(examples=good.examples + good.examples[:1])
        with self.assertRaises(AnalysisError):
            evaluation_set(examples=())


if __name__ == "__main__":
    unittest.main()
