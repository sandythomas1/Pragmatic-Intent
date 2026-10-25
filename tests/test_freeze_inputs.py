"""Freeze inputs: strict schema, repository-relative paths, globs and the panel (spec 008 T1)."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from typing import Any

from src.analysis.config import load_config, parse_config
from src.data import freeze
from src.data.freeze import FreezeError
from tests.analysis_fixtures import PANEL, Workspace, config_dict
from tests.freeze_fixtures import inputs_toml

INPUTS = "configs/freeze/freeze.toml"


class FreezeInputsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.ws = Workspace()
        self.addCleanup(self.ws.cleanup)
        self.ws.write("configs/analysis/analysis.toml", "version = 'x'\n")
        self.ws.write("configs/stage1/enc.toml", "[run]\n")
        self.ws.write("configs/stage1/tfidf.toml", "[run]\n")
        self.ws.write("prompts/llm.txt", "Classify the request.\n")
        self.ws.write("src/a.py", "A = 1\n")
        self.ws.write("src/pkg/b.py", "B = 2\n")
        self.ws.write("src/pkg/c.py", "C = 3\n")

    def raw(self, **changes: Any) -> dict[str, Any]:
        raw: dict[str, Any] = {
            "version": "freeze-inputs-v1",
            "analysis_config": "configs/analysis/analysis.toml",
            "code": ["src/a.py", "src/pkg/*.py"],
            "systems": {
                "enc": {"stage1": "configs/stage1/enc.toml", "seeds": [13, 42]},
                "tfidf": {"stage1": "configs/stage1/tfidf.toml", "seeds": [13]},
                "llm": {"files": ["prompts/llm.txt"], "seeds": [0], "llm_model": "model-2026-01-01"},
                "pipe": {"files": [], "seeds": [13]},
            },
        }
        raw.update(changes)
        return raw

    def load(self, raw: dict[str, Any] | None = None) -> freeze.FreezeInputs:
        self.ws.write(INPUTS, inputs_toml(self.raw() if raw is None else raw))
        return freeze.load_inputs(Path(INPUTS), root=self.ws.root)

    def assert_code(self, code: str, raw: dict[str, Any]) -> FreezeError:
        with self.assertRaises(FreezeError) as caught:
            self.load(raw)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def with_system(self, name: str, **table: Any) -> dict[str, Any]:
        raw = self.raw()
        raw["systems"][name] = table
        return raw


class LoadTest(FreezeInputsTestCase):
    def test_valid_inputs_load_with_sorted_code_and_systems(self) -> None:
        inputs = self.load()
        self.assertEqual([p.as_posix() for p in inputs.code], ["src/a.py", "src/pkg/b.py", "src/pkg/c.py"])
        self.assertEqual(list(inputs.systems), ["enc", "llm", "pipe", "tfidf"])
        self.assertEqual(inputs.systems["enc"].seeds, (13, 42))
        self.assertEqual(inputs.systems["enc"].stage1, Path("configs/stage1/enc.toml"))
        self.assertEqual(inputs.systems["llm"].files, (Path("prompts/llm.txt"),))
        self.assertEqual(inputs.systems["llm"].llm_model, "model-2026-01-01")
        self.assertIsNone(inputs.systems["pipe"].stage1)
        self.assertIsNone(inputs.systems["pipe"].llm_model)
        self.assertEqual(inputs.analysis_config, Path("configs/analysis/analysis.toml"))

    def test_overlapping_globs_are_deduplicated(self) -> None:
        inputs = self.load(self.raw(code=["src/pkg/*.py", "src/pkg/b.py", "src/**/*.py"]))
        self.assertEqual([p.as_posix() for p in inputs.code], ["src/a.py", "src/pkg/b.py", "src/pkg/c.py"])

    def test_the_real_freeze_inputs_load_and_match_the_real_panel(self) -> None:
        root = Path(__file__).resolve().parents[1]
        inputs = freeze.load_inputs(freeze.DEFAULT_INPUTS, root=root)
        freeze.match_panel(inputs, load_config(root / inputs.analysis_config))
        self.assertIn(Path("src/data/freeze.py"), inputs.code)


class SchemaTest(FreezeInputsTestCase):
    def test_unknown_top_level_key(self) -> None:
        self.assert_code("unknown_key", self.raw(extra=1))

    def test_missing_top_level_key(self) -> None:
        raw = self.raw()
        del raw["code"]
        self.assert_code("missing_key", raw)

    def test_wrong_version(self) -> None:
        self.assert_code("unknown_version", self.raw(version="freeze-inputs-v0"))

    def test_unknown_system_key(self) -> None:
        self.assert_code("unknown_key", self.with_system("enc", stage1="configs/stage1/enc.toml", seeds=[1], lr=1))

    def test_seeds_are_required(self) -> None:
        self.assert_code("missing_key", self.with_system("enc", stage1="configs/stage1/enc.toml"))

    def test_bad_seeds(self) -> None:
        cases = {"empty_seeds": [], "wrong_type": ["13"], "duplicate_seed": [13, 13]}
        for code, seeds in cases.items():
            with self.subTest(code=code):
                self.assert_code(code, self.with_system("enc", seeds=seeds))
        for seeds in ([-1], [True], [1.5]):
            with self.subTest(seeds=seeds):
                self.assert_code("wrong_type", self.with_system("enc", seeds=seeds))

    def test_too_many_seeds(self) -> None:
        self.assert_code("too_many_entries", self.with_system("enc", seeds=list(range(freeze.MAX_SEEDS + 1))))

    def test_bad_llm_model(self) -> None:
        for value in (7, "model with spaces", "x" * 129):
            with self.subTest(value=value):
                self.assert_code("wrong_type", self.with_system("llm", seeds=[0], llm_model=value))

    def test_empty_llm_model_loads_so_check_can_report_it(self) -> None:
        self.assertEqual(self.load(self.with_system("llm", seeds=[0], llm_model="")).systems["llm"].llm_model, "")

    def test_bad_system_name(self) -> None:
        raw = self.raw()
        raw["systems"] = {"Enc": {"seeds": [1]}}
        self.assert_code("bad_name", raw)

    def test_systems_must_be_a_non_empty_table(self) -> None:
        text = inputs_toml(self.raw(systems={}))
        for systems in ("systems = {}\n", "systems = 3\n"):
            with self.subTest(systems=systems):
                self.ws.write(INPUTS, text + systems)
                with self.assertRaises(FreezeError) as caught:
                    freeze.load_inputs(Path(INPUTS), root=self.ws.root)
                self.assertEqual(caught.exception.code, "wrong_type")

    def test_duplicate_recipe_file(self) -> None:
        self.assert_code("duplicate_file", self.with_system("llm", files=["prompts/llm.txt", "prompts/llm.txt"], seeds=[0]))
        self.assert_code("duplicate_file", self.with_system(
            "enc", stage1="configs/stage1/enc.toml", files=["configs/stage1/enc.toml"], seeds=[1]))

    def test_oversized_inputs_are_refused_unread(self) -> None:
        self.ws.write(INPUTS, "# " + "x" * freeze.MAX_INPUTS_BYTES + "\n")
        with self.assertRaises(FreezeError) as caught:
            freeze.load_inputs(Path(INPUTS), root=self.ws.root)
        self.assertEqual(caught.exception.code, "file_too_large")

    def test_invalid_toml(self) -> None:
        self.ws.write(INPUTS, "version = \n")
        with self.assertRaises(FreezeError) as caught:
            freeze.load_inputs(Path(INPUTS), root=self.ws.root)
        self.assertEqual(caught.exception.code, "invalid_toml")


class PathSafetyTest(FreezeInputsTestCase):
    def test_paths_must_be_repository_relative(self) -> None:
        cases = {
            "path_escape": ["../outside.toml", "configs/../configs/stage1/enc.toml", "./configs/stage1/enc.toml",
                            "configs//stage1/enc.toml", "configs/stage1/enc.toml/"],
            "path_not_relative": ["/etc/passwd", "C:/Windows/win.ini", "configs\\stage1\\enc.toml", "C:relative.toml",
                                  "configs/stage1/enc.toml:stream", "//server/share/x.toml"],
            "wrong_type": ["", 5],
            "missing_path": ["configs/stage1/absent.toml", "configs/stage1"],
        }
        for code, values in cases.items():
            for value in values:
                with self.subTest(value=value):
                    self.assert_code(code, self.with_system("enc", stage1=value, seeds=[1]))

    def test_analysis_config_path_is_checked_too(self) -> None:
        self.assert_code("path_escape", self.raw(analysis_config="../analysis.toml"))

    def test_a_symlinked_file_or_directory_is_refused(self) -> None:
        target = self.ws.root / "configs/stage1/enc.toml"
        try:
            os.symlink(target, self.ws.root / "configs/stage1/link.toml")
            os.symlink(self.ws.root / "configs/stage1", self.ws.root / "linkdir", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are not available on this platform/account")
        for value in ("configs/stage1/link.toml", "linkdir/enc.toml"):
            with self.subTest(value=value):
                self.assert_code("symlink", self.with_system("enc", stage1=value, seeds=[1]))

    def test_a_glob_that_matches_nothing_is_refused(self) -> None:
        error = self.assert_code("glob_empty", self.raw(code=["src/a.py", "src/missing/*.py"]))
        self.assertEqual(error.keys, ("code[1]",))

    def test_a_glob_matching_only_directories_is_refused(self) -> None:
        self.assert_code("glob_empty", self.raw(code=["src/pk?"]))

    def test_globs_cannot_escape_or_use_odd_characters(self) -> None:
        self.assert_code("path_escape", self.raw(code=["../*.py"]))
        self.assert_code("path_not_relative", self.raw(code=["/src/*.py"]))
        self.assert_code("bad_glob", self.raw(code=["src/[ab].py"]))
        self.assert_code("glob_empty", self.raw(code=[]))


class PanelTest(FreezeInputsTestCase):
    def test_matching_panel_passes(self) -> None:
        freeze.match_panel(self.load(), parse_config(config_dict()))

    def test_missing_and_extra_systems_are_named(self) -> None:
        raw = self.raw()
        del raw["systems"]["tfidf"]
        raw["systems"]["extra"] = {"seeds": [1]}
        with self.assertRaises(FreezeError) as caught:
            freeze.match_panel(self.load(raw), parse_config(config_dict()))
        self.assertEqual(caught.exception.code, "panel_mismatch")
        self.assertEqual(caught.exception.keys, ("tfidf", "extra"))

    def test_conditions_follow_the_design(self) -> None:
        panel = {system.name: system for system in parse_config(config_dict()).panel}
        self.assertEqual(freeze.conditions_for(panel["enc"]), ("none", "one", "full"))
        self.assertEqual(freeze.conditions_for(panel["tfidf"]), ("full",))
        self.assertEqual(freeze.conditions_for(panel["llm"]), ("untrained",))
        self.assertEqual(freeze.conditions_for(panel["pipe"]), ("none", "one", "full"))
        self.assertEqual([s["name"] for s in PANEL], ["enc", "tfidf", "llm", "pipe"])


if __name__ == "__main__":
    unittest.main()
