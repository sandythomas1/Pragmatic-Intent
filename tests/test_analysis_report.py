"""Paper tables, figure data and the transfer table (spec 007 T10)."""

from __future__ import annotations

import csv
import io
import json
import unittest
from pathlib import Path
from unittest import mock

from src.analysis import __main__ as cli
from src.analysis.files import AnalysisError
from src.analysis.report import FIGURE_COLUMNS, TRANSFER_LABEL, csv_bytes, escape_cell, transfer_rows, write_tables
from tests.analysis_fixtures import write_stage2_grid
from tests.test_analysis_cli import CLI_FIXTURE_TEXT, CliTestCase

TRANSFER = {"scorer_version": "transfer-v1", "data_kind": "llm_generated_transfer", "model_family": "gpt-4o",
            "gpt_family": True, "split": "validation", "n": 10, "request_recall": 0.9, "value_accuracy": 0.5,
            "end_to_end": 0.45, "invalid_outputs": 0}


def read_csv(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))


class DevTablesTest(CliTestCase):
    def tables(self) -> Path:
        return self.ws.root / "outputs/analysis/dev"

    def test_primary_row_is_labelled_and_shows_the_quadratic_beside_it(self) -> None:
        self.assertEqual(self.invoke()[0], 0)
        (row,) = read_csv(self.tables() / "primary_test.csv")
        self.assertEqual(row["label"], "L2 − L0 benefit difference (linear contrast)")
        self.assertEqual(row["weights"], "-1; 0; 1")
        for column in ("quadratic_point", "quadratic_ci_low", "quadratic_ci_high", "examples", "dialogues", "provenance"):
            self.assertNotEqual(row[column], "", column)
        markdown = (self.tables() / "primary_test.md").read_text(encoding="utf-8")
        self.assertIn("dev_diagnostic_not_a_finding", markdown)

    def test_every_row_names_its_denominators_and_provenance(self) -> None:
        self.invoke()
        for name in ("h1_rates", "h2_benefits", "h2_trends", "holm", "sensitivity", "mismatch_controls"):
            rows = read_csv(self.tables() / f"{name}.csv")
            self.assertTrue(rows, name)
            for row in rows:
                self.assertIn("report.json#provenance", row["provenance"], name)
                self.assertIn("examples", row)
                self.assertIn("dialogues", row)

    def test_figure_data_has_one_row_per_system_line_endpoint_and_level(self) -> None:
        self.invoke()
        rows = read_csv(self.tables() / "figure_data.csv")
        self.assertEqual(tuple(rows[0]), FIGURE_COLUMNS)
        self.assertEqual({r["contrast"] for r in rows}, {"full_minus_none"})
        self.assertNotIn("overall", {r["level"] for r in rows})
        pipe_l2 = [r for r in rows if (r["system"], r["line"], r["endpoint"], r["level"])
                   == ("pipe", "matched", "request_interpretation", "L2")]
        self.assertEqual(len(pipe_l2), 1)
        self.assertGreater(float(pipe_l2[0]["point"]), 0)

    def test_transfer_table_is_separate_labelled_and_flags_gpt(self) -> None:
        self.ws.write("outputs/transfer/llm.json", json.dumps(TRANSFER))
        systems = self.inputs_systems()
        systems["llm"] = {"stage2": write_stage2_grid(self.ws, self.evaluation, "llm", ["untrained"], [0]),
                          "transfer": "outputs/transfer/llm.json"}
        self.ws.inputs(systems, name="configs/analysis/inputs.toml")
        code, _, err = self.invoke()
        self.assertEqual((code, err), (0, ""))
        (row,) = read_csv(self.tables() / "transfer.csv")
        self.assertEqual((row["system"], row["gpt_family"], row["label"]), ("llm", "true", TRANSFER_LABEL))
        self.assertIn("LLM-generated", (self.tables() / "transfer.md").read_text(encoding="utf-8"))
        self.assertNotIn("llm", {r["system"] for r in read_csv(self.tables() / "h2_benefits.csv")
                                 if r.get("endpoint") == "transfer"})

    def test_a_main_benchmark_report_given_as_transfer_input_fails(self) -> None:
        self.ws.write("outputs/transfer/llm.json", json.dumps({**TRANSFER, "scorer_version": "stage2-v1"}))
        systems = self.inputs_systems()
        systems["llm"] = {"stage2": write_stage2_grid(self.ws, self.evaluation, "llm", ["untrained"], [0]),
                          "transfer": "outputs/transfer/llm.json"}
        self.ws.inputs(systems, name="configs/analysis/inputs.toml")
        with self.assertRaises(AnalysisError) as caught:
            cli.run(cli.build_parser().parse_args(self.args()))
        self.assertEqual(caught.exception.code, "not_a_transfer_report")
        with self.assertRaises(AnalysisError):
            transfer_rows({"llm": b'{"scorer_version": "transfer-v1", "data_kind": "llm_generated_transfer"}'})


class CommittedTablesTest(CliTestCase):
    """AC-007-13: committed test tables hold no IDs or text and are byte-identical across runs."""

    split = "test"

    def test_test_tables_go_to_results_without_ids_or_text_and_repeat_exactly(self) -> None:
        self.write_config(draft=False)
        from src.analysis.config import load_config
        sha = load_config(self.ws.root / "configs/analysis/analysis-v1.toml").sha256
        self.ws.write("data/manifests/freeze.json", json.dumps({"freeze_date": "2026-11-01", "analysis_config_sha256": sha}))
        with mock.patch.object(cli, "require_test_audit", return_value=self.audit):
            self.assertEqual(self.invoke("--allow-test")[0], 0)
            directory = self.ws.root / "results/analysis/test"
            first = {p.name: p.read_bytes() for p in sorted(directory.iterdir())}
            self.assertEqual(self.invoke("--allow-test")[0], 0)
        second = {p.name: p.read_bytes() for p in sorted(directory.iterdir())}
        self.assertEqual(first, second)
        self.assertIn("primary_test.csv", first)
        self.assertNotIn("precision.csv", first)
        for name, data in first.items():
            text = data.decode("utf-8")
            self.assertNotIn("PMUL", text, name)
            for sentinel in CLI_FIXTURE_TEXT:
                self.assertNotIn(sentinel, text, name)
        self.assertFalse((self.ws.root / "results/analysis/test/report.json").exists())  # full JSON stays ignored


class CellSafetyTest(unittest.TestCase):
    def test_formula_leading_text_is_escaped_and_numbers_are_not(self) -> None:
        self.assertEqual(escape_cell("=HYPERLINK(1)"), "'=HYPERLINK(1)")
        self.assertEqual(escape_cell("+1"), "'+1")
        self.assertEqual(escape_cell("@sum"), "'@sum")
        self.assertEqual(escape_cell(-0.25), "-0.25")
        self.assertEqual(escape_cell(None), "")
        self.assertEqual(escape_cell(True), "true")
        self.assertEqual(escape_cell(["-1", 0]), "'-1; 0")
        rows = list(csv.reader(io.StringIO(csv_bytes(["a", "b"], [{"a": "-cmd", "b": -1.5}]).decode("utf-8"))))
        self.assertEqual(rows[1], ["'-cmd", "-1.5"])

    def test_committed_tables_refuse_anything_that_looks_like_an_id(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            built = {"x": ("t", ("system",), [{"system": "PMUL1234"}], [])}
            with self.assertRaises(AnalysisError) as caught:
                write_tables(Path(tmp), built, committed=True)
            self.assertEqual(caught.exception.code, "id_in_table")
            self.assertEqual(list(Path(tmp).iterdir()), [])
            write_tables(Path(tmp), built, committed=False)  # dev tables are local diagnostics


if __name__ == "__main__":
    unittest.main()
