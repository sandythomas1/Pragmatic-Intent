"""Plan the frozen Stage 1 test grid: frozen seeds and conditions, seed-major order, safe reuse only.

The freeze is injected, so no test reads the repository's real freeze record or data.
"""

from __future__ import annotations

import contextlib
import datetime
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import plan_test_grid as grid
from src.analysis.config import load_config as load_analysis_config
from src.data.freeze import FreezeRecord, recipe_sha256
from src.stage1 import provenance

REPO = Path(__file__).resolve().parents[1]
FREEZE_CONTENT = "a" * 64
LARGE, UTTERANCE = "deberta-v3-large", "tfidf-utterance"


class PlanTestGridTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.items, self.dialogues = self.root / "items.jsonl", self.root / "dialogues.jsonl"
        self.items.write_text('{"fixture": 1}\n', encoding="utf-8")
        self.dialogues.write_text('{"context": "invented"}\n', encoding="utf-8")
        data = f'items = "{self.items.as_posix()}"\ndialogues = "{self.dialogues.as_posix()}"\n'
        self.recipes = {LARGE: self.root / "large.toml", UTTERANCE: self.root / "utterance.toml"}
        self.recipes[LARGE].write_text(f'[run]\nname = "{LARGE}"\nkind = "encoder"\n'
                                       f'[data]\ntrain_condition = "full"\n{data}'
                                       '[encoder]\npretrained = "invented/model"\n', encoding="utf-8")
        self.recipes[UTTERANCE].write_text(f'[run]\nname = "{UTTERANCE}"\nkind = "tfidf"\n'
                                           f'[data]\ntrain_condition = "none"\n{data}'
                                           '[tfidf]\nuse_context = false\n', encoding="utf-8")
        self.pins = {f"recipe.{LARGE}.seeds": "13,42", f"recipe.{UTTERANCE}.seeds": "13",
                     **{f"recipe.{name}.stage1": self.identity(name) for name in self.recipes}}
        self.out = self.root / "outputs/stage1-test"

    def identity(self, name: str) -> str:
        return recipe_sha256(grid.resolve_test_config(self.recipes[name], "full").to_dict())

    def frozen(self, **pins: str) -> FreezeRecord:
        config = load_analysis_config(REPO / "configs/analysis/analysis-v1.toml")
        return FreezeRecord({}, FREEZE_CONTENT, datetime.date(2026, 11, 9), {**self.pins, **pins}, config)

    def plan(self, systems: tuple[str, ...] = (LARGE,), **kwargs: object) -> list[grid.PlannedRun]:
        frozen = kwargs.pop("frozen", None) or self.frozen()
        return grid.plan(systems, frozen, self.recipes, out_root=self.out, **kwargs)

    def completed(self, condition: str = "none", seed: int = 13, **overrides: object) -> Path:
        config = grid.resolve_test_config(self.recipes[LARGE], condition)
        output = self.out / LARGE / f"train-{condition}" / f"seed{seed}"
        output.mkdir(parents=True)
        (output / "config.resolved.json").write_text(json.dumps(config.to_dict()), encoding="utf-8")
        predictions = output / "predictions.jsonl"
        predictions.write_text('{"prediction": "direct"}\n', encoding="utf-8")
        run = {"run": LARGE, "kind": "encoder", "seed": seed, "smoke": False, "train_split": "train",
               "eval_split": "test", "train_condition": condition, "policy": config.data.policy,
               "config_sha256": config.sha256(), **provenance.run_hashes(self.items, self.dialogues),
               "predictions_sha256": provenance.sha256(predictions), "freeze_content_sha256": FREEZE_CONTENT,
               **overrides}
        (output / "metrics.json").write_text(json.dumps({"run": run}), encoding="utf-8")
        return output

    def test_encoder_grid_is_seed_major_over_frozen_seeds_and_design_conditions(self) -> None:
        rows = self.plan()
        self.assertEqual([(run.seed, run.condition) for run in rows],
                         [(13, "none"), (13, "one"), (13, "full"), (42, "none"), (42, "one"), (42, "full")])
        self.assertEqual({(run.module, run.status) for run in rows}, {("src.stage1.encoder", "run")})
        self.assertFalse(self.out.exists())

    def test_test_time_baseline_trains_once_on_full(self) -> None:
        rows = self.plan((UTTERANCE, LARGE))
        self.assertEqual((rows[0].system, rows[0].module, rows[0].condition, rows[0].seed),
                         (UTTERANCE, "src.stage1.tfidf", "full", 13))
        self.assertEqual(len(rows), 7)
        self.assertEqual(rows[0].row().split("\t"), [UTTERANCE, "src.stage1.tfidf",
                                                     self.recipes[UTTERANCE].as_posix(), "full", "13", "run"])

    def test_fresh_plan_reads_no_data(self) -> None:
        self.items.unlink()
        self.dialogues.unlink()
        self.assertEqual(len(self.plan()), 6)

    def test_systems_outside_the_frozen_stage1_grid_are_refused(self) -> None:
        for systems in (("qwen2.5-7b-instruct",), ("hybrid",), ("deberta-v3-base",), (LARGE, LARGE), ()):
            with self.subTest(systems=systems), self.assertRaises(grid.PlanError):
                self.plan(systems)

    def test_a_recipe_that_moved_since_the_freeze_is_refused_before_any_run(self) -> None:
        with self.assertRaisesRegex(grid.PlanError, "recipe_not_frozen"):
            self.plan(frozen=self.frozen(**{f"recipe.{LARGE}.stage1": "b" * 64}))

    def test_a_config_for_another_run_name_is_refused(self) -> None:
        with self.assertRaisesRegex(grid.PlanError, "does not define"):
            grid.plan((LARGE,), self.frozen(), {LARGE: self.recipes[UTTERANCE]}, out_root=self.out)

    def test_memory_knobs_keep_the_frozen_identity(self) -> None:
        rows = self.plan(micro_batch_size=4, gradient_checkpointing=True)
        self.assertEqual(len(rows), 6)

    def test_a_verified_run_under_this_freeze_is_skipped_without_changing_its_bytes(self) -> None:
        output = self.completed()
        before = {path.name: path.read_bytes() for path in output.iterdir()}
        statuses = [run.status for run in self.plan()]
        self.assertEqual(statuses, ["skip", "run", "run", "run", "run", "run"])
        self.assertEqual(before, {path.name: path.read_bytes() for path in output.iterdir()})

    def test_an_interrupted_run_is_planned_again_so_its_checkpoint_resumes(self) -> None:
        output = self.out / LARGE / "train-none/seed13"
        output.mkdir(parents=True)
        (output / "checkpoint.pt").write_bytes(b"fixture")
        self.assertEqual(self.plan()[0].status, "run")

    def test_completed_runs_that_cannot_be_reused_refuse_the_whole_plan(self) -> None:
        cases = {"another freeze": {"freeze_content_sha256": "c" * 64},
                 "no freeze": {"freeze_content_sha256": None},
                 "a dev run": {"eval_split": "dev"},
                 "edited predictions": {"predictions_sha256": "d" * 64}}
        for label, overrides in cases.items():
            with self.subTest(label), tempfile.TemporaryDirectory() as temp:
                self.out = Path(temp)
                self.completed(**overrides)
                with self.assertRaisesRegex(grid.PlanError, "cannot reuse"):
                    self.plan()

    def test_cli_prints_rows_or_one_refusal_line(self) -> None:
        stdout, stderr = io.StringIO(), io.StringIO()
        with (mock.patch.object(grid, "load_frozen", return_value=(self.frozen(), self.recipes)),
              mock.patch.object(grid, "OUT_ROOT", self.out),
              contextlib.redirect_stdout(stdout)):
            self.assertEqual(grid.main(["--systems", UTTERANCE]), 0)
        self.assertEqual(stdout.getvalue().count("\n"), 1)
        with (mock.patch.object(grid, "load_frozen", side_effect=grid.PlanError("freeze refused (x): y")),
              contextlib.redirect_stderr(stderr)):
            self.assertEqual(grid.main(["--systems", LARGE]), 1)
        self.assertEqual(stderr.getvalue(), "test grid refused: freeze refused (x): y\n")


if __name__ == "__main__":
    unittest.main()
