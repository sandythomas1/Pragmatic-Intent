"""Tests for the ``auto-v1`` wording rules (all text invented)."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from src.data.audit_fact_drift import Vocabulary
from src.data.auto_levels import (
    auto_level, distribution, draw_spotcheck, load_human_labels, main, spotcheck_report, validate,
)
from src.evaluation.metrics import cohen_kappa

VOCAB = Vocabulary(places=frozenset({"riverside inn"}), foods=frozenset({"thai"}))


def level(text: str, social_only: bool = False) -> str:
    return auto_level(text, social_only, VOCAB).level


def item(dialogue: str, turn: int, target: str, direct: str, indirect: str, split: str = "dev",
         acts: dict | None = None) -> dict:
    return {
        "item_id": f"{dialogue}_t{turn:02d}", "dialogue_id": f"{dialogue}.json", "turn_index": turn, "split": split,
        "target_utterance": target, "direct_utterance": direct, "indirect_utterance": indirect,
        "user_acts": {"Hotel-Inform": [["Area", "north"]]} if acts is None else acts,
    }


class RubricExamplesTest(unittest.TestCase):
    """Every invented example in rubric v2 gets its documented label."""

    def test_rubric_table(self) -> None:
        cases = {
            "Book a table for two.": "L0",
            "I need a train after 6pm.": "L0",
            "What's the hotel's phone number?": "L0",
            "Could you book a table for two?": "L1",
            "Can I get the phone number?": "L1",
            "Would you mind checking trains after 6?": "L1",
            "There are two of us, and we're free around seven.": "L2",
            "I still don't have the hotel's number.": "L2",
            "It's our anniversary tonight and I haven't planned a thing.": "L3",
            "No preference on the area.": "INF",
            "Just the two of us.": "INF",
            "No need to book, I was just asking.": "NR",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(level(text), expected)

    def test_settled_rules(self) -> None:
        cases = {
            "I'm looking for a cheap hotel.": "L0",  # R5
            "I'd like to find a museum.": "L0",  # R5
            "Can you find an attraction in the centre?": "L1",  # R7
            "How about a gastropub then?": "L1",  # R7
            "Find me a pool nearby.": "L0",  # R7
            "5 people on Wednesday at 7.": "INF",  # R3
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(level(text), expected)


class PrecedenceTest(unittest.TestCase):
    def test_most_direct_request_wins(self) -> None:
        self.assertEqual(level("Pick one. I need the times."), "L0")
        self.assertEqual(level("Could you check? I need it by Friday."), "L0")
        self.assertEqual(level("Thanks. Can you help me with a taxi?"), "L1")

    def test_social_acts_override_wording(self) -> None:
        self.assertEqual(level("Can you believe how helpful that was?", social_only=True), "NR")

    def test_polite_command_is_l0(self) -> None:
        self.assertEqual(level("Please send the address."), "L0")
        self.assertEqual(level("Yes, please book it."), "L0")

    def test_negated_need_is_a_decline_not_a_request(self) -> None:
        self.assertEqual(level("I don't need a booking."), "NR")

    def test_subordinate_wh_clause_is_not_a_question(self) -> None:
        self.assertEqual(level("When I arrive on Monday, it will be late."), "L2")

    def test_hint_levels(self) -> None:
        self.assertEqual(level("The riverside inn sounded lovely."), "L2")
        self.assertEqual(level("Thai sounds lovely to me."), "L2")
        self.assertEqual(level("It has been a long and tiring week."), "L3")

    def test_bare_answer_is_inf(self) -> None:
        self.assertEqual(level("Yes."), "INF")
        self.assertEqual(level("Okay, sounds good!"), "INF")

    def test_curly_apostrophes(self) -> None:
        self.assertEqual(level("I’m looking for a hotel."), "L0")


class KappaTest(unittest.TestCase):
    def test_values(self) -> None:
        self.assertEqual(cohen_kappa([("a", "a"), ("b", "b")]), 1.0)
        self.assertAlmostEqual(cohen_kappa([("a", "a"), ("a", "b"), ("b", "a"), ("b", "b")]), 0.0)
        self.assertEqual(cohen_kappa([("a", "a"), ("a", "a")]), 1.0)

    def test_empty(self) -> None:
        with self.assertRaises(ValueError):
            cohen_kappa([])


class ValidationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.items = [
            item("D1", 2, "I need a hotel.", "Find me a hotel.", "Could you find a hotel?"),
            item("D2", 4, "Thanks, bye.", "Thank you.", "Cheers.", acts={"general-thank": [["none", "none"]]}),
        ]
        self.labels = self.root / "levels_round9.csv"
        with self.labels.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["item_id", "dialogue_id", "turn_index", "variant", "label_initial", "label_final",
                             "fragment", "annotator", "rubric_version"])
            writer.writerow(["r9-01", "D1.json", 2, "target", "L2", "L0", 0, "A1", "v2"])
            writer.writerow(["r9-02", "D1.json", 2, "indirect", "L1", "L1", 0, "A1", "v2"])
            writer.writerow(["r9-03", "D2.json", 4, "direct", "NR", "NR", 0, "A1", "v2"])
            writer.writerow(["r9-04", "D2.json", 4, "target", "NR", "NR", 0, "B2", "v2"])

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_agreement(self) -> None:
        labels = load_human_labels([self.labels])
        self.assertEqual(len(labels), 3)  # the other annotator's row is ignored
        report = validate(self.items, labels, VOCAB)
        pooled = report["agreement"]["all"]
        self.assertEqual(pooled["n"], 3)
        self.assertEqual(pooled["final"]["accuracy"], 1.0)
        self.assertAlmostEqual(pooled["initial"]["accuracy"], 2 / 3, places=4)
        self.assertIn("round9", report["agreement"])

    def test_missing_item_is_an_error(self) -> None:
        with self.assertRaises(ValueError):
            validate(self.items[1:], load_human_labels([self.labels]), VOCAB)

    def test_invalid_label_is_an_error(self) -> None:
        bad = self.root / "levels_round8.csv"
        bad.write_text(self.labels.read_text(encoding="utf-8").replace(",L1,L1,", ",L9,L1,"), encoding="utf-8")
        with self.assertRaises(ValueError):
            load_human_labels([bad])

    def test_distribution_skips_items_without_acts(self) -> None:
        items = self.items + [item("D3", 1, "Hello.", "Hi.", "Hey.", acts={})]
        counts = distribution(items, VOCAB)["levels"]["dev"]
        self.assertEqual(sum(counts["target"].values()), 2)
        self.assertEqual(counts["indirect"]["L1"], 1)
        self.assertEqual(counts["direct"]["NR"], 1)

    def test_cli_outputs_hold_no_text(self) -> None:
        items_path = self.root / "items.jsonl"
        items_path.write_text("".join(json.dumps(i) + "\n" for i in self.items), encoding="utf-8")
        out_dir = self.root / "out"
        for command in ("validate", "distribution"):
            code = main([command, "--items", str(items_path), "--annotations", str(self.root), "--out-dir", str(out_dir)])
            self.assertEqual(code, 0)
            written = (out_dir / f"{command}.json").read_text(encoding="utf-8")
            for record in self.items:
                for key in ("target_utterance", "direct_utterance", "indirect_utterance"):
                    self.assertNotIn(record[key], written)

    def test_cli_reports_missing_labels(self) -> None:
        items_path = self.root / "items.jsonl"
        items_path.write_text("", encoding="utf-8")
        empty = self.root / "empty"
        empty.mkdir()
        self.assertEqual(main(["validate", "--items", str(items_path), "--annotations", str(empty)]), 1)


class SpotCheckTest(unittest.TestCase):
    ITEMS = [
        item("D1", 1, "It has been a long week.", "Book a hotel.", "What a lovely evening it was."),
        item("D2", 1, "Nothing planned yet, sadly.", "Find a taxi.", "-It was quite a day."),
        item("D3", 1, "Such a long day it was.", "Find a pool.", "We were all tired.", split="test"),
    ]

    def test_draw_is_dev_only_seeded_and_blinded(self) -> None:
        sheet, key = draw_spotcheck(self.ITEMS, VOCAB, "L3", 3, seed=1)
        self.assertEqual(sheet, draw_spotcheck(self.ITEMS, VOCAB, "L3", 3, seed=1)[0])
        self.assertTrue(all(row["item_id"].startswith(("D1", "D2")) for row in key))
        self.assertNotIn("variant", sheet[0])
        self.assertTrue(any(row["utterance"].startswith("'-") for row in sheet))  # formula-escaped

    def test_draw_skips_labeled_turns_and_checks_pool(self) -> None:
        with self.assertRaises(ValueError):
            draw_spotcheck(self.ITEMS, VOCAB, "L3", 3, seed=1, exclude_turns={("D1.json", 1)})
        with self.assertRaises(ValueError):
            draw_spotcheck(self.ITEMS, VOCAB, "L9", 1, seed=1)

    def test_report(self) -> None:
        sheet, key = draw_spotcheck(self.ITEMS, VOCAB, "L3", 2, seed=1)
        sheet[0].update(verdict="OK")
        sheet[1].update(verdict="wrong", better_level="inf")
        report = spotcheck_report(sheet, key)
        self.assertEqual((report["ok"], report["wrong"], report["precision"]), (1, 1, 0.5))
        self.assertEqual(report["better_level_when_wrong"], {"INF": 1})

    def test_report_rejects_incomplete_rows(self) -> None:
        sheet, key = draw_spotcheck(self.ITEMS, VOCAB, "L3", 2, seed=1)
        sheet[0].update(verdict="ok")
        sheet[1].update(verdict="wrong")  # no better_level
        with self.assertRaises(ValueError):
            spotcheck_report(sheet, key)
        sheet[1].update(verdict="maybe")
        with self.assertRaises(ValueError):
            spotcheck_report(sheet, key)

    def test_cli_refuses_to_overwrite_a_sheet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            items_path = root / "items.jsonl"
            items_path.write_text("".join(json.dumps(i) + "\n" for i in self.ITEMS), encoding="utf-8")
            argv = ["spotcheck", "--items", str(items_path), "--annotations", str(root), "--count", "2",
                    "--spotcheck-dir", str(root / "sc")]
            self.assertEqual(main(argv), 0)
            self.assertTrue((root / "sc" / "spotcheck_L3" / "key.csv").exists())
            self.assertEqual(main(argv), 1)


if __name__ == "__main__":
    unittest.main()
