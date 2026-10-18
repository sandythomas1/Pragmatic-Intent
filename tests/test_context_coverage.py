"""Tests for ``coverage`` (spec 003 T13, FR13, FR14, AC-003-12). Invented fixtures only."""

from __future__ import annotations

import io
import json
import unittest
from collections.abc import Callable
from unittest import mock

from src.annotation import context as ctx
from src.annotation import context_coverage as cov
from src.annotation import context_passes as cp
from src.annotation import context_schema as cs
from src.annotation.levels import read_csv, write_csv
from tests.test_context_corrections import CorrectionCase
from tests.test_context_sealed_passes import dialogue_labels, literary_labels

Labels = dict[str, str]


def section(report: str, annotator: str) -> str:
    """The report section for one annotator."""
    start = report.index(f"== {annotator} ==")
    end = report.find("\n== ", start + 1)
    return report[start : end if end != -1 else len(report)]


def table(text: str, title: str) -> dict[str, dict[str, int]]:
    """Parse one rendered table: row label → column → count."""
    lines = text.splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith(title))
    columns = lines[start + 1].split()
    parsed: dict[str, dict[str, int]] = {}
    for line in lines[start + 2 :]:
        if not line.strip():
            break
        tokens = line.split()
        label = " ".join(tokens[: -len(columns)])
        parsed[label] = dict(zip(columns, map(int, tokens[-len(columns) :])))
    return parsed


class CoverageCase(CorrectionCase):
    """A1 (the literary screener) through all three passes; A2 through all three, reading turns as inform."""

    def setUp(self) -> None:
        super().setUp()
        self.seal_context()
        self.run_pass("reveal", "A1", lambda entry: {"future_dependence": "conflicts"})
        self.seal_form("A2")
        self.run_pass("context", "A2", self.a2_context, "--taxonomy", "ctx-tax-v0")
        self.run_pass("reveal", "A2", lambda entry: {"future_dependence": "none"})

    @staticmethod
    def a2_context(entry: dict) -> Labels:
        if entry["stratum"] == "literary":
            return literary_labels()
        return {"function": "inform", "evidence": "", "confidence": "probable"}

    def run_pass(self, pass_name: str, annotator: str, labels: Callable[[dict], Labels], *extra: str) -> None:
        paths = self.pass_paths(pass_name, annotator)
        self.assertEqual(self.cli("sheet", "--pass", pass_name, "--batch", "pilot1", "--annotator", annotator, "--seed", "3", *extra), 0)
        entries = {entry["row_id"]: entry for entry in json.loads(paths.snapshot.read_text(encoding="utf-8"))["rows"]}
        rows = read_csv(paths.sheet)
        for row in rows:
            row.update(labels(entries[row["row_id"]]))
        write_csv(paths.sheet, cp.SHEET_FIELDS[pass_name], rows, excel=True)
        self.assertEqual(self.cli("export", "--pass", pass_name, "--batch", "pilot1", "--annotator", annotator), 0)

    def report(self) -> str:
        return ctx.coverage(self.dirs, "pilot1")


class CoverageTableTests(CoverageCase):
    def test_every_form_by_function_cell_is_printed_including_zeros(self) -> None:
        cells = table(section(self.report(), "A1"), "form by function")
        self.assertEqual(list(cells), list(cs.FORM_LABELS))
        for counts in cells.values():
            self.assertEqual(list(counts), list(cs.FUNCTIONS))
        self.assertEqual(cells["INF"]["request"], 7)
        self.assertEqual(cells["L0"], dict.fromkeys(cs.FUNCTIONS, 0))

    def test_annotators_are_reported_separately_never_pooled(self) -> None:
        report = self.report()
        a1 = table(section(report, "A1"), "stratum by function")
        a2 = table(section(report, "A2"), "stratum by function")
        self.assertEqual((a1["dialogue"]["request"], a1["dialogue"]["inform"]), (5, 0))
        self.assertEqual((a2["dialogue"]["request"], a2["dialogue"]["inform"]), (0, 5))
        self.assertNotIn("== all", report.lower())

    def test_request_type_is_derived_and_inf_is_never_absent(self) -> None:
        a1 = table(section(self.report(), "A1"), "form by request type")
        self.assertEqual(a1["INF"]["form_unknown"], 7)
        self.assertEqual(a1["INF"]["none"], 0)
        a2 = table(section(self.report(), "A2"), "form by request type")
        self.assertEqual((a2["INF"]["none"], a2["INF"]["form_unknown"]), (5, 2))

    def test_intents_and_slots_list_unused_cells_as_zero(self) -> None:
        a1 = section(self.report(), "A1")
        intents = table(a1, "intent by stratum")
        self.assertEqual(intents["ctx-tax-v0 find_hotel"]["dialogue"], 5)
        self.assertEqual(intents["ctx-tax-v0 book_taxi"], {"dialogue": 0, "literary": 0})
        self.assertIn("ctx-tax-v0 out_of_taxonomy", intents)
        slots = table(a1, "slots per intent")
        self.assertEqual(slots["ctx-tax-v0 find_hotel.area*"], {"stated": 5, "?": 0, "absent": 0})
        self.assertEqual(slots["ctx-tax-v0 find_hotel.price"], {"stated": 0, "?": 0, "absent": 5})

    def test_reveal_tables(self) -> None:
        report = self.report()
        self.assertEqual(table(section(report, "A1"), "needs_adjudication")["rows"], {"true": 7, "false": 0})
        self.assertEqual(table(section(report, "A2"), "future dependence")["rows"]["none"], 7)
        self.assertEqual(table(section(report, "A1"), "confidence")["rows"], {"certain": 5, "probable": 2, "uncertain": 0})


class ExposureTests(CoverageCase):
    def test_screener_annotators_literary_items_are_exposed_in_every_pass(self) -> None:
        exposure = table(section(self.report(), "A1"), "prior_exposure")
        for pass_name in cs.PASSES:
            self.assertEqual(exposure[pass_name], {"true": 2, "false": 5}, pass_name)

    def test_a_non_screener_is_never_exposed(self) -> None:
        exposure = table(section(self.report(), "A2"), "prior_exposure")
        for pass_name in cs.PASSES:
            self.assertEqual(exposure[pass_name], {"true": 0, "false": 7}, pass_name)


class SupersededTests(CoverageCase):
    def test_rows_built_on_a_corrected_form_row_are_counted(self) -> None:
        self.assertEqual(self.prepare("form"), 0)
        self.edit("form", form="L2")
        self.assertEqual(self.apply("form"), 0)
        a1 = section(self.report(), "A1")
        self.assertEqual(table(a1, "built_on_superseded")["context"], {"true": 1, "false": 6})
        self.assertEqual(table(a1, "built_on_superseded")["reveal"], {"true": 0, "false": 7})
        self.assertIn("superseded rows: 1", a1)
        self.assertEqual(table(a1, "form by function")["L2"]["request"], 1)
        self.assertEqual(table(section(self.report(), "A2"), "built_on_superseded")["context"], {"true": 0, "false": 7})


class CoverageFailureTests(CoverageCase):
    def test_refuses_data_that_fails_validate(self) -> None:
        path = self.pass_paths("reveal").committed
        rows = read_csv(path)
        rows[0]["future_dependence"] = "none"
        write_csv(path, list(rows[0]), rows)
        with self.assertRaises(ctx.ValidationFailed):
            self.report()
        self.assertEqual(self.cli("coverage", "--batch", "pilot1"), 1)

    def test_unknown_batch(self) -> None:
        with self.assertRaises(cp.PassError):
            ctx.coverage(self.dirs, "pilot9")
        with mock.patch("sys.stderr", new_callable=io.StringIO), self.assertRaises(SystemExit):
            self.cli("coverage", "--batch", "../x")

    def test_cli_prints_the_report(self) -> None:
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(self.cli("coverage", "--batch", "pilot1"), 0)
        self.assertIn("== A1 ==", out.getvalue())
        self.assertIn("== A2 ==", out.getvalue())


class TableRenderTests(unittest.TestCase):
    def test_render_prints_zero_cells_and_aligns(self) -> None:
        lines = cov.Table("t", ["a", "long row"], ["x", "yy"], {("a", "x"): 3}).render()
        self.assertEqual(lines[0], "t")
        self.assertEqual(len({len(line) for line in lines[1:]}), 1)
        self.assertEqual(lines[2].split(), ["a", "3", "0"])
        self.assertEqual(lines[3].split(), ["long", "row", "0", "0"])

    def test_no_labels_yet(self) -> None:
        report = cov.report("pilot1", {"d:X:t02": "dialogue"}, {}, {}, None)
        self.assertIn("No annotator has exported labels", report)


if __name__ == "__main__":
    unittest.main()
