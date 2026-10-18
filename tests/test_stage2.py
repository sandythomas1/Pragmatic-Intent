"""Oracle/routed denominators, common sets, leakage and no-text reports."""

import json
import unittest

from src.data.direct_dataset import Turn
from src.evaluation import stage2
from src.evaluation.interpretation import Reference
from src.evaluation.stage1 import ScoringSets
from src.stage1.data import Stage1Example
from tests.test_interpretation import prediction


def examples():
    return [Stage1Example("x:indirect", "x", "D.json", 2, "indirect", "I could use a rest.", "indirect", "Hotel"),
            Stage1Example("y:direct", "y", "E.json", 2, "direct", "Reserve it.", "direct", "Hotel"),
            Stage1Example("z:direct", "z", "F.json", 2, "direct", "Goodbye.", "no_request", "general")]


def records(condition="none"):
    return [prediction(condition=condition, slots={}),
            prediction("y:direct", condition, prediction="direct", slots={}),
            prediction("z:direct", condition, prediction="no_request", category="no_request", slots={})]


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.examples = examples()
        self.gold = {e.example_id: Reference("no_request" if e.label == "no_request" else "booking", {}, frozenset())
                     for e in self.examples}

    def report(self, routed, oracle, **kwargs):
        return stage2.build_report(self.examples, self.gold, routed, oracle, conditions=("none",),
                                   bootstrap_samples=10, **kwargs)

    def test_route_miss_fails_but_oracle_still_succeeds(self):
        routed = records()
        routed[0].update(prediction="no_request", category=None)
        report = self.report(routed, [records()[0]])["conditions"]["none"]
        self.assertEqual(report["oracle"]["n"], 1)
        self.assertEqual(report["oracle"]["success"], 1.0)
        self.assertEqual(report["end_to_end"]["n"], 3)
        self.assertAlmostEqual(report["end_to_end"]["success"], 2 / 3)

    def test_direct_route_needs_interpretation_and_invalid_counts(self):
        routed = records()
        routed[1]["category"] = None
        routed[2] = {"example_id": "z:direct", "condition": "none", "invalid": True}
        report = self.report(routed, [records()[0]])["conditions"]["none"]
        self.assertEqual(report["invalid_outputs"], 1)
        self.assertEqual(report["end_to_end"]["success"], 1 / 3)

    def test_false_positive_and_oracle_completeness(self):
        routed = records()
        routed[2].update(prediction="direct", category="booking")
        self.assertEqual(self.report(routed, [records()[0]])["conditions"]["none"]["nonrequest_false_positives"], 1)
        with self.assertRaises(ValueError):
            self.report(routed, [])

    def test_nonrequest_abstention_needs_no_intent_but_invented_intent_fails(self):
        routed = records()
        routed[2]["category"] = None
        self.assertEqual(self.report(routed, [records()[0]])["conditions"]["none"]["end_to_end"]["success"], 1)
        routed[2]["category"] = "booking"
        result = self.report(routed, [records()[0]])["conditions"]["none"]
        self.assertEqual(result["nonrequest_unsupported_interpretations"], 1)
        self.assertEqual(result["end_to_end"]["success"], 2 / 3)

    def test_mismatch_contrast_uses_common_set_and_cue_sensitivity(self):
        routed = records("full") + records("none") + [records("mismatched")[0]]
        oracle = [records(c)[0] for c in ("full", "none", "mismatched")]
        sets = ScoringSets(frozenset({"x:indirect"}), {"mismatched": frozenset({"x:indirect"})})
        report = stage2.build_report(self.examples, self.gold, routed, oracle,
                                    conditions=("none", "full", "mismatched"), sets=sets, bootstrap_samples=10)
        self.assertEqual(report["contrasts"]["full-mismatched"]["n"], 1)
        self.assertEqual(report["contrasts"]["full-none"]["n"], 3)
        self.assertEqual(report["contrasts"]["full-mismatched"]["without_cue_donors"]["n"], 0)

    def test_unknown_slices_and_foreign_cue_ids_fail(self):
        with self.assertRaises(ValueError):
            self.report(records(), [records()[0]], slices={"rule_level": {"x:indirect": "PRIVATE SOURCE"}})
        with self.assertRaises(ValueError):
            self.report(records(), [records()[0]], sets=ScoringSets(frozenset(), {"mismatched": frozenset({"foreign"})}))

    def test_unmapped_request_kept_in_detection_and_explicitly_excluded(self):
        self.gold["x:indirect"] = Reference(None, {}, frozenset())
        report = self.report(records(), [])["conditions"]["none"]
        self.assertEqual(report["request_detection"]["n_requests"], 2)
        self.assertEqual(report["unmapped_requests"], 1)
        self.assertEqual(report["oracle"]["n"], 0)
        self.assertEqual(report["end_to_end"]["n"], 2)

    def test_report_never_contains_predicted_or_gold_text(self):
        routed = records()
        routed[0]["paraphrase"] = "PRIVATE MODEL PARAPHRASE"
        self.gold["x:indirect"] = Reference("booking", {"hotel.name": "PRIVATE SOURCE VALUE"}, frozenset())
        text = json.dumps(self.report(routed, [records()[0]]))
        self.assertNotIn("PRIVATE", text)

    def test_inputs_use_shared_renderer_and_exclude_gold_and_future(self):
        e = self.examples[0]
        item = {"item_id": "x", "dialogue_id": "D.json", "turn_index": 2, "mismatch": None,
                "user_acts": {"Hotel-Inform": [["Name", "GOLD SENTINEL"]]}}
        dialogues = {"D.json": [Turn("user", "Prior"), Turn("system", "Question"),
                                Turn("user", "ORIGINAL SENTINEL"), Turn("system", "FUTURE SENTINEL")]}
        rows = stage2.input_records([e], [item], dialogues, ("none", "full", "mismatched"))
        self.assertEqual(len(rows), 2)
        text = json.dumps(rows)
        self.assertNotIn("SENTINEL", text)
        self.assertIn("input_sha256", rows[0])
