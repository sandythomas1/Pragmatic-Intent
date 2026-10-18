"""Tests for the ``cat-v1`` act-to-category mapping (all values invented)."""

from __future__ import annotations

import unittest

from src.data.intent_categories import category_counts, primary_category, turn_categories


def item(acts: dict | None, split: str = "dev") -> dict:
    return {"split": split, "user_acts": acts}


class CategoryTest(unittest.TestCase):
    def test_single_categories(self) -> None:
        cases = {
            "info_seeking": {"Hotel-Request": [["Phone", "?"]]},
            "booking": {"Restaurant-Inform": [["People", "4"], ["Day", "friday"]]},
            "travel": {"Taxi-Inform": [["Dest", "the station"]]},
            "recommendation": {"Attraction-Inform": [["Area", "north"]]},
            "no_request": {"general-thank": [["none", "none"]]},
        }
        for expected, acts in cases.items():
            with self.subTest(expected=expected):
                self.assertEqual(turn_categories(item(acts)), frozenset({expected}))
                self.assertEqual(primary_category(item(acts)), expected)

    def test_hospital_and_police_are_info_seeking(self) -> None:
        self.assertEqual(primary_category(item({"Police-Inform": [["none", "none"]]})), "info_seeking")

    def test_several_categories_and_precedence(self) -> None:
        acts = {"Train-Inform": [["People", "2"], ["Dest", "a town"]], "Train-Request": [["Ref", "?"]],
                "general-thank": [["none", "none"]]}
        self.assertEqual(turn_categories(item(acts)), frozenset({"info_seeking", "booking", "travel"}))
        self.assertEqual(primary_category(item(acts)), "info_seeking")

    def test_domain_mention_without_slots(self) -> None:
        self.assertEqual(primary_category(item({"Hotel-Inform": [["none", "none"]]})), "recommendation")

    def test_no_acts_is_unknown(self) -> None:
        self.assertIsNone(turn_categories(item({})))
        self.assertIsNone(primary_category(item(None)))

    def test_counts(self) -> None:
        counts = category_counts([item({"Hotel-Request": [["Addr", "?"]]}), item({}), item({"Taxi-Inform": []}, "test")])
        self.assertEqual(counts["primary"]["dev"], {"info_seeking": 1, "(no acts)": 1})
        self.assertEqual(counts["any_of"]["test"], {"travel": 1})


if __name__ == "__main__":
    unittest.main()
