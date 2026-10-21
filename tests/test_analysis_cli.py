"""``python -m src.analysis run``: gates, stamps, outputs and determinism (spec 007 T9–T10)."""

from __future__ import annotations

import io
import json
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from typing import Any
from unittest import mock

from src.analysis import __main__ as cli
from src.analysis.config import load_config
from src.analysis.files import AnalysisError
from src.analysis.outcomes import load_evaluation_set
from src.data.direct_dataset import load_items
from src.evaluation.test_audit import SplitAudit, TestAuditError
from src.stage1.data import build_examples
from tests.analysis_fixtures import (
    DIRECT_TEXT,
    INDIRECT_TEXTS,
    Workspace,
    config_dict,
    config_toml,
    stage1_entries,
    write_corpus,
    write_stage1_grid,
    write_stage2_grid,
)

GENUINE = ("none", "one", "full")
CONFIG = "configs/analysis/analysis-v1.toml"
INPUTS = "configs/analysis/inputs.toml"
CLI_FIXTURE_TEXT = (DIRECT_TEXT, *INDIRECT_TEXTS.values(), "line 1 of the chat")


class CliTestCase(unittest.TestCase):
    split = "dev"

    def setUp(self) -> None:
        self.ws = Workspace()
        self.addCleanup(self.ws.cleanup)
        self.items, self.dialogues = write_corpus(self.ws, split=self.split)
        self.write_config(draft=self.split == "dev")
        examples, _ = build_examples(load_items(self.items), self.split, require_context=True)
        self.audit = SplitAudit(frozenset(e.example_id for e in examples), {},
                                frozenset(e.example_id for e in examples[:2]), "c" * 64)
        self.evaluation = load_evaluation_set(self.items, self.dialogues, self.split, "auto-v1",
                                              self.audit if self.split == "test" else None)
        levels = self.evaluation.slices["rule_level"]
        self.assertEqual(set(levels.values()), {"L0", "L1", "L2"})  # the fixture wording does what it claims

        def context_helps_at_l2(e, condition, train, seed, oracle=False):
            return {"category": "travel"} if condition == "none" and levels[e.example_id] == "L2" else {}

        def stage1(e, condition, train, seed):
            return e.label if (seed + len(e.example_id) + len(condition)) % 4 else "no_request"

        write_stage1_grid(self.ws, self.evaluation, "enc", GENUINE, (1, 2), stage1)
        self._systems = {"enc": {"stage1": stage1_entries("enc", GENUINE, (1, 2))},
                         "pipe": {"stage2": write_stage2_grid(self.ws, self.evaluation, "pipe", GENUINE, (1,),
                                                              context_helps_at_l2)}}
        self.ws.inputs(self._systems, split=self.split, name=INPUTS)

    def inputs_systems(self) -> dict[str, Any]:
        return dict(self._systems)

    def write_config(self, **options: Any) -> None:
        self.ws.write(CONFIG, config_toml(config_dict(**{"min_dialogues": 5, "samples": 200, **options})))

    def args(self, *extra: str) -> list[str]:
        return ["run", "--split", self.split, "--root", str(self.ws.root), "--config", CONFIG, "--inputs", INPUTS,
                *extra]

    def invoke(self, *extra: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(self.args(*extra))
        return code, out.getvalue(), err.getvalue()

    def report(self) -> dict[str, Any]:
        return json.loads((self.ws.root / f"outputs/analysis/{self.split}/report.json").read_text(encoding="utf-8"))

    def assert_no_ids_or_text(self, text: str) -> None:
        self.assertNotIn("PMUL", text)
        for sentinel in CLI_FIXTURE_TEXT:
            self.assertNotIn(sentinel, text)


class DevRunTest(CliTestCase):
    def test_dev_run_needs_no_audit_or_freeze_and_is_stamped_a_diagnostic(self) -> None:
        code, out, err = self.invoke()
        self.assertEqual((code, err), (0, ""))
        report = self.report()
        self.assertEqual((report["stamp"], report["split"]), ("dev_diagnostic_not_a_finding", "dev"))
        self.assertEqual(report["primary_test"]["status"], "ok")
        self.assertEqual(report["systems"], {"enc": "run", "tfidf": "not_run", "llm": "not_run", "pipe": "run"})
        provenance = report["provenance"]
        self.assertEqual(provenance["config_sha256"], load_config(self.ws.root / CONFIG).sha256)
        self.assertIsNone(provenance["test_audit"])
        self.assertEqual(provenance["command"], f"python -m src.analysis run --split dev --config {CONFIG} --inputs {INPUTS}")
        self.assertEqual(len(provenance["files"]), 6 * 3 + 3 * 2)
        self.assertIn("git_dirty", provenance)
        self.assertFalse((self.ws.root / "results").exists())  # dev writes nothing committed
        self.assertIn("precision", report)
        self.assertIn("component check passed for 9 runs", out)

    def test_two_runs_are_byte_identical_and_the_console_holds_no_ids_or_text(self) -> None:
        path = self.ws.root / "outputs/analysis/dev/report.json"
        _, first_out, first_err = self.invoke()
        first = path.read_bytes()
        self.invoke()
        self.assertEqual(path.read_bytes(), first)
        self.assert_no_ids_or_text(first_out + first_err)
        self.assert_no_ids_or_text(first.decode("utf-8"))

    def test_an_output_that_is_an_input_is_refused(self) -> None:
        self.ws.write("outputs/analysis/dev/report.json", (self.ws.root / INPUTS).read_text(encoding="utf-8"))
        with self.assertRaises(AnalysisError) as caught:
            cli.run(cli.build_parser().parse_args(self.args()[:-2] + ["--inputs", "outputs/analysis/dev/report.json"]))
        self.assertEqual(caught.exception.code, "output_is_input")

    def test_failures_exit_1_without_ids(self) -> None:
        self.ws.write_jsonl("outputs/stage1/enc/train-none/seed1/predictions.jsonl", [{"example_id": "PMUL9101_t02:direct"}])
        code, out, err = self.invoke()
        self.assertEqual(code, 1)
        self.assertIn("Analysis failed", err)
        self.assert_no_ids_or_text(out + err)


class TestGateTest(CliTestCase):
    """AC-007-9: every gate fails before any prediction file is opened."""

    split = "test"

    def freeze(self, sha: str | None = None) -> None:
        sha = sha or load_config(self.ws.root / CONFIG).sha256
        self.ws.write("data/manifests/freeze.json", json.dumps({"freeze_date": "2026-11-01", "analysis_config_sha256": sha}))

    def attempt(self, *extra: str, audit: Any = None) -> AnalysisError | TestAuditError:
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(cli, "load_inputs", side_effect=AssertionError("a prediction was read")))
            if audit is not None:
                stack.enter_context(mock.patch.object(cli, "require_test_audit", return_value=audit))
            with self.assertRaises((AnalysisError, TestAuditError)) as caught:
                cli.run(cli.build_parser().parse_args(self.args(*extra)))
        return caught.exception

    def test_each_gate_fails_first_and_in_order(self) -> None:
        self.write_config(draft=True)
        self.assertEqual(self.attempt().code, "test_not_allowed")
        self.assertEqual(self.attempt("--allow-test").code, "draft_config")
        self.write_config(draft=False)
        self.assertIn("audit", str(self.attempt("--allow-test")))  # the real spec 006 gate: no audit files
        self.assertEqual(self.attempt("--allow-test", audit=self.audit).code, "freeze_missing")
        self.freeze("0" * 64)
        self.assertEqual(self.attempt("--allow-test", audit=self.audit).code, "config_not_frozen")
        self.write_config(draft=False, samples=201)  # any edit after the freeze moves the hash
        self.freeze()
        self.write_config(draft=False)
        self.assertEqual(self.attempt("--allow-test", audit=self.audit).code, "config_not_frozen")

    def test_frozen_test_run_stamps_and_carries_the_duplicate_line(self) -> None:
        self.write_config(draft=False)
        self.freeze()
        with mock.patch.object(cli, "require_test_audit", return_value=self.audit):
            code, out, err = self.invoke("--allow-test")
        self.assertEqual((code, err), (0, ""), err)
        report = self.report()
        self.assertEqual(report["stamp"], "frozen_test")
        self.assertEqual(report["provenance"]["test_audit"]["content_sha256"], "c" * 64)
        self.assertIsNotNone(report["provenance"]["freeze_record_sha256"])
        self.assertTrue(report["provenance"]["command"].endswith("--allow-test"))
        self.assertNotIn("precision", report)
        headline = {(r["system"], r["contrast"]) for r in report["sensitivity"] if r["sensitivity"] == "primary_minus_dup"}
        for system in ("enc", "pipe"):
            for contrast in ("full_minus_none", "one_minus_none", "full_minus_one",
                             "full_minus_mismatched", "one_minus_mismatched_one"):
                self.assertIn((system, contrast), headline)
        self.assert_no_ids_or_text(out + err)


if __name__ == "__main__":
    unittest.main()
