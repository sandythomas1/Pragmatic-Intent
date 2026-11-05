"""Spec 009 T10: the freeze pins an LLM run's recipe files, rendered prompt and model (FR14, FR15)."""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from src.data import freeze
from tests.freeze_fixtures import FreezeRepo

REPO_ROOT = Path(__file__).resolve().parents[1]
RENDERED = "outputs/llm/prompts/p2.txt"
SYSTEM = "llm"
RECIPE_FILE = "prompts/llm.txt"
MODEL = "model-2026-01-01"


def frozen(**overrides: str) -> SimpleNamespace:
    pins = {f"recipe.{SYSTEM}.seeds": "0", f"recipe.{SYSTEM}.llm_model": MODEL,
            f"recipe.{SYSTEM}.file.{RECIPE_FILE}": "file-hash", f"recipe.{SYSTEM}.rendered.{RENDERED}": "prompt-hash",
            **overrides}
    return SimpleNamespace(pins=pins, config=SimpleNamespace(panel=(SimpleNamespace(name=SYSTEM),)))


class RenderedPinTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = FreezeRepo().build()
        self.addCleanup(self.repo.cleanup)

    def with_rendered(self) -> None:
        raw = self.repo.inputs_raw()
        raw["systems"]["llm"]["rendered_prompts"] = [RENDERED]
        self.repo.write_inputs(raw)

    def test_a_rendered_prompt_is_pinned_by_its_text_hash(self) -> None:
        self.repo.write(RENDERED, "rendered\n")
        self.with_rendered()
        pins = self.repo.state().pins
        self.assertEqual(pins[f"recipe.llm.rendered.{RENDERED}"], freeze.text_sha256(self.repo.root / RENDERED))

    def test_a_missing_rendered_prompt_is_a_finding_not_a_pin(self) -> None:
        self.with_rendered()
        state = self.repo.state()
        self.assertNotIn(f"recipe.llm.rendered.{RENDERED}", state.pins)
        self.assertIn("file_missing", [finding.code for finding in state.findings])

    def test_a_rendered_prompt_path_may_not_leave_the_repository(self) -> None:
        raw = self.repo.inputs_raw()
        raw["systems"]["llm"]["rendered_prompts"] = ["../outside.txt"]
        self.repo.write_inputs(raw)
        with self.assertRaises(freeze.FreezeError):
            self.repo.inputs()


    def test_a_real_freeze_catches_a_rendered_prompt_changed_afterwards(self) -> None:
        self.repo.write(RENDERED, "rendered\n")
        self.with_rendered()
        self.repo.freeze()
        self.assertIn(f"recipe.llm.rendered.{RENDERED}", freeze.require_freeze(self.repo.root).pins)
        self.repo.write(RENDERED, "rendered differently\n")
        with self.assertRaises(freeze.FreezeError) as caught:
            freeze.require_freeze(self.repo.root)
        self.assertEqual(caught.exception.code, "freeze_mismatch")


class CheckLlmRunTests(unittest.TestCase):
    def check(self, record: SimpleNamespace | None = None, *, system: str = SYSTEM,
              files: dict[str, str] | None = None, rendered: str | None = "prompt-hash",
              model: str = MODEL) -> None:
        freeze.check_llm_run(record or frozen(), system, {RECIPE_FILE: "file-hash"} if files is None else files,
                             rendered, model)

    def assert_refused(self, code: str, **kwargs: object) -> None:
        with self.assertRaises(freeze.FreezeError) as caught:
            self.check(**kwargs)  # type: ignore[arg-type]
        self.assertEqual(caught.exception.code, code)

    def test_a_run_matching_every_pin_passes(self) -> None:
        self.check()

    def test_a_transfer_run_has_no_rendered_main_prompt(self) -> None:
        self.check(rendered=None)

    def test_an_unfrozen_system_is_refused(self) -> None:
        self.assert_refused("system_not_frozen", system="zq-other")

    def test_a_changed_recipe_file_is_refused(self) -> None:
        self.assert_refused("recipe_not_frozen", files={RECIPE_FILE: "other"})

    def test_a_moved_recipe_file_is_refused(self) -> None:
        self.assert_refused("recipe_not_frozen", files={"prompts/moved.txt": "file-hash"})

    def test_no_recipe_files_at_all_is_refused(self) -> None:
        self.assert_refused("recipe_not_frozen", files={})

    def test_a_different_rendered_prompt_is_refused(self) -> None:
        self.assert_refused("prompt_not_frozen", rendered="other")

    def test_a_recipe_file_hash_is_not_accepted_as_the_rendered_prompt(self) -> None:
        self.assert_refused("prompt_not_frozen", rendered="file-hash")

    def test_a_different_model_is_refused(self) -> None:
        self.assert_refused("model_not_frozen", model="model-latest")

    def test_an_empty_frozen_model_never_matches(self) -> None:
        self.assert_refused("model_not_frozen", record=frozen(**{f"recipe.{SYSTEM}.llm_model": ""}), model="")


class CodePinTests(unittest.TestCase):
    def test_the_runner_and_its_backends_are_code_pins(self) -> None:
        inputs = freeze.load_inputs(Path("configs/freeze/freeze-v1.toml"), root=REPO_ROOT)
        code = {path.as_posix() for path in inputs.code}
        self.assertLessEqual({"src/llm/run.py", "src/llm/compose.py", "src/llm/backends/vllm_backend.py"}, code)


if __name__ == "__main__":
    unittest.main()
