"""Tests for literary edition segmentation and span resolution (spec 002, T2).

Invented fixture text only (tests/literary_fixtures.py).
"""

from __future__ import annotations

import tempfile
import unittest
from functools import partial
from pathlib import Path
from unittest import mock

from src.literary import sources as ls
from tests import literary_fixtures as fx

parse_fixture_kjv = partial(ls.parse_kjv, books=fx.KJV_BOOKS)


def texts(text: str, units: list[ls.Unit]) -> dict[str, str]:
    return {unit.unit_id: text[unit.start : unit.end] for unit in units}


class AesopParserTest(unittest.TestCase):
    def setUp(self) -> None:
        self.units = ls.parse_aesop("aesop_jones1912", fx.AESOP_TEXT)

    def test_fables_titles_narrative_and_morals(self) -> None:
        kinds = [(unit.unit_id, unit.kind) for unit in self.units]
        self.assertEqual(
            kinds,
            [
                ("aesop:the-owl-and-the-kettle:title", "title"),
                ("aesop:the-owl-and-the-kettle:p1", "narrative"),
                ("aesop:the-owl-and-the-kettle:p2", "moral"),
                ("aesop:the-hen-and-the-ladder:title", "title"),
                ("aesop:the-hen-and-the-ladder:p1", "narrative"),
            ],
        )

    def test_offsets_reproduce_exact_trimmed_source_text_with_crlf(self) -> None:
        by_id = texts(fx.AESOP_TEXT, self.units)
        self.assertEqual(by_id["aesop:the-owl-and-the-kettle:title"], "THE OWL AND THE KETTLE")
        self.assertEqual(by_id["aesop:the-owl-and-the-kettle:p2"], "Cold owls hint; warm badgers act.")
        narrative = by_id["aesop:the-owl-and-the-kettle:p1"]
        self.assertTrue(narrative.startswith("An Owl sat"))
        self.assertIn("long,\r\nand my feathers", narrative)
        for unit in self.units:
            self.assertEqual(fx.AESOP_TEXT[unit.start : unit.end], fx.AESOP_TEXT[unit.start : unit.end].strip())

    def test_contents_list_and_illustrations_are_not_fables(self) -> None:
        self.assertEqual(len({unit.episode_id for unit in self.units}), 2)
        self.assertNotIn("[Illustration", "".join(texts(fx.AESOP_TEXT, self.units).values()))

    def test_locators_are_ascii(self) -> None:
        self.assertEqual(self.units[1].locator, "THE OWL AND THE KETTLE, para 1")
        self.assertTrue(all(unit.locator.isascii() for unit in self.units))

    def test_duplicate_title_is_a_parse_error(self) -> None:
        text = fx.AESOP_TEXT.replace("THE HEN AND THE LADDER\r\n\r\n\r\nA Hen", "THE OWL AND THE KETTLE\r\n\r\n\r\nA Hen")
        with self.assertRaisesRegex(ls.ParseError, "duplicate fable title"):
            ls.parse_aesop("aesop_jones1912", text)

    def test_missing_markers_or_region_end_is_a_parse_error(self) -> None:
        with self.assertRaisesRegex(ls.ParseError, "START/END"):
            ls.parse_aesop("aesop_jones1912", fx.AESOP_TEXT.replace("*** END OF", "END"))
        with self.assertRaisesRegex(ls.ParseError, "ILLUSTRATIONS"):
            ls.parse_aesop("aesop_jones1912", fx.AESOP_TEXT.replace("\r\nILLUSTRATIONS\r\n", "\r\nPICTURES\r\n"))

    def test_fable_with_only_a_moral_is_a_parse_error(self) -> None:
        text = fx.AESOP_TEXT.replace("A Hen looked", "    A Hen looked").replace("\r\na fine loft", "\r\n    a fine loft")
        text = text.replace("\r\nsaid the Hen to herself", "\r\n    said the Hen to herself")
        with self.assertRaisesRegex(ls.ParseError, "no narrative paragraph"):
            ls.parse_aesop("aesop_jones1912", text)


class KjvParserTest(unittest.TestCase):
    def setUp(self) -> None:
        self.units = parse_fixture_kjv("kjv_pg10", fx.KJV_TEXT)
        self.by_locator = {unit.locator: fx.KJV_TEXT[unit.start : unit.end] for unit in self.units}

    def test_verses_in_order_with_alias_heading_ignored(self) -> None:
        self.assertEqual(
            [unit.unit_id for unit in self.units],
            ["kjv:first:1:1", "kjv:first:1:2", "kjv:first:1:3", "kjv:first:2:1", "kjv:second:1:1", "kjv:third:1:1"],
        )
        self.assertEqual(self.units[3].episode_id, "kjv:first:2")
        self.assertNotIn("Otherwise Called", "".join(self.by_locator.values()))

    def test_mid_line_markers_split_verses_and_exclude_the_marker(self) -> None:
        self.assertEqual(self.by_locator["First 1:1"], "In the first place a gardener came to the gate.")
        self.assertEqual(self.by_locator["First 1:2"], "And the gardener\r\nsaith unto the keeper, The gate is shut.")
        self.assertEqual(self.by_locator["First 2:1"], "Then the keeper\r\nsaid unto him, What seekest thou?")

    def test_separator_and_testament_heading_end_the_previous_verse(self) -> None:
        self.assertEqual(self.by_locator["Second 1:1"], "A potter dwelt by the river.")

    def test_marker_at_end_of_line(self) -> None:
        text = fx.KJV_TEXT.replace("1:3 And the keeper opened it.", "1:3\r\nAnd the keeper opened it.")
        units = parse_fixture_kjv("kjv_pg10", text)
        verse = next(unit for unit in units if unit.locator == "First 1:3")
        self.assertEqual(text[verse.start : verse.end], "And the keeper opened it.")

    def test_non_sequential_verse_is_a_parse_error(self) -> None:
        with self.assertRaisesRegex(ls.ParseError, "verse 1:4 follows 1:2"):
            parse_fixture_kjv("kjv_pg10", fx.KJV_TEXT.replace("1:3 And the keeper", "1:4 And the keeper"))
        with self.assertRaisesRegex(ls.ParseError, "follows the book heading"):
            parse_fixture_kjv("kjv_pg10", fx.KJV_TEXT.replace("1:1 A potter", "2:1 A potter"))

    def test_contents_must_match_the_book_list(self) -> None:
        with self.assertRaisesRegex(ls.ParseError, "lists 3 books; expected 66"):
            ls.parse_kjv("kjv_pg10", fx.KJV_TEXT)
        with self.assertRaisesRegex(ls.ParseError, "not found in the body"):
            parse_fixture_kjv("kjv_pg10", fx.KJV_TEXT.replace("\r\n\r\nThe Third Book\r\n\r\n1:1", "\r\n\r\nThe Book\r\n\r\n1:1"))

    def test_canonical_book_list_has_66_unique_slugs(self) -> None:
        self.assertEqual(len(ls.KJV_BOOKS), 66)
        self.assertEqual(len({slug for slug, _ in ls.KJV_BOOKS}), 66)


class LoadEditionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.raw_dir, self.manifest = fx.install_fixture_editions(Path(self._tmp.name))

    def test_loads_a_verified_edition_with_episode_helpers(self) -> None:
        edition = ls.load_edition("aesop_jones1912", self.raw_dir, self.manifest)
        self.assertEqual(edition.episode_ids, ("aesop:the-owl-and-the-kettle", "aesop:the-hen-and-the-ladder"))
        start, end = edition.episode_bounds("aesop:the-owl-and-the-kettle")
        self.assertTrue(edition.text[start:end].startswith("THE OWL"))
        self.assertTrue(edition.text[start:end].endswith("act."))
        moral = edition.units_overlapping("aesop:the-owl-and-the-kettle", end - 3, end)
        self.assertEqual([unit.kind for unit in moral], ["moral"])
        with self.assertRaises(ls.LiteraryError):
            edition.episode_units("aesop:nope")

    def test_injected_parser_is_used_for_fixture_bible(self) -> None:
        with mock.patch.dict(ls.PARSERS, {"kjv_pg10": parse_fixture_kjv}):
            edition = ls.load_edition("kjv_pg10", self.raw_dir, self.manifest)
        self.assertEqual(len(edition.units), 6)

    def test_corrupted_file_is_refused_before_parsing(self) -> None:
        path = self.raw_dir / "aesop_jones1912" / "pg11339.txt"
        data = bytearray(path.read_bytes())
        data[-5] ^= 0x01
        path.write_bytes(bytes(data))
        with mock.patch.object(ls, "parse_aesop", side_effect=AssertionError("parsed")):
            with self.assertRaisesRegex(ls.LiteraryError, "does not match the pinned"):
                ls.load_edition("aesop_jones1912", self.raw_dir, self.manifest)

    def test_missing_file_and_unknown_source(self) -> None:
        (self.raw_dir / "kjv_pg10" / "pg10.txt").unlink()
        with self.assertRaisesRegex(ls.LiteraryError, "is missing"):
            ls.load_edition("kjv_pg10", self.raw_dir, self.manifest)
        with self.assertRaisesRegex(ls.LiteraryError, "no literary parser"):
            ls.load_edition("circa", self.raw_dir, self.manifest)


class ResolveSpanTest(unittest.TestCase):
    TEXT = "Then the keeper\r\nsaid unto him, What seekest thou? The keeper said nothing."

    def test_whitespace_insensitive_unique_match(self) -> None:
        start, end = ls.resolve_span(self.TEXT, 0, len(self.TEXT), "keeper said unto  him,")
        self.assertEqual(self.TEXT[start:end], "keeper\r\nsaid unto him,")

    def test_zero_or_multiple_matches_are_rejected(self) -> None:
        with self.assertRaisesRegex(ls.LiteraryError, "does not occur"):
            ls.resolve_span(self.TEXT, 0, len(self.TEXT), "the gardener")
        with self.assertRaisesRegex(ls.LiteraryError, "more than once"):
            ls.resolve_span(self.TEXT, 0, len(self.TEXT), "keeper")
        with self.assertRaisesRegex(ls.LiteraryError, "empty"):
            ls.resolve_span(self.TEXT, 0, len(self.TEXT), "  ")

    def test_word_boundaries_and_region_limits(self) -> None:
        with self.assertRaisesRegex(ls.LiteraryError, "does not occur"):
            ls.resolve_span(self.TEXT, 0, len(self.TEXT), "hen")  # inside "Then" only
        start, _ = ls.resolve_span(self.TEXT, 20, len(self.TEXT), "keeper")
        self.assertGreater(start, 20)

    def test_overlapping_occurrences_count_as_ambiguous(self) -> None:
        with self.assertRaisesRegex(ls.LiteraryError, "more than once"):
            ls.resolve_span("no no no", 0, 8, "no no")

    def test_collapse_whitespace(self) -> None:
        self.assertEqual(ls.collapse_whitespace(" a\r\n  b\tc "), "a b c")


if __name__ == "__main__":
    unittest.main()
