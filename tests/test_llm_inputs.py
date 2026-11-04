"""Spec 009 T4: verified input streams and the oracle-subset check (invented fixtures only)."""

import json
import tempfile
import unittest
from pathlib import Path

from src.data.contexts import RENDERER_VERSION
from src.llm import inputs as li

SENTINEL = "zq-sentinel-input the purple lighthouse"


def main_record(example_id="PMUL9001_t02:indirect", condition="full", context="User: hi\nSystem: Hello.",
                target="we will be four", **changes):
    record = {"example_id": example_id, "condition": condition, "context": context, "target": target,
              "renderer_version": RENDERER_VERSION, "input_sha256": li.main_input_sha256(context, target)}
    record.update(changes)
    return record


def transfer_record(example_id="ir:validation:9001", **changes):
    record = {"example_id": example_id, "condition": "none", "utterance": "my knees hate stairs",
              "slot_description": "Whether the room is on the ground floor",
              "candidates": ["True", "False", "<ambiguous>"], "candidate_aliases": {"True": "yes", "False": "no"}}
    record.update(changes)
    record["input_sha256"] = li.transfer_input_sha256(record)
    return record


class StreamFixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name, records, *, raw=None):
        path = self.dir / name
        path.write_bytes(raw if raw is not None else
                         "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records).encode("utf-8"))
        return path


class MainStreamTests(StreamFixture):
    def test_valid_stream_loads_in_file_order_with_its_hash(self):
        records = [main_record(), main_record(condition="none", context="")]
        stream = li.load_stream(self.write("r.jsonl", records), "routed")
        self.assertEqual([r["condition"] for r in stream.records], ["full", "none"])
        self.assertEqual(len(stream.file_sha256), 64)

    def test_hash_matches_the_spec_005_exporter(self):
        from src.data.contexts import Rendered, input_sha256
        rendered = Rendered((), "User: hi", "a target", 0)
        self.assertEqual(li.main_input_sha256("User: hi", "a target"), input_sha256(rendered))

    def test_tampered_text_or_hash_is_refused(self):
        tampered = main_record()
        tampered["target"] = "we will be five"
        with self.assertRaisesRegex(li.InputError, "input_sha256 does not match"):
            li.load_stream(self.write("r.jsonl", [tampered]), "routed")
        with self.assertRaisesRegex(li.InputError, "lowercase SHA-256"):
            li.load_stream(self.write("r.jsonl", [main_record(input_sha256="X" * 64)]), "routed")

    def test_wrong_renderer_version_is_refused(self):
        with self.assertRaisesRegex(li.InputError, "renderer_version"):
            li.load_stream(self.write("r.jsonl", [main_record(renderer_version="render-v0")]), "routed")

    def test_schema_problems_are_refused(self):
        bad = [main_record(extra=1), {k: v for k, v in main_record().items() if k != "context"},
               main_record(condition="later"), main_record(example_id="bad id with spaces"),
               main_record(target="   ", input_sha256=li.main_input_sha256("User: hi\nSystem: Hello.", "   "))]
        for record in bad:
            with self.subTest(record=sorted(record)), self.assertRaises(li.InputError):
                li.load_stream(self.write("r.jsonl", [record]), "routed")

    def test_duplicate_key_and_duplicate_json_field_are_refused(self):
        with self.assertRaisesRegex(li.InputError, "duplicate"):
            li.load_stream(self.write("r.jsonl", [main_record(), main_record()]), "routed")
        raw = b'{"example_id":"a","example_id":"b"}\n'
        with self.assertRaisesRegex(li.InputError, "not one JSON object"):
            li.load_stream(self.write("r.jsonl", [], raw=raw), "routed")

    def test_empty_torn_and_oversized_files_are_refused(self):
        with self.assertRaisesRegex(li.InputError, "no records"):
            li.load_stream(self.write("r.jsonl", []), "routed")
        line = json.dumps(main_record()).encode()
        with self.assertRaisesRegex(li.InputError, "newline"):
            li.load_stream(self.write("r.jsonl", [], raw=line), "routed")
        long_line = b" " * (li.MAX_LINE_BYTES + 1) + b"\n"
        with self.assertRaisesRegex(li.InputError, "longer than"):
            li.load_stream(self.write("r.jsonl", [], raw=long_line), "routed")

    def test_errors_never_echo_ids_or_text(self):
        tampered = main_record(example_id="PMUL9999_t01:direct", target=SENTINEL)
        tampered["target"] = SENTINEL + " changed"
        with self.assertRaises(li.InputError) as caught:
            li.load_stream(self.write("r.jsonl", [main_record(), tampered]), "routed")
        self.assertNotIn("PMUL9999", str(caught.exception))
        self.assertNotIn("zq-sentinel", str(caught.exception))
        self.assertIn("line 2", str(caught.exception))

    def test_unknown_kind_is_refused(self):
        with self.assertRaises(li.InputError):
            li.load_stream(self.write("r.jsonl", [main_record()]), "test")


class TransferStreamTests(StreamFixture):
    def test_valid_transfer_stream_loads(self):
        stream = li.load_stream(self.write("t.jsonl", [transfer_record()]), "transfer")
        self.assertEqual(stream.kind, "transfer")

    def test_hash_matches_the_indirect_requests_exporter(self):
        from src.data.indirect_requests import TransferItem, input_record
        fields = TransferItem.__dataclass_fields__
        values = {"example_id": "ir:validation:9002", "split": "validation", "service": "Hotels_1", "utterance": "u",
                  "slot_description": "d", "candidates": ("A", "B"), "aliases": ("A", "B"), "target": "A"}
        record = input_record(TransferItem(**{name: values[name] for name in fields}))
        self.assertIsNone(li._verify_transfer(record))

    def test_transfer_problems_are_refused(self):
        bad = [transfer_record(condition="full"), transfer_record(candidates=[]),
               transfer_record(candidates=["A", "A"]), transfer_record(candidate_aliases={"Z": "zed"}),
               {**transfer_record(), "utterance": "changed"}]
        for record in bad:
            with self.subTest(), self.assertRaises(li.InputError):
                li.load_stream(self.write("t.jsonl", [record]), "transfer")


class SubsetAndDistinctTests(StreamFixture):
    def streams(self, routed, oracle):
        return (li.load_stream(self.write("r.jsonl", routed), "routed"),
                li.load_stream(self.write("o.jsonl", oracle), "oracle"))

    def test_oracle_subset_passes(self):
        routed, oracle = self.streams([main_record(), main_record("PMUL9002_t01:direct")], [main_record()])
        li.check_oracle_subset(routed, oracle)

    def test_ac_009_2_missing_or_rehashed_oracle_record_is_refused(self):
        routed, oracle = self.streams([main_record()], [main_record("PMUL9003_t03:indirect")])
        with self.assertRaisesRegex(li.InputError, "1 record\\(s\\) missing"):
            li.check_oracle_subset(routed, oracle)
        routed, oracle = self.streams([main_record()], [main_record(target="other words")])
        with self.assertRaisesRegex(li.InputError, "1 with a different input hash") as caught:
            li.check_oracle_subset(routed, oracle)
        self.assertNotIn("PMUL", str(caught.exception))

    def test_distinct_inputs_collapse_shared_hashes_in_hash_order(self):
        shared = dict(context="User: same", target="same target")
        routed, oracle = self.streams(
            [main_record("PMUL9004_t01:direct", **shared), main_record("PMUL9005_t01:direct", **shared),
             main_record("PMUL9006_t01:direct")], [main_record("PMUL9004_t01:direct", **shared)])
        distinct = li.distinct_inputs([routed, oracle])
        self.assertEqual(len(distinct), 2)
        self.assertEqual(list(distinct), sorted(distinct))


if __name__ == "__main__":
    unittest.main()
