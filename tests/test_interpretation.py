"""Weak act interpretation, strict envelopes and normalization on invented fixtures."""

import unittest

from src.evaluation import interpretation as ip
from tests.test_auto_levels import item


def prediction(example_id="x:indirect", condition="none", **changes):
    return {"example_id": example_id, "condition": condition, "prediction": "indirect",
            "category": "booking", "slots": {"hotel.people": "two"}, "requested_slots": [], **changes}


class ReferenceTests(unittest.TestCase):
    def test_inform_values_and_requested_names_are_distinct(self):
        row = item("D", 2, "x", "y", "z", acts={
            "Hotel-Inform": [["People", "two"], ["Stay", "?"], ["none", "none"]],
            "Hotel-Request": [["Phone", "?"], ["Addr", "?"]],
        })
        gold = ip.reference(row)
        self.assertEqual(gold.category, "info_seeking")
        self.assertEqual(gold.slots, {"hotel.people": "2"})
        self.assertEqual(gold.requested_slots, frozenset({"hotel.phone", "hotel.addr"}))

    def test_conflicting_act_values_are_explicitly_excluded_from_interpretation(self):
        row = item("D", 2, "x", "y", "z", acts={"Hotel-Inform": [["Area", "north"], ["Area", "south"]]})
        gold = ip.reference(row)
        self.assertIsNone(gold.category)
        self.assertEqual(gold.exclusion, "conflicting_act_values")

    def test_normalization_is_conservative_and_slot_specific(self):
        self.assertEqual(ip.normalize_value("hotel.people", "Two"), "2")
        self.assertEqual(ip.normalize_value("restaurant.time", "7 pm"), "19:00")
        self.assertEqual(ip.normalize_value("hotel.area", "city centre"), "centre")
        self.assertEqual(ip.normalize_value("hotel.price", "inexpensive"), "cheap")
        self.assertNotEqual(ip.normalize_value("hotel.name", "The Hill House"), ip.normalize_value("hotel.name", "Hill House"))
        self.assertNotEqual(ip.normalize_value("hotel.name", "One Inn"), ip.normalize_value("hotel.name", "1 Inn"))


class PredictionTests(unittest.TestCase):
    def test_text_export_cannot_escape_ignored_directories(self):
        from pathlib import Path
        root = Path(ip.__file__).resolve().parents[2]
        ip.require_local_text_output(root / "outputs" / "example.jsonl")
        for path in (root / "docs" / "bad.jsonl", root / "outputs" / ".." / "bad.jsonl"):
            with self.assertRaises(ValueError):
                ip.require_local_text_output(path)

    def test_strict_expected_sets(self):
        expected = {"none": {"x:indirect"}, "full": {"x:indirect"}}
        good = [prediction(), prediction(condition="full")]
        self.assertEqual(len(ip.validate_predictions(good, expected)), 2)
        for bad in (good[:1], good + good[:1], good + [prediction(example_id="foreign")],
                    [prediction(extra="bad"), good[1]], [prediction(slots=[]), good[1]],
                    [prediction(requested_slots=["hotel.phone", "hotel.phone"]), good[1]],
                    [prediction(condition="mismatched"), good[1]]):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    ip.validate_predictions(bad, expected)

    def test_invalid_marker_and_semantic_wrong_values(self):
        expected = {"none": {"x:indirect"}}
        invalid = {"example_id": "x:indirect", "condition": "none", "invalid": True}
        self.assertTrue(ip.validate_predictions([invalid], expected)["none"]["x:indirect"]["invalid"])
        self.assertTrue(ip.validate_predictions([prediction(slots={"hotel.people": "wrong"})], expected))
        with self.assertRaises(ValueError):
            ip.validate_predictions([{**invalid, "invalid": "true"}], expected)

    def test_slot_errors_and_empty_denominators(self):
        gold = ip.Reference("booking", {"hotel.people": "2"}, frozenset({"hotel.phone"}))
        outcome = ip.outcome(gold, prediction(slots={"hotel.people": "two"}, requested_slots=["hotel.phone"]))
        self.assertTrue(outcome["exact"])
        self.assertEqual(outcome["slots"], {"correct": 2, "gold": 2, "predicted": 2})
        bad = ip.outcome(gold, prediction(slots={"hotel.people": "3", "hotel.area": "north"}))
        self.assertFalse(bad["exact"])
        self.assertEqual(bad["slots"], {"correct": 0, "gold": 2, "predicted": 2})
        empty = ip.outcome(ip.Reference("booking", {}, frozenset()), prediction(slots={}))
        self.assertTrue(empty["exact"])
        self.assertEqual(empty["slots"]["gold"], 0)
