"""Test-time gates (spec 008 T7–T8): no verifying freeze, no test run, score or analysis."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

from src.analysis import __main__ as analysis_cli
from src.analysis.config import load_config as load_analysis_config
from src.analysis.files import AnalysisError, hash_file
from src.analysis.inputs import Stage1Run
from src.data import freeze
from src.data import split_audit as sa
from src.evaluation import run as legacy_run
from src.evaluation import stage1 as stage1_scorer
from src.evaluation import stage2, transfer
from src.stage1 import runner
from src.stage1.config import load_config as load_stage1_config
from tests.freeze_fixtures import ENCODER_TOML, FreezeRepo


def run_args(config: str, **options: Any) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    runner.add_common_args(parser)
    argv = ["--config", config, "--seed", str(options.pop("seed", 13))]
    for key, value in options.items():
        flag = "--" + key.replace("_", "-")
        if value is not False:
            argv += [flag] if value is True else [flag, str(value)]
    return parser.parse_args(argv)


class GateTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = FreezeRepo().build()
        self.addCleanup(self.repo.cleanup)
        self.enterContext(contextlib.chdir(self.repo.root))

    def test_args(self, **options: Any) -> argparse.Namespace:
        defaults = {"eval_split": "test", "allow_test": True, "train_condition": "none"}
        return run_args("configs/stage1/enc.toml", **{**defaults, **options})

    def assert_code(self, code: str, call: Any) -> AnalysisError:
        with self.assertRaises(AnalysisError) as caught:  # FreezeError, or spec 007's reader for a missing file
            call()
        self.assertEqual(caught.exception.code, code)
        return caught.exception


class RunnerGateTest(GateTestCase):
    def test_no_record_no_test_run(self) -> None:
        self.assert_code("freeze_missing", lambda: runner.load(self.test_args(), {}))

    def test_a_failing_record_no_test_run(self) -> None:
        self.repo.freeze()
        self.repo.write("src/tool.py", "VALUE = 2\n")
        self.assert_code("freeze_mismatch", lambda: runner.load(self.test_args(), {}))

    def test_a_frozen_run_proceeds_and_carries_the_freeze_hash(self) -> None:
        record = self.repo.freeze()
        for condition in ("none", "one", "full"):
            args = self.test_args(train_condition=condition, seed=42)
            config = runner.load(args, {"encoder": {"micro_batch_size": 4, "gradient_checkpointing": True}})
            self.assertEqual(config.data.eval_split, "test")
            self.assertEqual(args.freeze_content_sha256, record["content_sha256"])
        tfidf = run_args("configs/stage1/tfidf.toml", eval_split="test", allow_test=True)
        runner.load(tfidf, {})

    def test_runs_off_the_grid_are_refused(self) -> None:
        self.repo.freeze()
        self.assert_code("seed_not_frozen", lambda: runner.load(self.test_args(seed=7), {}))
        self.assert_code("condition_not_frozen", lambda: runner.load(self.test_args(train_condition="mismatched"), {}))
        tfidf = run_args("configs/stage1/tfidf.toml", eval_split="test", allow_test=True, train_condition="one")
        self.assert_code("condition_not_frozen", lambda: runner.load(tfidf, {}))
        # An unpinned recipe file for a frozen system name: the freeze verifies, the recipe does not match.
        self.repo.write("configs/stage1/enc_alt.toml", ENCODER_TOML.replace('pretrained = "org/model"',
                                                                            'pretrained = "org/model"\nepochs = 3'))
        alt = run_args("configs/stage1/enc_alt.toml", eval_split="test", allow_test=True, train_condition="full")
        self.assert_code("recipe_not_frozen", lambda: runner.load(alt, {}))

    def test_smoke_on_test_is_refused(self) -> None:
        self.repo.freeze()
        with self.assertRaisesRegex(ValueError, "--smoke on test is refused"):
            runner.load(self.test_args(smoke=True), {})

    def test_test_still_needs_allow_test_first(self) -> None:
        with self.assertRaisesRegex(ValueError, "--allow-test"):
            runner.load(self.test_args(allow_test=False), {})

    def test_dev_runs_ignore_the_freeze_entirely(self) -> None:
        for state in ("absent", "broken"):
            with self.subTest(freeze=state):
                if state == "broken":
                    self.repo.write(sa.FREEZE_FILE, "not json")
                args = run_args("configs/stage1/enc.toml")
                config = runner.load(args, {})
                self.assertEqual(config.data.eval_split, "dev")
                self.assertFalse(hasattr(args, "freeze_content_sha256"))

    def test_finish_records_the_freeze_hash_in_the_run_block(self) -> None:
        record = self.repo.freeze()
        args = self.test_args(results="results/stage1.jsonl", out_root="outputs/stage1")
        config = runner.load(args, {})
        prepared = runner.Prepared(train=[], train_inputs=[], eval=[], eval_sets={}, eval_inputs={})
        report = {"renderer_version": "render-v1", "sets": {}, "slices": {}, "conditions": {}, "contrasts": {}}
        with mock.patch.object(runner, "build_report", return_value=report):
            out = runner.finish(args, config, prepared, [], {"name": "fake"}, time.time())
        metrics = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
        self.assertEqual(metrics["run"]["freeze_content_sha256"], record["content_sha256"])
        logged = json.loads(Path("results/stage1.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(logged["freeze_content_sha256"], record["content_sha256"])


class ScorerGateTest(GateTestCase):
    def call(self, module: Any, argv: list[str]) -> tuple[int, str]:
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = module.main(argv)
        return code, err.getvalue()

    STAGE2 = ["inputs", "--split", "test", "--allow-test", "--out", "data/interim/stage2/test.jsonl"]
    TRANSFER = ["inputs", "--split", "test", "--allow-test", "--out", "data/interim/stage2/transfer.jsonl"]

    def test_stage2_and_transfer_refuse_without_a_record(self) -> None:
        for module, argv in ((stage2, self.STAGE2), (transfer, self.TRANSFER)):
            with self.subTest(module=module.__name__):
                code, err = self.call(module, argv)
                self.assertEqual(code, 1)
                self.assertIn("freeze_missing", err)
                self.assertFalse(Path(argv[-1]).exists())

    def test_stage2_and_transfer_refuse_a_failing_record(self) -> None:
        self.repo.freeze()
        self.repo.write("uv.lock", "version = 3\n")
        for module, argv in ((stage2, self.STAGE2), (transfer, self.TRANSFER)):
            with self.subTest(module=module.__name__):
                code, err = self.call(module, argv)
                self.assertEqual(code, 1)
                self.assertIn("freeze_mismatch", err)
                self.assertIn("env.uv_lock", err)

    def past_the_gate(self, module: Any) -> Any:
        """Stub the first step after the gate: the fixture holds no corpus text or transfer sources."""
        if module is transfer:
            return mock.patch.object(transfer.ir, "load_pinned", side_effect=ValueError("past the gate"))
        return mock.patch.object(stage2, "load_items", side_effect=ValueError("past the gate"))

    def test_a_verifying_record_lets_them_past_the_gate(self) -> None:
        self.repo.freeze()
        for module, argv in ((stage2, self.STAGE2), (transfer, self.TRANSFER)):
            with self.subTest(module=module.__name__), self.past_the_gate(module):
                with mock.patch.object(module, "require_freeze", wraps=freeze.require_freeze) as gate:
                    code, err = self.call(module, argv)
                gate.assert_called_once()
                self.assertEqual(code, 1)
                self.assertIn("past the gate", err)

    def test_dev_scoring_never_reads_the_freeze(self) -> None:
        self.repo.write(sa.FREEZE_FILE, "not json")
        for module, argv in ((stage2, ["inputs", "--split", "dev", "--out", "data/interim/stage2/dev.jsonl"]),
                             (transfer, ["inputs", "--split", "validation", "--out", "data/interim/stage2/transfer.jsonl"])):
            with self.subTest(module=module.__name__), self.past_the_gate(module):
                with mock.patch.object(module, "require_freeze") as gate:
                    code, err = self.call(module, argv)
                gate.assert_not_called()
                self.assertIn("past the gate", err)


class Stage1ScorerGateTest(GateTestCase):
    """The standalone Stage 1 re-scorer and the legacy evaluation CLI score test too (spec 008 FR16)."""

    STAGE1 = ["--predictions", "p.jsonl", "--out", "o.json", "--split", "test"]
    LEGACY = ["--annotations", "a.csv", "--split", "test", "--predictions", "p.jsonl", "--out-dir", "o"]

    def call(self, module: Any, argv: list[str]) -> tuple[int, str]:
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = module.main(argv)
        return code, err.getvalue()

    def past_the_gate(self, module: Any) -> Any:
        name = "load_items" if module is stage1_scorer else "load_examples"
        return mock.patch.object(module, name, side_effect=ValueError("past the gate"))

    def test_both_refuse_test_without_a_verifying_record(self) -> None:
        for module, argv in ((stage1_scorer, self.STAGE1), (legacy_run, self.LEGACY)):
            with self.subTest(module=module.__name__), self.past_the_gate(module):
                code, err = self.call(module, argv)
                self.assertEqual(code, 1)
                self.assertIn("freeze_missing", err)
        self.repo.freeze()
        self.repo.write("src/tool.py", "VALUE = 2\n")
        for module, argv in ((stage1_scorer, self.STAGE1), (legacy_run, self.LEGACY)):
            with self.subTest(module=module.__name__, record="failing"), self.past_the_gate(module):
                self.assertIn("freeze_mismatch", self.call(module, argv)[1])

    def test_both_pass_a_verifying_record_and_ignore_it_on_dev(self) -> None:
        self.repo.freeze()
        for module, argv in ((stage1_scorer, self.STAGE1), (legacy_run, self.LEGACY)):
            with self.subTest(module=module.__name__), self.past_the_gate(module):
                self.assertIn("past the gate", self.call(module, argv)[1])
        self.repo.write(sa.FREEZE_FILE, "not json")
        for module, argv in ((stage1_scorer, self.STAGE1), (legacy_run, self.LEGACY)):
            dev = [value if value != "test" else "dev" for value in argv]
            with self.subTest(module=module.__name__, split="dev"), self.past_the_gate(module):
                self.assertIn("past the gate", self.call(module, dev)[1])


class AnalysisGateTest(GateTestCase):
    def gate(self) -> Any:
        args = argparse.Namespace(allow_test=True, items=sa.DEFAULT_ITEMS, dialogues=sa.DEFAULT_DIALOGUES,
                                  registry=sa.DEFAULT_REGISTRY, audit=sa.DEFAULT_AUDIT, freeze=sa.FREEZE_FILE)
        config = load_analysis_config(self.repo.root / "configs/analysis/analysis-v1.toml")
        return analysis_cli.gate_test(args, self.repo.root, config)

    def stage1_inputs(self, *runs: tuple[str, str, str, int]) -> Any:
        """Inputs naming Stage 1 run directories whose resolved configs come from ``(system, toml, train, seed)``."""
        systems: dict[str, Any] = {}
        for system, toml, train, seed in runs:
            run_dir = self.repo.root / f"outputs/stage1/{system}/train-{train}/seed{seed}"
            run_dir.mkdir(parents=True, exist_ok=True)
            resolved = load_stage1_config(self.repo.root / toml, {"data": {"train_condition": train, "eval_split": "test"}},
                                          allow_test=True).to_dict()
            (run_dir / "config.resolved.json").write_text(json.dumps(resolved, indent=2) + "\n", encoding="utf-8")
            ref = hash_file(run_dir / "config.resolved.json", 1 << 20)
            systems.setdefault(system, SimpleNamespace(stage1=[], stage2=[]))
            systems[system].stage1.append(Stage1Run(train, seed, run_dir, ref, ref, ref))
        return SimpleNamespace(systems=systems)

    def test_no_record_no_test_analysis(self) -> None:
        self.assert_code("freeze_missing", self.gate)

    def test_a_failing_record_no_test_analysis(self) -> None:
        self.repo.freeze()
        self.repo.write("src/tool.py", "VALUE = 2\n")
        self.assert_code("freeze_mismatch", self.gate)

    def test_a_verifying_record_passes_the_gate(self) -> None:
        record = self.repo.freeze()
        _, frozen = self.gate()
        self.assertEqual(frozen.content_sha256, record["content_sha256"])

    def test_every_stage1_run_must_be_in_the_frozen_grid(self) -> None:
        self.repo.freeze()
        _, frozen = self.gate()
        enc, tfidf = "configs/stage1/enc.toml", "configs/stage1/tfidf.toml"
        analysis_cli.check_frozen_runs(frozen, self.stage1_inputs(
            ("enc", enc, "none", 13), ("enc", enc, "one", 42), ("enc", enc, "full", 13), ("tfidf", tfidf, "full", 13)))
        self.repo.write("configs/stage1/enc_alt.toml", ENCODER_TOML.replace('pretrained = "org/model"',
                                                                            'pretrained = "org/model"\nepochs = 3'))
        cases = {
            "seed_not_frozen": ("enc", enc, "none", 7),
            "condition_not_frozen": ("tfidf", tfidf, "one", 13),
            "recipe_not_frozen": ("enc", "configs/stage1/enc_alt.toml", "full", 13),
        }
        for code, run in cases.items():
            with self.subTest(code=code):
                self.assert_code(code, lambda run=run: analysis_cli.check_frozen_runs(frozen, self.stage1_inputs(run)))

    def test_cli_reports_a_freeze_failure_as_an_analysis_failure(self) -> None:
        self.repo.write_analysis_config(draft=False)
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = analysis_cli.main(["run", "--split", "test", "--allow-test", "--inputs", "configs/analysis/none.toml",
                                      "--root", str(self.repo.root)])
        self.assertEqual(code, 1)
        self.assertIn("freeze_missing", err.getvalue())


if __name__ == "__main__":
    unittest.main()
