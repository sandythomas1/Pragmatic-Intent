"""Spec 009 T10: the fail-closed test-split gates on the LLM runner and the hybrid composer.

Each test runs against a real freeze record in a fixture repository (invented IDs and text); only
the backend is fake, and its factory records every construction (AC-009-11).
"""

from __future__ import annotations

import io
import json
import random
import shutil
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from typing import Any
from unittest import mock

from src.data import freeze
from src.llm import compose as lc
from src.llm import prompt
from src.llm import recipe as rc
from src.llm import run as lr
from src.llm import schema as sc
from tests.analysis_fixtures import PANEL, config_dict, config_toml
from tests.freeze_fixtures import ENCODER_TOML, FreezeRepo
from tests.test_llm_compose import (INTERPRETATION, ORACLE, ROUTER_ROOT, SEEDS, TRAIN, jsonl, sha, write_router_run)
from tests.test_llm_run import ITEMS, KEYS, ORACLE as ORACLE_INPUTS, RECIPE, ROUTED, Factory, Root

RECIPE_PATH = Path("configs/llm/fake.toml")
ROUTER_RECIPE = Path("configs/stage1/router.toml")
INTERPRETER_DIR = Path("outputs/stage2/llm/test")
HYBRID_DIR = Path("outputs/stage2/hybrid/test")
TEST_INPUTS = """[inputs.test]
routed = "data/interim/stage2/test_routed_inputs.jsonl"
oracle = "data/interim/stage2/test_oracle_inputs.jsonl"
transfer = "data/interim/stage2/transfer_inputs.jsonl"

[backend_options]"""
OTHER_HASH = "cd" * 32


class GateRepo(FreezeRepo):
    """A frozen-ready repository whose panel holds an LLM recipe and the hybrid's router."""

    def __init__(self) -> None:
        super().__init__()
        self.llm = Root(self.root)
        self.model = "fake-model"
        self.main_prompt = "p1"

    def build(self, **options: Any) -> GateRepo:
        super().build(**options)
        raw = config_dict([*PANEL, {"name": lc.ROUTER_NAME, "family": "encoder", "design": "matched",
                                    "streams": ["stage1"]}], draft=False)
        raw["rules_version"] = "auto-v1"
        self.write("configs/analysis/analysis-v1.toml", "# the plan\n" + config_toml(raw))
        self.write(ROUTER_RECIPE, ENCODER_TOML.replace('name = "enc"', f'name = "{lc.ROUTER_NAME}"'))
        self.llm.write_jsonl("data/interim/stage2/test_routed_inputs.jsonl", ROUTED)
        self.llm.write_jsonl("data/interim/stage2/test_oracle_inputs.jsonl", ORACLE_INPUTS)
        self.write_llm_recipe()
        self.write_inputs()
        return self

    def write_llm_recipe(self, *, system: str = "llm", path: Path = RECIPE_PATH) -> None:
        text = RECIPE.format(backend="fake", model_id="fake-model", temperature=0, max_model_len=2048, extra="")
        text = text.replace('system = "fake-llm"', f'system = "{system}"').replace("[backend_options]", TEST_INPUTS)
        self.write(path, text.replace('main = "p1"', f'main = "{self.main_prompt}"'))

    def recipe(self, path: Path = RECIPE_PATH) -> rc.Recipe:
        return rc.load_recipe(path, self.root)

    def rendered(self) -> list[str]:
        recipe = self.recipe()
        keys = sc.load_slot_keys(recipe.slot_keys)
        return [prompt.main_instructions(recipe.prompt_path(self.main_prompt), keys).sha256,
                prompt.transfer_instructions(recipe.transfer_prompt).sha256]

    def inputs_raw(self) -> dict[str, Any]:
        raw = super().inputs_raw()
        files = [RECIPE_PATH.as_posix(), "configs/llm/slot_keys.json", "configs/llm/prompts/t1.txt"]
        if self.main_prompt == "p1":
            files.append("configs/llm/prompts/p1.txt")
        raw["systems"]["llm"] = {"files": files, "seeds": [0], "llm_model": self.model,
                                 "rendered_prompts": self.rendered()}
        raw["systems"][lc.ROUTER_NAME] = {"stage1": ROUTER_RECIPE.as_posix(), "seeds": list(SEEDS)}
        return raw


class GateTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = GateRepo()
        self.addCleanup(self.repo.cleanup)
        self.repo.build()
        self.root = self.repo.root


class RunnerGateTests(GateTestCase):
    def run_test(self, task: str = "main", recipe: rc.Recipe | None = None, factory: Factory | None = None,
                 **kwargs: Any) -> dict[str, Any]:
        return lr.run(recipe or self.repo.recipe(), split="test", task=task, root=self.root,
                      backend_factory=factory if factory is not None else Factory(), sleep=lambda _: None,
                      rng=random.Random(1), **kwargs)

    def assert_stopped(self, code: str, recipe: rc.Recipe | None = None, task: str = "main") -> None:
        """Refused with ``code``: no backend built, nothing cached, nothing scored (AC-009-11)."""
        factory = Factory()
        with self.assertRaises(freeze.FreezeError) as caught:
            self.run_test(task, recipe, factory)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(factory.built, [])
        self.assertFalse((self.root / "outputs/llm/cache").exists())
        self.assertFalse((self.root / "outputs/stage2").exists())

    def test_no_freeze_stops_the_run(self) -> None:
        self.assert_stopped("freeze_missing")

    def test_no_freeze_stops_the_run_before_any_input_is_read(self) -> None:
        (self.root / "data/interim/stage2/test_routed_inputs.jsonl").unlink()
        self.assert_stopped("freeze_missing")

    def test_a_recipe_file_changed_after_the_freeze_stops_the_run(self) -> None:
        self.repo.freeze()
        for relative in ("configs/llm/slot_keys.json", "configs/llm/prompts/p1.txt", RECIPE_PATH.as_posix()):
            with self.subTest(relative):
                path = self.root / relative
                original = path.read_bytes()
                path.write_bytes(original + b"\n")
                self.assert_stopped("freeze_mismatch")
                path.write_bytes(original)

    def test_a_recipe_outside_the_freeze_stops_the_run(self) -> None:
        self.repo.freeze()
        other = Path("configs/llm/other.toml")
        self.repo.write_llm_recipe(path=other)
        (self.root / other).write_text((self.root / other).read_text(encoding="utf-8") + "# zq\n", encoding="utf-8")
        self.assert_stopped("recipe_file_not_frozen", self.repo.recipe(other))

    def test_a_recipe_claiming_an_unfrozen_system_stops_the_run(self) -> None:
        self.repo.freeze()
        other = Path("configs/llm/other.toml")
        self.repo.write_llm_recipe(system="zq-other", path=other)
        self.assert_stopped("system_not_frozen", self.repo.recipe(other))

    def test_a_different_rendered_prompt_stops_the_run(self) -> None:
        """P2 is generated and git-ignored, so only the rendered hash can catch a changed file."""
        self.repo.main_prompt = "p2"
        self.repo.write_llm_recipe()
        self.repo.write_inputs()
        self.repo.freeze()
        self.run_test()  # the frozen file passes, so the refusal below is the edit's doing
        shutil.rmtree(self.root / "outputs/stage2")
        shutil.rmtree(self.root / "outputs/llm/cache")
        (self.root / "outputs/llm/prompts/p2.txt").write_text("zq a different prompt\n{{slot_keys}}\n", encoding="utf-8")
        self.assert_stopped("prompt_not_frozen")

    def test_a_different_llm_model_stops_the_run(self) -> None:
        self.repo.model = "zq-frozen-model"
        self.repo.write_inputs()
        self.repo.freeze()
        self.assert_stopped("llm_model_not_frozen")

    def test_an_unpinned_rendered_prompt_stops_the_run(self) -> None:
        raw = self.repo.inputs_raw()
        raw["systems"]["llm"]["rendered_prompts"] = [OTHER_HASH]
        self.repo.write_inputs(raw)
        self.repo.freeze()
        self.assert_stopped("prompt_not_frozen")
        self.assert_stopped("prompt_not_frozen", task="transfer")

    def test_the_frozen_recipe_runs_both_tasks_and_records_the_freeze(self) -> None:
        record = self.repo.freeze()
        factory = Factory()
        main = self.run_test(factory=factory)
        transfer = self.run_test("transfer", factory=factory)
        self.assertEqual(len(factory.built), 2)
        self.assertEqual(main["freeze_content_sha256"], record["content_sha256"])
        self.assertEqual(transfer["freeze_content_sha256"], record["content_sha256"])
        self.assertEqual((main["split"], main["selected_variant"], main["conditions"]), ("test", True, None))
        self.assertTrue((self.root / "outputs/stage2/llm/test/routed.jsonl").is_file())
        self.assertTrue((self.root / "outputs/stage2/llm/test/provenance.main.json").is_file())

    def test_a_generated_prompt_needs_no_file_pin(self) -> None:
        self.repo.main_prompt = "p2"
        self.repo.write_llm_recipe()
        self.repo.write_inputs()
        self.repo.freeze()
        self.assertEqual(self.run_test()["variant"], "p2")

    def test_a_test_run_cannot_choose_its_prompt_conditions_or_sample(self) -> None:
        self.repo.freeze()
        for kwargs in ({"variant": "p2"}, {"conditions": ["none"]}, {"sample": mock.Mock()}):
            with self.subTest(sorted(kwargs)):
                factory = Factory()
                with self.assertRaises(lr.RunRefused):
                    self.run_test(factory=factory, **kwargs)
                self.assertEqual(factory.built, [])
        self.assertFalse((self.root / "outputs/stage2").exists())

    def test_a_named_selected_variant_is_allowed(self) -> None:
        self.repo.freeze()
        self.assertEqual(self.run_test(variant="p1")["variant"], "p1")

    def test_dev_tools_stay_off_the_test_split_even_with_a_freeze(self) -> None:
        self.repo.freeze()
        factory = Factory()
        with self.assertRaises(lr.RunRefused):
            lr.smoke(self.repo.recipe(), split="test", root=self.root, backend_factory=factory)
        with self.assertRaises(lr.RunRefused):
            lr.size(self.repo.recipe(), split="test", root=self.root)
        self.assertEqual(factory.built, [])

    def test_dev_runs_do_not_touch_the_freeze(self) -> None:
        with mock.patch.object(lr, "require_freeze") as gate:
            provenance = lr.run(self.repo.recipe(), split="dev", task="main", root=self.root, backend_factory=Factory(),
                                sleep=lambda _: None, rng=random.Random(1))
        gate.assert_not_called()
        self.assertIsNone(provenance["freeze_content_sha256"])


class RunnerCliTests(GateTestCase):
    def main(self, *argv: str) -> tuple[int, str]:
        stderr = io.StringIO()
        with redirect_stderr(stderr), mock.patch.object(lr, "load_recipe", lambda path: self.repo.recipe()):
            code = lr.main(list(argv))
        return code, stderr.getvalue()

    def test_a_freeze_failure_exits_non_zero_and_names_the_code(self) -> None:
        missing = freeze.FreezeError("freeze_missing", "no record")
        with mock.patch.object(lr, "require_freeze", side_effect=missing), \
                mock.patch.object(lr, "default_backend_factory") as factory:
            code, stderr = self.main("run", "--recipe", "x.toml", "--split", "test", "--task", "main")
        self.assertEqual(code, 1)
        self.assertIn("LLM run stopped: freeze_missing", stderr)
        factory.assert_not_called()

    def test_the_sample_flag_is_refused_on_test_before_the_corpus_is_read(self) -> None:
        with mock.patch.object(lr, "draw") as draw:
            code, stderr = self.main("run", "--recipe", "x.toml", "--split", "test", "--task", "main",
                                     "--conditions", "none", "--sample")
        self.assertEqual(code, 1)
        self.assertIn("dev main-task", stderr)
        draw.assert_not_called()

    def test_size_and_smoke_refuse_test_before_the_recipe_is_read(self) -> None:
        for command in ("size", "smoke"):
            with self.subTest(command):
                stderr = io.StringIO()
                with redirect_stderr(stderr), mock.patch.object(lr, "load_recipe") as load:
                    code = lr.main([command, "--recipe", "x.toml", "--split", "test"])
                self.assertEqual(code, 1)
                self.assertIn("refused", stderr.getvalue())
                load.assert_not_called()


class ComposerGateTests(GateTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.write_router_grid()
        self.write_interpreter()

    def write_router_run(self, condition: str, seed: int, **change: Any) -> None:
        """A run as the runner leaves it, on the frozen recipe unless ``change`` moves its data options."""
        run_dir = write_router_run(self.root, condition, seed, config_split="test", run_split="test")
        config = freeze.stage1_recipe(self.root, ROUTER_RECIPE)
        config["data"].update(train_condition=condition, eval_split="test", **change)
        (run_dir / "config.resolved.json").write_text(json.dumps(config), encoding="utf-8")

    def write_router_grid(self) -> None:
        for condition in TRAIN:
            for seed in SEEDS:
                self.write_router_run(condition, seed)

    def write_interpreter(self, **overrides: Any) -> None:
        directory = self.root / INTERPRETER_DIR
        directory.mkdir(parents=True, exist_ok=True)
        files = {"interpretation.jsonl": jsonl(INTERPRETATION), "oracle.jsonl": jsonl(ORACLE)}
        for name, data in files.items():
            (directory / name).write_bytes(data)
        recipe = self.repo.recipe()
        provenance = {"version": "llm-run-v1", "task": "main", "split": "test", "system": "llm", "variant": "p1",
                      "selected_variant": True, "conditions": None, "model": recipe.model_ref,
                      "recipe": {"path": RECIPE_PATH.as_posix(), "text_sha256": recipe.text_sha256},
                      "prompt": {"rendered_sha256": self.repo.rendered()[0]},
                      "outputs": {name: sha(data) for name, data in files.items()}}
        provenance.update(overrides)
        (directory / "provenance.main.json").write_text(json.dumps(provenance), encoding="utf-8")

    def compose(self) -> dict[str, Any]:
        return lc.compose(split="test", router_root=ROUTER_ROOT, interpreter_dir=INTERPRETER_DIR, root=self.root)

    def assert_stopped(self, code: str) -> None:
        with self.assertRaises((freeze.FreezeError, lc.ComposeError)) as caught:
            self.compose()
        self.assertEqual(caught.exception.code, code)
        self.assertFalse((self.root / HYBRID_DIR).exists(), "a refusal writes nothing")

    def test_no_freeze_stops_compose_before_any_input_is_read(self) -> None:
        with mock.patch.object(lc, "load_router_runs") as router, mock.patch.object(lc, "load_interpreter") as llm:
            self.assert_stopped("freeze_missing")
        router.assert_not_called()
        llm.assert_not_called()

    def test_a_change_after_the_freeze_stops_compose(self) -> None:
        self.repo.freeze()
        (self.root / "configs/llm/prompts/p1.txt").write_text("zq moved\n{{slot_keys}}\n", encoding="utf-8")
        self.assert_stopped("freeze_mismatch")

    def test_a_router_run_with_an_unfrozen_seed_stops_compose(self) -> None:
        self.repo.freeze()
        for condition in TRAIN:  # the same extra seed everywhere, so only the freeze can refuse it
            self.write_router_run(condition, 99)
        self.assert_stopped("seed_not_frozen")

    def test_a_router_run_on_an_unfrozen_recipe_stops_compose(self) -> None:
        self.repo.freeze()
        self.write_router_run("one", SEEDS[1], max_context_words=1)
        self.assert_stopped("recipe_not_frozen")

    def test_an_interpreter_outside_the_freeze_stops_compose(self) -> None:
        self.repo.freeze()
        recipe = {"path": RECIPE_PATH.as_posix(), "text_sha256": OTHER_HASH}
        cases = {"system_not_frozen": {"system": "zq-other"}, "recipe_file_not_frozen": {"recipe": recipe},
                 "prompt_not_frozen": {"prompt": {"rendered_sha256": OTHER_HASH}},
                 "llm_model_not_frozen": {"model": "zq-other-model"}}
        for code, change in cases.items():
            with self.subTest(code):
                self.write_interpreter(**change)
                self.assert_stopped(code)

    def test_a_null_recipe_digest_stops_compose(self) -> None:
        self.repo.freeze()
        self.write_interpreter(recipe={"path": "configs/llm/zq.toml", "text_sha256": None})
        self.assert_stopped("recipe_file_not_frozen")

    def test_interpreter_provenance_without_the_gated_fields_stops_compose(self) -> None:
        self.repo.freeze()
        for change in ({"recipe": None}, {"prompt": {}}, {"recipe": {"path": ["zq"], "text_sha256": OTHER_HASH}}):
            with self.subTest(change):
                self.write_interpreter(**change)
                self.assert_stopped("malformed_interpreter")

    def test_the_frozen_grid_composes_and_records_the_freeze(self) -> None:
        record = self.repo.freeze()
        provenance = self.compose()
        self.assertEqual(provenance["freeze_content_sha256"], record["content_sha256"])
        self.assertEqual(len(provenance["counts"]), len(TRAIN) * len(SEEDS))
        self.assertTrue((self.root / HYBRID_DIR / "provenance.compose.json").is_file())

    def test_the_gate_checks_the_router_constant_not_the_callers_name(self) -> None:
        self.repo.freeze()
        for condition in TRAIN:
            for seed in SEEDS:
                run_dir = self.root / ROUTER_ROOT / f"train-{condition}" / f"seed{seed}"
                config = json.loads((run_dir / "config.resolved.json").read_text(encoding="utf-8"))
                (run_dir / "config.resolved.json").write_text(json.dumps({**config, "name": "enc"}), encoding="utf-8")
        with self.assertRaises(freeze.FreezeError) as caught:
            lc.compose(split="test", router_root=ROUTER_ROOT, interpreter_dir=INTERPRETER_DIR, root=self.root,
                       router_name="enc")
        self.assertEqual(caught.exception.code, "recipe_not_frozen")
        self.assertFalse((self.root / HYBRID_DIR).exists())

    def test_dev_compose_does_not_touch_the_freeze(self) -> None:
        for condition in TRAIN:
            for seed in SEEDS:
                write_router_run(self.root, condition, seed)
        dev = Path("outputs/stage2/llm/dev")
        shutil.copytree(self.root / INTERPRETER_DIR, self.root / dev)
        provenance_path = self.root / dev / "provenance.main.json"
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        provenance_path.write_text(json.dumps({**provenance, "split": "dev"}), encoding="utf-8")
        with mock.patch.object(lc, "require_freeze") as gate:
            result = lc.compose(split="dev", router_root=ROUTER_ROOT, interpreter_dir=dev, root=self.root)
        gate.assert_not_called()
        self.assertIsNone(result["freeze_content_sha256"])

    def test_the_cli_exits_non_zero_and_reads_nothing_without_a_freeze(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr), mock.patch.object(lc, "REPO_ROOT", self.root), \
                mock.patch.object(lc, "load_router_runs") as router:
            code = lc.main(["compose", "--split", "test", "--router-root", "zq-missing", "--interpreter", "zq-missing"])
        self.assertEqual(code, 1)
        self.assertIn("Compose stopped: freeze_missing", stderr.getvalue())
        router.assert_not_called()


if __name__ == "__main__":
    unittest.main()
