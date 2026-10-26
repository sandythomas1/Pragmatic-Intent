"""Reuse only matching, complete dev artifacts; preserve rejected files byte for byte."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.stage1 import provenance
from src.stage1.config import load_config
from src.stage1.grid_check import plan


class GridCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.items, self.dialogues = self.root / "items.jsonl", self.root / "dialogues.jsonl"
        self.items.write_text('{"fixture": 1}\n', encoding="utf-8")
        self.dialogues.write_text('{"context": "invented"}\n', encoding="utf-8")
        self.config = self.root / "encoder.toml"
        self.config.write_text('[run]\nname = "fixture"\nkind = "encoder"\n'
                               '[data]\ntrain_condition = "full"\n'
                               f'items = "{self.items.as_posix()}"\n'
                               f'dialogues = "{self.dialogues.as_posix()}"\n'
                               '[encoder]\npretrained = "invented/model"\n', encoding="utf-8")
        self.out = self.root / "outputs"

    def completed(self, **overrides: object) -> Path:
        config = load_config(self.config)
        output = self.out / "fixture/train-full/seed13"
        output.mkdir(parents=True, exist_ok=True)
        (output / "config.resolved.json").write_text(json.dumps(config.to_dict()), encoding="utf-8")
        predictions = output / "predictions.jsonl"
        predictions.write_text('{"prediction": "direct"}\n', encoding="utf-8")
        record = {"run": "fixture", "kind": "encoder", "seed": 13, "smoke": False,
                  "train_split": "train", "eval_split": "dev", "train_condition": "full",
                  "policy": config.data.policy, "config_sha256": config.sha256(),
                  **provenance.run_hashes(self.items, self.dialogues),
                  "predictions_sha256": provenance.sha256(predictions), **overrides}
        (output / "metrics.json").write_text(json.dumps({"run": record}), encoding="utf-8")
        return output

    def plan(self, **overrides: object) -> list[tuple[str, str, int, str]]:
        return plan(self.config, [13], ["full"], out_root=self.out, **overrides)

    def test_fresh_grid_needs_no_data_or_model_environment(self) -> None:
        self.items.unlink()
        self.dialogues.unlink()
        self.assertEqual(self.plan(), [("fixture", "full", 13, "run")])
        self.assertFalse(self.out.exists())

    def test_matching_complete_run_is_skipped_without_changing_its_bytes(self) -> None:
        output = self.completed()
        before = {p.name: p.read_bytes() for p in output.iterdir()}
        self.assertEqual(self.plan(), [("fixture", "full", 13, "skip")])
        self.assertEqual(before, {p.name: p.read_bytes() for p in output.iterdir()})

    def test_runtime_recipe_change_is_not_silently_skipped(self) -> None:
        self.completed()
        for override in ({"micro_batch_size": 4}, {"gradient_checkpointing": True}):
            with self.subTest(override), self.assertRaisesRegex(ValueError, "recipe differs"):
                self.plan(**override)

    def test_wrong_or_legacy_metadata_is_refused(self) -> None:
        for changed in ({"seed": True}, {"seed": 42}, {"smoke": True}, {"smoke": 0},
                        {"eval_split": "test"}, {"config_sha256": "wrong"}, {"source_sha256": None}):
            with self.subTest(changed):
                self.completed(**changed)
                with self.assertRaisesRegex(ValueError, "provenance"):
                    self.plan()

    def test_changed_data_bytes_are_refused(self) -> None:
        for path in (self.items, self.dialogues):
            with self.subTest(path.name):
                self.completed()
                path.write_text('{"changed": true}\n', encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "sha256"):
                    self.plan()

    def test_changed_source_is_refused(self) -> None:
        self.completed()
        with mock.patch("src.stage1.provenance.source_sha256", return_value="0" * 64):
            with self.assertRaisesRegex(ValueError, "source_sha256"):
                self.plan()

    def test_missing_corrupt_or_edited_artifacts_are_preserved_and_refused(self) -> None:
        for filename in ("config.resolved.json", "metrics.json", "predictions.jsonl"):
            for replacement in (None, b"", b"{broken json"):
                if filename == "metrics.json" and replacement is None:
                    continue  # no completion marker means the interrupted run may resume
                with self.subTest(filename=filename, replacement=replacement):
                    output = self.completed()
                    artifact = output / filename
                    if replacement is None:
                        artifact.unlink()
                    else:
                        artifact.write_bytes(replacement)
                    before = {p.name: p.read_bytes() for p in output.iterdir()}
                    with self.assertRaises(ValueError):
                        self.plan()
                    self.assertEqual(before, {p.name: p.read_bytes() for p in output.iterdir()})

    def test_invalid_grid_is_refused(self) -> None:
        for seeds, conditions in (([], ["full"]), ([True], ["full"]), ([-1], ["full"]),
                                  ([13, 13], ["full"]), ([13], []), ([13], ["full", "full"]),
                                  ([13], ["invalid"])):
            with self.subTest(seeds=seeds, conditions=conditions), self.assertRaises(ValueError):
                plan(self.config, seeds, conditions, out_root=self.out)

    def test_directory_traversal_run_name_is_refused(self) -> None:
        self.config.write_text(self.config.read_text().replace('"fixture"', '"../escape"'), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "directory name"):
            self.plan()


class SourceHashTest(unittest.TestCase):
    def test_source_hash_tracks_paths_and_content_but_not_checkout_line_endings(self) -> None:
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (root / "src").mkdir()
        source = root / "src/module.py"
        source.write_bytes(b"x = 1\r\n")
        before = provenance.source_sha256(root)
        source.write_bytes(b"x = 1\n")
        self.assertEqual(before, provenance.source_sha256(root))
        (root / "src/__pycache__").mkdir()
        (root / "src/__pycache__/module.pyc").write_bytes(b"ignored")
        self.assertEqual(before, provenance.source_sha256(root))
        source.write_bytes(b"x = 2\n")
        self.assertNotEqual(before, provenance.source_sha256(root))
        source.write_bytes(b"x = 1\n")
        source.rename(source.with_name("renamed.py"))
        self.assertNotEqual(before, provenance.source_sha256(root))

    def test_empty_source_tree_cannot_produce_a_misleading_identity(self) -> None:
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        with self.assertRaisesRegex(ValueError, "no Python source"):
            provenance.source_sha256(root)


if __name__ == "__main__":
    unittest.main()
