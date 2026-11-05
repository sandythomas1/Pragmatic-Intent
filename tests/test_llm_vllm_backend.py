"""Spec 009 T12: the vLLM backend, the vLLM recipe checks and ``size`` (vllm/transformers stubbed).

No real model, tokenizer or GPU is touched: ``vllm``, ``vllm.sampling_params`` and ``transformers``
are replaced in ``sys.modules`` by recording stand-ins. Fixtures are invented.
"""

import io
import json
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from src.llm import recipe as rc
from src.llm import run as lr
from src.llm.backends import backend_class, base
from src.llm.backends.fake import DEFAULT_ANSWER as ANSWER
from src.llm.backends.vllm_backend import VllmBackend, chat_token_counter, engine_arguments
from tests.test_llm_run import Root

COMMIT = "0123456789abcdef0123456789abcdef01234567"
VLLM_OPTIONS = f'revision = "{COMMIT}"\ngpu_memory_utilization = 0.85'
SCHEMA = {"type": "object", "properties": {"route": {"enum": ["direct", "no_request"]}}, "required": ["route"]}


class StubTokenizer:
    """Chat template = role:content lines plus a generation marker; one token per word."""

    def __init__(self):
        self.template_calls = []

    def apply_chat_template(self, messages, tokenize, add_generation_prompt):
        self.template_calls.append((tokenize, add_generation_prompt))
        return "\n".join(f"{m['role']}: {m['content']}" for m in messages) + ("\nassistant:" if add_generation_prompt else "")

    def __call__(self, text, add_special_tokens):
        assert add_special_tokens is False
        return {"input_ids": text.split()}


class StubEngine:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.chats = []
        self.finish = "stop"
        self.tokenizer = StubTokenizer()

    def get_tokenizer(self):
        return self.tokenizer

    def chat(self, conversations, sampling_params, use_tqdm, add_generation_prompt):
        self.chats.append((conversations, sampling_params, use_tqdm, add_generation_prompt))
        return [SimpleNamespace(prompt_token_ids=[1, 2, 3],
                                outputs=[SimpleNamespace(text=ANSWER, finish_reason=self.finish,
                                                         token_ids=[7, 8])])
                for _ in conversations]


def stub_modules():
    """Recording stand-ins for vllm, vllm.sampling_params and transformers."""
    vllm = types.ModuleType("vllm")
    vllm.engines = []

    def make_engine(**kwargs):
        engine = StubEngine(**kwargs)
        vllm.engines.append(engine)
        return engine

    vllm.LLM = make_engine
    vllm.SamplingParams = lambda **kwargs: ("sampling", kwargs)
    sampling = types.ModuleType("vllm.sampling_params")
    sampling.StructuredOutputsParams = lambda **kwargs: ("structured", kwargs)
    transformers = types.ModuleType("transformers")
    transformers.loads = []

    def from_pretrained(model, **kwargs):
        transformers.loads.append((model, kwargs))
        return StubTokenizer()

    transformers.AutoTokenizer = SimpleNamespace(from_pretrained=from_pretrained)
    return {"vllm": vllm, "vllm.sampling_params": sampling, "transformers": transformers}


class Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Root(Path(self._tmp.name), backend="vllm", model_id="zq-org/zq-model-7b", max_model_len=4096,
                         extra=VLLM_OPTIONS)
        self.modules = stub_modules()
        patcher = mock.patch.dict(sys.modules, self.modules)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self._tmp.cleanup()

    def backend(self):
        return backend_class("vllm").from_recipe(self.root.recipe())

    def request(self, key="a" * 64):
        return base.Request(key, ({"role": "system", "content": "zq rules"}, {"role": "user", "content": "zq turn"}),
                            SCHEMA)


class EngineTests(Fixture):
    def test_engine_is_pinned_greedy_bf16_and_never_trusts_remote_code(self):
        backend = self.backend()
        kwargs = self.modules["vllm"].engines[0].kwargs
        self.assertEqual(kwargs["model"], "zq-org/zq-model-7b")
        self.assertEqual((kwargs["revision"], kwargs["tokenizer_revision"]), (COMMIT, COMMIT))
        self.assertIs(kwargs["trust_remote_code"], False)
        self.assertEqual((kwargs["dtype"], kwargs["max_model_len"], kwargs["gpu_memory_utilization"]),
                         ("bfloat16", 4096, 0.85))
        self.assertTrue(kwargs["enable_prefix_caching"])
        self.assertEqual(backend.model_id, f"zq-org/zq-model-7b@{COMMIT}", "matches recipe.model_ref")

    def test_each_request_is_greedy_and_constrained_to_its_own_schema(self):
        backend = self.backend()
        other = {"type": "object", "properties": {"value": {"enum": ["zq-a", "zq-b"]}}}
        responses = backend.generate([self.request("a" * 64), base.Request("b" * 64, self.request().messages, other)])
        _, params, use_tqdm, add_generation_prompt = self.modules["vllm"].engines[0].chats[0]
        self.assertEqual([p[1]["structured_outputs"] for p in params],
                         [("structured", {"json": SCHEMA}), ("structured", {"json": other})])
        self.assertTrue(all(p[1]["temperature"] == 0 and p[1]["max_tokens"] == 256 for p in params))
        self.assertEqual((use_tqdm, add_generation_prompt), (False, True))
        self.assertEqual([(r.key, r.raw, r.finish_reason) for r in responses],
                         [("a" * 64, ANSWER, "stop"), ("b" * 64, ANSWER, "stop")])
        self.assertEqual(responses[0].usage, {"input_tokens": 3, "output_tokens": 2})

    def test_length_finish_maps_to_length_and_the_parser_marks_it_truncated(self):
        from src.llm.schema import Invalid, parse_main
        backend = self.backend()
        self.modules["vllm"].engines[0].finish = "length"
        response = backend.generate([self.request()])[0]
        self.assertEqual(response.finish_reason, "length")
        outcome = parse_main(response.raw, response.finish_reason, frozenset())
        self.assertIsInstance(outcome, Invalid)
        self.assertEqual(outcome.reason, "truncated")

    def test_aborted_request_is_an_unmapped_failure_that_stops_the_run(self):
        backend = self.backend()
        self.modules["vllm"].engines[0].finish = "abort"
        with self.assertRaises(base.RunStopped):
            base.generate_with_retry(backend, [self.request()], error_log=base.ErrorLog(
                Path("outputs/llm/errors/x.jsonl"), self.root.path), stats=base.CallStats(),
                sleep=lambda _: None, rng=__import__("random").Random(1))

    def test_token_counter_uses_the_chat_template_with_the_generation_prompt(self):
        backend = self.backend()
        count = backend.token_counter()
        self.assertEqual(count(self.request().messages), len("system: zq rules\nuser: zq turn\nassistant:".split()))
        self.assertEqual(self.modules["vllm"].engines[0].tokenizer.template_calls, [(False, True)])

    def test_counter_from_recipe_loads_only_the_pinned_tokenizer(self):
        counter = VllmBackend.counter_from_recipe(self.root.recipe())
        self.assertEqual(self.modules["transformers"].loads,
                         [("zq-org/zq-model-7b", {"revision": COMMIT, "trust_remote_code": False})])
        self.assertEqual(self.modules["vllm"].engines, [], "no engine, no GPU")
        self.assertGreater(counter(self.request().messages), 0)

    def test_optional_max_num_seqs_is_passed_through(self):
        self.assertEqual(engine_arguments("m", {"revision": COMMIT, "max_model_len": 512,
                                                "gpu_memory_utilization": 0.5, "max_num_seqs": 64})["max_num_seqs"], 64)
        self.assertNotIn("max_num_seqs", engine_arguments("m", {"revision": COMMIT, "max_model_len": 512,
                                                                "gpu_memory_utilization": 0.5}))

    def test_runner_end_to_end_on_the_stubbed_engine(self):
        provenance = lr.run(self.root.recipe(), split="dev", task="main", root=self.root.path,
                            sleep=lambda _: None)
        self.assertEqual(provenance["backend"], "vllm")
        self.assertEqual(provenance["model"], f"zq-org/zq-model-7b@{COMMIT}")
        self.assertEqual(provenance["preflight"]["over_limit"], 0)
        self.assertEqual(provenance["counts"]["invalid_calls_by_reason"], {})


class RecipeTests(Fixture):
    def test_vllm_options_are_refused_unless_pinned_and_bounded(self):
        cases = {
            "branch revision": dict(extra='revision = "main"\ngpu_memory_utilization = 0.85'),
            "short commit": dict(extra='revision = "0123abcd"\ngpu_memory_utilization = 0.85'),
            "missing revision": dict(extra="gpu_memory_utilization = 0.85"),
            "missing memory share": dict(extra=f'revision = "{COMMIT}"'),
            "memory share too high": dict(extra=f'revision = "{COMMIT}"\ngpu_memory_utilization = 0.99'),
            "integer memory share": dict(extra=f'revision = "{COMMIT}"\ngpu_memory_utilization = 1'),
            "window below max_tokens": dict(max_model_len=256, extra=VLLM_OPTIONS),
            "window too large": dict(max_model_len=10 ** 6, extra=VLLM_OPTIONS),
            "unknown option": dict(extra=VLLM_OPTIONS + '\nquantization = "awq"'),
            "remote code option": dict(extra=VLLM_OPTIONS + "\ntrust_remote_code = true"),
            "bad max_num_seqs": dict(extra=VLLM_OPTIONS + "\nmax_num_seqs = 0"),
        }
        for name, change in cases.items():
            with self.subTest(name):
                self.root.write_recipe(backend="vllm", model_id="zq-org/zq-model-7b",
                                       **{"max_model_len": 4096, **change})
                with self.assertRaises(rc.RecipeError):
                    self.root.recipe()

    def test_committed_qwen_recipe_loads_and_is_pinned(self):
        recipe = rc.load_recipe(Path("configs/llm/qwen2.5-7b-instruct.toml"))
        self.assertEqual((recipe.backend, recipe.model_id), ("vllm", "Qwen/Qwen2.5-7B-Instruct"))
        self.assertRegex(recipe.options["revision"], r"^[0-9a-f]{40}$")
        self.assertEqual((recipe.decoding["temperature"], recipe.max_tokens), (0, 256))
        self.assertEqual(set(recipe.variants), {"p1", "p2"})
        self.assertEqual(set(recipe.inputs), {"dev", "test"})


class SizeTests(Fixture):
    def test_size_reports_each_prompt_family_and_the_window_needed(self):
        report = lr.size(self.root.recipe(), split="dev", root=self.root.path)
        self.assertEqual(set(report["prompts"]), {"p1", "p2", "transfer"})
        self.assertEqual(report["prompts"]["p1"]["prompts"], 5, "distinct inputs, not records")
        self.assertTrue(report["fits"])
        self.assertEqual(report["required_max_model_len"],
                         max(v["required_max_model_len"] for v in report["prompts"].values()))
        self.assertGreater(report["required_max_model_len"], report["max_tokens"])
        self.assertEqual(self.modules["vllm"].engines, [], "sizing never builds the engine")
        text = json.dumps(report)
        for leaked in ("PMUL", "zq-sentinel", "zq book"):
            self.assertNotIn(leaked, text)

    def test_size_flags_a_window_that_is_too_small(self):
        self.root.write_recipe(backend="vllm", model_id="zq-org/zq-model-7b", max_model_len=270, extra=VLLM_OPTIONS)
        report = lr.size(self.root.recipe(), split="dev", root=self.root.path)
        self.assertFalse(report["fits"])
        self.assertGreater(report["required_max_model_len"], 270)

    def test_size_refuses_the_test_split_and_cli_prints_json(self):
        with self.assertRaises(lr.RunRefused):
            lr.size(self.root.recipe(), split="test", root=self.root.path)
        out = io.StringIO()
        with redirect_stdout(out), mock.patch.object(lr, "load_recipe", lambda path: self.root.recipe()), \
                mock.patch.object(lr, "size", lambda recipe, split: {"fits": True}):
            self.assertEqual(lr.main(["size", "--recipe", "x.toml", "--split", "dev"]), 0)
        self.assertEqual(json.loads(out.getvalue()), {"fits": True})


class ImportTests(unittest.TestCase):
    def test_module_imports_without_vllm_installed(self):
        self.assertNotIn("vllm", sys.modules)
        self.assertIs(backend_class("vllm"), VllmBackend)
        self.assertNotIn("vllm", sys.modules)
        self.assertEqual(chat_token_counter(StubTokenizer())([{"role": "user", "content": "a b"}]), 4)


if __name__ == "__main__":
    unittest.main()
