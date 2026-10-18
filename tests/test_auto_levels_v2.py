"""Rule-v2 development uses invented wording, never held-out round-2 items."""

import unittest

from src.data import auto_levels as v1
from src.data import auto_levels_v2 as v2
from tests.test_auto_levels import VOCAB, item


class WordingTests(unittest.TestCase):
    def test_disclosed_error_classes(self):
        cases = {
            "That is everything I needed, thank you.": "NR",
            "That's all for now. Thanks!": "NR",
            "That's all I need, thank you.": "NR",
            "I am all set, goodbye.": "NR",
            "That sounds good to me.": "INF",
            "It works for me.": "INF",
            "What about a bistro?": "L1",
            "Would it be possible to get a ride?": "L1",
            "The bistro would be lovely.": "L2",
            "We were hoping to go to Fernbridge.": "L2",
            "We are free around seven.": "L2",
            "It has been a long and tiring week.": "L3",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(v2.auto_level(text, False, VOCAB).level, expected)

    def test_mixed_requests_still_win(self):
        for text, expected in (
            ("That's all. Could you send the receipt?", "L1"),
            ("Thanks, I need a ride.", "L0"),
            ("What about lunch? Book it please.", "L0"),
        ):
            self.assertEqual(v2.auto_level(text, False, VOCAB).level, expected)

    def test_explicit_dispatch_preserves_v1(self):
        row = item("D", 2, "What about a bistro?", "Book it.", "Could you book it?")
        self.assertEqual(v1.level_item(row, "target", VOCAB).level, "L0")
        self.assertEqual(v1.level_item(row, "target", VOCAB, version="auto-v2").level, "L1")
        with self.assertRaises(ValueError):
            v1.level_item(row, "target", VOCAB, version="auto-v99")

    def test_social_override_and_rubric_examples(self):
        self.assertEqual(v2.auto_level("Anything", True, VOCAB).level, "NR")
        self.assertEqual(v2.auto_level("It's our anniversary tonight and I haven't planned a thing.", False, VOCAB).level, "L3")
        self.assertEqual(v2.auto_level("I need to leave after 8pm.", False, VOCAB).level, "L0")


class SpotcheckTests(unittest.TestCase):
    def test_duplicate_ids_cannot_replace_a_missing_row(self):
        sheet = [{"row_id": "s-001", "verdict": "ok"}] * 2
        key = [{"row_id": "s-001", "rule": "x"}, {"row_id": "s-002", "rule": "x"}]
        with self.assertRaises(ValueError):
            v1.spotcheck_report(sheet, key)

    def test_nonpositive_draw_count_rejected(self):
        with self.assertRaises(ValueError):
            v1.draw_spotcheck([], VOCAB, "L3", 0, 1)

    def test_fresh_draw_excludes_original_v1_turns(self):
        items = [item(f"D{i}", 2, "It has been a long week.", "Book it.", "It has been a tiring week.") for i in range(50)]
        old = v1.draw_spotcheck(items, VOCAB, "L3", 40, v1.DEFAULT_SPOTCHECK_SEED)[1]
        excluded = {(x["item_id"], x["variant"]) for x in old}
        _, key, snapshot = v2.fresh_spotcheck(items, VOCAB, set(), count=5, seed=23)
        by_id = {x["item_id"]: x for x in items}
        old_turns = {x["item_id"] for x in old}
        self.assertTrue(all(x["item_id"] not in old_turns for x in key))
        self.assertTrue(all(by_id[x["item_id"]]["split"] == "dev" for x in key))
        self.assertEqual(snapshot["rules_version"], "auto-v2")
        self.assertEqual(len(excluded), 40)

    def test_freeze_detects_source_change(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "freeze.json"
            v2.freeze(path)
            v2.require_freeze(path)
            path.write_text('{"rules_version":"auto-v2","rules_sha256":"changed"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                v2.require_freeze(path)

    def test_stage1_rescoring_records_the_selected_version(self):
        from src.evaluation.stage1 import build_report
        from tests.test_stage2 import examples
        example = examples()[0]
        report = build_report([example], [{"example_id": example.example_id, "condition": "none", "prediction": "indirect"}],
                              slices={"rule_level": {example.example_id: "L3"}}, bootstrap_samples=10,
                              rules_version="auto-v2")
        self.assertEqual(report["slices"]["rule_level"]["version"], "auto-v2")
