"""Paper tables from the committed test tables (spec 001 FR-12, AC-12). Synthetic fixtures only."""

from __future__ import annotations

import contextlib
import io
import itertools
import tempfile
import unittest
from pathlib import Path

from src.analysis import paper_tables as pt
from src.analysis.files import AnalysisError
from src.analysis.report import csv_bytes

PROVENANCE = "report.json#provenance (config 0123456789ab)"
STATS = {"point": 0.25, "ci_low": 0.2, "ci_high": 0.3, "p": 0.04, "p_holm": 0.08, "examples": 1200,
         "dialogues": 300, "status": "ok", "provenance": PROVENANCE}
LEVELS_ALL = ("overall", *pt.LEVELS)


def fixture_tables() -> dict[str, list[dict[str, object]]]:
    """The smallest set of rows every builder needs, all with the same statistics."""
    systems = sorted({(system, line, endpoint) for system, line, endpoint in pt.OVERALL_ROWS}
                     | {("hybrid", "matched", "request_interpretation"), ("hybrid", "matched", "stage1_correct")})
    return {
        "h1_rates": [{"system": s, "line": ln, "endpoint": e, "condition": c, "level": lv, **STATS}
                     for (s, ln, e), c, lv in itertools.product(systems, pt.CONDITIONS, LEVELS_ALL)],
        "h2_benefits": [{"system": "hybrid", "line": "matched", "endpoint": "request_interpretation",
                         "contrast": "full_minus_none", "level": lv, **STATS} for lv in LEVELS_ALL]
                       + [{"system": "hybrid", "line": "matched", "endpoint": "request_interpretation",
                           "contrast": c, "level": "overall", **STATS, "point": -0.014}
                          for c in ("one_minus_none", "full_minus_one")],
        "mismatch_controls": [{"system": s, "line": "test_time", "endpoint": e, "contrast": "full_minus_mismatched",
                               "level": "overall", **STATS} for s, _, e in pt.OVERALL_ROWS],
        "primary_test": [{"system": "hybrid", "line": "matched", "endpoint": "request_interpretation",
                          "quadratic_point": 0.01, "quadratic_ci_low": -0.02, "quadratic_ci_high": 0.04, **STATS,
                          "point": -0.0048}],
        "holm": [{"name": name, "endpoint": endpoint, **STATS} for name, endpoint in (
            ("h1-trend", "request_interpretation"), ("h2-detection-trend", "stage1_correct"),
            ("h4-detection-vs-oracle", ""), ("full-minus-mismatched", "request_interpretation"),
            ("h3-deberta-v3-large", "stage1_correct"), ("h3-qwen2.5-7b-instruct", "request_interpretation"))],
        "h4_rates": [{"system": "hybrid", "line": "matched", "condition": c, "level": "overall", "measure": m, **STATS}
                     for c, (m, _) in itertools.product(pt.CONDITIONS, pt.H4_MEASURES)],
        "sensitivity": [{"system": "hybrid", "line": "matched", "endpoint": "request_interpretation",
                         "contrast": "full_minus_none", "statistic": "primary_linear_trend",
                         "sensitivity": "primary_minus_dup", **STATS},
                        {"system": "hybrid", "line": "test_time", "endpoint": "request_interpretation",
                         "contrast": "full_minus_mismatched", "statistic": "overall_benefit",
                         "sensitivity": "without_cue_donors", **STATS}],
        "transfer": [{"system": "qwen2.5-7b-instruct", "gpt_family": "false", "n": 194, "request_recall": 0.031,
                      "value_accuracy": 0.608, "end_to_end": 0.021, "invalid_outputs": 0,
                      "data_kind": "llm_generated_transfer"}],
    }


def write_tables(directory: Path, tables: dict[str, list[dict[str, object]]]) -> None:
    for name, rows in tables.items():
        columns = list(dict.fromkeys(key for row in rows for key in row))
        (directory / f"{name}.csv").write_bytes(csv_bytes(columns, rows))


class FormattingTest(unittest.TestCase):
    def test_negative_numbers_use_a_true_minus_sign(self) -> None:
        self.assertEqual(pt.num("-0.0048"), "$-$0.005")

    def test_rounding_to_zero_never_prints_negative_zero(self) -> None:
        self.assertEqual(pt.num("-0.0001"), "0.000")
        self.assertEqual(pt.num("-0.0001", signed=True), "0.000")

    def test_signed_numbers_show_a_plus(self) -> None:
        self.assertEqual(pt.num("0.033", signed=True), "+0.033")

    def test_an_empty_cell_is_a_dash(self) -> None:
        self.assertEqual(pt.num(""), "--")
        self.assertEqual(pt.p_value(""), "--")

    def test_non_numbers_and_non_finite_values_fail(self) -> None:
        for bad in ("abc", "nan", "inf", "-inf"):
            with self.subTest(bad=bad), self.assertRaises(AnalysisError) as caught:
                pt.num(bad)
            self.assertEqual(caught.exception.code, "not_a_number")

    def test_small_p_values_are_bounded_not_printed_as_zero(self) -> None:
        self.assertEqual(pt.p_value("0.0001"), "$<$0.001")
        self.assertEqual(pt.p_value("0.0078"), "0.008")

    def test_a_flagged_statistic_gets_a_dagger(self) -> None:
        self.assertEqual(pt.flagged({"status": "sparse"}, "0.1"), "0.1" + pt.FLAG)
        self.assertEqual(pt.flagged({"status": "ok"}, "0.1"), "0.1")

    def test_unknown_systems_fail_rather_than_leak_csv_text(self) -> None:
        with self.assertRaises(AnalysisError) as caught:
            pt.system_label("\\input{/etc/passwd}")
        self.assertEqual(caught.exception.code, "unknown_system")

    def test_counts_must_be_whole_numbers(self) -> None:
        self.assertEqual(pt._count("2137"), "2{,}137")
        with self.assertRaises(AnalysisError):
            pt._count("12.5")


class LoadSourceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_a_missing_column_is_named(self) -> None:
        (self.dir / "t.csv").write_bytes(csv_bytes(["system"], [{"system": "hybrid"}]))
        with self.assertRaises(AnalysisError) as caught:
            pt.load_source(self.dir, "t", ("system", "point"))
        self.assertEqual(caught.exception.code, "missing_column")

    def test_two_configs_in_one_table_fail(self) -> None:
        rows = [{"point": 1, "provenance": PROVENANCE},
                {"point": 2, "provenance": "report.json#provenance (config ffffffffffff)"}]
        (self.dir / "t.csv").write_bytes(csv_bytes(["point", "provenance"], rows))
        with self.assertRaises(AnalysisError) as caught:
            pt.load_source(self.dir, "t", ("point",))
        self.assertEqual(caught.exception.code, "mixed_config")

    def test_non_utf8_fails_with_a_named_error(self) -> None:
        (self.dir / "t.csv").write_bytes(b"point\n\xff\xfe\n")
        with self.assertRaises(AnalysisError) as caught:
            pt.load_source(self.dir, "t", ("point",))
        self.assertEqual(caught.exception.code, "invalid_csv")

    def test_find_needs_exactly_one_row(self) -> None:
        rows = [{"system": "a", "point": 1}, {"system": "a", "point": 2}]
        (self.dir / "t.csv").write_bytes(csv_bytes(["system", "point"], rows))
        source = pt.load_source(self.dir, "t", ("system",))
        with self.assertRaises(AnalysisError) as caught:
            source.find(system="a")
        self.assertEqual(caught.exception.code, "ambiguous_row")
        with self.assertRaises(AnalysisError) as caught:
            source.find(system="b")
        self.assertEqual(caught.exception.code, "missing_row")

    def test_the_source_records_its_hash_and_config(self) -> None:
        (self.dir / "t.csv").write_bytes(csv_bytes(["point", "provenance"], [{"point": 1, "provenance": PROVENANCE}]))
        source = pt.load_source(self.dir, "t", ("point",))
        self.assertEqual(source.config, "0123456789ab")
        self.assertEqual(len(source.sha256), 64)


class BuildTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tables = Path(self.tmp.name) / "tables"
        self.out = Path(self.tmp.name) / "out"
        self.tables.mkdir()
        self.data = fixture_tables()
        write_tables(self.tables, self.data)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def fragments(self) -> dict[str, pt.Fragment]:
        return {f.name: f for f in pt.build(self.tables)}

    def test_every_fragment_is_built(self) -> None:
        self.assertEqual(set(self.fragments()), {"overall", "confirmatory", "levels", "stages", "transfer", "numbers"})

    def test_the_confirmatory_table_leads_with_the_primary_contrast(self) -> None:
        body = self.fragments()["confirmatory"].body
        self.assertLess(body.index("Linear contrast & $-$0.005 & [0.200, 0.300] & 0.040"), body.index("H1:"))
        self.assertIn("H3: DeBERTa-v3-large $-$ hybrid (detection)", body)
        self.assertIn("0.080", body)  # the Holm-adjusted p, not the raw one

    def test_an_unknown_holm_member_fails(self) -> None:
        self.data["holm"].append({"name": "surprise", "endpoint": "stage1_correct", **STATS})
        write_tables(self.tables, self.data)
        with self.assertRaises(AnalysisError) as caught:
            pt.build(self.tables)
        self.assertEqual(caught.exception.code, "unknown_family_member")

    def test_a_missing_level_fails_instead_of_printing_a_gap(self) -> None:
        self.data["h2_benefits"] = [r for r in self.data["h2_benefits"] if r["level"] != "L3"]
        write_tables(self.tables, self.data)
        with self.assertRaises(AnalysisError) as caught:
            pt.build(self.tables)
        self.assertEqual(caught.exception.code, "missing_row")

    def test_a_sparse_statistic_is_flagged_in_the_table(self) -> None:
        for row in self.data["h2_benefits"]:
            if row["level"] == "L3":
                row["status"] = "sparse"
        write_tables(self.tables, self.data)
        line = next(ln for ln in self.fragments()["levels"].body.splitlines() if ln.startswith("L3 &"))
        self.assertIn(pt.FLAG, line)

    def test_transfer_rows_must_be_labelled_llm_generated(self) -> None:
        self.data["transfer"][0]["data_kind"] = "human_authored"
        write_tables(self.tables, self.data)
        with self.assertRaises(AnalysisError) as caught:
            pt.build(self.tables)
        self.assertEqual(caught.exception.code, "transfer_label")

    def test_numbers_are_macros_with_the_config_hash(self) -> None:
        body = self.fragments()["numbers"].body
        self.assertIn("\\newcommand{\\AnalysisConfig}{0123456789ab}", body)
        self.assertIn("\\newcommand{\\PrimaryExamples}{1{,}200}", body)
        self.assertIn("\\newcommand{\\HybridInterpMismatchedOne}{0.250}", body)

    def test_overall_contrasts_h4_and_the_cue_free_control_have_macros(self) -> None:
        body = self.fragments()["numbers"].body
        self.assertIn("\\newcommand{\\OneNoneEst}{$-$0.014}", body)
        self.assertIn("\\newcommand{\\FullOneCI}{[0.200, 0.300]}", body)
        self.assertIn("\\newcommand{\\FullNoneEst}{+0.250}", body)
        self.assertIn("\\newcommand{\\HfourP}{0.080}", body)
        self.assertIn("\\newcommand{\\CueFreeEst}{+0.250}", body)

    def test_a_missing_overall_contrast_fails_by_name(self) -> None:
        self.data["h2_benefits"] = [r for r in self.data["h2_benefits"] if r["contrast"] != "full_minus_one"]
        write_tables(self.tables, self.data)
        with self.assertRaises(AnalysisError) as caught:
            self.fragments()
        self.assertEqual(caught.exception.code, "missing_row")

    def test_tables_with_different_configs_fail(self) -> None:
        self.data["transfer"][0]["provenance"] = "report.json#provenance (config ffffffffffff)"
        write_tables(self.tables, self.data)
        with self.assertRaises(AnalysisError) as caught:
            pt.build(self.tables)
        self.assertEqual(caught.exception.code, "mixed_config")


class WriteTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tables = Path(self.tmp.name) / "tables"
        self.out = Path(self.tmp.name) / "out"
        self.tables.mkdir()
        write_tables(self.tables, fixture_tables())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_main(self, *argv: str) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = pt.main(list(argv))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_each_fragment_names_its_sources_and_their_hashes(self) -> None:
        code, _, _ = self.run_main("--tables", str(self.tables), "--out", str(self.out))
        self.assertEqual(code, 0)
        text = (self.out / "levels.tex").read_text(encoding="utf-8")
        self.assertIn("h1_rates.csv sha256=", text)
        self.assertIn("h2_benefits.csv sha256=", text)
        self.assertIn("% Analysis config: 0123456789ab", text)
        self.assertIn(pt.COMMAND, text)
        self.assertTrue((self.out / "provenance.tex").is_file())

    def test_output_is_byte_identical_across_runs(self) -> None:
        self.run_main("--tables", str(self.tables), "--out", str(self.out))
        first = {p.name: p.read_bytes() for p in self.out.iterdir()}
        self.run_main("--tables", str(self.tables), "--out", str(self.out))
        self.assertEqual(first, {p.name: p.read_bytes() for p in self.out.iterdir()})

    def test_nothing_is_written_if_any_fragment_carries_a_dialogue_id(self) -> None:
        fragments = pt.build(self.tables)
        leaked = [*fragments, pt.Fragment("leak", (), "PMUL1234\n")]
        with self.assertRaises(AnalysisError) as caught:
            pt.write(leaked, self.out, "tables")
        self.assertEqual(caught.exception.code, "id_in_table")
        self.assertFalse(self.out.exists())

    def test_an_error_exits_1_with_a_named_message(self) -> None:
        (self.tables / "holm.csv").unlink()
        code, _, err = self.run_main("--tables", str(self.tables), "--out", str(self.out))
        self.assertEqual(code, 1)
        self.assertIn("not_a_file", err)

    def test_the_output_directory_cannot_be_the_tables_directory(self) -> None:
        code, _, _ = self.run_main("--tables", str(self.tables), "--out", str(self.tables))
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
