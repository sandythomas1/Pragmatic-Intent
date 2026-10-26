"""Exercise the Linux grid launcher without packages, model downloads or GPU jobs."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


@unittest.skipIf(os.name == "nt" or not shutil.which("bash"), "Linux/WSL launcher")
class GridLauncherTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "scripts").mkdir()
        launcher = Path(__file__).resolve().parents[1] / "scripts/stage1_grid.sh"
        (self.root / "scripts/stage1_grid.sh").write_text(launcher.read_text(), encoding="utf-8", newline="\n")
        self.config = self.root / "encoder.toml"
        self.config.write_text('[run]\nname = "fixture"\nkind = "encoder"\n'
                               '[data]\ntrain_condition = "full"\n'
                               '[encoder]\npretrained = "fixture"\n', encoding="utf-8")
        # Reuse the real config loader, with uv replaced only at the process boundary.
        self.calls = self.root / "calls.jsonl"
        shim = self.root / "uv"
        shim.write_text(f'#!{sys.executable}\n' + '''
import json, os, subprocess, sys
from pathlib import Path
args = sys.argv[1:]
with Path(os.environ["GRID_CALLS"]).open("a") as handle:
    handle.write(json.dumps(args) + "\\n")
python_args = args[args.index("python") + 1:]
if python_args[0] == "-c" or "src.stage1.grid_check" in python_args:
    sys.exit(subprocess.call([sys.executable, *python_args]))
sys.exit(int(os.environ.get("GRID_FAIL", "0")))
''', encoding="utf-8")
        shim.chmod(0o755)
        self.env = {**os.environ, "PATH": f"{self.root}:{os.environ['PATH']}",
                    "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
                    "GRID_CALLS": str(self.calls)}
        for key in ("SEEDS", "CONDITIONS", "CHECKPOINT_EVERY", "MICRO_BATCH", "GRAD_CKPT"):
            self.env.pop(key, None)

    def run_grid(self, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", "scripts/stage1_grid.sh", str(self.config), "fixture-machine", *args],
                              cwd=self.root, env={**self.env, **env}, capture_output=True, text=True)

    def commands(self) -> list[list[str]]:
        return [json.loads(line) for line in self.calls.read_text().splitlines()]

    def test_dry_run_plans_fifteen_dev_runs_without_training_or_output_directories(self) -> None:
        result = self.run_grid("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("--train-condition"), 15)
        self.assertNotIn("--train-condition mismatched", result.stdout)
        self.assertEqual(len(self.commands()), 1)  # config inspection only
        self.assertFalse((self.root / "outputs").exists())

    def test_runs_use_locked_uv_and_honor_resource_overrides(self) -> None:
        result = self.run_grid(SEEDS="13", CONDITIONS="full", MICRO_BATCH="4", GRAD_CKPT="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = self.commands()
        self.assertIn("--no-sync", commands[0])
        self.assertTrue(all("--locked" in command for command in commands))
        train = commands[1]
        self.assertIn("src.stage1.encoder", train)
        self.assertEqual(train[train.index("--micro-batch-size") + 1], "4")
        self.assertIn("--gradient-checkpointing", train)
        self.assertEqual(train[train.index("--checkpoint-every") + 1], "250")

    def test_zero_disables_checkpointing_and_gradient_checkpointing(self) -> None:
        result = self.run_grid(SEEDS="13", CONDITIONS="full", CHECKPOINT_EVERY="0", GRAD_CKPT="0")
        self.assertEqual(result.returncode, 0, result.stderr)
        train = self.commands()[1]
        self.assertNotIn("--checkpoint-every", train)
        self.assertNotIn("--gradient-checkpointing", train)

    def test_failed_run_stops_grid_and_preserves_log(self) -> None:
        result = self.run_grid(SEEDS="13 42", CONDITIONS="full", GRID_FAIL="7")
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertEqual(len(self.commands()), 2)
        self.assertTrue((self.root / "outputs/stage1/logs/fixture-train-full-seed13.log").is_file())

    def test_unknown_option_is_rejected_before_starting(self) -> None:
        result = self.run_grid("--dryrun")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.calls.exists())

    def test_invalid_controls_are_refused_before_training(self) -> None:
        for env in ({"CHECKPOINT_EVERY": "-1"}, {"GRAD_CKPT": "false"}, {"SEEDS": "13 13"},
                    {"CONDITIONS": "invalid"}, {"MICRO_BATCH": "12"}):
            with self.subTest(env):
                result = self.run_grid(**env)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                if self.calls.exists():
                    self.assertFalse(any("src.stage1.encoder" in command for command in self.commands()))

    def test_existing_metrics_without_matching_artifacts_are_refused(self) -> None:
        out = self.root / "outputs/stage1/fixture/train-full/seed13"
        out.mkdir(parents=True)
        metrics = out / "metrics.json"
        metrics.write_text('{"run": {"seed": 13}}\n', encoding="utf-8")
        before = metrics.read_bytes()
        result = self.run_grid(SEEDS="13", CONDITIONS="full")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertFalse(any("src.stage1.encoder" in command for command in self.commands()))
        self.assertEqual(metrics.read_bytes(), before)

    def test_later_stale_result_blocks_the_entire_grid_before_training(self) -> None:
        out = self.root / "outputs/stage1/fixture/train-full/seed42"
        out.mkdir(parents=True)
        (out / "metrics.json").write_text('{}\n', encoding="utf-8")
        result = self.run_grid(SEEDS="13 42", CONDITIONS="full")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertFalse(any("src.stage1.encoder" in command for command in self.commands()))


if __name__ == "__main__":
    unittest.main()
