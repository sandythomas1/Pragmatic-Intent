"""Tests for the DIRECT fact-drift audit.

Hand-written sentences and a tiny fixed vocabulary only: no real DIRECT text.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from src.data import audit_fact_drift as fd
from src.data.audit_fact_drift import Vocabulary, compare_slot, extract_mentions

VOCAB = Vocabulary(
    places=frozenset({"cambridge", "norwich", "stansted airport", "cambridge belfry", "cherry hinton village centre"}),
    foods=frozenset({"indian", "italian", "asian oriental", "north american", "gastropub", "british", "english"}),
)


def values(text: str, slot: str) -> list[set[str]]:
    return [set(mention) for mention in extract_mentions(text, VOCAB)[slot]]


def item(item_id: str, target: str, direct: str, indirect: str, acts: dict | None = None) -> dict:
    return {
        "item_id": item_id,
        "split": "test",
        "target_utterance": target,
        "direct_utterance": direct,
        "indirect_utterance": indirect,
        "user_acts": acts or {},
    }


class BuildVocabularyTest(unittest.TestCase):
    def test_keeps_frequent_names_and_drops_rare_and_stoplisted_ones(self) -> None:
        acts = {
            "Train-Inform": [["Dest", "Norwich"], ["Depart", "the place"]],
            "Restaurant-Inform": [["Food", "Indian"], ["Name", "rare bistro"], ["Food", "dont care"]],
        }
        items = [item(f"x{i}", "", "", "", acts) for i in range(fd.MIN_VOCAB_COUNT)]
        items.append(item("y", "", "", "", {"Restaurant-Inform": [["Name", "once only"]]}))

        vocab = fd.build_vocabulary(items)

        self.assertIn("norwich", vocab.places)
        self.assertIn("rare bistro", vocab.places)
        self.assertNotIn("the place", vocab.places)
        self.assertNotIn("once only", vocab.places)
        self.assertIn("indian", vocab.foods)
        self.assertNotIn("dont care", vocab.foods)

    def test_food_synonyms_are_always_in_the_vocabulary(self) -> None:
        vocab = fd.build_vocabulary([])
        self.assertTrue(set(fd.FOOD_SYNONYMS) <= vocab.foods)

    def test_items_without_acts_are_fine(self) -> None:
        self.assertEqual(fd.build_vocabulary([{"item_id": "z"}]), Vocabulary(frozenset(), frozenset(fd.FOOD_SYNONYMS)))


class ExtractTimeTest(unittest.TestCase):
    def test_24_hour_times_with_any_separator(self) -> None:
        self.assertEqual(values("Leave at 18:30, or 18;45, or 13.00", "time"), [{"18:30"}, {"18:45"}, {"13:00"}])

    def test_am_pm(self) -> None:
        self.assertEqual(values("at 6:30pm or 7 p.m. or 9 am or 12 am", "time"), [{"18:30"}, {"19:00"}, {"09:00"}, {"00:00"}])

    def test_twelve_hour_time_without_meridiem_is_ambiguous(self) -> None:
        self.assertEqual(values("around 3.15", "time"), [{"03:15", "15:15"}])

    def test_zero_padded_time_is_not_ambiguous(self) -> None:
        self.assertEqual(values("after 06:00", "time"), [{"06:00"}])

    def test_bare_numbers_prices_and_invalid_times_are_skipped(self) -> None:
        self.assertEqual(values("for 7 people, 3 nights, costs £3.50, at 25:00 or 9:75", "time"), [])


class ExtractNamesTest(unittest.TestCase):
    def test_longest_place_wins_and_article_is_dropped(self) -> None:
        self.assertEqual(values("Book the Cambridge Belfry please", "place"), [{"cambridge belfry"}])

    def test_place_names_are_masked_before_areas(self) -> None:
        text = "Get me to Cherry Hinton Village Centre"
        self.assertEqual(values(text, "place"), [{"cherry hinton village centre"}])
        self.assertEqual(values(text, "area"), [])

    def test_food_names_are_masked_before_areas(self) -> None:
        self.assertEqual(values("Some north american food", "food"), [{"north american"}])
        self.assertEqual(values("Some north american food", "area"), [])

    def test_plural_matches_but_partial_words_do_not(self) -> None:
        self.assertEqual(values("Any gastropubs?", "food"), [{"gastropub"}])
        self.assertEqual(values("Very gastropubby", "food"), [])
        self.assertEqual(values("the eastern side", "area"), [{"east"}])
        self.assertEqual(values("at least", "area"), [])

    def test_food_synonyms_are_canonical(self) -> None:
        self.assertEqual(values("English food", "food"), [{"british"}])

    def test_closed_lexicons(self) -> None:
        mentions = extract_mentions("A moderately priced place in the center on Friday", VOCAB)
        self.assertEqual(mentions["price"], [frozenset({"moderate"})])
        self.assertEqual(mentions["area"], [frozenset({"centre"})])
        self.assertEqual(mentions["day"], [frozenset({"friday"})])


class GuardTest(unittest.TestCase):
    def test_negation_blocks_an_assertion(self) -> None:
        self.assertEqual(values("I do not want anything expensive", "price"), [])

    def test_contractions_are_tokenized(self) -> None:
        for text in ("I don't want it expensive", "I dont want it expensive", "I don’t want it expensive", "I don�t want it expensive"):
            with self.subTest(text=text):
                self.assertEqual(values(text, "price"), [])

    def test_guard_is_limited_to_the_window(self) -> None:
        self.assertEqual(values("I don't want to stay in the north", "area"), [])
        self.assertEqual(values("No really I think the best is the north", "area"), [{"north"}])

    def test_clause_break_ends_a_guard(self) -> None:
        self.assertEqual(values("No, the north please", "area"), [{"north"}])
        self.assertEqual(values("Not that one. Friday works", "day"), [{"friday"}])

    def test_guard_carries_over_coordination(self) -> None:
        self.assertEqual(values("Not cheap or moderate", "price"), [])
        self.assertEqual(values("anything other than north, east, west", "area"), [])
        self.assertEqual(values("Not cheap, but I love Friday", "day"), [{"friday"}])

    def test_slot_specific_guards(self) -> None:
        self.assertEqual(values("the day after Monday", "day"), [])
        self.assertEqual(values("leave after 14:15", "time"), [{"14:15"}])  # "after" guards days, not times
        self.assertEqual(values("far from the west", "area"), [])
        self.assertEqual(values("something less expensive", "price"), [])
        self.assertEqual(values("earlier than 21:36", "time"), [])


class CompareSlotTest(unittest.TestCase):
    @staticmethod
    def m(*values: str) -> frozenset[str]:
        return frozenset(values)

    def test_no_target_value_means_no_outcome(self) -> None:
        self.assertIsNone(compare_slot([], [self.m("monday")]))

    def test_kept_dropped_substituted(self) -> None:
        self.assertEqual(compare_slot([self.m("monday")], [self.m("monday")]), "kept")
        self.assertEqual(compare_slot([self.m("monday")], []), "dropped")
        self.assertEqual(compare_slot([self.m("monday")], [self.m("tuesday")]), "substituted")

    def test_adding_a_value_without_losing_one_is_kept(self) -> None:
        self.assertEqual(compare_slot([self.m("monday")], [self.m("monday"), self.m("tuesday")]), "kept")

    def test_losing_one_of_two_without_a_replacement_is_dropped(self) -> None:
        self.assertEqual(compare_slot([self.m("monday"), self.m("sunday")], [self.m("monday")]), "dropped")

    def test_ambiguous_times_match_either_reading(self) -> None:
        self.assertEqual(compare_slot([self.m("15:15")], [self.m("03:15", "15:15")]), "kept")
        self.assertEqual(compare_slot([self.m("15:15")], [self.m("04:15", "16:15")]), "substituted")

    def test_nested_names_match_only_when_enabled(self) -> None:
        target, rewrite = [self.m("asian oriental")], [self.m("asian")]
        self.assertEqual(compare_slot(target, rewrite, nested=True), "kept")
        self.assertEqual(compare_slot(target, rewrite, nested=False), "substituted")


class AuditTest(unittest.TestCase):
    ITEMS = [
        item(
            "A_t02",
            "I will travel to Norwich on Thursday at 18:30.",
            "I want to get to Norwich on Tuesday at 18:30",  # day substituted
            "Norwich, Thursday, half six-ish works for me",  # time dropped only
        ),
        item(
            "B_t00",
            "A cheap place in the north, Indian food.",
            "Find a cheap Indian place in the south.",  # area substituted: counted, not flagged
            "USER: I could go for Italian, nothing pricey.",  # food substituted; speaker prefix
        ),
        item("C_t04", "Thanks, bye!", "That's all, thanks.", "Cheers."),  # no slots at all
    ]

    def test_audit_item_reports_outcomes_per_variant(self) -> None:
        outcomes = fd.audit_item(self.ITEMS[0], VOCAB)
        self.assertEqual(outcomes["direct"], {"place": "kept", "day": "substituted", "time": "kept"})
        self.assertEqual(outcomes["indirect"], {"place": "kept", "day": "kept", "time": "dropped"})

    def test_run_audit_flags_only_flag_slots(self) -> None:
        flagged, summary = fd.run_audit(self.ITEMS, VOCAB)

        self.assertEqual(
            [(record["item_id"], record["variant"], sorted(record["slots"])) for record in flagged],
            [("A_t02", "direct", ["day"]), ("B_t00", "indirect", ["food"])],
        )
        self.assertEqual(flagged[0]["slots"]["day"], {"target": ["thursday"], "rewrite": ["tuesday"]})
        self.assertEqual(summary["slot_outcomes"]["direct"]["area"]["substituted"], 1)
        self.assertEqual(summary["flagged"]["direct"], {"count": 1, "fraction": round(1 / 3, 4)})
        self.assertEqual(summary["speaker_prefix"], {"target": 0, "direct": 0, "indirect": 1})
        self.assertEqual(summary["flag_slots"], list(fd.FLAG_SLOTS))

    def test_run_audit_on_no_items(self) -> None:
        flagged, summary = fd.run_audit([], VOCAB)
        self.assertEqual(flagged, [])
        self.assertEqual(summary["flagged"]["direct"], {"count": 0, "fraction": 0.0})

    def test_speaker_prefix(self) -> None:
        self.assertTrue(fd.has_speaker_prefix("USER: hello"))
        self.assertTrue(fd.has_speaker_prefix("  SER : hello"))
        self.assertFalse(fd.has_speaker_prefix("The user: hello"))


class OutputAndCliTest(unittest.TestCase):
    def test_write_then_load_flags_round_trips(self) -> None:
        flagged, summary = fd.run_audit(AuditTest.ITEMS, VOCAB)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            fd.write_outputs(out, flagged, summary)
            self.assertEqual(fd.load_flags(out / "fact_drift.jsonl"), {("A_t02", "direct"), ("B_t00", "indirect")})
            self.assertEqual(json.loads((out / "fact_drift_summary.json").read_text(encoding="utf-8")), summary)

    def test_main_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            items_path = Path(tmp) / "items.jsonl"
            items_path.write_text("".join(json.dumps(record) + "\n" for record in AuditTest.ITEMS), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                code = fd.main(["--items", str(items_path), "--out-dir", tmp])
            self.assertEqual(code, 0)
            self.assertTrue((Path(tmp) / "fact_drift.jsonl").exists())
            self.assertTrue((Path(tmp) / "fact_drift_summary.json").exists())

    def test_main_reports_a_missing_items_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertLogs(fd.logger, level="ERROR"):
                code = fd.main(["--items", str(Path(tmp) / "missing.jsonl"), "--out-dir", tmp])
            self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
