"""Tests for seg-v1 prior segments and continuations (spec 003 T8). Invented text only."""

from __future__ import annotations

import tempfile
import unittest
from functools import partial
from pathlib import Path

from src.annotation import context_views as cv
from src.data.direct_dataset import Turn, build_context
from src.literary import sources as ls
from tests import literary_fixtures as fx

SENTINEL = "ZEBRA-SENTINEL"


def edition(text: str, units: list[tuple[str, str, str]]) -> ls.Edition:
    """An in-memory edition: each unit is (kind, unit_id suffix, exact unit text) found in ``text``."""
    built, cursor = [], 0
    for kind, suffix, unit_text in units:
        start = text.index(unit_text, cursor)
        cursor = start + len(unit_text)
        built.append(ls.Unit("fixture", f"ep:{suffix}", "ep", kind, suffix, start, cursor))
    return ls.Edition("fixture", "0" * 64, text, tuple(built))


TITLE = "THE HERON AND THE MOLE"
PARA1 = 'A Heron stood by the reeds. "The water is cold,"\r\nsaid the Heron to the Mole, "and my legs ache!" The Mole said nothing.'
PARA2 = f'At last the Heron said, "Dig me a dry hole." The Mole dug. {SENTINEL} in the story.'
MORAL = f"    Herons ask; moles dig. {SENTINEL} moral."
STORY = f"{TITLE}\r\n\r\n{PARA1}\r\n\r\n{PARA2}\r\n\r\n{MORAL}\r\n"
UNITS = [("title", "title", TITLE), ("narrative", "p1", PARA1), ("narrative", "p2", PARA2), ("moral", "p3", MORAL.strip())]


class SentenceTests(unittest.TestCase):
    def test_splits_after_terminal_punctuation_followed_by_whitespace(self) -> None:
        self.assertEqual(cv.sentences("Hi! Who are you? I am here."), ["Hi!", "Who are you?", "I am here."])

    def test_closing_quotes_stay_with_their_sentence(self) -> None:
        self.assertEqual(cv.sentences('He said, "Go." Then he left.'), ['He said, "Go."', "Then he left."])
        self.assertEqual(cv.sentences("“Stay!” she cried. ‘Why?’ he asked."),
                         ["“Stay!”", "she cried.", "‘Why?’", "he asked."])  # fmt: skip

    def test_no_split_without_following_whitespace(self) -> None:
        self.assertEqual(cv.sentences("It costs 3.50 pounds.That is all"), ["It costs 3.50 pounds.That is all"])

    def test_whitespace_is_collapsed_and_empty_pieces_dropped(self) -> None:
        self.assertEqual(cv.sentences("  One line\r\nwrapped.   \r\n  "), ["One line wrapped."])
        self.assertEqual(cv.sentences("   "), [])


class LiteraryPriorTests(unittest.TestCase):
    EDITION = edition(STORY, UNITS)

    def prior(self, target: str) -> list[str]:
        return [segment.text for segment in cv.literary_prior(self.EDITION, "ep", STORY.index(target))]

    def test_mid_paragraph_target_gets_the_earlier_sentences_separately(self) -> None:
        self.assertEqual(
            self.prior('"and my legs ache!"'),
            ["A Heron stood by the reeds.", '"The water is cold," said the Heron to the Mole,'],
        )

    def test_target_in_a_later_paragraph_gets_all_earlier_units(self) -> None:
        segments = cv.literary_prior(self.EDITION, "ep", STORY.index('"Dig me'))
        self.assertEqual([s.index for s in segments], [0, 1, 2, 3])
        self.assertEqual(segments[1].text, '"The water is cold," said the Heron to the Mole, "and my legs ache!"')  # quote kept
        self.assertEqual(segments[-1].text, "At last the Heron said,")
        self.assertTrue(all(segment.speaker == "" for segment in segments))

    def test_nothing_after_the_target_and_no_title_or_moral(self) -> None:
        for target in ('"The water', '"Dig me', "The Mole dug."):
            joined = " ".join(self.prior(target))
            with self.subTest(target=target):
                self.assertNotIn(SENTINEL, joined)
                self.assertNotIn("HERON AND THE MOLE", joined)
                self.assertNotIn("moles dig", joined)

    def test_first_sentence_target_has_no_prior(self) -> None:
        self.assertEqual(self.prior("A Heron stood"), [])

    def test_offset_outside_the_episode_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            cv.literary_prior(self.EDITION, "ep", len(STORY) + 5)

    def test_segments_never_cross_a_unit_boundary(self) -> None:
        # PARA1 ends without a trailing space; its last sentence must not merge with PARA2's first.
        segments = self.prior("The Mole dug.")
        self.assertIn("The Mole said nothing.", segments)
        self.assertIn('At last the Heron said, "Dig me a dry hole."', segments)


class LiteraryContinuationTests(unittest.TestCase):
    EDITION = edition(STORY, UNITS)

    def test_continuation_runs_to_the_episode_end_including_the_moral(self) -> None:
        target = '"and my legs ache!"'
        end = STORY.index(target) + len(target)
        segments = cv.literary_continuation(self.EDITION, "ep", end)
        self.assertEqual(segments[0].text, "The Mole said nothing.")
        self.assertEqual(segments[1].text, PARA2)
        self.assertEqual((segments[2].speaker, segments[2].text), ("moral", f"Herons ask; moles dig. {SENTINEL} moral."))
        self.assertEqual([s.index for s in segments], [0, 1, 2])

    def test_target_ending_its_unit_skips_the_empty_remainder(self) -> None:
        end = STORY.index(PARA1) + len(PARA1)
        self.assertEqual(cv.literary_continuation(self.EDITION, "ep", end)[0].text, PARA2)


class PinnedEditionTests(unittest.TestCase):
    """The same rules on the spec 002 fixture editions, through the real parsers."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        raw_dir, manifest = fx.install_fixture_editions(Path(tmp.name))
        self.aesop = ls.load_edition("aesop_jones1912", raw_dir, manifest)
        parser = partial(ls.parse_kjv, books=fx.KJV_BOOKS)
        kjv_text = fx.KJV_TEXT
        self.kjv = ls.Edition("kjv_pg10", "0" * 64, kjv_text, tuple(parser("kjv_pg10", kjv_text)))

    def test_aesop_mid_paragraph_target(self) -> None:
        text = self.aesop.text
        segments = cv.literary_prior(self.aesop, "aesop:the-owl-and-the-kettle", text.index('"Then fetch'))
        self.assertEqual(
            [s.text for s in segments],
            ['An Owl sat by a cold Kettle and said to the Badger, "The night is long, and my feathers are thin."', "The Badger answered,"],
        )
        continuation = cv.literary_continuation(self.aesop, "aesop:the-owl-and-the-kettle", text.index("sticks.\"") + 8)
        self.assertEqual([(s.speaker, s.text) for s in continuation], [("moral", "Cold owls hint; warm badgers act.")])

    def test_kjv_prior_uses_earlier_verses_of_the_chapter_without_markers(self) -> None:
        text = self.kjv.text
        segments = cv.literary_prior(self.kjv, "kjv:first:1", text.index("The gate is shut."))
        self.assertEqual(
            [s.text for s in segments],
            ["In the first place a gardener came to the gate.", "And the gardener saith unto the keeper,"],
        )
        chapter_two = cv.literary_prior(self.kjv, "kjv:first:2", text.index("What seekest"))
        self.assertEqual([s.text for s in chapter_two], ["Then the keeper said unto him,"])  # episode = chapter


class DialogueViewTests(unittest.TestCase):
    TURNS = [
        Turn("user", "I want a quiet place  to eat."),
        Turn("system", "There are three.\nPick one?"),
        Turn("user", "The cheapest, please."),
        Turn("system", f"{SENTINEL} booked."),
        Turn("user", f"{SENTINEL} thanks."),
    ]

    def test_prior_equals_the_full_context_condition(self) -> None:
        for turn_index in range(len(self.TURNS)):
            item = {"dialogue_id": "X.json", "turn_index": turn_index}
            expected = build_context(item, {"X.json": self.TURNS}, "full")  # type: ignore[arg-type]
            prior = cv.dialogue_prior(self.TURNS, turn_index)
            with self.subTest(turn_index=turn_index):
                self.assertEqual([(s.speaker, s.text) for s in prior], [(t.speaker, t.text) for t in expected])
                self.assertEqual([s.index for s in prior], list(range(turn_index)))

    def test_prior_never_contains_the_target_or_later_turns(self) -> None:
        self.assertNotIn(SENTINEL, cv.render(cv.dialogue_prior(self.TURNS, 2)))
        self.assertNotIn("cheapest", cv.render(cv.dialogue_prior(self.TURNS, 2)))

    def test_continuation_is_numbered_by_turn_index(self) -> None:
        continuation = cv.dialogue_continuation(self.TURNS, 2)
        self.assertEqual([(s.index, s.speaker) for s in continuation], [(3, "system"), (4, "user")])
        self.assertEqual(cv.dialogue_continuation(self.TURNS, 4), [])

    def test_turn_outside_the_dialogue_is_rejected(self) -> None:
        for bad in (-1, 5):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                cv.dialogue_prior(self.TURNS, bad)

    def test_render_is_one_line_per_segment(self) -> None:
        rendered = cv.render(cv.dialogue_prior(self.TURNS, 2))
        self.assertEqual(rendered, "[0] USER: I want a quiet place to eat.\n[1] SYSTEM: There are three. Pick one?")
        self.assertEqual(cv.render([cv.Segment(0, "", "Plain narrative.")]), "[0] Plain narrative.")
        self.assertEqual(cv.render([]), "")


if __name__ == "__main__":
    unittest.main()
