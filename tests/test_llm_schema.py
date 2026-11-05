"""Spec 009 T1: closed answer schemas, strict parsing and the slot-key vocabulary (invented fixtures)."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from src.evaluation import interpretation as ip
from src.llm import schema as sc
from tests.test_auto_levels import item

KEYS = ("hotel.area", "hotel.people", "hotel.phone", "train.leaveat")
CANDIDATES = ["yes", "no", sc.AMBIGUOUS]


def answer(**changes):
    body = {"route": "indirect", "category": "booking",
            "slots": [{"slot": "hotel.people", "value": "two"}], "requested_slots": ["hotel.phone"]}
    body.update(changes)
    return json.dumps(body)


def parse(raw, finish="stop"):
    return sc.parse_main(raw, finish, frozenset(KEYS))


class ParseMainTests(unittest.TestCase):
    def test_valid_answer_is_parsed_without_change(self):
        result = parse(answer())
        self.assertEqual(result, sc.MainAnswer("indirect", "booking", (("hotel.people", "two"),), ("hotel.phone",)))

    def test_ac_009_3_content_failures_map_to_one_reason(self):
        long_value = "x" * (sc.MAX_VALUE_CHARS + 1)
        cases = {
            "malformed json": ('{"route": "indirect",', "stop", "parse"),
            "code fence is not repaired": ("```json\n" + answer() + "\n```", "stop", "parse"),
            "duplicate json key": ('{"route":"direct","route":"indirect","category":"booking","slots":[],"requested_slots":[]}', "stop", "parse"),
            "nan constant": (answer().replace('"two"', "NaN"), "stop", "parse"),
            "out-of-enum category": (answer(category="shopping"), "stop", "category"),
            "no_request as interpretation category": (answer(category="no_request"), "stop", "category"),
            "null category": (answer(category=None), "stop", "category"),
            "unknown slot key": (answer(slots=[{"slot": "hotel.wifi", "value": "yes"}]), "stop", "slot_key"),
            "unknown requested key": (answer(requested_slots=["taxi.phone"]), "stop", "slot_key"),
            "duplicate slot key": (answer(slots=[{"slot": "hotel.people", "value": "2"},
                                                 {"slot": "hotel.people", "value": "3"}]), "stop", "slot_duplicate"),
            "duplicate requested key": (answer(requested_slots=["hotel.phone", "hotel.phone"]), "stop", "slot_duplicate"),
            "over-long value": (answer(slots=[{"slot": "hotel.area", "value": long_value}]), "stop", "too_long"),
            "too many slots": (answer(slots=[{"slot": "hotel.area", "value": "n"}] * (sc.MAX_SLOTS + 1)), "stop", "too_long"),
            "over-long raw output": (" " * sc.MAX_RAW_CHARS + answer(), "stop", "too_long"),
            "empty": ("", "stop", "empty"),
            "whitespace only": ("  \n", "stop", "empty"),
            "refusal": ("I can't help with that.", "refusal", "refusal"),
            "truncation at token limit": (answer()[:-5], "length", "truncated"),
            "complete json but length stop": (answer(), "length", "truncated"),
        }
        for name, (raw, finish, reason) in cases.items():
            with self.subTest(name):
                self.assertEqual(parse(raw, finish), sc.Invalid(reason))

    def test_schema_shape_failures(self):
        cases = {
            "not an object": "[1, 2]",
            "extra paraphrase field": answer(paraphrase="Book it."),
            "missing field": json.dumps({"route": "direct", "category": "booking", "slots": []}),
            "unknown route": answer(route="maybe"),
            "route not a string": answer(route=["direct"]),
            "slots as object": answer(slots={"hotel.people": "two"}),
            "slot pair with extra key": answer(slots=[{"slot": "hotel.area", "value": "n", "note": "x"}]),
            "numeric value": answer(slots=[{"slot": "hotel.people", "value": 2}]),
            "blank value": answer(slots=[{"slot": "hotel.area", "value": "  "}]),
            "control character in value": answer(slots=[{"slot": "hotel.area", "value": "no\u0000rth"}]),
            "requested slot not a string": answer(requested_slots=[3]),
        }
        for name, raw in cases.items():
            with self.subTest(name):
                self.assertEqual(parse(raw), sc.Invalid("schema"))

    def test_deep_nesting_is_a_parse_failure_not_a_crash(self):
        self.assertEqual(parse("[" * 4000 + "]" * 4000), sc.Invalid("parse"))

    def test_nesting_bound_is_platform_independent(self):
        # Just past the bound is a parse failure even though json itself would decode it.
        self.assertEqual(parse("[" * (sc.MAX_NESTING + 1) + "]" * (sc.MAX_NESTING + 1)), sc.Invalid("parse"))
        self.assertEqual(parse("[" * sc.MAX_NESTING + "]" * sc.MAX_NESTING), sc.Invalid("schema"))

    def test_brackets_inside_strings_do_not_count_as_nesting(self):
        deep_text = "[" * 48 + '\\"' + "{" * 40  # 88 brackets + an escaped quote, within the value limit
        raw = answer(slots=[{"slot": "hotel.area", "value": deep_text}])
        self.assertIsInstance(parse(raw), sc.MainAnswer)

    def test_backend_contract_violations_raise(self):
        with self.assertRaises(ValueError):
            parse(answer(), "content_filter")
        with self.assertRaises(TypeError):
            parse(None)
        with self.assertRaises(ValueError):
            sc.Invalid("other")


class ParseTransferTests(unittest.TestCase):
    def test_valid_and_invalid_transfer_answers(self):
        self.assertEqual(sc.parse_transfer('{"request": true, "value": "yes"}', "stop", CANDIDATES),
                         sc.TransferAnswer(True, "yes"))
        self.assertEqual(sc.parse_transfer(json.dumps({"request": False, "value": sc.AMBIGUOUS}), "stop", ["yes", "no"]),
                         sc.TransferAnswer(False, sc.AMBIGUOUS))
        cases = {
            '{"request": true, "value": "maybe"}': "transfer_value",
            '{"request": true, "value": "Yes"}': "transfer_value",
            '{"request": "true", "value": "yes"}': "schema",
            '{"request": 1, "value": "yes"}': "schema",
            '{"request": true, "value": null}': "schema",
            '{"request": true}': "schema",
            '{"request": true, "value": "yes"': "parse",
        }
        for raw, reason in cases.items():
            with self.subTest(raw):
                self.assertEqual(sc.parse_transfer(raw, "stop", CANDIDATES), sc.Invalid(reason))
        self.assertEqual(sc.parse_transfer("", "refusal", CANDIDATES), sc.Invalid("refusal"))

    def test_candidate_sets_are_validated(self):
        self.assertEqual(sc.transfer_values(["a", "b"]), ("a", "b", sc.AMBIGUOUS))
        for bad in ([], ["a", "a"], ["a", ""], "ab", ["x"] * (sc.MAX_CANDIDATES + 1)):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    sc.transfer_values(bad)


class SchemaTests(unittest.TestCase):
    def test_main_schema_enums_and_bounds(self):
        schema = sc.main_schema(KEYS)
        properties = schema["properties"]
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), set(properties))
        self.assertNotIn("paraphrase", properties)
        self.assertEqual(properties["category"]["enum"], ["info_seeking", "booking", "travel", "recommendation"])
        self.assertEqual(properties["route"]["enum"], ["direct", "indirect", "no_request"])
        self.assertEqual(properties["requested_slots"]["items"]["enum"], list(KEYS))
        self.assertEqual(properties["slots"]["items"]["properties"]["value"]["maxLength"], sc.MAX_VALUE_CHARS)

    def test_transfer_schema_is_per_record(self):
        schema = sc.transfer_schema(["yes", "no"])
        self.assertEqual(schema["properties"]["value"]["enum"], ["yes", "no", sc.AMBIGUOUS])
        self.assertNotEqual(sc.schema_sha256(schema), sc.schema_sha256(sc.transfer_schema(["no", "yes"])))

    def test_schema_hash_is_stable_and_tracks_enums(self):
        first = sc.schema_sha256(sc.main_schema(KEYS))
        self.assertEqual(first, sc.schema_sha256(sc.main_schema(list(KEYS))))
        self.assertRegex(first, r"\A[0-9a-f]{64}\Z")
        self.assertNotEqual(first, sc.schema_sha256(sc.main_schema(KEYS + ("train.people",))))

    def test_main_schema_refuses_bad_vocabularies(self):
        for bad in ((), ("hotel.people", "hotel.area"), ("Hotel.Area",), ("hotel.area", "hotel.area"), ("area",)):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    sc.main_schema(bad)


class RowTests(unittest.TestCase):
    def test_valid_answers_round_trip_through_the_scorer_validator(self):
        expected = {"none": {"x:indirect", "y:direct", "z:direct"}}
        rows = [sc.routed_row("x:indirect", "none", parse(answer())),
                sc.routed_row("y:direct", "none", parse(answer(route="no_request"))),
                sc.routed_row("z:direct", "none", parse("{"))]
        accepted = ip.validate_predictions(rows, expected)["none"]
        self.assertEqual(accepted["x:indirect"]["slots"], {"hotel.people": "two"})
        self.assertEqual(accepted["y:direct"], {"example_id": "y:direct", "condition": "none", "prediction": "no_request",
                                                "category": None, "slots": {}, "requested_slots": []})
        self.assertTrue(accepted["z:direct"]["invalid"])

    def test_oracle_rows_keep_the_interpretation_even_for_no_request_routes(self):
        row = sc.oracle_row("x:indirect", "full", parse(answer(route="no_request")))
        self.assertEqual((row["prediction"], row["category"], row["slots"]), ("no_request", "booking", {"hotel.people": "two"}))
        ip.validate_predictions([row], {"full": {"x:indirect"}})
        self.assertEqual(sc.oracle_row("x:indirect", "full", sc.Invalid("empty")),
                         {"example_id": "x:indirect", "condition": "full", "invalid": True})

    def test_transfer_rows_match_the_transfer_contract(self):
        self.assertEqual(sc.transfer_row("ir:validation:0001", "none", sc.TransferAnswer(True, "yes")),
                         {"example_id": "ir:validation:0001", "condition": "none", "request": True, "value": "yes"})
        self.assertEqual(set(sc.transfer_row("ir:validation:0001", "none", sc.Invalid("schema"))),
                         {"example_id", "condition", "invalid"})


def corpus():
    return [
        item("TR1", 1, "t", "Book it for two.", "We are two.", split="train",
             acts={"Hotel-Inform": [["People", "two"], ["Area", "north"]], "Hotel-Request": [["Phone", "?"]]}),
        item("TR2", 1, "t", "When does it leave?", "I wonder when it leaves.", split="train",
             acts={"Train-Request": [["Leave", "?"]], "general-thank": [["none", "none"]]}),
        item("DV1", 1, "t", "Find a taxi.", "A taxi would help.", split="dev",
             acts={"Taxi-Inform": [["Dest", "museum"]], "Hotel-Inform": [["Area", "north"]]}),
        item("TS1", 1, "t", "Police please.", "I need the police.", split="test",
             acts={"Police-Request": [["Addr", "?"]]}),
    ]


class VocabularyTests(unittest.TestCase):
    def test_vocabulary_is_train_only_sorted_and_deterministic(self):
        items = corpus()
        keys = sc.build_slot_keys(items)
        self.assertEqual(keys, ["hotel.area", "hotel.people", "hotel.phone", "train.leave"])
        self.assertEqual(keys, sc.build_slot_keys(list(reversed(items))))

    def test_vocabulary_without_train_references_is_refused(self):
        with self.assertRaises(ValueError):
            sc.build_slot_keys([i for i in corpus() if i["split"] != "train"])

    def test_document_round_trip_and_strict_loading(self):
        document = sc.slot_keys_document(sc.build_slot_keys(corpus()), "a" * 64)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "slot_keys.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            self.assertEqual(sc.load_slot_keys(path), tuple(document["slot_keys"]))
            bad_documents = [
                {**document, "text": "x"}, {**document, "version": "slot-keys-v0"},
                {**document, "split": "dev"}, {**document, "items_sha256": "A" * 64},
                {**document, "slot_keys": ["hotel.area", "hotel.area"]},
                {**document, "slot_keys": ["hotel.people", "hotel.area"]},
                {**document, "slot_keys": ["hotel.Area"]}, {**document, "slot_keys": []},
            ]
            for bad in bad_documents:
                with self.subTest(bad=bad):
                    path.write_text(json.dumps(bad), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        sc.load_slot_keys(path)

    def test_dev_coverage_reports_counts_only(self):
        items = corpus()
        counts = sc.dev_coverage(items, sc.build_slot_keys(items))
        self.assertEqual(counts, {"dev_examples": 2, "dev_keys": 2, "dev_keys_outside": 1, "dev_examples_affected": 2})

    def test_cli_writes_identical_bytes_and_prints_no_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            items_path = Path(tmp) / "items.jsonl"
            items_path.write_text("".join(json.dumps(i) + "\n" for i in corpus()), encoding="utf-8")
            outputs = []
            for name in ("a.json", "b.json"):
                out = Path(tmp) / name
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    self.assertEqual(sc.main(["slot-keys", "--items", str(items_path), "--out", str(out), "--check-dev"]), 0)
                outputs.append(out.read_bytes())
                for text in ("Book it", "taxi", "police", "DV1", "TS1"):
                    self.assertNotIn(text, stdout.getvalue())
            self.assertEqual(outputs[0], outputs[1])
            self.assertNotIn(b"Book it", outputs[0])
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(sc.main(["slot-keys", "--items", str(items_path), "--out", str(items_path)]), 1)


if __name__ == "__main__":
    unittest.main()
