"""IndirectRequests is separate, synthetic transfer data; fixtures are invented."""

import json
import tempfile
import unittest
from pathlib import Path

from src.data import indirect_requests as ir
from src.evaluation import transfer


def source(**changes):
    return {"utterance": "The lamps hurt my eyes.", "situation": "PRIVATE SITUATION",
            "slot_description": "Whether the lamps should be on", "service": "Lights_1",
            "possible_slot_values": "['True', 'False']",
            "bool_rephrased_slot_values": "['on', 'off']", "target_slot_value": "False", **changes}


class AdapterTests(unittest.TestCase):
    def load(self, rows, split="validation"):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.jsonl"
            path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
            return ir.load_records(path, split)

    def test_aliases_ambiguity_and_safe_inputs(self):
        records = self.load([source(), source(target_slot_value="<ambiguous>")])
        self.assertEqual(records[0].resolve("OFF"), "False")
        self.assertEqual(records[1].target, "<ambiguous>")
        safe = ir.input_record(records[0])
        self.assertEqual(safe["condition"], "none")
        self.assertNotIn("PRIVATE", json.dumps(safe))
        self.assertNotIn("target_slot_value", safe)
        self.assertIn("<ambiguous>", safe["candidates"])

    def test_malformed_literal_candidates_target_and_split(self):
        for changes in ({"possible_slot_values": "__import__('os').getcwd()"},
                        {"possible_slot_values": "['True', 'true']"},
                        {"possible_slot_values": "[True, False]"},
                        {"bool_rephrased_slot_values": "['on']"},
                        {"bool_rephrased_slot_values": "['same', 'same']"},
                        {"target_slot_value": "not in candidates"}):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    self.load([source(**changes)])
        with self.assertRaises(ValueError):
            self.load([source()], "../test")

    def test_pin_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad"
            path.write_text("changed", encoding="utf-8")
            with self.assertRaises(ValueError):
                ir.verify_pin(path, 7, "0" * 64)


class TransferTests(unittest.TestCase):
    load = AdapterTests.load
    def test_separate_detection_value_and_ambiguity_slices(self):
        gold = self.load([source(), source(target_slot_value="<ambiguous>")])
        predictions = [{"example_id": gold[0].example_id, "condition": "none", "request": False, "value": "off"},
                       {"example_id": gold[1].example_id, "condition": "none", "request": True, "value": "<ambiguous>"}]
        report = transfer.build_report(gold, predictions, model_family="gpt")
        self.assertEqual(report["request_recall"], 0.5)
        self.assertEqual(report["value_accuracy"], 1.0)
        self.assertEqual(report["end_to_end"], 0.5)
        self.assertEqual(report["by_ambiguity"]["ambiguous"]["n"], 1)
        self.assertTrue(report["gpt_family"])
        self.assertEqual(report["data_kind"], "llm_generated_transfer")
        self.assertNotIn("lamps", json.dumps(report))

    def test_invalid_and_out_of_candidate_values_fail(self):
        gold = self.load([source()])
        valid = {"example_id": gold[0].example_id, "condition": "none", "request": True, "value": "UNKNOWN"}
        report = transfer.build_report(gold, [valid], model_family="other")
        self.assertEqual(report["value_accuracy"], 0)
        invalid = {"example_id": gold[0].example_id, "condition": "none", "invalid": True}
        report = transfer.build_report(gold, [invalid], model_family="other")
        self.assertEqual((report["invalid_outputs"], report["end_to_end"]), (1, 0))
        for bad in ([], [valid, valid], [{**valid, "condition": "full"}], [{**valid, "request": "true"}],
                    [{**valid, "extra": "x"}], [{**valid, "value": ["False"]}]):
            with self.assertRaises(ValueError):
                transfer.build_report(gold, bad, model_family="other")

    def test_test_split_requires_explicit_opt_in_before_reading_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(transfer.main(["inputs", "--split", "test", "--out", str(Path(tmp) / "out.jsonl")]), 1)
