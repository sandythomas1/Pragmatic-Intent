"""Recipe hash and the runner's ``--eval-split`` (spec 008 T2)."""

from __future__ import annotations

import argparse
import json
import unittest
from pathlib import Path
from unittest import mock

from src.data import freeze
from src.data.freeze import FreezeError
from src.stage1 import runner
from src.stage1.config import load_config
from tests.analysis_fixtures import Workspace

ENCODER = """# a comment that must not move the hash
[run]
name = "enc"
kind = "encoder"

[data]
train_condition = "full"

[encoder]
pretrained = "org/model"
revision = "0123456789abcdef0123456789abcdef01234567"
learning_rate = 1e-5
micro_batch_size = 8
"""

TFIDF = """[run]
name = "tfidf"
kind = "tfidf"

[data]
train_condition = "full"

[tfidf]
use_context = true
ngram_max = 2
"""


def args(config: Path, **options: object) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    runner.add_common_args(parser)
    argv = ["--config", str(config), "--seed", "1"]
    for key, value in options.items():
        flag = "--" + key.replace("_", "-")
        argv += [flag] if value is True else [flag, str(value)]
    return parser.parse_args(argv)


class RecipeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.ws = Workspace()
        self.addCleanup(self.ws.cleanup)

    def recipe(self, relative: str, text: str) -> str:
        self.ws.write(relative, text)
        return freeze.recipe_sha256(freeze.stage1_recipe(self.ws.root, Path(relative)))


class RecipeHashTest(RecipeTestCase):
    def test_a_run_resolved_config_has_its_recipe_hash(self) -> None:
        expected = self.recipe("enc.toml", ENCODER)
        path = self.ws.root / "enc.toml"
        for overrides in ({"data": {"train_condition": "none"}},
                          {"data": {"train_condition": "one", "eval_split": "test"}},
                          {"encoder": {"micro_batch_size": 4, "gradient_checkpointing": True}}):
            with self.subTest(overrides=overrides):
                config = load_config(path, overrides, allow_test=True)
                # As runner.finish writes it, then as the analysis reads it back.
                resolved = json.loads(json.dumps(config.to_dict(), indent=2) + "\n")
                self.assertEqual(freeze.recipe_sha256(resolved), expected)

    def test_semantic_fields_move_the_hash(self) -> None:
        base = self.recipe("enc.toml", ENCODER)
        changes = {
            "learning_rate": ("learning_rate = 1e-5", "learning_rate = 2e-5"),
            "revision": ("0123456789abcdef0123456789abcdef01234567", "fedcba9876543210fedcba9876543210fedcba98"),
            "epochs": ("micro_batch_size = 8", "micro_batch_size = 8\nepochs = 3"),
            "name": ('name = "enc"', 'name = "enc2"'),
            "eval_conditions": ('train_condition = "full"', 'train_condition = "full"\neval_conditions = ["none", "full"]'),
        }
        for field, (old, new) in changes.items():
            with self.subTest(field=field):
                self.assertNotEqual(self.recipe(f"{field}.toml", ENCODER.replace(old, new)), base)

    def test_tfidf_semantic_field_moves_the_hash(self) -> None:
        self.assertNotEqual(self.recipe("a.toml", TFIDF), self.recipe("b.toml", TFIDF.replace("ngram_max = 2", "ngram_max = 3")))

    def test_comments_whitespace_and_key_order_do_not_move_it(self) -> None:
        base = self.recipe("enc.toml", ENCODER)
        reordered = ENCODER.replace("# a comment that must not move the hash\n", "") \
            .replace('learning_rate = 1e-5\nmicro_batch_size = 8\n', 'micro_batch_size = 8\nlearning_rate   = 0.00001  # same\n')
        self.assertEqual(self.recipe("reordered.toml", reordered), base)
        self.assertEqual(self.recipe("crlf.toml", ENCODER.replace("\n", "\r\n")), base)

    def test_runtime_fields_in_the_file_do_not_move_it(self) -> None:
        base = self.recipe("enc.toml", ENCODER)
        variant = ENCODER.replace('train_condition = "full"', 'train_condition = "one"\neval_split = "dev"') \
            .replace("micro_batch_size = 8", "micro_batch_size = 16\ngradient_checkpointing = true")
        self.assertEqual(self.recipe("variant.toml", variant), base)

    def test_invalid_recipes_raise_a_named_error_with_the_relative_path(self) -> None:
        for name, text in {"bad.toml": "[run]\nname = 1\n", "broken.toml": "[run\n",
                           "unknown.toml": ENCODER.replace("[encoder]", "[encoder]\nlr = 1")}.items():
            with self.subTest(name=name):
                self.ws.write(name, text)
                with self.assertRaises(FreezeError) as caught:
                    freeze.stage1_recipe(self.ws.root, Path(name))
                self.assertEqual((caught.exception.code, caught.exception.keys), ("invalid_recipe", (name,)))
                self.assertNotIn(str(self.ws.root), str(caught.exception))
        with self.assertRaises(FreezeError) as caught:
            freeze.stage1_recipe(self.ws.root, Path("absent.toml"))
        self.assertEqual(caught.exception.code, "invalid_recipe")

    def test_a_recipe_must_be_an_object(self) -> None:
        with self.assertRaises(FreezeError) as caught:
            freeze.recipe_sha256([1, 2])  # type: ignore[arg-type]
        self.assertEqual(caught.exception.code, "malformed_recipe")

    def test_every_committed_stage1_config_hashes(self) -> None:
        root = Path(__file__).resolve().parents[1]
        configs = sorted((root / "configs/stage1").glob("*.toml"))
        self.assertGreaterEqual(len(configs), 6)
        hashes = {freeze.recipe_sha256(freeze.stage1_recipe(root, p.relative_to(root))) for p in configs}
        self.assertEqual(len(hashes), len(configs))


class EvalSplitTest(RecipeTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.ws.write("tfidf.toml", TFIDF)
        self.config = self.ws.root / "tfidf.toml"

    def test_no_flag_keeps_the_config_split(self) -> None:
        self.assertEqual(runner.load(args(self.config), {}).data.eval_split, "dev")

    def test_dev_flag_is_the_same_config(self) -> None:
        self.assertEqual(runner.load(args(self.config, eval_split="dev"), {}), runner.load(args(self.config), {}))

    def test_test_needs_allow_test(self) -> None:
        with self.assertRaisesRegex(ValueError, "--allow-test"):
            runner.load(args(self.config, eval_split="test"), {})
        # With --allow-test the override reaches the spec 008 gate (tested in test_freeze_gates).
        with mock.patch.object(runner, "require_freeze", return_value=mock.Mock(content_sha256="f" * 64)):
            config = runner.load(args(self.config, eval_split="test", allow_test=True), {})
        self.assertEqual(config.data.eval_split, "test")

    def test_only_dev_or_test_are_accepted(self) -> None:
        parser = argparse.ArgumentParser()
        runner.add_common_args(parser)
        with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
            parser.parse_args(["--config", "x", "--seed", "1", "--eval-split", "train"])

    def test_programmatic_namespaces_without_the_flag_still_load(self) -> None:
        namespace = argparse.Namespace(config=self.config, train_condition=None, allow_test=False)
        self.assertEqual(runner.load(namespace, {}).data.eval_split, "dev")


if __name__ == "__main__":
    unittest.main()
