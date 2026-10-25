"""Spec 006 T7/T8: the test-audit loader and test scoring gates, using invented data only."""

from __future__ import annotations

import hashlib
import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from src.data import split_audit as sa
from src.data.direct_dataset import CONDITIONS
from src.evaluation import stage1, stage2
from src.evaluation.test_audit import TestAuditError, load_test_audit, require_test_audit
from src.stage1 import runner
from src.stage1.config import load_config
from tests.test_interpretation import prediction
from tests.test_split_audit import AuditCorpus, row

PRIMARY = {"MUL9002_t02:direct", "MUL9002_t02:indirect"}
EXCLUDED = {"PMUL9001_t02:direct": "inspected:calibration_labels", "PMUL9001_t02:indirect": "inspected:calibration_labels",
            "SNG90003_t02:direct": "cross_split_duplicate_dialogue",
            "SNG90003_t02:indirect": "cross_split_duplicate_dialogue"}


class AuditedCorpus(AuditCorpus):
    """``AuditCorpus`` with its audit built, plus helpers to tamper with it."""

    def __init__(self, test: unittest.TestCase) -> None:
        super().__init__(test)
        self.audit()

    def require(self):  # type: ignore[no-untyped-def]
        return require_test_audit(self.paths.items, self.paths.dialogues, registry_path=self.paths.registry,
                                  audit_path=self.paths.audit, summary_path=self.paths.summary)

    def reseal(self, csv_text: str) -> None:
        """Replace the audit CSV and recompute both summary hashes, as a careful forger would."""
        data = csv_text.encode("utf-8")
        self.paths.audit.write_bytes(data)
        summary = self.summary()
        summary["audit_sha256"] = hashlib.sha256(data).hexdigest()
        summary["content_sha256"] = sa.audit_content_sha256(summary)
        self.paths.summary.write_bytes(sa.summary_bytes(summary))

    def scoring_args(self) -> list[str]:
        return ["--items", str(self.paths.items), "--dialogues", str(self.paths.dialogues),
                "--registry", str(self.paths.registry), "--audit", str(self.paths.audit)]


class LoadTestAuditTest(unittest.TestCase):
    def setUp(self) -> None:
        self.corpus = AuditedCorpus(self)

    def test_valid_audit_loads(self) -> None:
        audit = self.corpus.require()
        self.assertEqual(audit.primary_ids, PRIMARY)
        self.assertEqual(audit.excluded, EXCLUDED)
        self.assertEqual(audit.dup_ids, {"MUL9002_t02:direct"})
        self.assertEqual(audit.content_sha256, self.corpus.summary()["content_sha256"])

    def test_missing_audit_fails(self) -> None:
        self.corpus.paths.audit.unlink()
        with self.assertRaisesRegex(TestAuditError, "needs the spec 006 audit"):
            self.corpus.require()

    def test_stale_inputs_fail(self) -> None:
        for name, change in (("items_sha256", lambda: self.corpus.paths.items.write_bytes(
                                  self.corpus.paths.items.read_bytes() + b"\n")),
                             ("dialogues_sha256", lambda: self.corpus.paths.dialogues.write_bytes(
                                  self.corpus.paths.dialogues.read_bytes() + b"\n")),
                             ("registry_pre_freeze_sha256", lambda: self.corpus.write_registry(
                                  [row("PMUL9001.json", "levels_round1"), row("MUL9002.json", "manual",
                                                                              reason="viewed_text")]))):
            with self.subTest(name=name):
                corpus = AuditedCorpus(self)
                self.corpus = corpus
                change()
                with self.assertRaisesRegex(TestAuditError, f"stale test audit: {name}"):
                    corpus.require()

    def test_post_scoring_rows_keep_the_audit_current(self) -> None:
        self.corpus.write_registry([row("PMUL9001.json", "levels_round1"),
                                    row("MUL9002.json", "manual", reason="error_audit", phase="post_scoring")])
        self.assertEqual(self.corpus.require().primary_ids, PRIMARY)

    def test_tampering_breaks_a_hash(self) -> None:
        csv_text = self.corpus.paths.audit.read_text(encoding="utf-8")
        flipped = csv_text.replace("MUL9002.json,indirect,1,1,,", "MUL9002.json,indirect,1,0,inspected:viewed_text,")
        self.assertNotEqual(flipped, csv_text)
        self.corpus.paths.audit.write_text(flipped, encoding="utf-8", newline="")
        with self.assertRaisesRegex(TestAuditError, "audit_sha256"):
            self.corpus.require()
        corpus = AuditedCorpus(self)
        summary = corpus.summary()
        summary["primary"]["genuine"] += 1
        corpus.paths.summary.write_bytes(sa.summary_bytes(summary))
        with self.assertRaisesRegex(TestAuditError, "content hash"):
            corpus.require()

    def test_resealed_rows_are_still_validated(self) -> None:
        good = self.corpus.paths.audit.read_text(encoding="utf-8")
        primary_line = next(line for line in good.splitlines() if line.startswith("MUL9002_t02:indirect"))
        cases = {
            "primary and exclusion disagree": primary_line.replace(",1,,", ",0,,"),
            "malformed item": primary_line.replace("MUL9002_t02,", "=cmd,"),
            "malformed example": primary_line.replace("MUL9002_t02:indirect", "MUL9002_t02:target"),
            "not 0 or 1": primary_line.replace(",1,,", ",yes,,"),
            "wrong number of cells": primary_line + ",extra",
        }
        for expected, bad_line in cases.items():
            with self.subTest(expected=expected):
                self.corpus.reseal(good.replace(primary_line, bad_line))
                with self.assertRaisesRegex(TestAuditError, expected):
                    self.corpus.require()
        self.corpus.reseal(good + primary_line + "\n")
        with self.assertRaisesRegex(TestAuditError, "duplicate example_id|disagree with the summary"):
            self.corpus.require()
        self.corpus.reseal(good.replace(",1,,", ",0,inspected:made_up,", 1))
        with self.assertRaisesRegex(TestAuditError, "exclusion is unknown"):
            self.corpus.require()

    def test_wrong_schema_and_unreadable_summary_fail(self) -> None:
        summary = self.corpus.summary()
        summary["schema_version"] = "split-audit-v0"
        summary["content_sha256"] = sa.audit_content_sha256(summary)
        self.corpus.paths.summary.write_bytes(sa.summary_bytes(summary))
        with self.assertRaisesRegex(TestAuditError, "not a split-audit-v1"):
            self.corpus.require()
        self.corpus.paths.summary.write_text("{not json", encoding="utf-8")
        with self.assertRaisesRegex(TestAuditError, "unreadable"):
            self.corpus.require()

    def test_load_compares_with_the_given_hashes(self) -> None:
        recorded = self.corpus.summary()["inputs"]
        audit = load_test_audit(self.corpus.paths.audit, self.corpus.paths.summary,
                                items_sha256=recorded["items_sha256"], dialogues_sha256=recorded["dialogues_sha256"],
                                registry_sha256=recorded["registry_pre_freeze_sha256"])
        self.assertEqual(audit.primary_ids, PRIMARY)
        with self.assertRaises(TestAuditError):
            load_test_audit(self.corpus.paths.audit, self.corpus.paths.summary, items_sha256="0" * 64,
                            dialogues_sha256=recorded["dialogues_sha256"],
                            registry_sha256=recorded["registry_pre_freeze_sha256"])

    def test_coverage_and_prediction_filtering(self) -> None:
        audit = self.corpus.require()
        self.assertEqual(audit.drop_excluded([{"example_id": "PMUL9001_t02:direct"}, {"example_id": "MUL9002_t02:direct"},
                                              "not a row"]),
                         [{"example_id": "MUL9002_t02:direct"}, "not a row"])
        report = audit.report(2)
        self.assertEqual((report["primary_examples"], report["excluded_examples"], report["dup_exact_primary"]), (2, 4, 1))


def stage1_predictions(ids: list[str], conditions: tuple[str, ...] = CONDITIONS) -> str:
    return "".join(json.dumps({"example_id": i, "condition": c, "prediction": i.split(":")[1]}) + "\n"
                   for c in conditions for i in ids)


class Stage1TestScoringTest(unittest.TestCase):
    def setUp(self) -> None:
        self.corpus = AuditedCorpus(self)
        self.predictions = self.corpus.root / "predictions.jsonl"
        self.out = self.corpus.root / "metrics.json"

    def score(self, *extra: str, split: str = "test") -> int:
        # The spec 008 freeze gate has its own tests (test_freeze_gates); here it simply passes.
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), \
                mock.patch("src.data.freeze.require_freeze", return_value=mock.Mock(content_sha256="f" * 64)):
            return stage1.main(["--predictions", str(self.predictions), "--out", str(self.out), "--split", split,
                                "--bootstrap-samples", "20", *self.corpus.scoring_args(), *extra])

    def test_primary_examples_only_with_one_dup_line_per_contrast(self) -> None:
        self.predictions.write_text(stage1_predictions(sorted(PRIMARY | EXCLUDED.keys())), encoding="utf-8")
        self.assertEqual(self.score(), 0)
        report = json.loads(self.out.read_text(encoding="utf-8"))
        self.assertEqual((report["n_examples"], report["sets"]["genuine"], report["sets"]["mismatch"]), (2, 2, 2))
        for name, contrast in report["contrasts"].items():
            with self.subTest(contrast=name):
                self.assertEqual(contrast["n"], 2)
                self.assertEqual(contrast["primary_minus_dup"]["n"], 1)
                self.assertEqual("without_cue_donors" in contrast, contrast["set"] == "mismatch")
                self.assertNotIn("primary_minus_dup", contrast.get("without_cue_donors", {}))
        self.assertEqual(report["test_audit"]["excluded_by_reason"], {"cross_split_duplicate_dialogue": 2,
                                                                      "inspected:calibration_labels": 2})
        self.assertNotIn("SECRET", self.out.read_text(encoding="utf-8"))

    def test_predictions_for_primary_only_are_enough(self) -> None:
        self.predictions.write_text(stage1_predictions(sorted(PRIMARY)), encoding="utf-8")
        self.assertEqual(self.score(), 0)

    def test_missing_or_stale_audit_fails(self) -> None:
        self.predictions.write_text(stage1_predictions(sorted(PRIMARY)), encoding="utf-8")
        self.corpus.write_registry([row("PMUL9001.json", "levels_round1"), row("MUL9002.json", "levels_round3")])
        self.assertEqual(self.score(), 1)
        self.assertFalse(self.out.exists())
        self.assertEqual(self.score("--audit", str(self.corpus.root / "nope.csv")), 1)

    def test_dev_scoring_is_unchanged(self) -> None:
        self.predictions.write_text(stage1_predictions(["WOZ90004_t02:direct", "WOZ90004_t02:indirect"],
                                                       ("none", "one", "full")),  # no donor, no mismatch set
                                    encoding="utf-8")
        self.corpus.paths.audit.unlink()  # dev never reads the audit
        self.assertEqual(self.score(split="dev"), 0)
        report = json.loads(self.out.read_text(encoding="utf-8"))
        self.assertNotIn("test_audit", report)
        self.assertFalse(any("primary_minus_dup" in c for c in report["contrasts"].values()))


class RunnerTestSplitTest(unittest.TestCase):
    """A trainer evaluating on test checks the audit in ``prepare``, before any training."""

    def setUp(self) -> None:
        self.corpus = AuditedCorpus(self)
        paths = self.corpus.paths
        config = self.corpus.root / "run.toml"
        config.write_text(f'[run]\nname = "probe"\nkind = "tfidf"\nbootstrap_samples = 10\n'
                          f'[data]\ntrain_condition = "full"\neval_split = "test"\n'
                          f'items = "{paths.items.as_posix()}"\ndialogues = "{paths.dialogues.as_posix()}"\n'
                          f'[tfidf]\nuse_context = true\n', encoding="utf-8")
        self.config = load_config(config, allow_test=True)

    def audit_at(self, audit: Path):  # type: ignore[no-untyped-def]
        paths = self.corpus.paths
        return mock.patch.object(runner, "require_test_audit", lambda items, dialogues: require_test_audit(
            items, dialogues, registry_path=paths.registry, audit_path=audit, summary_path=paths.summary))

    def test_prepare_keeps_primary_examples(self) -> None:
        with self.audit_at(self.corpus.paths.audit):
            prepared = runner.prepare(self.config)
        self.assertEqual({e.example_id for e in prepared.eval}, PRIMARY)
        self.assertEqual(prepared.test_audit.dup_ids, {"MUL9002_t02:direct"})

    def test_prepare_fails_without_the_audit(self) -> None:
        with self.audit_at(self.corpus.root / "nope.csv"), self.assertRaises(TestAuditError):
            runner.prepare(self.config)


class Stage2TestScoringTest(unittest.TestCase):
    def setUp(self) -> None:
        self.corpus = AuditedCorpus(self)
        self.root = self.corpus.root

    def run_stage2(self, *argv: str) -> int:
        # The export guard keeps real text under the repo's ignored folders; this fixture is a temp dir.
        # The spec 008 freeze gate has its own tests (test_freeze_gates); here it simply passes.
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), \
                mock.patch.object(stage2.ip, "require_local_text_output"), \
                mock.patch.object(stage2, "require_freeze", return_value=mock.Mock(content_sha256="f" * 64)):
            return stage2.main([*argv, "--split", "test", "--allow-test", "--conditions", "none", "full",
                                *self.corpus.scoring_args()])

    def write(self, name: str, ids: list[str], *, indirect_only: bool = False) -> Path:
        path = self.root / name
        rows = [prediction(i, c, prediction=i.split(":")[1], category=None, slots={})
                for c in ("none", "full") for i in ids if not indirect_only or i.endswith(":indirect")]
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        return path

    def test_inputs_hold_primary_examples_only(self) -> None:
        out = self.root / "inputs.jsonl"
        self.assertEqual(self.run_stage2("inputs", "--out", str(out)), 0)
        exported = {json.loads(line)["example_id"] for line in out.read_text(encoding="utf-8").splitlines()}
        self.assertEqual(exported, PRIMARY)

    def test_score_uses_primary_denominators_and_one_dup_line(self) -> None:
        everything = sorted(PRIMARY | EXCLUDED.keys())
        routed, oracle = self.write("routed.jsonl", everything), self.write("oracle.jsonl", everything, indirect_only=True)
        out = self.root / "stage2.json"
        self.assertEqual(self.run_stage2("score", "--predictions", str(routed), "--oracle-predictions", str(oracle),
                                         "--out", str(out), "--bootstrap-samples", "20"), 0)
        report = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(report["sets"]["genuine"], 2)
        self.assertEqual(report["conditions"]["full"]["n"], 2)
        contrast = report["contrasts"]["full-none"]
        self.assertEqual(contrast["n"], 2)
        self.assertEqual(contrast["primary_minus_dup"]["n"], 1)
        self.assertEqual(report["test_audit"]["primary_examples"], 2)

    def test_missing_or_stale_audit_fails(self) -> None:
        out = self.root / "inputs.jsonl"
        self.corpus.paths.dialogues.write_bytes(self.corpus.paths.dialogues.read_bytes() + b"\n")
        self.assertEqual(self.run_stage2("inputs", "--out", str(out)), 1)
        self.assertFalse(out.exists())
        self.assertEqual(self.run_stage2("inputs", "--out", str(out), "--audit", str(self.root / "nope.csv")), 1)


if __name__ == "__main__":
    unittest.main()
