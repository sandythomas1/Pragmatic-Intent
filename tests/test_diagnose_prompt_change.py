"""The prompt-change diagnosis on invented fixtures: statuses, transitions and what it writes."""

import json
import tempfile
import unittest
from pathlib import Path

from scripts import diagnose_prompt_change as dp
from src.analysis.files import AnalysisError
from src.evaluation import interpretation as ip

ALLOWED = frozenset({"train.leave", "train.dest", "train.depart", "hotel.area", "hotel.phone"})
TRAIN = ip.Reference("booking", {"train.dest": "ely", "train.leave": "09:00"}, frozenset())
HOTEL = ip.Reference("info_seeking", {"hotel.area": "north"}, frozenset({"hotel.phone"}))


def row(category="booking", slots=None, requested=(), **changes):
    return {"example_id": "x", "condition": "none", "prediction": "indirect", "category": category,
            "slots": {} if slots is None else slots, "requested_slots": list(requested), **changes}


EXACT_TRAIN = row(slots={"train.dest": "Ely", "train.leave": "9 am"})


class StatusTests(unittest.TestCase):
    def test_exact_agrees_with_the_stage2_scorer(self):
        self.assertTrue(ip.outcome(TRAIN, EXACT_TRAIN)["exact"])
        self.assertEqual(dp.status(TRAIN, EXACT_TRAIN), "exact")

    def test_each_failure_gets_one_named_status(self):
        cases = {
            "invalid": {"example_id": "x", "condition": "none", "invalid": True},
            "category_wrong": row(category="info_seeking", slots={"train.dest": "ely", "train.leave": "09:00"}),
            "slots_extra": row(slots={"train.dest": "ely", "train.leave": "09:00", "train.depart": "cambridge"}),
            "slots_missing": row(slots={"train.dest": "ely"}),
            "slots_value": row(slots={"train.dest": "ely", "train.leave": "10:00"}),
            "slots_mixed": row(slots={"train.dest": "ely", "train.depart": "09:00"}),
        }
        for expected, prediction in cases.items():
            with self.subTest(expected):
                self.assertEqual(dp.status(TRAIN, prediction), expected)

    def test_requested_slots_count_like_stated_ones(self):
        self.assertEqual(dp.status(HOTEL, row("info_seeking", {"hotel.area": "north"})), "slots_missing")
        self.assertEqual(dp.status(HOTEL, row("info_seeking", {"hotel.area": "north"}, ["hotel.phone"])), "exact")

    def test_group_follows_the_gold_trip_slots(self):
        self.assertEqual(dp.group(TRAIN), "trip")
        self.assertEqual(dp.group(HOTEL), "other")

    def test_extra_names_outside_the_slot_list_are_pooled(self):
        prediction = row(slots={"train.dest": "ely", "train.leave": "09:00", "train.platform": "2", "train.depart": "x"})
        self.assertEqual(dp.extra_keys(TRAIN, prediction, ALLOWED), ["train.depart", dp.UNLISTED_KEY])


class CompareTests(unittest.TestCase):
    def setUp(self):
        self.gold = {"a": TRAIN, "b": TRAIN, "c": HOTEL}
        extra = row(slots={"train.dest": "ely", "train.leave": "09:00", "train.depart": "cambridge"})
        hotel_exact = row("info_seeking", {"hotel.area": "north"}, ["hotel.phone"])
        self.before = {"none": {"a": EXACT_TRAIN, "b": {"invalid": True}, "c": row("info_seeking")}}
        self.after = {"none": {"a": extra, "b": EXACT_TRAIN, "c": hotel_exact}}

    def test_paired_counts_transitions_and_groups(self):
        report = dp.compare({"none": ["a", "b", "c"]}, self.gold, self.before, self.after, ALLOWED)
        entry = report["conditions"]["none"]
        self.assertEqual((entry["n"], entry["lost"], entry["gained"]), (3, 1, 2))
        self.assertEqual(entry["lost_to"], {"slots_extra": 1})
        self.assertEqual(entry["gained_from"], {"invalid": 1, "slots_missing": 1})
        self.assertAlmostEqual(entry["exact_before"], 1 / 3)
        self.assertAlmostEqual(entry["exact_after"], 2 / 3)
        self.assertAlmostEqual(entry["delta"], 1 / 3)
        self.assertEqual(entry["by_group"]["trip"]["lost"], 1)
        self.assertEqual(entry["by_group"]["other"]["gained"], 1)
        self.assertEqual(entry["extra_slot_names"], {"before": [], "after": [["train.depart", 1]]})
        self.assertEqual(report["pooled"], {"n": 3, "lost": 1, "gained": 2, "delta": 1 / 3})

    def test_status_totals_match_the_population(self):
        entry = dp.compare({"none": ["a", "b", "c"]}, self.gold, self.before, self.after, ALLOWED)["conditions"]["none"]
        self.assertEqual(sum(entry["status_before"].values()), 3)
        self.assertEqual(sum(entry["status_after"].values()), 3)

    def test_identical_runs_change_nothing(self):
        entry = dp.compare({"none": ["a", "b", "c"]}, self.gold, self.before, self.before, ALLOWED)["conditions"]["none"]
        self.assertEqual((entry["lost"], entry["gained"], entry["delta"]), (0, 0, 0))

    def test_report_holds_no_example_id_or_slot_value(self):
        text = json.dumps(dp.compare({"none": ["a", "b", "c"]}, self.gold, self.before, self.after, ALLOWED))
        for secret in ('"a"', '"b"', '"c"', "ely", "cambridge", "north", "09:00"):
            self.assertNotIn(secret, text)


class FileTests(unittest.TestCase):
    def test_rows_outside_the_dev_members_are_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "interpretation.jsonl"
            path.write_text(json.dumps(row(example_id="other")) + "\n", encoding="utf-8")
            with self.assertRaises(AnalysisError) as caught:
                dp._rows_by_condition(path, {"none": {"x"}})
            self.assertEqual(caught.exception.code, "not_a_dev_run")

    def test_uncompared_conditions_are_ignored(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "interpretation.jsonl"
            rows = [row(example_id="x"), row(example_id="x", condition="one")]
            path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
            self.assertEqual(set(dp._rows_by_condition(path, {"none": {"x"}})["none"]), {"x"})

    def test_cli_refuses_an_output_outside_outputs(self):
        self.assertEqual(dp.main(["--before", "a", "--after", "b", "--out", "results/report.json"]), 1)


if __name__ == "__main__":
    unittest.main()
