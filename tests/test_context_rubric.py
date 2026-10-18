"""The committed taxonomy draft and the ctx-v0 rubric stay complete and consistent (spec 003 T7)."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from src.annotation import context_schema as cs
from src.annotation import context_taxonomy as ct

REPO_ROOT = Path(__file__).resolve().parents[1]
TAXONOMY = REPO_ROOT / "data" / "annotations" / ct.TAXONOMY_FILE
RUBRIC = REPO_ROOT / "docs" / "context_supplement.md"
LITERARY_V0 = {"give", "help", "permit", "stop", "inform_me", "joint_action"}


class TaxonomyDraftTests(unittest.TestCase):
    TAXONOMY = ct.load_taxonomy(TAXONOMY)

    def test_v0_is_valid_and_contains_the_spec_intents(self) -> None:
        self.assertIn("ctx-tax-v0", self.TAXONOMY.versions)
        intents = self.TAXONOMY.intents["ctx-tax-v0"]
        literary = {intent_id for intent_id, intent in intents.items() if intent.allows("literary")}
        self.assertEqual(literary, LITERARY_V0)
        self.assertEqual(intents["joint_action"].stratum, "both")  # FR3: proposals and hortatives
        for intent_id in LITERARY_V0:
            self.assertEqual(intents[intent_id].required, (), intent_id)  # FR3: no required literary slots
        self.assertTrue(any(intent_id.startswith("find_") for intent_id in intents))
        self.assertTrue(any(intent_id.startswith("book_") for intent_id in intents))
        self.assertIn("ask_attribute", intents)


class RubricCoverageTests(unittest.TestCase):
    TEXT = RUBRIC.read_text(encoding="utf-8")

    def test_every_enum_value_is_explained(self) -> None:
        enums = {
            "passes": cs.PASSES,
            "strata": cs.STRATA,
            "form labels": cs.FORM_LABELS,
            "functions": cs.FUNCTIONS,
            "confidences": cs.CONFIDENCES,
            "depths": tuple(value for value in cs.DEPTHS if value),
            "future dependence": cs.FUTURE_DEPENDENCE,
            "correction reasons": cs.CORRECTION_REASONS,
            "request statuses": cs.REQUEST_STATUSES,
            "request types": cs.REQUEST_TYPES,
            "reserved intent": (cs.OUT_OF_TAXONOMY,),
        }
        for enum, values in enums.items():
            for value in values:
                with self.subTest(enum=enum, value=value):
                    self.assertIn(f"`{value}`", self.TEXT)

    def test_every_v0_intent_and_slot_is_listed(self) -> None:
        taxonomy = ct.load_taxonomy(TAXONOMY)
        for intent_id, intent in taxonomy.intents["ctx-tax-v0"].items():
            row = re.search(rf"^\| `{intent_id}` \| (\w+) \| ([^|]*) \| ([^|]*) \|$", self.TEXT, re.MULTILINE)
            with self.subTest(intent=intent_id):
                self.assertIsNotNone(row)
                assert row is not None
                self.assertEqual(row[1], intent.stratum)
                listed = lambda cell: [] if cell.strip() == "none" else [name.strip() for name in cell.split(",")]  # noqa: E731
                self.assertEqual(listed(row[2]), list(intent.required))
                self.assertEqual(listed(row[3]), list(intent.optional))

    def test_versions_named_in_the_rubric_match_the_code(self) -> None:
        for version in (cs.PROTOCOL_VERSION, cs.SEGMENTER_VERSION, "ctx-tax-v0"):
            self.assertIn(f"`{version}`", self.TEXT)


if __name__ == "__main__":
    unittest.main()
