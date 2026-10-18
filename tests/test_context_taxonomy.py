"""Tests for the versioned intent taxonomy and slot checks (spec 003 T6). Invented values only."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.annotation import context as ctx
from src.annotation import context_schema as cs
from src.annotation import context_taxonomy as ct
from src.annotation.levels import write_csv
from tests import context_fixtures as fx


def row(version: str = "ctx-tax-v0", intent: str = "find_hotel", stratum: str = "dialogue",
        required: str = "area", optional: str = "price;stars", description: str = "Look for a hotel") -> dict[str, str]:  # fmt: skip
    return {
        "taxonomy_version": version,
        "intent_id": intent,
        "stratum": stratum,
        "required_slots": required,
        "optional_slots": optional,
        "description": description,
    }


ROWS = [
    row(),
    row(intent="give", stratum="literary", required="", optional="", description="Hand something over"),
    row(intent="joint_action", stratum="both", required="", optional="", description="Propose doing it together"),
    row(version="ctx-tax-v1", intent="find_hotel", required="area;price", optional="", description="Look for a hotel"),
]


class TaxonomyValidationTests(unittest.TestCase):
    def problems(self, *rows: dict[str, str]) -> str:
        return "\n".join(ct.validate_rows(list(rows)))

    def test_valid_rows(self) -> None:
        self.assertEqual(ct.validate_rows(ROWS), [])

    def test_duplicate_intent_within_a_version(self) -> None:
        self.assertIn("duplicate intent", self.problems(row(), row(description="Again")))

    def test_same_intent_in_two_versions_is_fine(self) -> None:
        self.assertEqual(ct.validate_rows([row(), row(version="ctx-tax-v1")]), [])

    def test_field_rules(self) -> None:
        cases = {
            "taxonomy_version": row(version="v0"),
            "intent_id": row(intent="Find-Hotel"),
            "stratum": row(stratum="fiction"),
            "slot name 'Area'": row(required="Area"),
            "listed twice": row(optional="price;price"),
            "both required and optional": row(required="area", optional="area"),
            "reserved": row(intent=cs.OUT_OF_TAXONOMY),
            "description is empty": row(description="  "),
            "formula": row(description="=HYPERLINK(x)"),
            "longer than": row(description="x" * (ct.MAX_DESCRIPTION_CHARS + 1)),
            "newline": row(description="two\nlines"),
        }
        for fragment, bad in cases.items():
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.problems(bad))

    def test_wrong_columns(self) -> None:
        self.assertIn("columns", self.problems({**row(), "extra": "x"}))

    def test_build_and_lookup(self) -> None:
        taxonomy = ct.build(ROWS)
        self.assertEqual(taxonomy.versions, ("ctx-tax-v0", "ctx-tax-v1"))
        hotel = taxonomy.intent("ctx-tax-v0", "find_hotel")
        self.assertEqual((hotel.required, hotel.optional), (("area",), ("price", "stars")))
        self.assertEqual(taxonomy.intent("ctx-tax-v1", "find_hotel").required, ("area", "price"))  # per version
        self.assertIs(taxonomy.intent("ctx-tax-v0", cs.OUT_OF_TAXONOMY), ct.OUT_OF_TAXONOMY)
        with self.assertRaises(cs.SchemaError):
            taxonomy.intent("ctx-tax-v0", "book_taxi")
        with self.assertRaises(cs.SchemaError):
            taxonomy.intent("ctx-tax-v9", "find_hotel")

    def test_intent_stratum(self) -> None:
        taxonomy = ct.build(ROWS)
        self.assertTrue(taxonomy.intent("ctx-tax-v0", "find_hotel").allows("dialogue"))
        self.assertFalse(taxonomy.intent("ctx-tax-v0", "find_hotel").allows("literary"))
        self.assertTrue(taxonomy.intent("ctx-tax-v0", "joint_action").allows("literary"))
        self.assertTrue(ct.OUT_OF_TAXONOMY.allows("literary"))

    def test_missing_versions(self) -> None:
        taxonomy = ct.build(ROWS[:3])  # v1 deleted
        self.assertEqual(ct.missing_versions(taxonomy, ["ctx-tax-v0"]), [])
        self.assertIn("ctx-tax-v1", ct.missing_versions(taxonomy, ["ctx-tax-v0", "ctx-tax-v1"])[0])


class VersionHashTests(unittest.TestCase):
    def test_hash_detects_redefinition_but_not_wording_or_order(self) -> None:
        base = ct.version_sha256(ROWS, "ctx-tax-v0")
        self.assertEqual(ct.version_sha256(list(reversed(ROWS)), "ctx-tax-v0"), base)
        reworded = [dict(r, description="Reworded") for r in ROWS]
        self.assertEqual(ct.version_sha256(reworded, "ctx-tax-v0"), base)
        reordered_slots = [dict(ROWS[0], optional_slots="stars;price"), *ROWS[1:]]
        self.assertEqual(ct.version_sha256(reordered_slots, "ctx-tax-v0"), base)
        for changed in (
            [dict(ROWS[0], required_slots="area;price", optional_slots="stars"), *ROWS[1:]],
            [dict(ROWS[0], stratum="both"), *ROWS[1:]],
            ROWS[1:],  # intent removed
        ):
            with self.subTest(changed=changed[0]):
                self.assertNotEqual(ct.version_sha256(changed, "ctx-tax-v0"), base)
        self.assertEqual(ct.version_sha256(ROWS, "ctx-tax-v1"), ct.version_sha256(ROWS[3:], "ctx-tax-v1"))

    def test_unknown_version(self) -> None:
        with self.assertRaises(cs.SchemaError):
            ct.version_sha256(ROWS, "ctx-tax-v9")


class SlotTests(unittest.TestCase):
    HOTEL = ct.build(ROWS).intent("ctx-tax-v0", "find_hotel")

    def test_parse(self) -> None:
        self.assertEqual(ct.parse_slots(""), [])
        self.assertEqual(ct.parse_slots(" area = north ; price=? ;"), [("area", "north"), ("price", "?")])
        self.assertEqual(ct.parse_slots("area=a=b"), [("area", "a=b")])
        self.assertEqual(ct.parse_slots("area=café near the river"), [("area", "café near the river")])

    def test_malformed_pairs(self) -> None:
        for text, fragment in (
            ("area", "not name=value"),
            ("area=", "no value"),
            ("Area=north", "slot name"),
            ("=north", "slot name"),
            ("area=north;area=south", "twice"),
            ("area=north\nprice=cheap", "newline"),
        ):
            with self.subTest(text=text), self.assertRaises(cs.SchemaError) as raised:
                ct.parse_slots(text)
            self.assertIn(fragment, str(raised.exception))

    def test_unstated_value_satisfies_a_required_slot(self) -> None:
        # Review R2 / AC-003-6: area=? is the honest record of an unstated required slot.
        pairs = ct.parse_slots("area=?")
        self.assertEqual(ct.slot_problems(self.HOTEL, pairs), [])
        self.assertEqual(ct.unstated(pairs), ["area"])

    def test_missing_required_and_undefined_slots(self) -> None:
        problems = ct.slot_problems(self.HOTEL, ct.parse_slots("price=cheap;parking=yes"))
        self.assertTrue(any("required slot 'area' is missing" in problem for problem in problems))
        self.assertTrue(any("'parking' is not defined" in problem for problem in problems))

    def test_version_specific_requirements(self) -> None:
        v1 = ct.build(ROWS).intent("ctx-tax-v1", "find_hotel")
        self.assertEqual(ct.slot_problems(self.HOTEL, ct.parse_slots("area=north")), [])
        self.assertTrue(ct.slot_problems(v1, ct.parse_slots("area=north")))  # price is required in v1

    def test_out_of_taxonomy_takes_no_slots(self) -> None:
        self.assertEqual(ct.slot_problems(ct.OUT_OF_TAXONOMY, []), [])
        self.assertTrue(ct.slot_problems(ct.OUT_OF_TAXONOMY, [("area", "north")]))

    def test_slotless_intent_rejects_any_slot(self) -> None:
        give = ct.build(ROWS).intent("ctx-tax-v0", "give")
        self.assertTrue(ct.slot_problems(give, [("object", "water")]))

    def test_canonical_slots_is_order_independent(self) -> None:
        self.assertEqual(ct.canonical_slots(ct.parse_slots("price=?;area=north")), "area=north;price=?")
        self.assertEqual(ct.canonical_slots(ct.parse_slots("area=north;price=?")), "area=north;price=?")


class TaxonomyFileTests(fx.ContextCase):
    def write(self, rows: list[dict[str, str]]) -> None:
        write_csv(self.dirs.taxonomy, ct.TAXONOMY_FIELDS, rows, excel=True)

    def test_check_passes_on_a_valid_file_with_a_byte_order_mark(self) -> None:
        self.write(ROWS)
        self.assertEqual(self.cli("taxonomy-check"), 0)
        self.assertEqual(ctx.taxonomy_check(self.dirs).versions, ("ctx-tax-v0", "ctx-tax-v1"))

    def test_check_fails_on_a_missing_or_invalid_file(self) -> None:
        self.assertEqual(self.cli("taxonomy-check"), 1)
        self.write([*ROWS, row(description="Duplicate hotel")])
        with self.assertRaises(ct.TaxonomyError) as raised:
            ct.load_taxonomy(self.dirs.taxonomy)
        self.assertIn("duplicate intent", str(raised.exception))

    def test_reordered_columns_are_rejected(self) -> None:
        fields = (ct.TAXONOMY_FIELDS[1], ct.TAXONOMY_FIELDS[0], *ct.TAXONOMY_FIELDS[2:])
        write_csv(self.dirs.taxonomy, fields, ROWS)
        self.assertEqual(self.cli("taxonomy-check"), 1)

    def test_deleting_a_version_that_labels_reference_is_reported(self) -> None:
        self.write(ROWS[:3])  # v1 removed
        labels = self.dirs.annotations_dir / "context_context_A1.csv"
        write_csv(labels, ("item_id", "taxonomy_version"), [{"item_id": "d:DEV001:t02", "taxonomy_version": "ctx-tax-v1"}])
        with self.assertRaises(ct.TaxonomyError) as raised:
            ctx.taxonomy_check(self.dirs)
        self.assertIn("ctx-tax-v1", str(raised.exception))
        self.assertEqual(self.cli("taxonomy-check"), 1)


class MissingDirTests(unittest.TestCase):
    def test_missing_file_message_names_the_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ct.TaxonomyError) as raised:
            ct.load_taxonomy(Path(tmp) / ct.TAXONOMY_FILE)
        self.assertIn("no taxonomy", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
