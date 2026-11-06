"""Spec 009 T10: the rendered-prompt pin, ``check_llm_run`` and the ``src/llm`` code pins."""

from __future__ import annotations

import datetime
import unittest
from pathlib import Path
from typing import Any

from src.data import freeze
from src.llm.paths import REPO_ROOT
from tests.freeze_fixtures import INPUTS, RENDERED, FreezeRepo

MODEL = "model-2026-01-01"
PROMPT = "prompts/llm.txt"
OTHER_HASH = "cd" * 32


class FreezeLlmTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = FreezeRepo().build()
        self.addCleanup(self.repo.cleanup)

    def write_llm(self, **changes: Any) -> None:
        raw = self.repo.inputs_raw()
        raw["systems"]["llm"].update(changes)
        self.repo.write_inputs(raw)


class RenderedPromptPinTests(FreezeLlmTestCase):
    def test_hashes_are_pinned_sorted_so_the_pin_is_order_independent(self) -> None:
        self.write_llm(rendered_prompts=[OTHER_HASH, RENDERED])
        self.assertEqual(self.repo.state().pins["recipe.llm.rendered_prompts"], f"{RENDERED},{OTHER_HASH}")

    def test_an_llm_system_without_them_cannot_be_frozen(self) -> None:
        for name, change in {"empty": [], "absent": None}.items():
            with self.subTest(name):
                raw = self.repo.inputs_raw()
                del raw["systems"]["llm"]["rendered_prompts"]
                if change is not None:
                    raw["systems"]["llm"]["rendered_prompts"] = change
                self.repo.write_inputs(raw)
                state = self.repo.state()
                self.assertIn("rendered_prompts_missing", [finding.code for finding in state.findings])
                self.assertNotIn("recipe.llm.rendered_prompts", state.pins)

    def test_other_families_do_not_need_them(self) -> None:
        self.assertEqual(self.repo.state().findings, [])
        self.assertNotIn("recipe.pipe.rendered_prompts", self.repo.state().pins)

    def test_bad_values_are_refused_on_load(self) -> None:
        cases = {"not a list": (RENDERED, "wrong_type"), "not a hash": (["zq"], "wrong_type"),
                 "uppercase": ([RENDERED.upper()], "wrong_type"), "not text": ([1], "wrong_type"),
                 "repeated": ([RENDERED, RENDERED], "duplicate_prompt"),
                 "too many": ([f"{i:064x}" for i in range(freeze.MAX_RECIPE_FILES + 1)], "too_many_entries")}
        for name, (value, code) in cases.items():
            with self.subTest(name):
                self.write_llm(rendered_prompts=value)
                with self.assertRaises(freeze.FreezeError) as caught:
                    self.repo.inputs()
                self.assertEqual(caught.exception.code, code)

    def test_the_pin_survives_the_record_and_a_change_is_a_freeze_mismatch(self) -> None:
        self.repo.freeze()
        frozen = freeze.require_freeze(self.repo.root)
        self.assertEqual(frozen.pins["recipe.llm.rendered_prompts"], RENDERED)
        self.write_llm(rendered_prompts=[OTHER_HASH])
        with self.assertRaises(freeze.FreezeError) as caught:
            freeze.require_freeze(self.repo.root)
        self.assertEqual(caught.exception.code, "freeze_mismatch")
        self.assertIn("recipe.llm.rendered_prompts", caught.exception.keys)


class CheckLlmRunTests(FreezeLlmTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.repo.freeze()
        self.frozen = freeze.require_freeze(self.repo.root)
        self.files = {PROMPT: freeze.text_sha256(self.repo.root / PROMPT)}

    def refused(self, code: str, *, system: str = "llm", files: dict[str, str] | None = None,
                rendered: Any = RENDERED, model: Any = MODEL) -> freeze.FreezeError:
        with self.assertRaises(freeze.FreezeError) as caught:
            freeze.check_llm_run(self.frozen, system, self.files if files is None else files, rendered, model)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_the_frozen_identity_passes(self) -> None:
        freeze.check_llm_run(self.frozen, "llm", self.files, RENDERED, MODEL)

    def test_a_system_outside_the_frozen_panel_is_refused(self) -> None:
        self.assertEqual(self.refused("system_not_frozen", system="zq-other").keys, ("recipe.zq-other",))

    def test_a_changed_file_is_refused_and_named(self) -> None:
        error = self.refused("recipe_file_not_frozen", files={PROMPT: OTHER_HASH})
        self.assertEqual(error.keys, (f"recipe.llm.file.{PROMPT}",))

    def test_a_file_with_no_pin_is_refused_even_with_a_valid_one_beside_it(self) -> None:
        error = self.refused("recipe_file_not_frozen", files={**self.files, "configs/llm/zq.toml": OTHER_HASH})
        self.assertEqual(error.keys, ("recipe.llm.file.configs/llm/zq.toml",))

    def test_a_null_digest_on_an_unpinned_path_is_not_a_match(self) -> None:
        """A hand-edited provenance can carry null, and a missing pin must not compare equal to it."""
        self.refused("recipe_file_not_frozen", files={"configs/llm/zq.toml": None})

    def test_another_systems_pinned_file_does_not_count(self) -> None:
        pipe = "prompts/pipe.txt"
        self.refused("recipe_file_not_frozen", files={pipe: freeze.text_sha256(self.repo.root / pipe)})

    def test_an_empty_file_list_is_not_a_pass(self) -> None:
        self.refused("recipe_file_not_frozen", files={})

    def test_a_rendered_prompt_outside_the_pin_is_refused(self) -> None:
        for name, rendered in {"other": OTHER_HASH, "empty": "", "not text": None, "two hashes": f"{RENDERED},{RENDERED}",
                               "uppercase": RENDERED.upper()}.items():
            with self.subTest(name):
                self.assertEqual(self.refused("prompt_not_frozen", rendered=rendered).keys,
                                 ("recipe.llm.rendered_prompts",))

    def test_a_system_with_no_rendered_pin_passes_no_prompt(self) -> None:
        pipe = "prompts/pipe.txt"
        files = {pipe: freeze.text_sha256(self.repo.root / pipe)}
        self.refused("prompt_not_frozen", system="pipe", files=files, rendered="")
        self.refused("prompt_not_frozen", system="pipe", files=files, rendered=RENDERED)

    def test_every_rendered_hash_of_the_system_passes(self) -> None:
        pins = {**self.frozen.pins, "recipe.llm.rendered_prompts": f"{RENDERED},{OTHER_HASH}"}
        frozen = freeze.FreezeRecord(self.frozen.record, self.frozen.content_sha256, self.frozen.freeze_date, pins,
                                     self.frozen.config)
        for rendered in (RENDERED, OTHER_HASH):
            freeze.check_llm_run(frozen, "llm", self.files, rendered, MODEL)

    def test_a_different_model_is_refused(self) -> None:
        for model in ("model-2026-02-02", "", None):
            with self.subTest(model=model):
                self.assertEqual(self.refused("llm_model_not_frozen", model=model).keys, ("recipe.llm.llm_model",))

    def test_a_system_with_no_model_pin_passes_no_model(self) -> None:
        pins = {**self.frozen.pins}
        del pins["recipe.llm.llm_model"]
        frozen = freeze.FreezeRecord(self.frozen.record, self.frozen.content_sha256, self.frozen.freeze_date, pins,
                                     self.frozen.config)
        for model in (MODEL, ""):
            with self.subTest(model=model), self.assertRaises(freeze.FreezeError) as caught:
                freeze.check_llm_run(frozen, "llm", self.files, RENDERED, model)
            self.assertEqual(caught.exception.code, "llm_model_not_frozen")


class CodePinTests(FreezeLlmTestCase):
    def test_freeze_check_shows_src_llm_files_among_the_code_pins(self) -> None:
        self.repo.write("src/llm/run.py", "VALUE = 1\n")
        self.repo.write("src/llm/backends/vllm_backend.py", "VALUE = 2\n")
        raw = self.repo.inputs_raw()
        raw["code"] += ["src/llm/*.py", "src/llm/backends/*.py"]
        self.repo.write_inputs(raw)
        state = freeze.check_state(self.repo.inputs(), self.repo.root, on=datetime.date(2026, 11, 7),
                                   today=datetime.date(2026, 11, 8), git=lambda root: {"git_commit": "a" * 40,
                                                                                       "git_dirty": False})
        self.assertEqual(state.findings, [])
        self.assertIn("code.src/llm/run.py", state.pins)
        self.assertIn("code.src/llm/backends/vllm_backend.py", state.pins)

    def test_the_committed_inputs_pin_the_whole_llm_package(self) -> None:
        inputs = freeze.load_inputs(INPUTS, root=REPO_ROOT)
        expected = {path.relative_to(REPO_ROOT) for path in (REPO_ROOT / "src/llm").rglob("*.py")}
        self.assertTrue(expected)
        self.assertLessEqual(expected, set(inputs.code))
        self.assertIn(Path("src/llm/backends/base.py"), inputs.code)


if __name__ == "__main__":
    unittest.main()
