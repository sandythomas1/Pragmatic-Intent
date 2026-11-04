"""Spec 009 T8: recipe loading, the runner end to end on a fake backend, streams and provenance.

Fixtures are invented (PMUL9xxx IDs, zq- sentinel text) and live in a temporary repository root.
"""

import io
import json
import logging
import os
import random
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from src.data import indirect_requests as ir
from src.evaluation import interpretation as ip
from src.evaluation import transfer as tr
from src.llm import inputs as li
from src.llm import recipe as rc
from src.llm import run as lr
from src.llm import schema as sc
from src.llm.backends import base, fake
from src.llm.cache import CacheError, exclusive_lock
from src.llm.preflight import PreflightError

KEYS = ["hotel.area", "hotel.people", "hotel.phone"]
SENTINEL = "zq-sentinel the purple lighthouse"
FAKE_KEY = "sk-test-zq-not-a-real-key-1111"
RECIPE = """version = "llm-recipe-v1"
system = "fake-llm"
backend = "{backend}"
model_id = "{model_id}"
batch_size = 2
slot_keys = "configs/llm/slot_keys.json"

[decoding]
temperature = {temperature}
max_tokens = 256

[prompts]
main = "p1"
transfer = "configs/llm/prompts/t1.txt"

[prompts.variants]
p1 = "configs/llm/prompts/p1.txt"
p2 = "outputs/llm/prompts/p2.txt"

[inputs.dev]
routed = "data/interim/stage2/dev_routed_inputs.jsonl"
oracle = "data/interim/stage2/dev_oracle_inputs.jsonl"
transfer = "data/interim/stage2/transfer_inputs.jsonl"

[backend_options]
max_model_len = {max_model_len}
{extra}
"""


def main_record(example_id, condition, context, target):
    return {"example_id": example_id, "condition": condition, "context": context, "target": target,
            "renderer_version": "render-v1", "input_sha256": li.main_input_sha256(context, target)}


ROUTED = [
    main_record("PMUL9001_t02:direct", "none", "", "zq book a room for two"),
    main_record("PMUL9001_t02:direct", "full", f"USER: {SENTINEL}", "zq book a room for two"),
    main_record("PMUL9002_t04:indirect", "none", "", "zq-bad output please"),
    main_record("PMUL9002_t04:indirect", "one", "SYSTEM: zq hello", "zq-bad output please"),
    main_record("PMUL9002_t04:indirect", "full", f"USER: {SENTINEL}", "zq-silent thanks"),
    main_record("PMUL9003_t02:direct", "none", "", "zq book a room for two"),  # same input as row 1
]
ORACLE = [ROUTED[2], ROUTED[3], ROUTED[4]]
ITEMS = [ir.TransferItem("PMUL9101", "validation", "Hotels_1", f"zq is it pricey {SENTINEL}", "zq price band",
                         ("cheap", "moderate"), ("", ""), "cheap"),
         ir.TransferItem("PMUL9102", "validation", "Hotels_1", "zq any wifi", "zq has wifi",
                         ("True", "False"), ("has wifi", "no wifi"), "True")]


def respond(request):
    """Scripted answers keyed on the invented target text; never looks at IDs."""
    user = request.messages[-1]["content"]
    if request.schema["properties"].keys() == {"request", "value"}:
        value = request.schema["properties"]["value"]["enum"][0]
        return json.dumps({"request": True, "value": value}), "stop", {"input_tokens": 7, "output_tokens": 3}
    if "zq-bad" in user:
        return "not json at all", "stop", {"input_tokens": 9, "output_tokens": 4}
    route = "no_request" if "zq-silent" in user else "direct"
    body = {"route": route, "category": "booking", "slots": [{"slot": "hotel.people", "value": "two"}],
            "requested_slots": []}
    return json.dumps(body), "stop", {"input_tokens": 11, "output_tokens": 6}


class Root:
    """A throwaway repository root with prompts, vocabulary, inputs and a recipe."""

    def __init__(self, path: Path, **recipe):
        self.path = path
        self.write("configs/llm/prompts/p1.txt", "Classify the target turn.\nSlots:\n{{slot_keys}}\n")
        self.write("outputs/llm/prompts/p2.txt", "Classify the target turn, with examples.\nSlots:\n{{slot_keys}}\n")
        self.write("configs/llm/prompts/t1.txt", "Answer the transfer questions.\n")
        self.write("configs/llm/slot_keys.json", json.dumps(sc.slot_keys_document(KEYS, "0" * 64)))
        self.write_jsonl("data/interim/stage2/dev_routed_inputs.jsonl", ROUTED)
        self.write_jsonl("data/interim/stage2/dev_oracle_inputs.jsonl", ORACLE)
        self.write_jsonl("data/interim/stage2/transfer_inputs.jsonl", [ir.input_record(item) for item in ITEMS])
        self.write_recipe(**recipe)

    def write(self, relative, text):
        target = self.path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")

    def write_jsonl(self, relative, rows):
        self.write(relative, "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows))

    def write_recipe(self, backend="fake", model_id="fake-model", temperature=0, max_model_len=2048, extra=""):
        self.write("configs/llm/fake.toml", RECIPE.format(backend=backend, model_id=model_id, temperature=temperature,
                                                          max_model_len=max_model_len, extra=extra))

    def recipe(self):
        return rc.load_recipe(Path("configs/llm/fake.toml"), self.path)

    def read(self, relative):
        return (self.path / relative).read_bytes()

    def rows(self, relative):
        return [json.loads(line) for line in self.read(relative).decode("utf-8").splitlines()]


class Factory:
    """Builds fake backends and records every construction (and each backend's calls)."""

    def __init__(self, failures=(), model_id=None):
        self.failures = list(failures)
        self.model_id = model_id
        self.built = []

    def __call__(self, recipe):
        backend = fake.FakeBackend(model_id=self.model_id or recipe.model_ref, respond=respond, failures=self.failures)
        self.built.append(backend)
        return backend

    @property
    def calls(self):
        return sum(backend.calls for backend in self.built)


class Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Root(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def run_task(self, task="main", factory=None, root=None, **kwargs):
        root = root or self.root
        factory = factory if factory is not None else Factory()
        provenance = lr.run(root.recipe(), split="dev", task=task, root=root.path, backend_factory=factory,
                            sleep=lambda _: None, rng=random.Random(1), **kwargs)
        return provenance, factory


class RecipeTests(Fixture):
    def test_valid_recipe_loads_with_resolved_paths_and_hash(self):
        recipe = self.root.recipe()
        self.assertEqual((recipe.system, recipe.backend, recipe.model_ref, recipe.max_tokens), ("fake-llm", "fake", "fake-model", 256))
        self.assertTrue(recipe.prompt_path("p2").is_relative_to(self.root.path))
        self.assertRegex(recipe.text_sha256, r"^[0-9a-f]{64}$")
        self.assertFalse(recipe.paid)

    def test_revision_is_part_of_the_model_reference(self):
        self.root.write_recipe(extra='revision = "0123abcd"')
        self.assertEqual(self.root.recipe().model_ref, "fake-model@0123abcd")

    def test_bad_recipes_are_refused(self):
        cases = {
            "non-zero temperature": dict(temperature=0.7),
            "floating model": dict(model_id="some-model-latest"),
            "unknown backend": dict(backend="shell"),
            "credential option": dict(extra='api_key = "sk-zq"'),
            "bad revision": dict(extra='revision = "main branch"'),
        }
        for name, change in cases.items():
            with self.subTest(name), self.assertRaises(rc.RecipeError) as caught:
                self.root.write_recipe(**change)
                self.root.recipe()
            self.assertNotIn("sk-zq", str(caught.exception))

    def test_unknown_fields_escaping_paths_and_unselected_main_are_refused(self):
        text = (self.root.path / "configs/llm/fake.toml").read_text(encoding="utf-8")
        edits = {"unknown field": text.replace('system = "fake-llm"', 'system = "fake-llm"\nshell = "x"'),
                 "escaping path": text.replace('"configs/llm/slot_keys.json"', '"../outside.json"'),
                 "absolute path": text.replace('"configs/llm/slot_keys.json"', '"/etc/passwd"'),
                 "main not a variant": text.replace('main = "p1"', 'main = "p9"'),
                 "routed without oracle": text.replace('oracle = "data/interim/stage2/dev_oracle_inputs.jsonl"\n', "")}
        for name, edited in edits.items():
            with self.subTest(name):
                self.root.write("configs/llm/fake.toml", edited)
                with self.assertRaises(rc.RecipeError):
                    self.root.recipe()

    def test_recipe_outside_the_root_is_refused(self):
        with tempfile.TemporaryDirectory() as other, self.assertRaises(rc.RecipeError):
            rc.load_recipe(Path(other) / "fake.toml", self.root.path)


class StreamTests(Fixture):
    def test_ac_009_1_main_streams_validate_with_one_row_per_record(self):
        provenance, factory = self.run_task()
        routed = self.root.rows("outputs/stage2/fake-llm/dev/routed.jsonl")
        oracle = self.root.rows("outputs/stage2/fake-llm/dev/oracle.jsonl")
        for rows, records in ((routed, ROUTED), (oracle, ORACLE)):
            expected = {}
            for record in records:
                expected.setdefault(record["condition"], set()).add(record["example_id"])
            ip.validate_predictions(rows, expected)
            self.assertEqual([(r["example_id"], r["condition"]) for r in rows],
                             [(r["example_id"], r["condition"]) for r in records], "input-file order")
        distinct = len({r["input_sha256"] for r in ROUTED})
        self.assertEqual(distinct, 5)
        self.assertEqual(factory.calls, distinct, "one call per distinct input (FR2)")
        by_key = {(r["example_id"], r["condition"]): r for r in routed}
        self.assertTrue(by_key[("PMUL9002_t04:indirect", "none")]["invalid"])
        silent = by_key[("PMUL9002_t04:indirect", "full")]
        self.assertEqual((silent["prediction"], silent["category"], silent["slots"]), ("no_request", None, {}))
        oracle_silent = {(r["example_id"], r["condition"]): r for r in oracle}[("PMUL9002_t04:indirect", "full")]
        self.assertEqual(oracle_silent["category"], "booking", "oracle keeps the interpretation")
        self.assertEqual(provenance["counts"]["invalid_calls_by_reason"], {"parse": 2}, "zq-bad under two contexts")
        self.assertEqual(provenance["counts"]["invalid_rows_by_reason"], {"oracle": {"parse": 2}, "routed": {"parse": 2}})

    def test_ac_009_1_transfer_stream_passes_the_transfer_scorer(self):
        provenance, factory = self.run_task("transfer")
        rows = self.root.rows("outputs/stage2/fake-llm/dev/transfer.jsonl")
        report = tr.build_report(ITEMS, rows, model_family="fake")
        self.assertEqual((report["n"], report["invalid_outputs"], report["detected_requests"]), (2, 0, 2))
        self.assertEqual(factory.calls, 2)
        self.assertTrue(provenance["schema_per_record"])
        self.assertTrue((self.root.path / "outputs/stage2/fake-llm/dev/provenance.transfer.json").exists())


class ResumeTests(Fixture):
    def test_ac_009_4_kill_and_rerun_is_byte_identical_and_calls_only_misses(self):
        killed = Factory(failures=[None] + [base.TransportError("down", status=503)] * 5)
        with self.assertRaises(base.RunStopped):
            self.run_task(factory=killed)
        self.assertFalse((self.root.path / "outputs/stage2/fake-llm/dev/routed.jsonl").exists(), "no partial stream")
        resumed_provenance, resumed = self.run_task()
        self.assertEqual(resumed.calls, 5 - 2, "the first batch (2 inputs) was cached before the kill")
        self.assertEqual(resumed_provenance["counts"]["cache_hits"], 2)

        with tempfile.TemporaryDirectory() as other:
            clean = Root(Path(other))
            self.run_task(root=clean)
            for name in ("routed.jsonl", "oracle.jsonl"):
                self.assertEqual(self.root.read(f"outputs/stage2/fake-llm/dev/{name}"),
                                 clean.read(f"outputs/stage2/fake-llm/dev/{name}"))

        again_provenance, again = self.run_task()
        self.assertEqual(again.built, [], "a fully cached rerun never constructs the backend")
        self.assertEqual((again_provenance["counts"]["calls"], again_provenance["counts"]["cache_hits"]), (0, 5))
        self.assertIsNone(again_provenance["preflight"])

    def test_changed_prompt_or_schema_invalidates_every_hit(self):
        self.run_task()
        self.root.write("configs/llm/prompts/p1.txt", "Classify the target turn (edited).\nSlots:\n{{slot_keys}}\n")
        _, after_prompt = self.run_task()
        self.assertEqual(after_prompt.calls, 5)
        self.root.write("configs/llm/slot_keys.json", json.dumps(sc.slot_keys_document(KEYS + ["train.leaveat"], "0" * 64)))
        _, after_schema = self.run_task()
        self.assertEqual(after_schema.calls, 5)

    def test_task_namespaces_are_separate(self):
        self.run_task()
        _, transfer = self.run_task("transfer")
        self.assertEqual(transfer.calls, 2)


class SelectionTests(Fixture):
    def test_variant_and_condition_subsets_write_to_the_selection_tree_and_reuse_answers(self):
        provenance, factory = self.run_task(variant="p2", conditions=["full", "none"])
        rows = self.root.rows("outputs/llm/selection/fake-llm/p2/dev/routed.jsonl")
        self.assertEqual({r["condition"] for r in rows}, {"none", "full"})
        self.assertEqual(provenance["conditions"], ["none", "full"], "canonical order")
        self.assertFalse(provenance["selected_variant"])
        self.assertFalse((self.root.path / "outputs/stage2").exists())
        self.assertEqual(factory.calls, len({r["input_sha256"] for r in ROUTED if r["condition"] in {"none", "full"}}))

        self.run_task(conditions=["none", "full"])
        _, full = self.run_task()
        self.assertEqual(full.calls, 1, "the selected variant's none/full answers are reused; only 'one' is new")

    def test_bad_requests_are_refused_before_any_backend(self):
        cases = [dict(variant="p9"), dict(conditions=["none", "none"]), dict(conditions=["sideways"])]
        for kwargs in cases:
            factory = Factory()
            with self.subTest(kwargs), self.assertRaises((lr.RunRefused, rc.RecipeError)):
                self.run_task(factory=factory, **kwargs)
            self.assertEqual(factory.built, [])
        with self.assertRaises(lr.RunRefused):
            self.run_task("transfer", variant="p2")


class SafetyTests(Fixture):
    def test_test_split_is_refused_before_inputs_or_backend(self):
        factory = Factory()
        with self.assertRaisesRegex(lr.RunRefused, "T10"):
            lr.run(self.root.recipe(), split="test", task="main", root=self.root.path, backend_factory=factory)
        self.assertEqual(factory.built, [])
        self.assertFalse((self.root.path / "outputs/llm/cache").exists())

    def test_cli_refuses_the_test_split_without_reading_the_recipe(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            code = lr.main(["run", "--recipe", "configs/llm/does-not-exist.toml", "--split", "test", "--task", "main"])
        self.assertEqual(code, 1)
        self.assertIn("refused", stderr.getvalue())

    def test_paid_backend_is_refused_until_the_ledger_exists(self):
        self.root.write_recipe(backend="anthropic", model_id="claude-zq-20260101")
        factory = Factory()
        with self.assertRaisesRegex(lr.RunRefused, "T7"):
            self.run_task(factory=factory)
        self.assertEqual(factory.built, [])

    def test_backend_that_does_not_match_the_recipe_is_refused(self):
        with self.assertRaisesRegex(lr.RunRefused, "does not match"):
            self.run_task(factory=Factory(model_id="other-model"))

    def test_preflight_refuses_an_overlong_prompt_before_any_call(self):
        self.root.write_recipe(max_model_len=270)
        factory = Factory()
        with self.assertRaises(PreflightError):
            self.run_task(factory=factory)
        self.assertEqual(factory.calls, 0)

    def test_a_held_cache_lock_refuses_a_second_run(self):
        cache = self.root.path / "outputs/llm/cache/fake-llm/main.jsonl"
        factory = Factory()
        with exclusive_lock(cache), self.assertRaisesRegex(CacheError, "another run"):
            self.run_task(factory=factory)
        self.assertEqual(factory.built, [])

    def test_tampered_input_is_refused(self):
        tampered = dict(ROUTED[0], target="zq something else")
        self.root.write_jsonl("data/interim/stage2/dev_routed_inputs.jsonl", [tampered, *ROUTED[1:]])
        with self.assertRaises(li.InputError):
            self.run_task()


class ProvenanceTests(Fixture):
    FR8 = ("backend", "model", "decoding", "schema_sha256", "inputs", "code", "started", "finished",
           "counts", "usage", "spend", "prompt", "recipe", "outputs", "preflight")

    def test_ac_009_5_every_fr8_field_and_no_key_or_sentinel_anywhere(self):
        factory = Factory(failures=[fake.echoing_error(503, FAKE_KEY)])
        stderr = io.StringIO()
        with mock.patch.dict(os.environ, {"ZQ_PROVIDER_API_KEY": FAKE_KEY}), redirect_stderr(stderr), \
                self.assertLogs("src.llm", logging.INFO) as logs:
            provenance, _ = self.run_task(factory=factory)
        text = self.root.read("outputs/stage2/fake-llm/dev/provenance.main.json").decode("utf-8")
        self.assertEqual(json.loads(text), provenance)
        for field in self.FR8:
            self.assertIn(field, provenance)
        self.assertEqual(set(provenance["prompt"]), {"path", "template_sha256", "rendered_sha256", "framing_version"})
        self.assertTrue({"source_sha256", "git_commit", "git_dirty"} <= set(provenance["code"]))
        self.assertEqual(provenance["inputs"]["routed"]["records"], len(ROUTED))
        counts = provenance["counts"]
        self.assertEqual((counts["retries"], counts["transport_errors"], counts["calls"]), (1, 1, 5 + 2))
        self.assertEqual(provenance["usage"]["new_calls"], provenance["usage"]["all_answers"])
        shown = text + "\n".join(logs.output) + stderr.getvalue()
        for secret in ("zq-sentinel", "purple lighthouse", FAKE_KEY, "PMUL9001", "zq book"):
            self.assertNotIn(secret, shown)
        output_hashes = provenance["outputs"]
        self.assertEqual(set(output_hashes), {"routed.jsonl", "oracle.jsonl"})


if __name__ == "__main__":
    unittest.main()
