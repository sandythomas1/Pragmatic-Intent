"""Spec 004 rendering, budget, sets, cue flags, checks and manifest, using invented data only."""

from __future__ import annotations

import unittest
from typing import Any

from src.data.audit_fact_drift import Vocabulary
from src.data.contexts import (BUDGET_WORDS, CueFlags, Rendered, cue_flags, genuine, in_mismatch_set, input_sha256,
                               render, render_context, target_sha256, target_values)
from src.data.direct_dataset import CONDITIONS, Turn

VOCAB = Vocabulary(places=frozenset({"cambridge", "broxbourne"}), foods=frozenset({"chinese"}))

SENTINELS = ("ORIGTARGET", "LATERTURN", "OTHERVARIANT", "ACTVALUE")


def dialogues() -> dict[str, list[Turn]]:
    return {
        "d1.json": [Turn("user", "hello there"), Turn("system", "how can I help"),
                    Turn("user", "ORIGTARGET original wording"), Turn("system", "LATERTURN reply"),
                    Turn("user", "LATERTURN thanks")],
        "d2.json": [Turn("user", "a taxi please"), Turn("system", "where to"),
                    Turn("user", "the station"), Turn("system", "booked")],
    }


def item(item_id: str = "d1_t02", dialogue: str = "d1.json", turn: int = 2, split: str = "dev",
         donor: str | None = "d2.json", **extra: Any) -> dict[str, Any]:
    record = {"item_id": item_id, "dialogue_id": dialogue, "turn_index": turn, "split": split,
              "target_utterance": "ORIGTARGET original wording", "direct_utterance": "Find me a hotel.",
              "indirect_utterance": "OTHERVARIANT a hotel would be nice.", "turn_domains": ["hotel"],
              "active_domains": ["hotel"], "user_acts": {"Hotel-Inform": [["Name", "actvalue"]]},
              "quality_labels": None,
              "mismatch": {"donor_dialogue_id": donor, "start": 0, "length": turn} if donor and turn else None,
              "mismatch_status": "ok" if donor and turn else ("not_needed" if not turn else "unavailable")}
    record.update(extra)
    return record


class RenderTest(unittest.TestCase):
    def test_conditions_show_prior_turns_and_keep_the_target(self) -> None:
        source = item()
        rendered = {c: render(source, "Find me a hotel.", dialogues(), c) for c in CONDITIONS}
        self.assertEqual(rendered["none"].context, "")
        self.assertEqual(rendered["one"].context, "System: how can I help")
        self.assertEqual(rendered["full"].context, "User: hello there\nSystem: how can I help")
        self.assertEqual(rendered["mismatched"].context, "User: a taxi please\nSystem: where to")
        self.assertEqual(rendered["mismatched_one"].context, "System: where to")
        self.assertEqual({r.target for r in rendered.values()}, {"Find me a hotel."})
        self.assertEqual({r.dropped for r in rendered.values()}, {0})

    def test_no_future_evidence_reaches_any_context(self) -> None:
        source = item()
        source["user_acts"] = {"Hotel-Inform": [["Name", "ACTVALUE"]]}
        for condition in CONDITIONS:
            context = render(source, source["direct_utterance"], dialogues(), condition).context
            for sentinel in SENTINELS:
                self.assertNotIn(sentinel, context, (condition, sentinel))

    def test_budget_drops_oldest_whole_turns_and_never_the_target(self) -> None:
        turns = {"d1.json": [Turn("user", "one two three"), Turn("system", "four five"),
                             Turn("user", "six"), Turn("system", "seven eight nine ten"), Turn("user", "x")]}
        source = item(turn=4, donor=None)
        # Lines are 4, 3, 2 and 5 words; the target is 2 words.
        full = render(source, "the target", turns, "full", budget=9)
        self.assertEqual((full.context, full.dropped), ("User: six\nSystem: seven eight nine ten", 2))
        self.assertEqual(full.target, "the target")
        exact = render(source, "the target", turns, "full", budget=16)
        self.assertEqual(exact.dropped, 0)
        tight = render(source, "the target", turns, "full", budget=15)
        self.assertEqual(tight.dropped, 1)
        over = render(source, "a target longer than the budget", turns, "full", budget=3)
        self.assertEqual((over.turns, over.context, over.dropped), ((), "", 4))
        self.assertEqual(render(source, "the target", turns, "one", budget=3).context,
                         "System: seven eight nine ten")  # one-turn conditions are never budgeted
        with self.assertRaises(ValueError):
            render(source, "the target", turns, "full", budget=0)

    def test_mismatch_budget_applies_to_the_donor_window(self) -> None:
        source = item()
        rendered = render(source, "Find me a hotel.", dialogues(), "mismatched", budget=8)
        self.assertEqual((rendered.context, rendered.dropped), ("System: where to", 1))
        self.assertEqual(render(source, "Find me a hotel.", dialogues(), "mismatched_one", budget=1).context,
                         "System: where to")

    def test_default_budget_is_the_d06_value(self) -> None:
        self.assertEqual(BUDGET_WORDS, 350)
        long_turn = Turn("system", " ".join(["w"] * 400))
        source = item(turn=2, donor=None)
        rendered = render(source, "short", {"d1.json": [Turn("user", "hi"), long_turn, Turn("user", "t")]}, "full")
        self.assertEqual((rendered.context, rendered.dropped), ("", 2))  # oldest first, then the long turn

    def test_missing_donor_is_undefined_only_for_mismatch_conditions(self) -> None:
        source = item(donor=None)
        self.assertIsNone(render(source, "x", dialogues(), "mismatched"))
        self.assertIsNone(render(source, "x", dialogues(), "mismatched_one"))
        self.assertEqual(render(source, "x", dialogues(), "full").context,
                         "User: hello there\nSystem: how can I help")

    def test_hashes_are_pinned_and_sensitive(self) -> None:
        rendered = Rendered((), "System: hi", "Book it.", 0)
        # Independently checked: printf '%s' '{"context":"System: hi","target":"Book it."}' | shasum -a 256
        self.assertEqual(input_sha256(rendered), "6bd1cb65b26aae6ed8306855fd69267973bce9e703e6a373a01ecf692f6bd338")
        self.assertEqual(target_sha256("Book it."), "9add10a61972898e77495504f19ee0291d6438f9bf652975bf56bc7c8af22fce")
        self.assertNotEqual(input_sha256(rendered), input_sha256(Rendered((), "System: hi!", "Book it.", 0)))
        self.assertNotEqual(input_sha256(rendered), input_sha256(Rendered((), "System: hi", "Book it", 0)))

    def test_sets(self) -> None:
        self.assertFalse(genuine(item(turn=0)))
        self.assertTrue(genuine(item(donor=None)))
        self.assertFalse(in_mismatch_set(item(donor=None)))
        self.assertTrue(in_mismatch_set(item()))
        self.assertEqual(render_context([]), "")



class CueFlagTest(unittest.TestCase):
    ACTS = {"Train-Inform": [["Day", "monday"], ["Dest", "Cambridge"], ["Leave", "do nt care"]],
            "Restaurant-Inform": [["Price", "2"], ["Food", "chinese"]]}

    def flags(self, donor_turns: list[Turn], full_turns: list[Turn] | None = None, budget: int = BUDGET_WORDS) -> CueFlags:
        source = item(user_acts=self.ACTS)
        turns = dialogues()
        turns["d2.json"] = donor_turns + [Turn("user", "u"), Turn("system", "s")]
        if full_turns is not None:
            turns["d1.json"] = full_turns + turns["d1.json"][2:]
        rendered = {c: render(source, "Find me a train.", turns, c, budget) for c in CONDITIONS}
        return cue_flags(source, rendered, turns, VOCAB)

    def test_target_values_skip_dont_care_and_impossible_values(self) -> None:
        self.assertEqual(target_values(item(user_acts=self.ACTS)),
                         {"day": {"monday"}, "place": {"cambridge"}, "food": {"chinese"}})

    def test_donor_cue_is_flagged_per_mismatch_condition(self) -> None:
        last = self.flags([Turn("user", "a taxi please"), Turn("system", "for monday then")])
        self.assertEqual((last.donor_cue, last.donor_cue_one), (True, True))
        earlier = self.flags([Turn("user", "on monday please"), Turn("system", "where to")])
        self.assertEqual((earlier.donor_cue, earlier.donor_cue_one), (True, False))
        clean = self.flags([Turn("user", "a taxi please"), Turn("system", "where to")])
        self.assertEqual(clean, CueFlags(False, False, False))
        guarded = self.flags([Turn("user", "not on monday"), Turn("system", "the day after monday")])
        self.assertEqual((guarded.donor_cue, guarded.donor_cue_one), (False, False))

    def test_dropped_cue_flags_a_budget_removed_turn_naming_a_target_value(self) -> None:
        full = [Turn("user", "I am going to cambridge"), Turn("system", "fine")]
        dropped = self.flags([Turn("user", "a taxi please"), Turn("system", "where to")], full, budget=8)
        self.assertTrue(dropped.dropped_cue)
        kept = self.flags([Turn("user", "a taxi please"), Turn("system", "where to")], full)
        self.assertFalse(kept.dropped_cue)

    def test_items_without_a_donor_have_no_donor_flags(self) -> None:
        source = item(donor=None, user_acts=self.ACTS)
        rendered = {c: render(source, "x", dialogues(), c) for c in CONDITIONS}
        self.assertEqual(cue_flags(source, rendered, dialogues(), VOCAB), CueFlags(False, False, False))


if __name__ == "__main__":
    unittest.main()
