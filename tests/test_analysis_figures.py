"""Context-by-level figure (spec 007 T11). Rendering tests skip cleanly without matplotlib."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from src.analysis.figures import main, read_figure_data, render
from src.analysis.files import AnalysisError
from src.analysis.report import FIGURE_COLUMNS, csv_bytes

HAS_MATPLOTLIB = importlib.util.find_spec("matplotlib") is not None


def figure_rows() -> list[dict[str, object]]:
    rows = []
    for system, line in (("pipe", "matched"), ("enc", "matched"), ("enc", "test_time")):
        for endpoint in (("request_interpretation", "stage1_correct") if system == "pipe" else ("stage1_correct",)):
            for i, level in enumerate(("L0", "L1", "L2", "L3")):
                point = 0.05 * i
                rows.append({"system": system, "line": line, "endpoint": endpoint, "contrast": "full_minus_none",
                             "level": level, "point": point, "ci_low": point - 0.04, "ci_high": point + 0.04,
                             "examples": 100, "dialogues": 40, "status": "sparse" if level == "L3" else "ok"})
    return rows


class FigureDataTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def write(self, rows, columns=FIGURE_COLUMNS) -> Path:
        path = self.root / "figure_data.csv"
        path.write_bytes(csv_bytes(columns, rows))
        return path

    def test_valid_data_parses_numbers(self) -> None:
        rows = read_figure_data(self.write(figure_rows()))
        self.assertEqual(len(rows), 16)
        self.assertIsInstance(rows[0]["point"], float)

    def test_malformed_data_fails_with_named_errors(self) -> None:
        good = figure_rows()
        cases = {
            "missing_column": self.write(good, [c for c in FIGURE_COLUMNS if c != "ci_high"]),
        }
        for code, path in cases.items():
            with self.subTest(code), self.assertRaises(AnalysisError) as caught:
                read_figure_data(path)
            self.assertEqual(caught.exception.code, code)
        for code, change in (("bad_number", {"ci_low": "about 0.1"}), ("bad_number", {"ci_high": "inf"}),
                             ("bad_number", {"ci_low": ""}), ("unknown_value", {"level": "L9"}),
                             ("unknown_value", {"endpoint": "=cmd"})):
            with self.subTest(code=code, change=change), self.assertRaises(AnalysisError) as caught:
                read_figure_data(self.write([{**good[0], **change}]))
            self.assertEqual(caught.exception.code, code)

    def test_empty_statistic_rows_are_allowed(self) -> None:
        row = {**figure_rows()[0], "point": None, "ci_low": None, "ci_high": None, "status": "empty"}
        self.assertIsNone(read_figure_data(self.write([row]))[0]["point"])


@unittest.skipUnless(HAS_MATPLOTLIB, "matplotlib is not installed (uv group 'figures')")
class RenderTest(FigureDataTest):
    def test_two_renders_give_byte_identical_svg(self) -> None:
        rows = read_figure_data(self.write(figure_rows()))
        first = render(rows, self.root / "a" / "figure")
        second = render(rows, self.root / "b" / "figure")
        self.assertEqual([p.suffix for p in first], [".svg", ".pdf"])
        self.assertEqual(first[0].read_bytes(), second[0].read_bytes())
        svg = first[0].read_text(encoding="utf-8")
        self.assertIn("pipe · matched", svg)
        self.assertIn("detection (Stage 1)", svg)
        self.assertNotIn("<dc:date>", svg)

    def test_cli_writes_both_formats_and_refuses_to_overwrite_its_input(self) -> None:
        data = self.write(figure_rows())
        self.assertEqual(main(["--data", str(data), "--out", str(self.root / "out" / "fig")]), 0)
        self.assertTrue((self.root / "out" / "fig.pdf").exists())
        self.assertEqual(main(["--data", str(data), "--out", str(self.root / "figure_data")]), 1)


if __name__ == "__main__":
    unittest.main()
