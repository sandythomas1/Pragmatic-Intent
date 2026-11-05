"""Spec 009 T5: the append-only, resumable response cache (invented fixtures only)."""

import dataclasses
import tempfile
import unittest
from pathlib import Path

from src.llm import cache as ca
from src.llm.schema import MAX_RAW_CHARS

H = "a" * 64


def parts(**changes):
    values = dict(task="main", backend="vllm", model_id="Qwen/Qwen2.5-7B-Instruct@0123abcd",
                  prompt_sha256="1" * 64, decoding={"temperature": 0, "max_tokens": 256},
                  schema_sha256="2" * 64, input_sha256="3" * 64)
    values.update(changes)
    return ca.KeyParts(**values)


def entry(key, raw='{"route":"direct"}', reason="stop", usage=None):
    return ca.Entry(key, raw, reason, usage if usage is not None else {"input_tokens": 10, "output_tokens": 5},
                    "2026-11-03T00:00:00+00:00")


class KeyTests(unittest.TestCase):
    def test_key_is_stable(self):
        self.assertEqual(parts().key, parts().key)
        self.assertEqual(parts(decoding={"max_tokens": 256, "temperature": 0}).key, parts().key)

    def test_changing_any_single_component_misses(self):
        changes = {"task": "transfer", "backend": "anthropic", "model_id": "other-model",
                   "prompt_sha256": "4" * 64, "decoding": {"temperature": 0, "max_tokens": 128},
                   "schema_sha256": "5" * 64, "input_sha256": "6" * 64}
        base = parts().key
        for name, value in changes.items():
            with self.subTest(component=name):
                self.assertNotEqual(parts(**{name: value}).key, base)

    def test_malformed_parts_are_refused(self):
        for change in ({"task": "other"}, {"backend": "Bad Name"}, {"prompt_sha256": "x"},
                       {"decoding": {}}, {"model_id": "has spaces"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                parts(**change)


class CacheFixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.path = Path("outputs/llm/cache/main.jsonl")
        self.file = self.root / self.path

    def tearDown(self):
        self._tmp.cleanup()

    def cache(self):
        return ca.ResponseCache(self.path, self.root).load()


class CacheTests(CacheFixture):
    def test_round_trip_and_resume(self):
        first = self.cache()
        self.assertEqual(first.append([entry("a" * 64), entry("b" * 64, raw="", reason="length")]), 2)
        second = self.cache()
        self.assertEqual(len(second), 2)
        self.assertEqual(second.get("b" * 64).finish_reason, "length")
        self.assertIsNone(second.get("c" * 64))

    def test_identical_repeat_is_skipped_and_different_repeat_refused(self):
        cache = self.cache()
        cache.append([entry(H)])
        self.assertEqual(cache.append([entry(H)]), 0)
        with self.assertRaises(ca.CacheError):
            cache.append([entry(H, raw='{"route":"indirect"}')])
        with self.assertRaises(ca.CacheError):
            cache.append([entry("b" * 64), entry("b" * 64, usage={"output_tokens": 1})])
        self.assertEqual(len(self.cache()), 1, "a refused batch writes nothing")

    def test_created_time_is_not_content(self):
        cache = self.cache()
        cache.append([entry(H)])
        self.assertEqual(cache.append([dataclasses.replace(entry(H), created="2027-01-01T00:00:00+00:00")]), 0)

    def test_torn_final_line_is_dropped_and_cut_before_the_next_append(self):
        self.cache().append([entry("a" * 64), entry("b" * 64)])
        data = self.file.read_bytes()
        self.file.write_bytes(data[:-7])  # kill mid-write of the second line
        with self.assertLogs("src.llm.cache", "WARNING"):
            cache = self.cache()
        self.assertEqual(len(cache), 1)
        cache.append([entry("b" * 64)])
        self.assertEqual(self.file.read_bytes(), data, "resume leaves exactly the uninterrupted bytes")
        self.assertEqual(len(self.cache()), 2)

    def test_corrupt_middle_line_is_refused_without_echoing_content(self):
        self.cache().append([entry("a" * 64, raw="zq-sentinel-raw"), entry("b" * 64)])
        lines = self.file.read_bytes().split(b"\n")
        self.file.write_bytes(lines[0][:-3] + b"\n" + lines[1] + b"\n")
        with self.assertRaises(ca.CacheError) as caught:
            self.cache()
        self.assertIn("line 1", str(caught.exception))
        self.assertNotIn("zq-sentinel", str(caught.exception))

    def test_a_second_holder_of_the_cache_lock_is_refused_and_the_lock_is_released(self):
        with ca.exclusive_lock(self.file):
            with self.assertRaisesRegex(ca.CacheError, "another run"):
                with ca.exclusive_lock(self.file):
                    pass
        with ca.exclusive_lock(self.file):
            pass

    def test_repeated_json_key_in_a_line_is_refused(self):
        self.cache().append([entry("a" * 64)])
        line = self.file.read_bytes().rstrip(b"\n")
        self.file.write_bytes(line[:-1] + b',"raw":"zq-other"}\n')
        with self.assertRaisesRegex(ca.CacheError, "line 1 is malformed"):
            self.cache()

    def test_two_writers_with_different_content_are_detected_on_load(self):
        one, two = self.cache(), self.cache()
        one.append([entry(H)])
        two.append([entry(H, raw='{"route":"no_request"}')])
        with self.assertRaisesRegex(ca.CacheError, "different content"):
            self.cache()

    def test_identical_duplicate_lines_load(self):
        one, two = self.cache(), self.cache()
        one.append([entry(H)])
        two.append([entry(H)])
        self.assertEqual(len(self.cache()), 1)

    def test_unknown_fields_version_and_bad_values_are_refused(self):
        good = entry(H).line()
        for bad in (good.replace(b'"v":"llm-cache-v1"', b'"v":"llm-cache-v0"'),
                    good.replace(b'"finish_reason":"stop"', b'"finish_reason":"eos"'),
                    good.replace(b'"output_tokens":5', b'"output_tokens":-5'),
                    good[:-2] + b',"extra":1}\n'):
            with self.subTest(bad=bad[:40]):
                self.file.parent.mkdir(parents=True, exist_ok=True)
                self.file.write_bytes(bad)
                with self.assertRaises(ca.CacheError):
                    self.cache()

    def test_path_outside_outputs_is_refused(self):
        for path in (Path("data/interim/cache.jsonl"), Path("outputs/../cache.jsonl"), Path("cache.jsonl")):
            with self.subTest(path=str(path)), self.assertRaises(ValueError):
                ca.ResponseCache(path, self.root)

    def test_must_load_before_use(self):
        with self.assertRaises(RuntimeError):
            ca.ResponseCache(self.path, self.root).get(H)

    def test_entry_bounds(self):
        ca.Entry(H, "x" * (MAX_RAW_CHARS + 1), "stop")
        with self.assertRaises(ValueError):
            ca.Entry(H, "x" * (MAX_RAW_CHARS + 2), "stop")
        with self.assertRaises(ValueError):
            ca.Entry("short", "", "stop")

    def test_new_entry_stamps_utc(self):
        self.assertTrue(ca.new_entry(H, "", "stop").created.endswith("+00:00"))


if __name__ == "__main__":
    unittest.main()
