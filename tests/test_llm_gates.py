"""Spec 009 T10: `--split test` stops before any backend or write without a matching freeze (AC-009-11)."""

from __future__ import annotations

import io
import random
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

from src.data import freeze
from src.llm import compose as lc
from src.llm import run as lr
from tests import test_llm_compose as tc
from tests import test_llm_run as tr

FREEZE_SHA = "f" * 64
INTERPRETER_SYSTEM = "qwen-zq"
INTERPRETER_MODEL = "zq/model@abc"
RECIPE_PATH = "configs/llm/zq.toml"
RECIPE_SHA = "a" * 64
PROMPT_SHA = "b" * 64
FILLED_SHA = "c" * 64
TEST_INPUTS = """
[inputs.test]
routed = "data/interim/stage2/test_routed_inputs.jsonl"
oracle = "data/interim/stage2/test_oracle_inputs.jsonl"
transfer = "data/interim/stage2/transfer_inputs.jsonl"
"""


def record(pins: dict[str, str], *panel: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(pins=pins, config=SimpleNamespace(panel=panel), content_sha256=FREEZE_SHA)


class RunnerGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = tr.Root(Path(self._tmp.name))
        self.root.write_jsonl("data/interim/stage2/test_routed_inputs.jsonl", tr.ROUTED)
        self.root.write_jsonl("data/interim/stage2/test_oracle_inputs.jsonl", tr.ORACLE)
        text = (self.root.path / "configs/llm/fake.toml").read_text(encoding="utf-8")
        self.root.write("configs/llm/fake.toml", text + TEST_INPUTS)
        self.recipe = self.root.recipe()

    def pins(self, **overrides: str) -> dict[str, str]:
        system = self.recipe.system
        files = lr.frozen_recipe_files(self.recipe, self.root.path)
        pins = {f"recipe.{system}.seeds": "0", f"recipe.{system}.llm_model": self.recipe.model_ref,
                f"recipe.{system}.rendered.prompt": freeze.text_sha256(self.recipe.prompt_path(self.recipe.main_prompt))}
        pins.update({f"recipe.{system}.file.{path}": sha for path, sha in files.items()})
        pins.update(overrides)
        return pins

    def run_test(self, pins: dict[str, str] | None = None, factory: tr.Factory | None = None,
                 task: str = "main", **kwargs: Any) -> tuple[dict[str, Any], tr.Factory]:
        factory = factory if factory is not None else tr.Factory()
        frozen = record(self.pins() if pins is None else pins, SimpleNamespace(name=self.recipe.system))
        with mock.patch.object(lr, "require_freeze", return_value=frozen):
            provenance = lr.run(self.recipe, split="test", task=task, root=self.root.path, backend_factory=factory,
                                sleep=lambda _: None, rng=random.Random(1), **kwargs)
        return provenance, factory

    def assert_refused(self, pins: dict[str, str] | None = None, **kwargs: Any) -> None:
        factory = tr.Factory()
        with self.assertRaises(lr.RunRefused):
            self.run_test(pins, factory, **kwargs)
        self.assertEqual(factory.built, [])
        self.assertFalse((self.root.path / "outputs/llm/cache").exists())
        self.assertFalse((self.root.path / "outputs/stage2").exists())

    def test_no_freeze_stops_before_the_backend(self) -> None:
        factory = tr.Factory()
        with self.assertRaisesRegex(lr.RunRefused, "freeze"):
            lr.run(self.recipe, split="test", task="main", root=self.root.path, backend_factory=factory)
        self.assertEqual(factory.built, [])
        self.assertFalse((self.root.path / "outputs/llm/cache").exists())

    def test_a_failing_freeze_is_a_refusal(self) -> None:
        factory = tr.Factory()
        error = freeze.FreezeError("freeze_mismatch", "1 pin(s) differ from the freeze: code.x", ["code.x"])
        with mock.patch.object(lr, "require_freeze", side_effect=error), self.assertRaisesRegex(lr.RunRefused, "differ"):
            lr.run(self.recipe, split="test", task="main", root=self.root.path, backend_factory=factory)
        self.assertEqual(factory.built, [])

    def test_a_moved_recipe_file_stops_before_the_backend(self) -> None:
        pins = self.pins()
        del pins[f"recipe.{self.recipe.system}.file.configs/llm/fake.toml"]
        self.assert_refused(pins)

    def test_a_changed_recipe_file_stops_before_the_backend(self) -> None:
        self.assert_refused(self.pins(**{f"recipe.{self.recipe.system}.file.configs/llm/slot_keys.json": "0" * 64}))

    def test_a_different_rendered_prompt_stops_before_the_backend(self) -> None:
        self.assert_refused(self.pins(**{f"recipe.{self.recipe.system}.rendered.prompt": "0" * 64}))

    def test_a_different_model_stops_before_the_backend(self) -> None:
        self.assert_refused(self.pins(**{f"recipe.{self.recipe.system}.llm_model": "other-model"}))

    def test_an_unselected_variant_is_refused_even_if_its_file_is_pinned(self) -> None:
        other = next(name for name in self.recipe.variants if name != self.recipe.main_prompt)
        self.assert_refused(variant=other)

    def test_a_condition_subset_is_refused(self) -> None:
        self.assert_refused(conditions=("none",))

    def test_a_sample_is_refused(self) -> None:
        self.assert_refused(sample=SimpleNamespace(example_ids=frozenset()))

    def test_a_matching_run_proceeds_and_records_the_freeze(self) -> None:
        provenance, factory = self.run_test()
        self.assertEqual(len(factory.built), 1)
        self.assertEqual(provenance["freeze_content_sha256"], FREEZE_SHA)

    def test_the_composer_accepts_what_a_frozen_run_records(self) -> None:
        """The two gates must agree on real provenance, which a hand-written fixture can't show."""
        self.run_test()
        directory = next(self.root.path.rglob("provenance.main.json")).parent
        frozen = record(self.pins(), SimpleNamespace(name=self.recipe.system))
        lc.check_frozen_interpreter(frozen, lc.load_interpreter(directory, "test"))

    def test_transfer_is_gated_on_the_same_pins(self) -> None:
        pins = self.pins()
        del pins[f"recipe.{self.recipe.system}.file.configs/llm/prompts/t1.txt"]
        self.assert_refused(pins, task="transfer")

    def test_a_dev_run_records_no_freeze(self) -> None:
        provenance = lr.run(self.recipe, split="dev", task="main", root=self.root.path, backend_factory=tr.Factory(),
                            sleep=lambda _: None, rng=random.Random(1))
        self.assertNotIn("freeze_content_sha256", provenance)

    def test_smoke_and_size_stay_refused_on_test(self) -> None:
        for command in (["smoke"], ["size"]):
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                code = lr.main([*command, "--recipe", "configs/llm/does-not-exist.toml", "--split", "test"])
            self.assertEqual(code, 1)
            self.assertIn("refused", stderr.getvalue())

    def test_the_cli_refuses_without_a_freeze_before_reading_the_recipe(self) -> None:
        stderr = io.StringIO()
        with mock.patch.object(lr, "require_freeze", side_effect=freeze.FreezeError("no_freeze", "no freeze record")), \
                redirect_stderr(stderr):
            code = lr.main(["run", "--recipe", "configs/llm/does-not-exist.toml", "--split", "test", "--task", "main"])
        self.assertEqual(code, 1)
        self.assertIn("refused", stderr.getvalue())


class ComposerGateTests(unittest.TestCase):
    INTERPRETER = tc.INTERPRETER_DIR

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        for target in ("source_sha256", "git_state"):
            value = "zq" if target == "source_sha256" else {"git_commit": "zq", "git_dirty": False}
            patch = mock.patch.object(lc, target, return_value=value)
            patch.start()
            self.addCleanup(patch.stop)
        for condition in tc.TRAIN:
            for seed in tc.SEEDS:
                tc.write_router_run(self.root, condition, seed, config_split="test", run_split="test")
        self.write_interpreter()
        config = (self.root / tc.ROUTER_ROOT / "train-none/seed13/config.resolved.json").read_text(encoding="utf-8")
        self.recipe_sha = freeze.recipe_sha256(lc.json.loads(config))

    def write_interpreter(self, **overrides: Any) -> None:
        run = {"system": INTERPRETER_SYSTEM, "model": INTERPRETER_MODEL,
               "recipe": {"path": RECIPE_PATH, "text_sha256": RECIPE_SHA},
               "prompt": {"template_sha256": PROMPT_SHA, "rendered_sha256": FILLED_SHA}}
        tc.write_interpreter(self.root, split="test", **{**run, **overrides})

    def frozen(self, **overrides: str) -> SimpleNamespace:
        pins = {f"recipe.{lc.ROUTER_NAME}.seeds": ",".join(str(seed) for seed in tc.SEEDS),
                f"recipe.{lc.ROUTER_NAME}.stage1": self.recipe_sha,
                f"recipe.{INTERPRETER_SYSTEM}.seeds": "0",
                f"recipe.{INTERPRETER_SYSTEM}.llm_model": INTERPRETER_MODEL,
                f"recipe.{INTERPRETER_SYSTEM}.file.{RECIPE_PATH}": RECIPE_SHA,
                f"recipe.{INTERPRETER_SYSTEM}.rendered.prompt": PROMPT_SHA, **overrides}
        return record(pins, SimpleNamespace(name=lc.ROUTER_NAME, family="encoder", design="matched"),
                      SimpleNamespace(name=INTERPRETER_SYSTEM))

    def compose(self, frozen: SimpleNamespace) -> dict[str, Any]:
        with mock.patch.object(lc, "require_freeze", return_value=frozen):
            return lc.compose(split="test", router_root=tc.ROUTER_ROOT, interpreter_dir=self.INTERPRETER, root=self.root)

    def assert_nothing_written(self) -> None:
        self.assertFalse((self.root / "outputs/stage2/hybrid").exists())

    def test_no_freeze_is_refused_and_nothing_is_written(self) -> None:
        with self.assertRaises(lc.ComposeError) as caught:
            lc.compose(split="test", router_root=tc.ROUTER_ROOT, interpreter_dir=self.INTERPRETER, root=self.root)
        self.assertEqual(caught.exception.code, "refused")
        self.assert_nothing_written()

    def test_an_unfrozen_seed_is_refused_and_nothing_is_written(self) -> None:
        with self.assertRaises(lc.ComposeError) as caught:
            self.compose(self.frozen(**{f"recipe.{lc.ROUTER_NAME}.seeds": "13"}))
        self.assertEqual(caught.exception.code, "seed_not_frozen")
        self.assert_nothing_written()

    def test_an_unfrozen_recipe_is_refused_and_nothing_is_written(self) -> None:
        with self.assertRaises(lc.ComposeError) as caught:
            self.compose(self.frozen(**{f"recipe.{lc.ROUTER_NAME}.stage1": "0" * 64}))
        self.assertEqual(caught.exception.code, "recipe_not_frozen")
        self.assert_nothing_written()

    def assert_interpreter_refused(self, code: str, **overrides: Any) -> None:
        self.write_interpreter(**overrides)
        with self.assertRaises(lc.ComposeError) as caught:
            self.compose(self.frozen())
        self.assertEqual(caught.exception.code, code)
        self.assert_nothing_written()

    def test_an_interpreter_run_that_is_not_the_frozen_one_is_refused(self) -> None:
        cases = {
            "another system": ("system_not_frozen", {"system": "zq-other"}),
            "another model": ("model_not_frozen", {"model": "zq/model@other"}),
            "a changed recipe": ("recipe_not_frozen", {"recipe": {"path": RECIPE_PATH, "text_sha256": "0" * 64}}),
            "a moved recipe": ("recipe_not_frozen", {"recipe": {"path": "configs/llm/moved.toml",
                                                                "text_sha256": RECIPE_SHA}}),
            "a changed prompt": ("prompt_not_frozen", {"prompt": {"template_sha256": "0" * 64}}),
            "the filled-instructions hash": ("prompt_not_frozen", {"prompt": {"template_sha256": FILLED_SHA}}),
        }
        for name, (code, overrides) in cases.items():
            with self.subTest(name):
                self.assert_interpreter_refused(code, **overrides)

    def test_interpreter_provenance_without_usable_identity_fields_is_refused(self) -> None:
        cases = {
            "no recipe": {"recipe": None},
            "recipe not a table": {"recipe": "zq"},
            "no recipe hash": {"recipe": {"path": RECIPE_PATH}},
            "null recipe hash": {"recipe": {"path": RECIPE_PATH, "text_sha256": None}},
            "null recipe hash on an unpinned path": {"recipe": {"path": "configs/llm/moved.toml", "text_sha256": None}},
            "null recipe path": {"recipe": {"path": None, "text_sha256": RECIPE_SHA}},
            "no prompt": {"prompt": None},
            "no prompt hash": {"prompt": {"rendered_sha256": PROMPT_SHA}},
            "null prompt hash": {"prompt": {"template_sha256": None}},
        }
        for name, overrides in cases.items():
            with self.subTest(name):
                self.assert_interpreter_refused("malformed_interpreter", **overrides)

    def test_a_dev_compose_does_not_need_the_interpreter_identity(self) -> None:
        for condition in tc.TRAIN:
            for seed in tc.SEEDS:
                tc.write_router_run(self.root, condition, seed)
        tc.write_interpreter(self.root)
        lc.compose(split="dev", router_root=tc.ROUTER_ROOT, interpreter_dir=self.INTERPRETER, root=self.root)
        self.assertTrue((self.root / "outputs/stage2/hybrid/dev/provenance.compose.json").is_file())

    def test_frozen_router_runs_compose_and_record_the_freeze(self) -> None:
        provenance = self.compose(self.frozen())
        self.assertEqual(provenance["freeze_content_sha256"], FREEZE_SHA)
        self.assertTrue((self.root / "outputs/stage2/hybrid/test/provenance.compose.json").is_file())


if __name__ == "__main__":
    unittest.main()
