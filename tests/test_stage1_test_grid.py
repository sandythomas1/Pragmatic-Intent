"""Exercise the single-GPU test-grid launcher without packages, data, a freeze or a GPU.

uv is replaced at the process boundary: the planner call prints a canned plan, and each trainer
call is recorded with the device it could see. The planner itself is tested in
tests/test_plan_test_grid.py.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLAN = "\n".join([
    "tfidf-utterance\tsrc.stage1.tfidf\tconfigs/stage1/tfidf_utterance.toml\tfull\t13\tskip",
    "deberta-v3-large\tsrc.stage1.encoder\tconfigs/stage1/encoder_deberta_v3_large.toml\tnone\t13\trun",
    "deberta-v3-large\tsrc.stage1.encoder\tconfigs/stage1/encoder_deberta_v3_large.toml\tone\t13\trun",
    "deberta-v3-large\tsrc.stage1.encoder\tconfigs/stage1/encoder_deberta_v3_large.toml\tfull\t13\trun",
    "tfidf-context\tsrc.stage1.tfidf\tconfigs/stage1/tfidf_context.toml\tfull\t13\trun",
])


@unittest.skipIf(os.name == "nt" or not shutil.which("bash") or not shutil.which("flock"), "Linux/WSL launcher")
class TestGridLauncherTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "scripts").mkdir()
        launcher = Path(__file__).resolve().parents[1] / "scripts/stage1_test_grid.sh"
        (self.root / "scripts/stage1_test_grid.sh").write_text(launcher.read_text(), encoding="utf-8", newline="\n")
        self.calls = self.root / "calls.jsonl"
        shim = self.root / "bin/uv"
        shim.parent.mkdir()
        shim.write_text(f"#!{sys.executable}\n" + '''
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
with Path(os.environ["GRID_CALLS"]).open("a") as handle:
    handle.write(json.dumps({"args": args, "cuda": os.environ.get("CUDA_VISIBLE_DEVICES")}) + "\\n")
if "scripts.plan_test_grid" in args:
    print(os.environ["GRID_PLAN"])
    sys.exit(int(os.environ.get("GRID_PLAN_RC", "0")))
if os.environ.get("GRID_TOUCH_STOP"):
    Path("outputs/stage1-test/STOP").touch()
sys.exit(int(os.environ.get("GRID_FAIL", "0")))
''', encoding="utf-8")
        shim.chmod(0o755)
        self.env = {**os.environ, "PATH": f"{shim.parent}:{os.environ['PATH']}",
                    "GRID_CALLS": str(self.calls), "GRID_PLAN": PLAN}
        for key in ("GPU", "SYSTEMS", "MAX_RUNS", "CHECKPOINT_EVERY", "MICRO_BATCH", "GRAD_CKPT",
                    "UV_PROJECT_ENVIRONMENT", "CUDA_VISIBLE_DEVICES"):
            self.env.pop(key, None)

    def launch(self, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", "scripts/stage1_test_grid.sh", "lab-5090", *args],
                              cwd=self.root, env={**self.env, **env}, capture_output=True, text=True)

    def calls_made(self) -> list[dict[str, object]]:
        if not self.calls.exists():
            return []
        return [json.loads(line) for line in self.calls.read_text().splitlines()]

    def trainer_calls(self) -> list[list[str]]:
        return [call["args"] for call in self.calls_made() if "scripts.plan_test_grid" not in call["args"]]

    def test_dry_run_prints_test_commands_skips_done_runs_and_writes_nothing(self) -> None:
        result = self.launch("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("skip tfidf-utterance train-full seed 13", result.stdout)
        commands = [line for line in result.stdout.splitlines() if line.startswith("uv ")]
        self.assertEqual(len(commands), 4)
        for line in commands:
            for flag in ("--eval-split test", "--allow-test", "--out-root outputs/stage1-test",
                         "--results results/stage1-test.jsonl", "--machine lab-5090", "--locked --group gpu"):
                self.assertIn(flag, line)
        self.assertIn("--checkpoint-every 250", commands[0])
        self.assertNotIn("--checkpoint-every", commands[3])  # TF-IDF has no checkpoints
        self.assertIn("4 run(s) planned, 0 left", result.stdout)
        self.assertEqual(self.trainer_calls(), [])
        self.assertFalse((self.root / "outputs").exists())

    def test_planner_runs_without_syncing_gpu_packages(self) -> None:
        self.launch("--dry-run", SYSTEMS="deberta-v3-large", MICRO_BATCH="4")
        planner = self.calls_made()[0]["args"]
        self.assertEqual(planner[:3], ["run", "--locked", "--no-sync"])
        self.assertEqual(planner[planner.index("--systems") + 1], "deberta-v3-large")
        self.assertEqual(planner[planner.index("--micro-batch-size") + 1], "4")

    def test_a_real_run_needs_exactly_one_gpu(self) -> None:
        for gpu in (None, "", "0,1", "all", "-1"):
            with self.subTest(gpu=gpu):
                env = {} if gpu is None else {"GPU": gpu}
                result = self.launch(**env)
                self.assertEqual(result.returncode, 2)
                self.assertIn("exactly one device", result.stderr)
        self.assertEqual(self.calls_made(), [])

    def test_trainers_see_only_the_chosen_gpu_and_log_under_the_test_root(self) -> None:
        result = self.launch(GPU="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls_made()
        self.assertEqual(len(calls), 5)
        self.assertEqual({call["cuda"] for call in calls[1:]}, {"1"})
        logs = sorted(path.name for path in (self.root / "outputs/stage1-test/logs").iterdir())
        self.assertEqual(logs, ["deberta-v3-large-train-full-seed13.log", "deberta-v3-large-train-none-seed13.log",
                                "deberta-v3-large-train-one-seed13.log", "tfidf-context-train-full-seed13.log"])

    def test_max_runs_caps_the_session_and_reports_what_is_left(self) -> None:
        result = self.launch(GPU="0", MAX_RUNS="2")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.trainer_calls()), 2)
        self.assertIn("2 run(s) started, 2 left for a later session", result.stdout)

    def test_stop_file_ends_the_session_after_the_current_run(self) -> None:
        result = self.launch(GPU="0", GRID_TOUCH_STOP="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.trainer_calls()), 1)
        self.assertIn("1 run(s) started, 3 left", result.stdout)
        again = self.launch(GPU="0")
        self.assertEqual(again.returncode, 1)
        self.assertIn("remove it to start a session", again.stderr)
        self.assertEqual(len(self.trainer_calls()), 1)

    def test_a_failed_run_stops_the_session(self) -> None:
        result = self.launch(GPU="0", GRID_FAIL="3")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.trainer_calls()), 1)

    def test_a_refused_plan_starts_no_run(self) -> None:
        result = self.launch(GPU="0", GRID_PLAN_RC="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.trainer_calls(), [])

    def test_a_second_launcher_in_the_same_checkout_is_refused(self) -> None:
        import fcntl  # POSIX only; the class is skipped on Windows

        lock = self.root / "outputs/stage1-test/.lock"
        lock.parent.mkdir(parents=True)
        with lock.open("w") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.launch(GPU="0")
        self.assertEqual(result.returncode, 1)
        self.assertIn("another stage1_test_grid.sh is running", result.stderr)
        self.assertEqual(self.calls_made(), [])

    def test_the_llm_environment_is_refused(self) -> None:
        result = self.launch("--dry-run", UV_PROJECT_ENVIRONMENT="/home/lab/.venvs/pi-llm")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unset UV_PROJECT_ENVIRONMENT", result.stderr)
        self.assertEqual(self.calls_made(), [])

    def test_bad_settings_are_refused_before_planning(self) -> None:
        for env in ({"MAX_RUNS": "two"}, {"CHECKPOINT_EVERY": "-1"}, {"GRAD_CKPT": "yes"}, {"MICRO_BATCH": "0"}):
            with self.subTest(env=env):
                self.assertEqual(self.launch("--dry-run", **env).returncode, 2)
        self.assertEqual(subprocess.run(["bash", "scripts/stage1_test_grid.sh", "lab 5090"], cwd=self.root,
                                        env=self.env, capture_output=True).returncode, 2)
        self.assertEqual(self.calls_made(), [])


if __name__ == "__main__":
    unittest.main()
