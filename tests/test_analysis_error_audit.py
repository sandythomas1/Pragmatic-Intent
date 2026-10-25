"""Error audit: gate, stratified draw, registration, sheet, export and report (spec 007 T12–T13)."""

from __future__ import annotations

import csv
import datetime
import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from src.analysis import __main__ as cli
from src.analysis import error_audit as ea
from src.analysis.config import load_config
from src.data import split_audit as sa
from tests.analysis_fixtures import analysis_config, write_stage2_grid
from tests.test_analysis_cli import CLI_FIXTURE_TEXT, CONFIG, GENUINE, INPUTS, CliTestCase
from tests.test_split_audit import row as registry_row

REGISTRY = "data/annotations/inspected_test_dialogues.csv"
TODAY = datetime.date(2026, 11, 20)


def dialogue_number(example) -> int:
    return int(example.dialogue_id[4:8]) - 9100


class ErrorAuditTestCase(CliTestCase):
    split = "test"

    def setUp(self) -> None:
        super().setUp()

        def wrong_under_full(e, condition, train, seed, oracle=False):
            d = dialogue_number(e)
            wrong = not oracle and condition == "full" and d <= 10 and (seed >= 2 or d % 2)
            return {"category": "travel"} if wrong else {}

        systems = self.inputs_systems()
        systems["pipe"] = {"stage2": write_stage2_grid(self.ws, self.evaluation, "pipe", GENUINE, (1, 2, 3),
                                                       wrong_under_full)}
        self.ws.inputs(systems, split="test", name=INPUTS)
        self.write_config(draft=False)
        self.sha = load_config(self.ws.root / CONFIG).sha256
        self.ws.write("data/manifests/freeze.json", json.dumps({"freeze_date": "2026-11-01",
                                                                "analysis_config_sha256": self.sha}))
        index = sa.load_corpus_index(self.items)
        sa.write_registry(self.ws.root / REGISTRY, [registry_row("PMUL9112.json", "manual", reason="viewed_text")],
                          index.dialogue_split)
        self.registry_before = (self.ws.root / REGISTRY).read_bytes()
        with mock.patch.object(cli, "require_test_audit", return_value=self.audit), \
                mock.patch.object(cli, "require_freeze", return_value=mock.Mock(content_sha256="e" * 64)), \
                mock.patch.object(cli, "check_frozen_runs"):  # spec 008 gates: tested in test_freeze_gates
            self.assertEqual(self.invoke("--allow-test")[0], 0)

    def sample(self, *, on: str = "2026-11-15", inspector: str = "A1", **paths: str) -> tuple[int, str, str]:
        argv = ["error-audit", "sample", "--on", on, "--inspector", inspector, "--inputs", INPUTS,
                "--config", CONFIG, "--root", str(self.ws.root)]
        for key, value in paths.items():
            argv += [f"--{key}", value]
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(cli, "require_test_audit", return_value=self.audit), \
                mock.patch.object(cli, "_today", return_value=TODAY), redirect_stdout(out), redirect_stderr(err):
            code = cli.main(argv)
        return code, out.getvalue(), err.getvalue()

    def sheet_dir(self) -> Path:
        return self.ws.root / ea.SHEET_DIR

    def assert_nothing_registered(self) -> None:
        self.assertEqual((self.ws.root / REGISTRY).read_bytes(), self.registry_before)
        self.assertEqual(list(self.sheet_dir().glob("*")) if self.sheet_dir().exists() else [], [])

    def registry(self) -> list[dict[str, str]]:
        return sa.load_registry(self.ws.root / REGISTRY, sa.load_corpus_index(self.items).dialogue_split)


class GateTest(ErrorAuditTestCase):
    """AC-007-14: each failure registers nothing."""

    def test_each_gate_failure_registers_nothing(self) -> None:
        dev_report = self.ws.write("outputs/analysis/dev/report.json", json.dumps({"stamp": "dev_diagnostic_not_a_finding",
                                                                                 "config": {"sha256": self.sha}}))
        other = self.ws.write("other.json", json.dumps({"stamp": "frozen_test", "config": {"sha256": "0" * 64}}))
        cases = [
            ("before freeze", dict(on="2026-10-31"), "before the freeze date"),
            ("after today", dict(on="2026-11-21"), "after today"),
            ("malformed date", dict(on="15/11/2026"), "YYYY-MM-DD"),
            ("bad inspector", dict(inspector="Sandy"), "annotator ID"),
            ("claude may not inspect test", dict(inspector="claude"), "annotator ID"),
            ("missing report", dict(report="outputs/analysis/test/none.json"), "does not exist"),
            ("non-frozen report", dict(report=dev_report), "not a frozen_test"),
            ("report under another config", dict(report=other), "another analysis config"),
        ]
        for name, options, message in cases:
            with self.subTest(name):
                code, out, err = self.sample(**options)
                self.assertEqual(code, 1)
                self.assertIn(message, err)
                self.assert_nothing_registered()
        (self.ws.root / "data/manifests/freeze.json").unlink()
        code, _, err = self.sample()
        self.assertEqual(code, 1)
        self.assertIn("freeze record is required", err)
        self.assert_nothing_registered()

    def test_there_is_no_freeze_date_override(self) -> None:
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            cli.build_parser().parse_args(["error-audit", "sample", "--on", "2026-11-15", "--inspector", "A1",
                                           "--inputs", INPUTS, "--freeze-date", "2026-10-01"])


class SampleTest(ErrorAuditTestCase):
    def test_valid_sample_registers_post_scoring_rows_then_writes_the_sheet(self) -> None:
        pre_freeze = sa.pre_freeze_sha256(self.registry())
        code, out, err = self.sample()
        self.assertEqual((code, err), (0, ""), err)
        summary = json.loads((self.sheet_dir() / ea.SUMMARY_NAME).read_text(encoding="utf-8"))
        strata = {s["level"]: (s["errors"], s["drawn"], s["shortfall"]) for s in summary["strata"]}
        self.assertEqual(strata, {"L0": (20, 15, 0), "L1": (10, 10, 5), "L2": (10, 10, 5), "L3": (0, 0, 15)})
        with (self.sheet_dir() / ea.SHEET_NAME).open(encoding="utf-8", newline="") as handle:
            sheet = list(csv.DictReader(handle))
        self.assertEqual(len(sheet), 35)
        self.assertEqual(tuple(sheet[0]), ea.SHEET_FIELDS)
        self.assertTrue(all(row["code"] == "" and row["gold_questionable"] == "" for row in sheet))
        for row in sheet:  # the lowest seed whose output was wrong
            expected = "1" if (int(row["dialogue_id"][4:8]) - 9100) % 2 else "2"
            self.assertEqual(row["seed_shown"], expected, row["dialogue_id"])
            self.assertEqual(row["predicted_category"], "travel")
        added = [r for r in self.registry() if r["reason"] == "error_audit"]
        self.assertEqual(sorted(r["dialogue_id"] for r in added), sorted({r["dialogue_id"] for r in sheet}))
        self.assertTrue(all((r["phase"], r["inspector"], r["inspected_on"]) == ("post_scoring", "A1", "2026-11-15")
                            for r in added))
        self.assertEqual(sa.pre_freeze_sha256(self.registry()), pre_freeze)  # the frozen set never moves
        self.assertNotIn("PMUL", out)
        for sentinel in CLI_FIXTURE_TEXT:
            self.assertNotIn(sentinel, out)
        self.assertIn("drawn L0 15/15, L1 10/15, L2 10/15, L3 0/15", out)

    def test_a_second_draw_is_refused(self) -> None:
        self.assertEqual(self.sample()[0], 0)
        registry = (self.ws.root / REGISTRY).read_bytes()
        code, _, err = self.sample()
        self.assertEqual(code, 1)
        self.assertIn("re-sample", err)
        self.assertEqual((self.ws.root / REGISTRY).read_bytes(), registry)

    def test_sheet_write_failures_leave_the_registry_byte_identical(self) -> None:
        for target in ("tmp", "replace"):
            with self.subTest(target):
                original_replace = os.replace

                def failing_replace(src, dst):
                    if str(dst).endswith(ea.SHEET_NAME):
                        raise OSError("disk full")
                    return original_replace(src, dst)

                patch = (mock.patch.object(ea, "sheet_bytes", side_effect=OSError("disk full")) if target == "tmp"
                         else mock.patch.object(ea.os, "replace", side_effect=failing_replace))
                with patch:
                    code, _, err = self.sample()
                self.assertEqual(code, 1)
                self.assertIn("disk full", err)
                self.assert_nothing_registered()


class DrawTest(unittest.TestCase):
    def test_same_seed_same_sample_and_short_strata_taken_whole(self) -> None:
        config = analysis_config()
        levels = {f"e{i:03d}": ("L0", "L1", "L2", "L3")[i % 4] for i in range(80)}
        levels.update({f"x{i}": "L3" for i in range(3)})
        errors = sorted(i for i in levels if not i.startswith("e") or levels[i] != "L3")
        first, strata = ea.draw(errors, levels, config)
        self.assertEqual(ea.draw(errors, levels, config), (first, strata))
        self.assertEqual([s["drawn"] for s in strata], [15, 15, 15, 3])
        self.assertEqual(strata[3]["shortfall"], 12)
        shuffled = list(reversed(errors))
        self.assertEqual(ea.draw(shuffled, levels, config)[0], first)  # IDs are sorted before drawing


class ExportTest(ErrorAuditTestCase):
    """AC-007-15."""

    def setUp(self) -> None:
        super().setUp()
        self.assertEqual(self.sample()[0], 0)
        self.sheet_path = self.sheet_dir() / ea.SHEET_NAME
        with self.sheet_path.open(encoding="utf-8", newline="") as handle:
            self.rows = list(csv.DictReader(handle))

    def coded(self) -> list[dict[str, str]]:
        return [{**row, "code": ea.ERROR_CODES[i % len(ea.ERROR_CODES)], "gold_questionable": "yes" if i == 0 else ""}
                for i, row in enumerate(self.rows)]

    def write(self, rows: list[dict[str, str]]) -> None:
        self.sheet_path.write_bytes(ea.sheet_bytes(rows))

    def export(self) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["error-audit", "export", "--root", str(self.ws.root)])
        return code, out.getvalue(), err.getvalue()

    def test_invalid_sheets_are_rejected_with_named_errors(self) -> None:
        good = self.coded()
        cases = {
            "uncoded_row": [{**good[0], "code": ""}, *good[1:]],
            "unknown_code": [{**good[0], "code": "misread"}, *good[1:]],
            "over_inference is not a code": [{**good[0], "code": "over_inference"}, *good[1:]],
            "bad_flag": [{**good[0], "gold_questionable": "maybe"}, *good[1:]],
            "added row": [*good, {**good[0], "example_id": "PMUL9111_t02:direct"}],
            "removed row": good[1:],
            "duplicated row": [*good, good[0]],
            "locked_column_edited": [{**good[0], "predicted_category": "booking"}, *good[1:]],
            "formula_cell": [{**good[0], "code": "=HYPERLINK(1)"}, *good[1:]],
        }
        for name, rows in cases.items():
            with self.subTest(name):
                self.write(rows)
                code, _, err = self.export()
                self.assertEqual(code, 1)
                self.assertNotIn("PMUL", err)
                self.assertFalse((self.ws.root / ea.CODES_PATH).exists())

    def test_valid_sheet_gives_a_text_free_codes_file_the_scan_accepts(self) -> None:
        self.write(self.coded())
        code, out, err = self.export()
        self.assertEqual((code, err), (0, ""))
        text = (self.ws.root / ea.CODES_PATH).read_text(encoding="utf-8")
        rows = list(csv.DictReader(io.StringIO(text)))
        self.assertEqual(tuple(rows[0]), ea.CODES_FIELDS)
        self.assertEqual(len(rows), 35)
        for sentinel in CLI_FIXTURE_TEXT:
            self.assertNotIn(sentinel, text)
        index = sa.load_corpus_index(self.items)
        scan = sa.scan_sheets(self.ws.root, self.registry(), index, registry_path=Path(REGISTRY))
        self.assertEqual(scan.failures, [])
        self.assertIn("results/error_audit/codes.csv", scan.test_dialogues)
        # Without the post_scoring rows, the committed codes file fails the scan.
        bare = [r for r in self.registry() if r["reason"] != "error_audit"]
        self.assertTrue(any("results/error_audit/codes.csv" in f for f in
                            sa.scan_sheets(self.ws.root, bare, index, registry_path=Path(REGISTRY)).failures))

    def test_report_counts_codes_by_level(self) -> None:
        self.write(self.coded())
        self.assertEqual(self.export()[0], 0)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(cli.main(["error-audit", "report", "--root", str(self.ws.root)]), 0)
        counts = json.loads((self.ws.root / "results/error_audit/summary.json").read_text(encoding="utf-8"))
        self.assertEqual(counts["n"], 35)
        self.assertEqual(sum(sum(level.values()) for level in counts["counts"].values()), 35)
        self.assertEqual(sum(counts["counts"]["L0"].values()), 15)
        self.assertEqual(counts["counts"]["L3"], {code: 0 for code in ea.ERROR_CODES})
        self.assertEqual(counts["gold_questionable"], 1)
        markdown = (self.ws.root / "results/error_audit/summary.md").read_text(encoding="utf-8")
        self.assertIn("| L3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 15 |", markdown)
        self.assertNotIn("PMUL", markdown + json.dumps(counts) + out.getvalue())


class ScanLocationTest(unittest.TestCase):
    def test_results_error_audit_is_a_post_scoring_location(self) -> None:
        self.assertIn(Path("results/error_audit"), sa.POST_SCORING_SCAN_DIRS)
        self.assertNotIn(Path("results/error_audit"), sa.PRE_FREEZE_SCAN_DIRS)


if __name__ == "__main__":
    unittest.main()
