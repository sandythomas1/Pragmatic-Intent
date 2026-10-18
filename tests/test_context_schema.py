"""Tests for the contextual annotation schema (spec 003 T1). Invented values only."""

from __future__ import annotations

import hashlib
import itertools
import unittest

from src.annotation import context_schema as cs


class InputCheckTests(unittest.TestCase):
    def test_batch_accepts_simple_names(self) -> None:
        for value in ("pilot1", "p", "pilot-2_b", "a" * 32):
            self.assertEqual(cs.batch_id(value), value)

    def test_batch_rejects_path_tricks_and_bad_shapes(self) -> None:
        for value in ("../x", "pilot1/..", "pilot1\\x", "", ".", "Pilot1", "1pilot", "pilot 1", "pilot1\n", "a" * 33):
            with self.subTest(value=value), self.assertRaises(cs.SchemaError):
                cs.batch_id(value)

    def test_batch_rejects_windows_device_names(self) -> None:
        for value in ("con", "nul", "aux", "prn", "com1", "lpt9"):
            with self.subTest(value=value), self.assertRaises(cs.SchemaError):
                cs.batch_id(value)
        self.assertEqual(cs.batch_id("console"), "console")

    def test_annotator(self) -> None:
        self.assertEqual(cs.annotator_id("A1"), "A1")
        self.assertEqual(cs.annotator_id("a" * 16), "a" * 16)
        for value in ("A 1", "a" * 17, "1A", "", "A1\n", "A1;"):
            with self.subTest(value=value), self.assertRaises(cs.SchemaError):
                cs.annotator_id(value)

    def test_trailing_newline_is_not_a_match(self) -> None:
        # re.match(r"...$") would accept this; fullmatch must not.
        with self.assertRaises(cs.SchemaError):
            cs.require_match(cs.NAME_RE, "find_hotel\n", "intent")

    def test_non_string_is_rejected(self) -> None:
        with self.assertRaises(cs.SchemaError):
            cs.require_match(cs.NAME_RE, None, "intent")  # type: ignore[arg-type]

    def test_item_ids(self) -> None:
        self.assertEqual(cs.item_id("d:PMUL1234:t06"), "d:PMUL1234:t06")
        self.assertEqual(cs.item_id("lit-0123456789"), "lit-0123456789")
        for value in ("d:PMUL1234:t6", "d::t06", "lit-0123456789a", "lit-ABCDEF0123", "PMUL1234_t06", "d:P/1:t06", "d:-P1:t06"):
            with self.subTest(value=value), self.assertRaises(cs.SchemaError):
                cs.item_id(value)

    def test_dialogue_item_id_strips_json_and_pads(self) -> None:
        self.assertEqual(cs.dialogue_item_id("PMUL1234.json", 6), "d:PMUL1234:t06")
        self.assertEqual(cs.dialogue_item_id("SNG01699.json", 112), "d:SNG01699:t112")
        with self.assertRaises(cs.SchemaError):
            cs.dialogue_item_id("PMUL1234.json", -2)
        with self.assertRaises(cs.SchemaError):
            cs.dialogue_item_id("../etc.json", 2)

    def test_enum(self) -> None:
        self.assertEqual(cs.require_enum("request", cs.FUNCTIONS, "function"), "request")
        for value in ("Request", "", "requests"):
            with self.subTest(value=value), self.assertRaises(cs.SchemaError):
                cs.require_enum(value, cs.FUNCTIONS, "function")

    def test_form_labels_are_rubric_v2(self) -> None:
        self.assertEqual(cs.FORM_LABELS, ("L0", "L1", "L2", "L3", "INF", "NR", "?"))


class FreeTextTests(unittest.TestCase):
    def test_accepts_ordinary_and_unicode_text(self) -> None:
        for value in ("", "find a cheap hotel", "café – naïve", "a b", "=SUM(A1)", "x" * cs.MAX_FREE_TEXT_CHARS):
            with self.subTest(value=value):
                self.assertEqual(cs.free_text(value, "notes"), value)

    def test_rejects_line_breaks_controls_and_hidden_characters(self) -> None:
        for value in ("a\nb", "a\rb", "a\tb", "a\x00b", "a b", "a b", "a‮b", "a​b"):
            with self.subTest(value=repr(value)), self.assertRaises(cs.SchemaError):
                cs.free_text(value, "notes")

    def test_rejects_over_limit(self) -> None:
        with self.assertRaises(cs.SchemaError):
            cs.free_text("x" * (cs.MAX_FREE_TEXT_CHARS + 1), "paraphrase")
        with self.assertRaises(cs.SchemaError):
            cs.free_text("abcd", "slot value", limit=3)


class CanonicalHashTests(unittest.TestCase):
    ROW = {"item_id": "d:XYZ001:t04", "form": "L2", "note": "café – ok"}
    # Computed independently: sha256 of '{"form":"L2","item_id":"d:XYZ001:t04","note":"café – ok"}' in UTF-8.
    PINNED = "030adcfd9d801edce55460bd2ced5e51e8f5438bd39a93481adddb0c67012032"

    def test_pinned_value(self) -> None:
        # Fails if key order, separators, ensure_ascii or the encoding ever change (AC-003-10).
        self.assertEqual(cs.canonical_hash(self.ROW), self.PINNED)

    def test_pinned_value_matches_independent_serialization(self) -> None:
        literal = '{"form":"L2","item_id":"d:XYZ001:t04","note":"café – ok"}'
        self.assertEqual(hashlib.sha256(literal.encode("utf-8")).hexdigest(), self.PINNED)

    def test_insertion_order_does_not_matter(self) -> None:
        for keys in itertools.permutations(self.ROW):
            with self.subTest(keys=keys):
                self.assertEqual(cs.canonical_hash({key: self.ROW[key] for key in keys}), self.PINNED)

    def test_excluded_fields_do_not_change_the_hash(self) -> None:
        extended = dict(self.ROW, prior_sha256="a" * 64, text_sha256="b" * 64, status="superseded")
        self.assertEqual(cs.canonical_hash(extended), self.PINNED)

    def test_every_value_change_changes_the_hash(self) -> None:
        for key in self.ROW:
            with self.subTest(key=key):
                self.assertNotEqual(cs.canonical_hash(dict(self.ROW, **{key: self.ROW[key] + "x"})), self.PINNED)

    def test_explicit_exclude_overrides_default(self) -> None:
        with_status = dict(self.ROW, status="superseded")
        self.assertNotEqual(cs.canonical_hash(with_status, exclude=()), self.PINNED)

    def test_non_string_values_are_rejected(self) -> None:
        for value in (4, None, 1.0, ["L2"]):
            with self.subTest(value=value), self.assertRaises(TypeError):
                cs.canonical_hash({"turn_index": value})  # type: ignore[dict-item]

    def test_text_hash_covers_gold_fields_only(self) -> None:
        base = cs.text_hash("d:XYZ001:t04", "context", "A1", "area=?", "find me a restaurant")
        self.assertEqual(len(base), 64)
        self.assertEqual(base, cs.text_hash("d:XYZ001:t04", "context", "A1", "area=?", "find me a restaurant"))
        variants = [
            ("d:XYZ001:t06", "context", "A1", "area=?", "find me a restaurant"),
            ("d:XYZ001:t04", "reveal", "A1", "area=?", "find me a restaurant"),
            ("d:XYZ001:t04", "context", "A2", "area=?", "find me a restaurant"),
            ("d:XYZ001:t04", "context", "A1", "area=north", "find me a restaurant"),
            ("d:XYZ001:t04", "context", "A1", "area=?", "find me a hotel"),
        ]
        for args in variants:
            with self.subTest(args=args):
                self.assertNotEqual(cs.text_hash(*args), base)


class DerivedFieldTests(unittest.TestCase):
    def test_request_status(self) -> None:
        expected = {
            "request": "present",
            "uncertain": "uncertain",
            "inform": "absent",
            "decline": "absent",
            "social": "absent",
            "other": "absent",
        }
        self.assertEqual({function: cs.request_status(function) for function in cs.FUNCTIONS}, expected)
        with self.assertRaises(cs.SchemaError):
            cs.request_status("Request")

    def test_request_type_full_table(self) -> None:
        for form, status in itertools.product(cs.FORM_LABELS, cs.REQUEST_STATUSES):
            with self.subTest(form=form, status=status):
                result = cs.request_type(form, status)
                self.assertIn(result, cs.REQUEST_TYPES)
                if status == "absent":
                    self.assertEqual(result, "none")
                elif status == "uncertain":
                    self.assertEqual(result, "uncertain")
                elif form == "L0":
                    self.assertEqual(result, "direct")
                elif form in ("L1", "L2", "L3"):
                    self.assertEqual(result, "indirect")
                else:
                    self.assertEqual(result, "form_unknown")

    def test_wording_only_inf_in_a_request_context_is_never_absent(self) -> None:
        # Spec 001 AC-03 / spec 003 AC-003-8.
        status = cs.request_status("request")
        self.assertEqual(status, "present")
        self.assertEqual(cs.request_type("INF", status), "form_unknown")

    def test_request_type_rejects_unknown_values(self) -> None:
        with self.assertRaises(cs.SchemaError):
            cs.request_type("L4", "present")
        with self.assertRaises(cs.SchemaError):
            cs.request_type("L1", "yes")

    def test_future_dependence_flags(self) -> None:
        eligible = {value: cs.confirmatory_eligible(value) for value in cs.FUTURE_DEPENDENCE}
        self.assertEqual(eligible, {"none": True, "corroborates": True, "conflicts": True, "required": False})
        adjudicate = {value: cs.needs_adjudication(value) for value in cs.FUTURE_DEPENDENCE}
        self.assertEqual(adjudicate, {"none": False, "corroborates": False, "conflicts": True, "required": False})
        for function in (cs.confirmatory_eligible, cs.needs_adjudication):
            with self.subTest(function=function.__name__), self.assertRaises(cs.SchemaError):
                function("")


if __name__ == "__main__":
    unittest.main()
