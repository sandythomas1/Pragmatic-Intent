"""Estimands on the shared bootstrap (spec 007 T6–T8)."""

from __future__ import annotations

import unittest
from typing import Any

from src.analysis.estimands import H3_CAPTION, MAIN_EFFECT_LABEL, analyse
from src.analysis.files import AnalysisError
from src.stage1.data import Stage1Example
from tests.analysis_fixtures import FULL_FAMILY, analysis_config, grid, large_evaluation, synthetic_table

GENUINE = ("none", "one", "full")


def number(example: Stage1Example) -> int:
    return int(example.dialogue_id[4:8]) - 9000


class EstimandTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.evaluation = large_evaluation()
        self.level = self.evaluation.slices["rule_level"]

    def analyse(self, runs: dict[str, Any], *, split: str = "dev", evaluation=None, **config: Any) -> dict[str, Any]:
        config = analysis_config(**{"min_dialogues": 5, **config})
        table = synthetic_table(evaluation or self.evaluation, config, runs)
        return analyse(table, config, split=split)

    def helps_only_at_l2(self, e: Stage1Example, condition: str, train: str, seed: int) -> bool:
        return not (condition == "none" and self.level[e.example_id] == "L2")

    def helps_equally(self, e: Stage1Example, condition: str, train: str, seed: int) -> bool:
        return condition != "none" or number(e) % 2 == 0

    def pipe(self, correct, seeds=(1, 2)) -> dict[str, Any]:
        return {"pipe": grid(GENUINE, seeds, correct)}

    @staticmethod
    def find(rows: list[dict[str, Any]], **fields: Any) -> dict[str, Any]:
        matches = [row for row in rows if all(row.get(k) == v for k, v in fields.items())]
        if len(matches) != 1:
            raise AssertionError(f"{len(matches)} rows match {fields}")
        return matches[0]


class PrimaryTestTest(EstimandTestCase):
    """AC-007-5 (second and third cases), AC-007-8."""

    def test_context_helping_only_at_l2_gives_a_positive_interval_excluding_zero(self) -> None:
        report = self.analyse(self.pipe(self.helps_only_at_l2))
        primary = report["primary_test"]
        self.assertEqual((primary["status"], primary["decision"]), ("ok", "interval_excludes_0"))
        self.assertAlmostEqual(primary["estimate"]["point"], 1.0)
        self.assertGreater(primary["estimate"]["ci"][0], 0)
        self.assertIsNotNone(primary["estimate"]["p"])
        self.assertIn("point", primary["quadratic"])
        self.assertNotIn("p", primary["quadratic"])  # descriptive only

    def test_equal_benefit_is_labelled_a_main_effect_without_interaction(self) -> None:
        report = self.analyse(self.pipe(self.helps_equally))
        h2 = report["h2"]
        fields = dict(system="pipe", line="matched", endpoint="request_interpretation", contrast="full_minus_none")
        overall = self.find(h2["benefits"], **fields, level="overall")
        self.assertGreater(overall["ci"][0], 0)
        linear = self.find(h2["trends"], **fields, trend="linear")
        self.assertLessEqual(linear["ci"][0], 0)
        self.assertGreaterEqual(linear["ci"][1], 0)
        for row in h2["trends"]:
            if all(row[k] == v for k, v in fields.items()) and row["trend"] == "level_minus_L0":
                self.assertLessEqual(row["ci"][0], 0, row["levels"])
                self.assertGreaterEqual(row["ci"][1], 0, row["levels"])
        self.assertIn({**fields, "label": MAIN_EFFECT_LABEL}, h2["labels"])
        self.assertEqual(report["primary_test"]["decision"], "interval_includes_0")

    def test_primary_cell_below_the_minimum_fails_the_run(self) -> None:
        with self.assertRaises(AnalysisError) as caught:
            self.analyse(self.pipe(self.helps_only_at_l2), min_dialogues=61)
        self.assertEqual(caught.exception.code, "primary_untestable")

    def test_sparse_exploratory_cell_is_sparse_with_no_p_value(self) -> None:
        # NR occurs in every fifth dialogue only: 12 dialogues, below a minimum of 20.
        report = self.analyse({**self.pipe(self.helps_only_at_l2), "enc": grid(GENUINE, (1,), self.helps_only_at_l2)},
                              min_dialogues=20)
        nr = self.find(report["h2"]["benefits"], system="enc", line="matched", endpoint="stage1_correct",
                       contrast="full_minus_none", level="NR")
        self.assertEqual((nr["status"], nr["dialogues"]), ("sparse", 12))
        self.assertNotIn("p", nr)
        self.assertEqual(report["primary_test"]["status"], "ok")
        self.assertGreater(report["statistics"]["sparse"], 0)

    def test_not_run_primary_is_reported_on_dev_and_fails_on_test(self) -> None:
        runs = {"enc": grid(GENUINE, (1,), self.helps_only_at_l2)}
        self.assertEqual(self.analyse(runs)["primary_test"]["status"], "not_run")
        with self.assertRaises(AnalysisError) as caught:
            self.analyse(runs, split="test")
        self.assertEqual(caught.exception.code, "primary_not_run")


class LineTest(EstimandTestCase):
    def test_matched_line_uses_train_c_and_test_time_uses_full(self) -> None:
        def trained_on_full(e, condition, train, seed):
            return train == "full"

        report = self.analyse({**self.pipe(self.helps_only_at_l2), "enc": grid(GENUINE, (1,), trained_on_full)})
        fields = dict(system="enc", endpoint="stage1_correct", contrast="full_minus_none", level="overall")
        self.assertEqual(self.find(report["h2"]["benefits"], line="matched", **fields)["point"], 1.0)
        self.assertEqual(self.find(report["h2"]["benefits"], line="test_time", **fields)["point"], 0.0)
        # Mismatch controls use the full-trained model and the mismatch set on both sides.
        control = self.find(report["mismatch_controls"], system="enc", endpoint="stage1_correct",
                            contrast="full_minus_mismatched", level="overall")
        self.assertEqual((control["line"], control["point"]), ("test_time", 0.0))
        self.assertEqual(control["examples"], len(self.evaluation.sets.mismatch_ids))


class PrecisionReportTest(EstimandTestCase):
    def test_dev_precision_report_has_half_width_cells_and_two_seed_endpoints(self) -> None:
        report = self.analyse({**self.pipe(self.helps_equally), "enc": grid(GENUINE, (1,), self.helps_equally)},
                              samples=200)
        rows = {row["system"]: row for row in report["precision"]}
        self.assertEqual(set(rows), {"pipe", "enc"})
        primary = rows["pipe"]
        self.assertTrue(primary["configured_primary"])
        self.assertEqual(primary["endpoint"], "request_interpretation")
        self.assertEqual(rows["enc"]["endpoint"], "stage1_correct")  # Stage 1-only fallback
        self.assertAlmostEqual(primary["half_width"], (primary["estimate"]["ci"][1] - primary["estimate"]["ci"][0]) / 2)
        self.assertEqual(primary["second_seed"]["seed"], 8)
        self.assertEqual(len(primary["second_seed"]["ci"]), 2)
        self.assertIsInstance(primary["monte_carlo_ok"], bool)
        cells = {(c["level"], c["condition"]): c for c in primary["cells"]}
        self.assertEqual(cells[("L2", "full")]["dialogues"], 60)
        self.assertEqual(cells[("INF", "none")]["dialogues"], 0)

    def test_test_runs_carry_no_precision_report(self) -> None:
        report = self.analyse(self.pipe(self.helps_only_at_l2), split="test")
        self.assertNotIn("precision", report)


class SecondaryEstimandTest(EstimandTestCase):
    """T7: H1, H3, H4, H5."""

    def test_h1_reports_rates_per_condition_and_level_with_a_trend(self) -> None:
        def falls_with_level(e, condition, train, seed):
            return self.level[e.example_id] in ("L0", "NR") or (self.level[e.example_id] == "L1" and number(e) % 2)

        report = self.analyse(self.pipe(falls_with_level))
        rates = report["h1"]["rates"]
        fields = dict(system="pipe", line="matched", endpoint="request_interpretation", condition="none")
        self.assertEqual(self.find(rates, **fields, level="L0")["point"], 1.0)
        self.assertEqual(self.find(rates, **fields, level="L2")["point"], 0.0)
        trend = self.find(report["h1"]["trends"], **fields)
        self.assertEqual(trend["point"], -1.0)
        self.assertEqual({row["condition"] for row in rates}, {"none", "one", "full", "mismatched", "mismatched_one"})

    def test_h4_uses_identical_examples_and_has_the_predicted_sign(self) -> None:
        # Detection is flat (Stage 2 rows always route to the gold type); oracle success falls with level.
        def oracle_falls(e, condition, train, seed):
            return self.level[e.example_id] in ("L0", "L1")

        report = self.analyse(self.pipe(oracle_falls))
        rates = report["h4"]["rates"]
        cells: dict[tuple[str, str], set[tuple[str, int, int]]] = {}
        for row in rates:
            cells.setdefault((row["condition"], row["level"]), set()).add((row["measure"], row["examples"], row["dialogues"]))
        self.assertIn(("mismatched", "L1"), cells)
        for cell, measures in cells.items():  # detection, oracle and routed on the same examples
            self.assertEqual({m for m, _, _ in measures}, {"detection", "oracle", "routed"}, cell)
            self.assertEqual(len({(n, d) for _, n, d in measures}), 1, cell)
        contrast = self.find(report["h4"]["contrasts"], system="pipe")
        # The oracle population is gold indirect, so its L0 cell is empty and the contrast cannot form.
        self.assertEqual(contrast["status"], "empty")

    def test_h4_contrast_is_negative_when_detection_holds_and_oracle_falls(self) -> None:
        def l1_easy(e, condition, train, seed):
            return self.level[e.example_id] != "L3"

        report = self.analyse(self.pipe(l1_easy), primary_levels=["L1", "L2", "L3"])
        contrast = self.find(report["h4"]["contrasts"], system="pipe")
        self.assertEqual(contrast["status"], "ok")
        self.assertAlmostEqual(contrast["point"], -1.0)  # drop(detection) 0 minus drop(oracle) 1

    def test_h3_tests_test_time_lines_and_describes_primary_lines_with_a_caption(self) -> None:
        runs = {**self.pipe(self.helps_only_at_l2), "enc": grid(GENUINE, (1,), self.helps_only_at_l2),
                "tfidf": grid(["full"], (1,), self.helps_only_at_l2)}
        report = self.analyse(runs)
        tested = report["h3"]["tested"]
        self.assertEqual({row["line"] for row in tested}, {"test_time"})
        self.assertEqual({row["system"] for row in tested}, {"enc", "tfidf"})
        self.assertEqual({row["endpoint"] for row in tested}, {"stage1_correct"})
        descriptive = report["h3"]["descriptive"]
        self.assertEqual({row["caption"] for row in descriptive}, {H3_CAPTION})
        self.assertIn("matched vs matched", {row["line"] for row in descriptive})
        self.assertIn("test_time vs matched", {row["line"] for row in descriptive})
        self.assertIn("L2", {row["level"] for row in descriptive})

    def test_stage1_only_systems_appear_in_detection_tables_only(self) -> None:
        report = self.analyse({**self.pipe(self.helps_only_at_l2), "enc": grid(GENUINE, (1,), self.helps_only_at_l2)})
        enc_endpoints = {row["endpoint"] for row in report["h2"]["benefits"] if row["system"] == "enc"}
        self.assertEqual(enc_endpoints, {"stage1_correct"})
        self.assertNotIn("enc", {row["system"] for row in report["h4"]["rates"]})
        self.assertEqual({row["endpoint"] for row in report["h1"]["rates"] if row["system"] == "pipe"},
                         {"request_interpretation", "type_exact", "stage1_correct"})

    def test_intent_standardization_excludes_categories_missing_at_a_level(self) -> None:
        def category(dialogue: int, level: str) -> str:
            if dialogue % 3 == 0:
                return "travel" if level != "L2" else "booking"  # travel never occurs at L2
            return "booking" if dialogue % 2 else "info_seeking"

        evaluation = large_evaluation(category_of=category)
        report = self.analyse(self.pipe(self.helps_only_at_l2), evaluation=evaluation)
        exclusion = self.find(report["h5"]["exclusions"], system="pipe")
        self.assertEqual(exclusion["excluded"], ["travel"])
        self.assertEqual(exclusion["included"], ["booking", "info_seeking"])
        considered = [i for i, level in evaluation.slices["rule_level"].items() if level in ("L0", "L1", "L2")]
        travel = [i for i in considered if evaluation.slices["category"][i] == "travel"]
        self.assertAlmostEqual(exclusion["excluded_share"], len(travel) / len(considered))
        self.assertAlmostEqual(sum(exclusion["weights"].values()), 1.0)
        self.assertIn("travel", {row["category"] for row in report["h5"]["benefits"]})

    def test_single_category_standardization_equals_the_unstandardized_line(self) -> None:
        evaluation = large_evaluation(category_of=lambda dialogue, level: "booking")

        def varied(e, condition, train, seed):
            return condition != "none" or (number(e) + len(self.level[e.example_id])) % 3 == 0

        report = self.analyse(self.pipe(varied), evaluation=evaluation)
        for level in ("L0", "L1", "L2"):
            standardized = self.find(report["h5"]["standardized"], system="pipe", level=level)
            plain = self.find(report["h2"]["benefits"], system="pipe", line="matched",
                              endpoint="request_interpretation", contrast="full_minus_none", level=level)
            self.assertAlmostEqual(standardized["point"], plain["point"])


class HolmFamilyTest(EstimandTestCase):
    """T8 / AC-007-7: the family comes from the config, and a missing system keeps its place."""

    def runs(self, *, llm: bool) -> dict[str, Any]:
        def noisy(e, condition, train, seed):
            return condition != "none" or (number(e) * 7 + len(self.level[e.example_id])) % 3 != 0

        runs = {**self.pipe(noisy), "enc": grid(GENUINE, (1,), self.helps_equally),
                "tfidf": grid(["full"], (1,), self.helps_only_at_l2)}
        if llm:  # an untrained system that behaves exactly like the primary: its H3 difference is 0, p = 1
            runs["llm"] = grid(["untrained"], (1,), noisy)
        return runs

    def test_deleting_a_panel_system_keeps_the_family_and_the_other_adjusted_p_values(self) -> None:
        with_llm = self.analyse(self.runs(llm=True), family=FULL_FAMILY, samples=200)["holm"]
        without = self.analyse(self.runs(llm=False), family=FULL_FAMILY, samples=200)["holm"]
        self.assertEqual((with_llm["family_size"], without["family_size"]), (7, 7))
        present = {row["name"]: row for row in with_llm["members"]}
        absent = {row["name"]: row for row in without["members"]}
        self.assertEqual(present["h3-llm"]["p"], 1.0)
        self.assertEqual((absent["h3-llm"]["status"], absent["h3-llm"]["p"]), ("not_run", 1.0))
        for name in present:
            if name != "h3-llm":
                self.assertEqual(present[name]["p_holm"], absent[name]["p_holm"], name)
        self.assertEqual([row["name"] for row in without["members"]], [m["name"] for m in FULL_FAMILY])

    def test_member_rows_carry_raw_and_adjusted_p_and_an_interval(self) -> None:
        holm = self.analyse(self.runs(llm=True), family=FULL_FAMILY)["holm"]
        members = {row["name"]: row for row in holm["members"]}
        for name in ("h1", "h2-detection", "corruption", "h3-enc", "h3-tfidf"):
            row = members[name]
            self.assertEqual(row["status"], "ok", name)
            self.assertIsNotNone(row["ci"], name)
            self.assertGreaterEqual(row["p_holm"], row["p"], name)
        # H4 needs an L0 oracle cell, which this fixture lacks: untestable, p = 1, place kept.
        self.assertEqual((members["h4"]["status"], members["h4"]["p"]), ("untestable", 1.0))
        self.assertEqual(holm["alpha"], 0.05)

    def test_primary_contrast_is_never_a_family_member(self) -> None:
        report = self.analyse(self.runs(llm=True), family=FULL_FAMILY)
        primary = report["primary_test"]
        for row in report["holm"]["members"]:
            self.assertFalse(row["kind"] == "h2_trend" and row["system"] == primary["system"]
                             and row["endpoint"] == primary["endpoint"] and row.get("contrast") == primary["contrast"])


class SensitivityTest(EstimandTestCase):
    """T8 / FR18: one line per sensitivity, never crossed."""

    def test_each_headline_contrast_carries_its_sensitivity_lines(self) -> None:
        dup = frozenset(e.example_id for e in self.evaluation.examples if number(e) % 10 == 3)
        evaluation = large_evaluation(split="test", dup_ids=dup)
        report = self.analyse({**self.pipe(self.helps_equally), "enc": grid(GENUINE, (1,), self.helps_equally)},
                              split="test", evaluation=evaluation)
        rows = report["sensitivity"]
        for system, endpoint in (("pipe", "request_interpretation"), ("enc", "stage1_correct")):
            for contrast in ("full_minus_none", "one_minus_none", "full_minus_one",
                             "full_minus_mismatched", "one_minus_mismatched_one"):
                lines = [r["sensitivity"] for r in rows if r["system"] == system and r["endpoint"] == endpoint
                         and r["contrast"] == contrast and r["statistic"] == "overall_benefit"]
                expected = ["primary_minus_dup"] + (["without_cue_donors"] if "mismatched" in contrast else [])
                self.assertEqual(sorted(lines), sorted(expected), (system, contrast))
        self.assertEqual({r["sensitivity"] for r in rows}, {"primary_minus_dup", "without_cue_donors"})
        primary = self.find(rows, statistic="primary_linear_trend")
        self.assertEqual((primary["system"], primary["sensitivity"]), ("pipe", "primary_minus_dup"))
        full = self.find(report["h2"]["benefits"], system="pipe", line="matched", endpoint="request_interpretation",
                         contrast="full_minus_none", level="overall")
        trimmed = self.find(rows, system="pipe", endpoint="request_interpretation", contrast="full_minus_none",
                            sensitivity="primary_minus_dup", statistic="overall_benefit")
        self.assertEqual(full["examples"] - trimmed["examples"],
                         sum(1 for i in dup if evaluation.slices["rule_level"][i] != "NR"))
        donors = self.find(rows, system="pipe", endpoint="request_interpretation", contrast="full_minus_mismatched",
                           sensitivity="without_cue_donors")
        self.assertEqual(donors["examples"], len(evaluation.sets.mismatch_ids) - 2)

    def test_dev_has_no_duplicate_line(self) -> None:
        report = self.analyse(self.pipe(self.helps_equally))
        self.assertEqual({r["sensitivity"] for r in report["sensitivity"]}, {"without_cue_donors"})


if __name__ == "__main__":
    unittest.main()
