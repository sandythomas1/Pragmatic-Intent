"""Spec 006 split and prior-inspection audit, using invented IDs and data only."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.data import split_audit as sa

SPLITS = {"PMUL9001.json": "test", "MUL9002.json": "test", "SNG90003.json": "test", "WOZ90004.json": "dev",
          "SSNG9005.json": "train"}


def row(dialogue_id: str = "PMUL9001.json", source: str = "levels_round1", **overrides: str) -> dict[str, str]:
    values = {"dialogue_id": dialogue_id, "source": source,
              "reason": sa.SOURCE_REASONS.get(source, "viewed_text"), "inspector": "A1",
              "inspected_on": "2026-09-20", "phase": "pre_freeze", "registry_version": sa.REGISTRY_VERSION}
    values.update(overrides)
    return values


class CanonicalDialogueIdTest(unittest.TestCase):
    def test_bare_and_json_forms_are_the_same_dialogue(self) -> None:
        self.assertEqual(sa.canonical_dialogue_id("PMUL1762"), "PMUL1762.json")
        self.assertEqual(sa.canonical_dialogue_id("PMUL1762.json"), "PMUL1762.json")
        for raw in ("MUL9484", "SNG91699", "SSNG9123", "WOZ90000.json"):  # invented, not corpus IDs
            self.assertTrue(sa.canonical_dialogue_id(raw).endswith(".json"))

    def test_malformed_ids_are_rejected(self) -> None:
        for raw in ("", "../x", "PMUL1762.json;", "=cmd", "PMUL1762.json ", " PMUL1762", "pmul1762", "PMUL17",
                    "PMUL1762.JSON", "PMUL1762.json.json", "XYZ1234", "PMUL" + "1" * 200):
            with self.subTest(raw=raw[:20]), self.assertRaises(ValueError):
                sa.canonical_dialogue_id(raw)

    def test_non_string_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            sa.canonical_dialogue_id(1762)  # type: ignore[arg-type]

    def test_error_message_is_truncated(self) -> None:
        with self.assertRaises(ValueError) as caught:
            sa.canonical_dialogue_id("x" * 500)
        self.assertLess(len(str(caught.exception)), 80)


class ValidateRegistryTest(unittest.TestCase):
    def problems(self, *rows: dict[str, str]) -> list[str]:
        return sa.validate_registry(list(rows), SPLITS)

    def test_valid_rows_pass(self) -> None:
        self.assertEqual(self.problems(row(), row(source="fact_drift_review", inspector="claude"),
                                       row("MUL9002.json", "manual", reason="error_audit", phase="post_scoring")), [])

    def test_each_rule_is_named(self) -> None:
        cases = {
            "dev split": row("WOZ90004.json"),
            "train split": row("SSNG9005.json"),
            "not in the corpus": row("PMUL9999.json"),
            "must be written as": row("PMUL9001"),
            "malformed dialogue ID": row("=HYPERLINK(1)"),
            "source": row(source="round9"),
            "not allowed for source": row(reason="viewed_text"),
            "pseudonymous": row(inspector="Sandy Thomas"),
            "inspected_on": row(inspected_on="20/09/2026"),
            "phase": row(phase="frozen"),
            "registry_version": row(registry_version="inspected-v0"),
        }
        for expected, bad in cases.items():
            with self.subTest(rule=expected):
                problems = self.problems(bad)
                self.assertTrue(any(expected in problem for problem in problems), problems)

    def test_manual_rows_need_a_manual_reason(self) -> None:
        self.assertTrue(self.problems(row(source="manual", reason="calibration_labels")))
        self.assertTrue(self.problems(row(source="manual", reason="")))

    def test_duplicate_dialogue_and_source_is_rejected(self) -> None:
        problems = self.problems(row(), row(inspected_on="2026-09-21"))
        self.assertTrue(any("duplicate" in problem for problem in problems))

    def test_same_dialogue_from_two_sources_is_allowed(self) -> None:
        self.assertEqual(self.problems(row(), row(source="fact_drift_review", inspector="claude")), [])

    def test_wrong_columns_are_rejected(self) -> None:
        extra = dict(row(), notes="free text")
        missing = {key: value for key, value in row().items() if key != "phase"}
        self.assertTrue(self.problems(extra))
        self.assertTrue(self.problems(missing))

    def test_formula_leading_values_cannot_pass_validation(self) -> None:
        # Every committed field is a validated ID, enum or date, so formula prefixes never reach disk.
        for field in sa.REGISTRY_FIELDS:
            for prefix in ("=", "+", "-", "@"):
                with self.subTest(field=field, prefix=prefix):
                    self.assertTrue(self.problems(row(**{field: prefix + row()[field]})))


class RegistryIoTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "registry.csv"

    def test_round_trip_is_byte_identical_and_sorted(self) -> None:
        rows = [row("SNG90003.json", "claude_session", inspector="claude"),
                row("PMUL9001.json", "fact_drift_review", inspector="claude"), row("PMUL9001.json", "levels_round1")]
        sa.write_registry(self.path, rows, SPLITS)
        first = self.path.read_bytes()
        loaded = sa.load_registry(self.path, SPLITS)
        self.assertEqual([(r["dialogue_id"], r["source"]) for r in loaded],
                         [("PMUL9001.json", "levels_round1"), ("PMUL9001.json", "fact_drift_review"),
                          ("SNG90003.json", "claude_session")])
        sa.write_registry(self.path, loaded, SPLITS)
        self.assertEqual(self.path.read_bytes(), first)
        self.assertNotIn(b"\r\n", first)
        self.assertTrue(first.startswith(b"dialogue_id,source,"))

    def test_invalid_rows_never_reach_disk(self) -> None:
        with self.assertRaises(sa.RegistryError):
            sa.write_registry(self.path, [row("WOZ90004.json")], SPLITS)
        self.assertFalse(self.path.exists())

    def test_missing_file_is_empty(self) -> None:
        self.assertEqual(sa.load_registry(self.path, SPLITS), [])

    def test_bom_from_excel_is_accepted(self) -> None:
        sa.write_registry(self.path, [row()], SPLITS)
        self.path.write_bytes(b"\xef\xbb\xbf" + self.path.read_bytes())
        self.assertEqual(len(sa.load_registry(self.path, SPLITS)), 1)

    def test_bad_files_are_rejected(self) -> None:
        header = ",".join(sa.REGISTRY_FIELDS) + "\n"
        good = ",".join(row().values()) + "\n"
        cases = {
            "columns": "dialogue_id,source\nPMUL9001.json,levels_round1\n",
            "not UTF-8": None,
            "malformed CSV": header + '"PMUL9001.json' + good[13:],
            "dev split": header + good.replace("PMUL9001.json", "WOZ90004.json"),
            "columns do not match": header + good.strip() + ",extra\n",
        }
        for expected, content in cases.items():
            with self.subTest(case=expected):
                if content is None:
                    self.path.write_bytes(header.encode() + b"\xff\xfe\n")
                else:
                    self.path.write_text(content, encoding="utf-8", newline="")
                with self.assertRaises(sa.RegistryError) as caught:
                    sa.load_registry(self.path, SPLITS)
                self.assertIn(expected, str(caught.exception))

    def test_oversized_file_is_rejected_before_parsing(self) -> None:
        self.path.write_bytes(b"x" * (sa.MAX_REGISTRY_BYTES + 1))
        with self.assertRaises(sa.RegistryError) as caught:
            sa.load_registry(self.path, SPLITS)
        self.assertIn("larger than", str(caught.exception))


class DerivedViewsTest(unittest.TestCase):
    def test_pre_freeze_hash_ignores_post_scoring_rows(self) -> None:
        base = [row(), row("MUL9002.json", "fact_drift_review", inspector="claude")]
        post = row("SNG90003.json", "manual", reason="error_audit", phase="post_scoring")
        self.assertEqual(sa.pre_freeze_sha256(base), sa.pre_freeze_sha256([*base, post]))
        self.assertEqual(sa.pre_freeze_sha256(base), sa.pre_freeze_sha256(list(reversed(base))))

    def test_pre_freeze_hash_changes_with_any_pre_freeze_field(self) -> None:
        base = [row()]
        for field, value in (("inspected_on", "2026-09-21"), ("inspector", "A2"), ("dialogue_id", "MUL9002.json")):
            with self.subTest(field=field):
                self.assertNotEqual(sa.pre_freeze_sha256(base), sa.pre_freeze_sha256([row(**{field: value})]))

    def test_precedence_picks_the_earliest_source(self) -> None:
        rows = [row(source="fact_drift_review", inspector="claude"), row(source="levels_round1"),
                row("MUL9002.json", "claude_session", inspector="claude"),
                row("MUL9002.json", "manual", reason="viewed_text")]
        self.assertEqual(sa.exclusion_reasons(rows),
                         {"MUL9002.json": "session_output_unverified", "PMUL9001.json": "calibration_labels"})

    def test_post_scoring_rows_never_exclude(self) -> None:
        rows = [row("SNG90003.json", "manual", reason="error_audit", phase="post_scoring")]
        self.assertEqual(sa.exclusion_reasons(rows), {})

    def test_post_scoring_row_does_not_override_pre_freeze_precedence(self) -> None:
        rows = [row(source="fact_drift_review", inspector="claude"),
                row(source="levels_round1", phase="post_scoring")]
        self.assertEqual(sa.exclusion_reasons(rows), {"PMUL9001.json": "fact_drift_review_unrecorded"})

    def test_sources_and_reasons_are_consistent(self) -> None:
        self.assertEqual(set(sa.SOURCE_REASONS) | {"manual"}, set(sa.SOURCES))
        self.assertEqual(sa.SOURCES[0], "levels_round1")


LEVELS_HEADER = "item_id,dialogue_id,turn_index,variant,label_initial,label_final,fragment,annotator,rubric_version\n"
SENTINEL = "SECRETUTTERANCE please book it"


class Workspace:
    """A temporary repository root with an invented items.jsonl and inspection sources."""

    def __init__(self, test: unittest.TestCase) -> None:
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.registry = self.root / "data/annotations/inspected_test_dialogues.csv"
        items = [("PMUL9001_t02", "PMUL9001.json", "test"), ("MUL9002_t00", "MUL9002.json", "test"),
                 ("SNG90003_t04", "SNG90003.json", "test"), ("WOZ90004_t02", "WOZ90004.json", "dev"),
                 ("SSNG9005_t00", "SSNG9005.json", "train")]
        self.write("data/interim/direct/items.jsonl", "".join(
            json.dumps({"item_id": i, "dialogue_id": d, "split": s, "target_utterance": SENTINEL}) + "\n"
            for i, d, s in items))
        self.index = sa.load_corpus_index(self.root / "data/interim/direct/items.jsonl")

    def write(self, relative: str, content: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="")
        return path

    def levels(self, relative: str, *dialogues: str, annotator: str = "A1") -> Path:
        return self.write(relative, LEVELS_HEADER + "".join(
            f"r1-{n:02d},{d},2,target,L0,L0,0,{annotator},v2\n" for n, d in enumerate(dialogues, start=1)))

    def sources(self, fact_drift_sha: str | None = None, sheet_sha: str | None = None) -> tuple[sa.DerivedSource, ...]:
        drift = self.root / "drift.jsonl"
        sheet = self.root / "sheet_items.csv"
        return (
            sa.DerivedSource("levels_round1", Path("levels1.csv"), "levels", "2026-09-25", None, None),
            sa.DerivedSource("obsolete_round3_sheet", Path("sheet_items.csv"), "items_sheet", "2026-10-01", "claude",
                             sheet_sha or (sa.file_sha256(sheet) if sheet.exists() else "0" * 64)),
            sa.DerivedSource("fact_drift_review", Path("drift.jsonl"), "fact_drift", "2026-10-01", "claude",
                             fact_drift_sha or (sa.file_sha256(drift) if drift.exists() else "0" * 64)),
        )

    def standard_sources(self) -> tuple[sa.DerivedSource, ...]:
        self.levels("levels1.csv", "PMUL9001.json", "WOZ90004.json")
        self.write("sheet_items.csv", f"item_id,dialogue_id,turn_index,variant,utterance\nr3-01,MUL9002.json,0,target,{SENTINEL}\n")
        self.write("drift.jsonl", json.dumps({"item_id": "PMUL9001_t02", "slots": ["day"], "split": "test",
                                              "variant": "direct"}) + "\n"
                   + json.dumps({"item_id": "WOZ90004_t02", "slots": ["day"], "split": "dev", "variant": "direct"}) + "\n")
        return self.sources()

    def register(self, **kwargs: object) -> dict[str, int]:
        if "sources" not in kwargs:
            kwargs["sources"] = self.standard_sources()
        return sa.register(self.registry, self.index, root=self.root, **kwargs)  # type: ignore[arg-type]

    def rows(self) -> list[dict[str, str]]:
        return sa.load_registry(self.registry, self.index.dialogue_split)


class RegisterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.ws = Workspace(self)

    def test_derives_only_test_dialogues_with_fixed_reasons_and_dates(self) -> None:
        self.ws.register()
        got = {(r["dialogue_id"], r["source"], r["reason"], r["inspector"], r["inspected_on"], r["phase"])
               for r in self.ws.rows()}
        self.assertEqual(got, {
            ("PMUL9001.json", "levels_round1", "calibration_labels", "A1", "2026-09-25", "pre_freeze"),
            ("MUL9002.json", "obsolete_round3_sheet", "sealed_labels", "claude", "2026-10-01", "pre_freeze"),
            ("PMUL9001.json", "fact_drift_review", "fact_drift_review_unrecorded", "claude", "2026-10-01", "pre_freeze"),
        })

    def test_registry_is_text_free(self) -> None:
        self.ws.register()
        self.assertNotIn("SECRETUTTERANCE", self.ws.registry.read_text(encoding="utf-8"))

    def test_rerun_on_another_day_is_byte_identical(self) -> None:
        sources = self.ws.standard_sources()
        self.ws.register(sources=sources)
        first = self.ws.registry.read_bytes()
        with mock.patch.object(sa.datetime, "date", wraps=sa.datetime.date) as fake_date:
            fake_date.today.return_value = sa.datetime.date(2027, 1, 1)
            self.ws.register(sources=sources)
        self.assertEqual(self.ws.registry.read_bytes(), first)

    def test_changed_local_source_is_refused(self) -> None:
        sources = self.ws.standard_sources()
        self.ws.write("drift.jsonl", json.dumps({"item_id": "SNG90003_t04", "split": "test"}) + "\n")
        with self.assertRaises(sa.RegistryError) as caught:
            self.ws.register(sources=sources)
        self.assertIn("changed since inspection", str(caught.exception))
        self.assertFalse(self.ws.registry.exists())

    def test_missing_local_source_keeps_committed_rows(self) -> None:
        sources = self.ws.standard_sources()
        self.ws.register(sources=sources)
        before = self.ws.registry.read_bytes()
        (self.ws.root / "drift.jsonl").unlink()
        (self.ws.root / "sheet_items.csv").unlink()
        with self.assertLogs(sa.logger, "WARNING") as logs:
            self.ws.register(sources=sources)
        self.assertEqual(self.ws.registry.read_bytes(), before)
        self.assertTrue(any("missing" in line for line in logs.output))

    def test_committed_row_that_is_no_longer_derivable_is_an_error(self) -> None:
        self.ws.register()
        self.ws.levels("levels1.csv", "WOZ90004.json")  # PMUL9001 vanished from a committed source
        with self.assertRaises(sa.RegistryError) as caught:
            self.ws.register(sources=self.ws.sources())
        self.assertIn("no longer derivable", str(caught.exception))

    def test_changed_committed_row_is_an_error(self) -> None:
        self.ws.register()
        self.ws.levels("levels1.csv", "PMUL9001.json", annotator="A2")
        with self.assertRaises(sa.RegistryError) as caught:
            self.ws.register(sources=self.ws.sources())
        self.assertIn("never change", str(caught.exception))

    def test_unknown_or_malformed_fact_drift_item_is_an_error(self) -> None:
        self.ws.standard_sources()
        for line in ('{"item_id": "PMUL9999_t00"}', '["PMUL9001_t02"]', '{"item_id": ["PMUL9001_t02"]}', "{}"):
            with self.subTest(line=line):
                self.ws.write("drift.jsonl", line + "\n")
                with self.assertRaises(sa.RegistryError) as caught:
                    self.ws.register(sources=self.ws.sources())
                self.assertIn("not in items.jsonl", str(caught.exception))

    def test_malformed_dialogue_in_a_source_is_an_error(self) -> None:
        self.ws.standard_sources()
        self.ws.levels("levels1.csv", "=cmd")
        with self.assertRaises(sa.RegistryError):
            self.ws.register(sources=self.ws.sources())

    def test_manual_row_is_added_and_preserved(self) -> None:
        extra = [sa.manual_row("SNG90003", "viewed_text", "A1", "2026-10-20", None)]
        self.ws.register(extra=extra)
        self.ws.register()  # a later run without --add keeps it
        self.assertIn(("SNG90003.json", "manual", "viewed_text"),
                      {(r["dialogue_id"], r["source"], r["reason"]) for r in self.ws.rows()})

    def test_manual_row_needs_a_manual_reason(self) -> None:
        with self.assertRaises(sa.RegistryError):
            self.ws.register(extra=[sa.manual_row("SNG90003", "calibration_labels", "A1", "2026-10-20", None)])

    def test_after_the_freeze_new_pre_freeze_rows_are_refused(self) -> None:
        self.ws.register()
        late = sa.manual_row("SNG90003", "viewed_text", "A1", "2026-10-20", "2026-10-28")
        self.assertEqual(late["phase"], "pre_freeze")
        with self.assertRaises(sa.RegistryError) as caught:
            self.ws.register(freeze_date="2026-10-28", extra=[late])
        self.assertIn("freeze recorded on 2026-10-28", str(caught.exception))

    def test_after_the_freeze_post_scoring_rows_leave_the_pre_freeze_hash(self) -> None:
        self.ws.register()
        before = sa.pre_freeze_sha256(self.ws.rows())
        audit = sa.manual_row("SNG90003", "error_audit", "A1", "2026-11-15", "2026-10-28")
        self.assertEqual(audit["phase"], "post_scoring")
        self.ws.register(freeze_date="2026-10-28", extra=[audit])
        self.assertEqual(sa.pre_freeze_sha256(self.ws.rows()), before)
        self.assertEqual(sa.exclusion_reasons(self.ws.rows()).get("SNG90003.json"), None)

    def test_freeze_day_itself_is_post_scoring(self) -> None:
        self.assertEqual(sa.phase_for("2026-10-27", "2026-10-28"), "pre_freeze")
        self.assertEqual(sa.phase_for("2026-10-28", "2026-10-28"), "post_scoring")
        self.assertEqual(sa.phase_for("2026-12-01", None), "pre_freeze")

    def test_real_source_table_is_consistent(self) -> None:
        for source in sa.DERIVED_SOURCES:
            with self.subTest(source=source.code):
                self.assertIn(source.code, sa.SOURCE_REASONS)
                self.assertTrue(sa._is_iso_date(source.inspected_on))
                self.assertIn(source.kind, ("levels", "items_sheet", "fact_drift"))
                local = str(source.path).replace("\\", "/").startswith("data/interim/")
                self.assertEqual(source.sha256 is not None, local)
        self.assertNotIn("round2_items", " ".join(str(s.path) for s in sa.DERIVED_SOURCES))


class FreezeDateTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.file = Path(tmp.name) / "freeze.json"

    def test_flag_until_a_freeze_file_exists(self) -> None:
        self.assertIsNone(sa.resolve_freeze_date(None, self.file))
        self.assertEqual(sa.resolve_freeze_date("2026-10-28", self.file), "2026-10-28")
        self.file.write_text('{"freeze_date": "2026-10-30"}', encoding="utf-8")
        self.assertEqual(sa.resolve_freeze_date(None, self.file), "2026-10-30")
        with self.assertRaises(ValueError):
            sa.resolve_freeze_date("2026-10-28", self.file)

    def test_bad_dates_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            sa.resolve_freeze_date("28/10/2026", self.file)
        for content in ('{"freeze_date": 20261028}', '["2026-10-28"]', "{}"):
            with self.subTest(content=content):
                self.file.write_text(content, encoding="utf-8")
                with self.assertRaises(ValueError):
                    sa.resolve_freeze_date(None, self.file)


class ScanSheetsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.ws = Workspace(self)
        self.ws.register()
        self.registry = self.ws.rows()

    def scan(self, **kwargs: object) -> sa.ScanReport:
        return sa.scan_sheets(self.ws.root, self.registry, self.ws.index,
                              registry_path=Path("data/annotations/inspected_test_dialogues.csv"), **kwargs)  # type: ignore[arg-type]

    def test_registered_and_dev_only_sheets_pass(self) -> None:
        self.ws.write("data/interim/labeling/round1_items.csv",
                      f"item_id,dialogue_id,utterance\nr1-01,PMUL9001.json,{SENTINEL}\nr1-02,WOZ90004.json,{SENTINEL}\n")
        self.ws.write("data/interim/context/pilot1/form_A1.csv", "item_id,label\nd:WOZ90004:t02,\n")
        report = self.scan()
        self.assertEqual(report.failures, [])
        self.assertEqual(report.test_dialogues["data/interim/labeling/round1_items.csv"], 1)

    def test_unregistered_test_dialogue_fails_naming_file_and_id(self) -> None:
        self.ws.write("data/interim/auto_levels/x/key.csv", "row_id,item_id\n1,SNG90003_t04\n")
        report = self.scan()
        self.assertEqual(report.failures,
                         ["data/interim/auto_levels/x/key.csv: test dialogue SNG90003.json is not registered as pre_freeze"])

    def test_ids_are_found_inside_compound_values_and_text_files(self) -> None:
        self.ws.write("data/annotations/context_items.csv", "item_id,source_ref\nd:SNG90003:t04,SNG90003.json#4\n")
        self.ws.write("data/interim/literary/notes.jsonl", '{"see": "SNG90003"}\n')
        self.assertEqual(len(self.scan().failures), 2)

    def test_mul_inside_pmul_and_longer_numbers_do_not_match(self) -> None:
        self.ws.write("data/interim/labeling/x.csv", "a,b\nPMUL90021,XMUL9002\n")  # neither is MUL9002
        self.assertEqual(self.scan().failures, [])

    def test_blind_sheet_needs_its_key(self) -> None:
        self.ws.write("data/interim/auto_levels/y/sheet.csv", f"row_id,utterance\n1,{SENTINEL}\n")
        report = self.scan()
        self.assertEqual(len(report.failures), 1)
        self.assertIn("key.csv", report.failures[0])
        self.ws.write("data/interim/auto_levels/y/key.csv", "row_id,item_id\n1,WOZ90004_t02\n")
        self.assertEqual(self.scan().failures, [])

    def test_blind_sheet_key_can_be_its_spec_003_sheet_info(self) -> None:
        self.ws.write("data/interim/context/p/form_A1.csv", f"row_id,utterance\n1,{SENTINEL}\n")
        self.assertEqual(len(self.scan().failures), 1)
        self.ws.write("data/interim/context/p/form_A1_sheet_info.json",
                      json.dumps({"rows": [{"row_id": "1", "item_id": "SNG90003_t04"}]}))
        report = self.scan()
        self.assertEqual(report.failures, ["data/interim/context/p/form_A1_sheet_info.json: "
                                           "test dialogue SNG90003.json is not registered as pre_freeze"])

    def test_extra_cells_are_scanned_too(self) -> None:
        self.ws.write("data/interim/labeling/notes.csv", f"item_id,note\nWOZ90004_t02,{SENTINEL}\nr,a,SNG90003_t04\n")
        self.assertEqual(self.scan().failures,
                         ["data/interim/labeling/notes.csv: test dialogue SNG90003.json is not registered as pre_freeze"])

    def test_unparseable_csv_and_orphan_xlsx_fail(self) -> None:
        self.ws.write("data/interim/labeling/broken.csv", 'a,b\n"unterminated,1\n')
        (self.ws.root / "data/interim/labeling/round9_labels.xlsx").write_bytes(b"PK\x03\x04")
        failures = self.scan().failures
        self.assertTrue(any("broken.csv" in f and "malformed" in f for f in failures), failures)
        self.assertTrue(any("round9_labels.xlsx" in f for f in failures), failures)

    def test_xlsx_with_sibling_items_csv_is_skipped_and_logged(self) -> None:
        self.ws.write("data/interim/labeling/round1_items.csv", "item_id,dialogue_id\nr1-01,PMUL9001.json\n")
        (self.ws.root / "data/interim/labeling/round1_labels.xlsx").write_bytes(b"PK\x03\x04")
        report = self.scan()
        self.assertEqual(report.failures, [])
        self.assertTrue(any("round1_labels.xlsx" in s for s in report.skipped))

    def test_registry_file_itself_is_not_scanned(self) -> None:
        late = sa.manual_row("SNG90003", "error_audit", "A1", "2026-11-15", "2026-10-28")
        self.ws.register(freeze_date="2026-10-28", extra=[late])
        self.registry = self.ws.rows()
        self.assertEqual(self.scan(freeze_date="2026-10-28").failures, [])

    def test_post_scoring_sheets_need_a_row_of_either_phase(self) -> None:
        self.ws.write("data/interim/error_audit/sample.csv", "example_id\nSNG90003_t04:direct\n")
        self.assertIn("is not registered", self.scan().failures[0])
        self.ws.register(freeze_date="2026-10-28",
                         extra=[sa.manual_row("SNG90003", "error_audit", "A1", "2026-11-15", "2026-10-28")])
        self.registry = self.ws.rows()
        self.assertEqual(self.scan(freeze_date="2026-10-28").failures, [])

    def test_post_scoring_row_does_not_satisfy_a_pre_freeze_sheet(self) -> None:
        self.ws.register(freeze_date="2026-10-28",
                         extra=[sa.manual_row("SNG90003", "error_audit", "A1", "2026-11-15", "2026-10-28")])
        self.registry = self.ws.rows()
        path = self.ws.write("data/interim/labeling/old.csv", "dialogue_id\nSNG90003.json\n")
        os.utime(path, (0, sa.datetime.datetime(2026, 10, 2).timestamp()))
        self.assertEqual(len(self.scan(freeze_date="2026-10-28").failures), 1)

    def test_scan_output_holds_no_text(self) -> None:
        self.ws.write("data/interim/labeling/round1_items.csv", f"dialogue_id,utterance\nSNG90003.json,{SENTINEL}\n")
        report = self.scan()
        self.assertNotIn("SECRETUTTERANCE", repr(report))

    def test_missing_directories_are_fine(self) -> None:
        self.assertEqual(self.scan().files, 0)


class TranscriptScanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.ws = Workspace(self)
        self.logs = self.ws.root / "logs"
        self.logs.mkdir()

    def log(self, name: str, content: bytes) -> None:
        (self.logs / name).write_bytes(content)

    def test_reports_only_test_ids_in_canonical_form(self) -> None:
        secret = b"sk-ant-api03-SECRETKEY"
        self.log("a.jsonl", b'{"text": "PMUL9001 and WOZ90004.json ' + secret + b'"}\n{"x": "MUL9002.json"}\n')
        self.log("b.txt", b"SNG90003")  # not a .jsonl log
        tests, files = sa.scan_transcripts([self.logs], self.ws.index)
        self.assertEqual((tests, files), (["MUL9002.json", "PMUL9001.json"], 1))

    def test_cli_prints_ids_only(self) -> None:
        self.log("a.jsonl", f'{{"text": "PMUL9001 {SENTINEL} sk-ant-SECRETKEY"}}\n'.encode())
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "stdout", stdout), mock.patch.object(sys, "stderr", stderr), \
                self.assertLogs(sa.logger, "INFO") as logs:
            code = sa.main(["scan", "--items", str(self.ws.root / "data/interim/direct/items.jsonl"),
                            "--registry", str(self.ws.registry), "--transcripts", str(self.logs)])
        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue(), "PMUL9001.json\n")
        everything = stdout.getvalue() + stderr.getvalue() + "\n".join(logs.output)
        self.assertNotIn("SECRET", everything)

    def test_ids_split_across_chunks_are_found_exactly(self) -> None:
        with mock.patch.object(sa, "_CHUNK_BYTES", 64):
            for offset in range(0, 80):
                with self.subTest(offset=offset):
                    # SNG90003 straddles chunk boundaries at every offset; its 7-character prefix
                    # SNG9000 must never be reported, and neither may MUL9002 inside PMUL90021.
                    self.log("a.jsonl", b"x" * offset + b" SNG90003 " + b"y" * (100 - offset) + b" PMUL90021 \n")
                    tests, _ = sa.scan_transcripts([self.logs], self.ws.index)
                    self.assertEqual(tests, ["SNG90003.json"])

    def test_tiny_and_empty_files(self) -> None:
        self.log("a.jsonl", b"MUL9002")
        self.log("b.jsonl", b"")
        self.assertEqual(sa.scan_transcripts([self.logs], self.ws.index)[0], ["MUL9002.json"])

    def test_invalid_utf8_and_long_lines_do_not_crash(self) -> None:
        self.log("a.jsonl", b"\xff\xfe" * 10 + b"z" * (3 << 20) + b" PMUL9001 \xc3")
        self.assertEqual(sa.scan_transcripts([self.logs], self.ws.index)[0], ["PMUL9001.json"])

    @unittest.skipUnless(hasattr(os, "symlink"), "no symlinks")
    def test_symlinks_are_not_followed(self) -> None:
        outside = self.ws.root / "outside"
        outside.mkdir()
        (outside / "c.jsonl").write_bytes(b"PMUL9001")
        try:
            os.symlink(outside, self.logs / "link", target_is_directory=True)
            os.symlink(outside / "c.jsonl", self.logs / "d.jsonl")
        except OSError:
            self.skipTest("symlinks need privileges on this OS")
        self.assertEqual(sa.scan_transcripts([self.logs], self.ws.index), ([], 0))

    def test_missing_directory_is_an_error(self) -> None:
        with self.assertRaises(ValueError):
            sa.scan_transcripts([self.ws.root / "nope"], self.ws.index)

    def test_register_keeps_the_first_session_date(self) -> None:
        rows = sa.transcript_rows(["SNG90003.json"], [], "2026-10-20", None)
        merged, _ = sa.merge_rows([], rows, None)
        again = sa.transcript_rows(["SNG90003.json"], merged, "2026-10-25", None)
        self.assertEqual(again, [])
        self.assertEqual(merged[0]["inspected_on"], "2026-10-20")
        self.assertEqual(merged[0]["reason"], "session_output_unverified")

    def test_hits_after_the_freeze_are_post_scoring(self) -> None:
        rows = sa.transcript_rows(["SNG90003.json"], [], "2026-11-02", "2026-10-28")
        self.assertEqual(rows[0]["phase"], "post_scoring")

    def test_cli_register_adds_rows(self) -> None:
        self.log("a.jsonl", b"SNG90003\n")
        with mock.patch.object(sys, "stdout", io.StringIO()), self.assertLogs(sa.logger, "INFO"):
            code = sa.main(["scan", "--items", str(self.ws.root / "data/interim/direct/items.jsonl"),
                            "--registry", str(self.ws.registry), "--transcripts", str(self.logs),
                            "--register", "--on", "2026-10-20"])
        self.assertEqual(code, 0)
        self.assertEqual([(r["dialogue_id"], r["source"], r["inspected_on"]) for r in self.ws.rows()],
                         [("SNG90003.json", "claude_session", "2026-10-20")])


# --------------------------------------------------------------------------- check and audit (T5, T6)


class DupV1Test(unittest.TestCase):
    def test_case_punctuation_whitespace_and_compatibility_forms_collapse(self) -> None:
        key = sa.dup_v1("Find a hotel on Monday, please!")
        for variant in ("find a HOTEL on monday please", "  Find a hotel -- on Monday,please?! ",
                        "Ｆｉｎｄ a hotel on Monday please", "find_a hotel\ton monday please"):
            with self.subTest(variant=variant):
                self.assertEqual(sa.dup_v1(variant), key)
        self.assertEqual(sa.dup_v1("STRASSE"), sa.dup_v1("Straße"))

    def test_one_word_difference_stays_distinct(self) -> None:
        self.assertNotEqual(sa.dup_v1("Find a hotel on Monday"), sa.dup_v1("Find a hotel on Tuesday"))

    def test_punctuation_only_is_empty(self) -> None:
        self.assertEqual(sa.dup_v1(" ?!... "), "")


def record(item_id: str, split: str, donor: str | None = None) -> sa.SplitRecord:
    return sa.SplitRecord(item_id, item_id.split("_")[0] + ".json", split, donor)


class CheckSplitsTest(unittest.TestCase):
    TEST_LIST = {"PMUL9001.json", "MUL9002.json"}
    VAL_LIST = {"WOZ90004.json"}

    def check(self, records: list[sa.SplitRecord], turns: dict[str, list[str]] | None = None) -> sa.CheckReport:
        return sa.check_splits(records, self.TEST_LIST, self.VAL_LIST, turns or {})

    def clean(self) -> list[sa.SplitRecord]:
        return [record("PMUL9001_t02", "test", "MUL9002.json"), record("MUL9002_t02", "test", "PMUL9001.json"),
                record("WOZ90004_t02", "dev"), record("SSNG9005_t02", "train")]

    def test_clean_splits_pass(self) -> None:
        report = self.check(self.clean())
        self.assertTrue(report.ok)
        self.assertEqual(report.failures, dict.fromkeys(sa.CHECK_RULES, 0))
        self.assertEqual(report.test_dialogues, 2)

    def test_each_rule_is_named_with_its_first_id(self) -> None:
        cases = {
            "one_split_per_dialogue": [record("SSNG9005_t04", "dev")],  # also in train
            "test_in_test_list": [record("SNG90003_t02", "test")],
            "train_not_in_lists": [record("WOZ90004_t04", "train")],  # in valListFile
            "dev_in_val_list": [record("MUL9010_t02", "dev")],
            "donor_same_split": [record("PMUL9001_t04", "test", "SSNG9005.json")],
        }
        for rule, extra in cases.items():
            with self.subTest(rule=rule):
                report = self.check(self.clean() + extra)
                self.assertFalse(report.ok)
                self.assertGreater(report.failures[rule], 0)
                self.assertIn(rule, report.first)
        two_splits = self.check(self.clean() + cases["one_split_per_dialogue"])
        self.assertEqual(two_splits.first["disjoint_splits"], "SSNG9005.json")

    def test_every_failure_is_counted_and_the_first_is_sorted(self) -> None:
        report = self.check(self.clean() + [record("SNG90003_t02", "test"), record("MUL9011_t02", "test")])
        self.assertEqual(report.failures["test_in_test_list"], 2)
        self.assertEqual(report.first["test_in_test_list"], "MUL9011.json")

    def test_unknown_donor_is_a_cross_split_donor(self) -> None:
        report = self.check(self.clean() + [record("PMUL9001_t04", "test", "PMUL9999.json")])
        self.assertEqual(report.failures["donor_same_split"], 1)

    def test_duplicate_dialogues(self) -> None:
        turns = {"PMUL9001.json": ["I need a hotel.", "Book it for Monday!"],
                 "SSNG9005.json": ["i need a HOTEL", "book it for monday"],
                 "MUL9002.json": ["Hello"], "SNG90012.json": ["hello"],  # one user turn: ignored
                 "WOZ90004.json": ["A taxi please", "at noon"], "MUL9013.json": ["a taxi, please", "At noon."]}
        records = self.clean() + [record("SNG90012_t00", "train"), record("MUL9013_t00", "train")]
        report = self.check(records, turns)
        self.assertEqual(report.duplicate_test, {"PMUL9001.json": "train"})
        self.assertEqual(report.duplicate_dev_train, 1)
        self.assertTrue(report.ok)  # duplicates never fail the check

    def test_needs_decision_only_above_one_percent(self) -> None:
        def report_with(test_dialogues: int) -> sa.CheckReport:
            ids = [f"PMUL{9100 + n}" for n in range(test_dialogues)]
            records = [record(f"{d}_t02", "test") for d in ids] + [record("SSNG9005_t02", "train")]
            turns = {f"{ids[0]}.json": ["a hotel", "monday"], "SSNG9005.json": ["A hotel.", "Monday"]}
            return sa.check_splits(records, {f"{d}.json" for d in ids}, set(), turns)

        below, above = report_with(200), report_with(50)
        self.assertEqual((len(below.duplicate_test), below.needs_decision), (1, False))
        self.assertEqual((len(above.duplicate_test), above.needs_decision), (1, True))

    def test_split_records_validate_ids_and_splits(self) -> None:
        good = {"item_id": "PMUL9001_t02", "dialogue_id": "PMUL9001.json", "split": "test",
                "mismatch": {"donor_dialogue_id": "MUL9002.json"}}
        self.assertEqual(sa.split_records([good])[0].donor_dialogue_id, "MUL9002.json")
        for bad in ({**good, "dialogue_id": "../x"}, {**good, "split": "holdout"},
                    {**good, "mismatch": {"donor_dialogue_id": "=cmd"}}):
            with self.assertRaises(ValueError):
                sa.split_records([bad])

    def test_list_files_are_pinned_and_validated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "testListFile.txt"
            path.write_text("PMUL9001.json\nMUL9002.json\n", encoding="utf-8")
            self.assertEqual(sa.read_list_file(path, None), {"PMUL9001.json", "MUL9002.json"})
            self.assertEqual(sa.read_list_file(path, sa.file_sha256(path)), {"PMUL9001.json", "MUL9002.json"})
            with self.assertRaisesRegex(ValueError, "pinned"):
                sa.read_list_file(path, "0" * 64)
            path.write_text("PMUL9001.json\n=cmd\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "entry 2"):
                sa.read_list_file(path, None)


def corpus_item(item_id: str, split: str, turn: int, *, donor: str | None = None,
                direct: str = f"{SENTINEL} on monday.", indirect: str = f"{SENTINEL}, I wonder about monday.",
                acts: dict | None = None) -> dict:
    return {"item_id": item_id, "dialogue_id": item_id.split("_")[0] + ".json", "split": split, "turn_index": turn,
            "target_utterance": f"{SENTINEL} target", "direct_utterance": direct, "indirect_utterance": indirect,
            "user_acts": acts or {"Hotel-Inform": [["Day", "monday"], ["Name", "SECRETSLOTVALUE"]]},
            "quality_labels": None, "turn_domains": ["hotel"], "active_domains": ["hotel"],
            "mismatch": {"donor_dialogue_id": donor, "start": 0, "length": turn} if donor else None}


class AuditCorpus:
    """An invented repository: items, dialogues, list files, a spec 004 manifest and a registry.

    PMUL9001 is inspected (round 1); MUL9002 is clean but its donor is PMUL9001; SNG90003 repeats a
    train dialogue's user turns; WOZ90006 is a one-user-turn test dialogue. MUL9002's direct
    paraphrase equals a train utterance up to case and punctuation.
    """

    EXAMPLES = {"PMUL9001_t02:direct": 1, "PMUL9001_t02:indirect": 1, "MUL9002_t02:direct": 1,
                "MUL9002_t02:indirect": 1, "SNG90003_t02:direct": 0, "SNG90003_t02:indirect": 0}

    def __init__(self, test: unittest.TestCase) -> None:
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        self.test = test
        self.root = Path(tmp.name)
        self.items = [
            corpus_item("PMUL9001_t02", "test", 2, donor="MUL9002.json"),
            corpus_item("MUL9002_t00", "test", 0),
            corpus_item("MUL9002_t02", "test", 2, donor="PMUL9001.json", direct="Find me a HOTEL, for Monday!",
                        indirect=f"{SENTINEL} anything near the river"),
            corpus_item("SNG90003_t02", "test", 2, indirect="Find me a hotel for Tuesday"),
            corpus_item("WOZ90006_t00", "test", 0),
            corpus_item("WOZ90004_t02", "dev", 2),
            corpus_item("SSNG9005_t02", "train", 2, direct="find me a hotel for monday"),
            corpus_item("PMUL9008_t02", "train", 2, donor="SSNG9005.json"),
            corpus_item("MUL9007_t00", "train", 0, acts={"general-thank": [["none", "none"]]}),
        ]
        user_turns = {"PMUL9001": [f"{SENTINEL} one", "two"], "MUL9002": [f"{SENTINEL} three", "four"],
                      "SNG90003": ["I need a hotel.", f"{SENTINEL}!"], "SSNG9005": ["i need a HOTEL", SENTINEL.lower()],
                      "WOZ90006": ["Hello"], "MUL9007": ["hello"],
                      "WOZ90004": ["A taxi please", "at noon"], "PMUL9008": ["a taxi, please", "At noon."]}
        self.paths = sa.AuditPaths(
            items=self.root / "items.jsonl", dialogues=self.root / "dialogues.jsonl", multiwoz_dir=self.root / "mw",
            registry=self.root / "registry.csv", context_manifest=self.root / "contexts_test.csv",
            audit=self.root / "out/split_audit_test.csv", summary=self.root / "out/split_audit_test_summary.json")
        self.write_items()
        self.paths.dialogues.write_text("".join(json.dumps({"dialogue_id": f"{d}.json", "turns": [
            turn for text in texts for turn in ({"speaker": "user", "text": text, "domains": []},
                                                {"speaker": "system", "text": f"{SENTINEL} reply", "domains": []})]})
            + "\n" for d, texts in user_turns.items()), encoding="utf-8", newline="")
        self.paths.multiwoz_dir.mkdir()
        (self.paths.multiwoz_dir / "testListFile.txt").write_text(
            "PMUL9001.json\nMUL9002.json\nSNG90003.json\nWOZ90006.json\n", encoding="utf-8", newline="")
        (self.paths.multiwoz_dir / "valListFile.txt").write_text("WOZ90004.json\n", encoding="utf-8", newline="")
        self.write_manifest()
        self.write_registry([row("PMUL9001.json", "levels_round1")])

    def write_items(self) -> None:
        self.paths.items.write_text("".join(json.dumps(item) + "\n" for item in self.items),
                                    encoding="utf-8", newline="")

    def write_manifest(self, examples: dict[str, int] | None = None) -> None:
        data = ("example_id,mismatch_set\n" + "".join(f"{k},{v}\n" for k, v in sorted(
            (examples or self.EXAMPLES).items()))).encode("utf-8")
        self.paths.context_manifest.write_bytes(data)
        summary = {"manifest_sha256": hashlib.sha256(data).hexdigest(),
                   "inputs": {"items_sha256": sa.file_sha256(self.paths.items),
                              "dialogues_sha256": sa.file_sha256(self.paths.dialogues)}}
        self.paths.context_manifest.with_name("contexts_test_summary.json").write_text(json.dumps(summary),
                                                                                      encoding="utf-8")

    def write_registry(self, rows: list[dict[str, str]]) -> None:
        splits = {item["dialogue_id"]: item["split"] for item in self.items}
        sa.write_registry(self.paths.registry, rows, splits)

    def audit(self, verify: bool = False) -> int:
        with self.test.assertLogs(sa.logger, "INFO") as logs:
            code = sa.run_audit(self.paths, verify=verify, pinned=False)
        self.logs = "\n".join(logs.output)
        return code

    def rows(self) -> dict[str, dict[str, str]]:
        with self.paths.audit.open(encoding="utf-8", newline="") as handle:
            return {r["example_id"]: r for r in csv.DictReader(handle)}

    def summary(self) -> dict:
        return json.loads(self.paths.summary.read_text(encoding="utf-8"))


class RunCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.corpus = AuditCorpus(self)

    def test_fixture_corpus_passes_and_finds_duplicates(self) -> None:
        items = [json.loads(line) for line in self.corpus.paths.items.read_text(encoding="utf-8").splitlines()]
        report = sa.run_check(items, self.corpus.paths.dialogues, self.corpus.paths.multiwoz_dir, pinned=False)
        self.assertTrue(report.ok, report.failures)
        self.assertEqual(report.duplicate_test, {"SNG90003.json": "train"})  # WOZ90006 has one user turn
        self.assertEqual(report.duplicate_dev_train, 1)
        self.assertTrue(report.needs_decision)  # 1 of 4 test dialogues

    def test_cli_refuses_unpinned_list_files(self) -> None:
        with self.assertLogs(sa.logger, "INFO") as logs:
            code = sa.main(["check", "--items", str(self.corpus.paths.items), "--dialogues",
                            str(self.corpus.paths.dialogues), "--multiwoz-dir", str(self.corpus.paths.multiwoz_dir)])
        self.assertEqual(code, 1)
        self.assertIn("pinned", "\n".join(logs.output))

    def test_cli_exit_codes_with_matching_pins(self) -> None:
        mw = self.corpus.paths.multiwoz_dir
        pins = {split: (name, sa.file_sha256(mw / name)) for split, (name, _) in sa.LIST_FILES.items()}
        args = ["check", "--items", str(self.corpus.paths.items), "--dialogues", str(self.corpus.paths.dialogues),
                "--multiwoz-dir", str(mw)]
        with mock.patch.object(sa, "LIST_FILES", pins):
            with self.assertLogs(sa.logger, "INFO") as logs:
                self.assertEqual(sa.main(args), 0)
            self.assertIn("needs_decision", "\n".join(logs.output))
            self.assertNotIn("SECRET", "\n".join(logs.output))
            (mw / "valListFile.txt").write_text("", encoding="utf-8")
            pins["dev"] = ("valListFile.txt", sa.file_sha256(mw / "valListFile.txt"))
            with self.assertLogs(sa.logger, "INFO") as logs:
                self.assertEqual(sa.main(args), 1)
            self.assertIn("dev_in_val_list failed for 1 ID(s); first WOZ90004.json", "\n".join(logs.output))


class AuditTest(unittest.TestCase):
    def setUp(self) -> None:
        self.corpus = AuditCorpus(self)

    def test_inspected_dialogue_is_non_primary_everywhere(self) -> None:
        self.assertEqual(self.corpus.audit(), 0)
        rows = self.corpus.rows()
        self.assertEqual(set(rows), set(AuditCorpus.EXAMPLES))
        for variant in ("direct", "indirect"):
            inspected = rows[f"PMUL9001_t02:{variant}"]
            self.assertEqual((inspected["primary"], inspected["exclusion"], inspected["mismatch_set"]),
                             ("0", "inspected:calibration_labels", "1"))
            duplicate = rows[f"SNG90003_t02:{variant}"]
            self.assertEqual((duplicate["primary"], duplicate["exclusion"]), ("0", "cross_split_duplicate_dialogue"))
            self.assertEqual(rows[f"MUL9002_t02:{variant}"]["primary"], "1")

    def test_flags_never_change_primary(self) -> None:
        self.corpus.audit()
        rows = self.corpus.rows()
        flagged = rows["MUL9002_t02:direct"]
        self.assertEqual((flagged["dup_exact"], flagged["primary"], flagged["donor_inspected"]), ("1", "1", "1"))
        self.assertEqual(rows["MUL9002_t02:indirect"]["dup_exact"], "0")
        self.assertEqual(rows["SNG90003_t02:indirect"]["dup_exact"], "0")  # differs from train in one word
        self.assertEqual(rows["PMUL9001_t02:direct"]["donor_inspected"], "0")  # its donor is not inspected

    def test_summary_counts(self) -> None:
        self.corpus.audit()
        summary = self.corpus.summary()
        self.assertEqual(summary["test"], {"dialogues": 4, "items": 5, "genuine_examples": 6, "mismatch_examples": 4})
        self.assertEqual(summary["excluded"]["dialogues"], {"cross_split_duplicate_dialogue": 1,
                                                            "inspected:calibration_labels": 1})
        self.assertEqual(summary["excluded"]["items"], {"cross_split_duplicate_dialogue": 1,
                                                        "inspected:calibration_labels": 1})
        self.assertEqual(summary["excluded"]["examples"], {"cross_split_duplicate_dialogue": 2,
                                                           "inspected:calibration_labels": 2})
        self.assertEqual(summary["primary"], {"genuine": 2, "mismatch": 2})
        self.assertEqual(summary["dup_exact"]["overall"], {"flagged": 1, "n": 2, "rate": 0.5})
        self.assertEqual(summary["dup_exact"]["by_variant"]["direct"], {"flagged": 1, "n": 1, "rate": 1.0})
        self.assertEqual(sum(v["n"] for v in summary["dup_exact"]["by_rule_level"].values()), 2)
        self.assertEqual(summary["donor_inspected"], {"primary_mismatch_examples": 2})  # both MUL9002 paraphrases
        self.assertTrue(summary["needs_decision"])
        self.assertEqual(summary["cross_split_duplicates"]["test_dialogues"], 1)
        self.assertEqual(summary["content_sha256"], sa.audit_content_sha256(summary))
        self.assertEqual(summary["inputs"]["registry_pre_freeze_sha256"],
                         sa.pre_freeze_sha256([row("PMUL9001.json", "levels_round1")]))

    def test_build_is_byte_identical_and_verify_passes(self) -> None:
        self.corpus.audit()
        first = (self.corpus.paths.audit.read_bytes(), self.corpus.paths.summary.read_bytes())
        self.assertEqual(self.corpus.audit(verify=True), 0)
        self.corpus.audit()
        self.assertEqual((self.corpus.paths.audit.read_bytes(), self.corpus.paths.summary.read_bytes()), first)
        self.assertNotIn(b"\r\n", first[0] + first[1])

    def test_changed_pre_freeze_row_changes_the_content_hash(self) -> None:
        self.corpus.audit()
        before = self.corpus.summary()["content_sha256"]
        self.corpus.write_registry([row("PMUL9001.json", "levels_round1", inspected_on="2026-09-21")])
        self.assertEqual(self.corpus.audit(verify=True), 1)
        self.corpus.audit()
        self.assertNotEqual(self.corpus.summary()["content_sha256"], before)
        self.assertEqual(self.corpus.rows()["PMUL9001_t02:direct"]["primary"], "0")

    def test_one_byte_of_items_changes_the_content_hash(self) -> None:
        self.corpus.audit()
        before = self.corpus.summary()["content_sha256"]
        self.corpus.items[-1]["target_utterance"] += "x"
        self.corpus.write_items()
        with self.assertRaisesRegex(ValueError, "other items"):  # spec 004's manifest is now stale
            self.corpus.audit(verify=True)
        self.corpus.write_manifest()  # a rebuilt spec 004 manifest
        self.assertEqual(self.corpus.audit(verify=True), 1)
        self.corpus.audit()
        self.assertNotEqual(self.corpus.summary()["content_sha256"], before)

    def test_post_scoring_rows_are_disclosed_without_moving_anything(self) -> None:
        self.corpus.audit()
        csv_before, summary_before = self.corpus.paths.audit.read_bytes(), self.corpus.summary()
        self.corpus.write_registry([row("PMUL9001.json", "levels_round1"),
                                    row("MUL9002.json", "manual", reason="error_audit", phase="post_scoring",
                                        inspected_on="2026-11-20")])
        self.corpus.audit()
        summary = self.corpus.summary()
        self.assertEqual(self.corpus.paths.audit.read_bytes(), csv_before)
        self.assertEqual(summary["content_sha256"], summary_before["content_sha256"])
        self.assertEqual(summary["disclosure"], {"post_scoring_dialogues": 1})
        self.assertEqual(summary_before["disclosure"], {"post_scoring_dialogues": 0})

    def test_outputs_and_logs_hold_no_text(self) -> None:
        self.corpus.audit()
        outputs = self.corpus.paths.audit.read_text(encoding="utf-8") + self.corpus.paths.summary.read_text(
            encoding="utf-8") + self.corpus.logs
        for fragment in ("SECRET", "monday", "hotel", "taxi", "Hello", "reply"):
            self.assertNotIn(fragment.lower(), outputs.lower())

    def test_manifest_mismatches_fail_loudly(self) -> None:
        self.corpus.write_manifest({**AuditCorpus.EXAMPLES, "WOZ90006_t00:direct": 0})
        with self.assertRaisesRegex(ValueError, "1 missing, 0 extra"):
            self.corpus.audit()
        self.corpus.write_manifest({**AuditCorpus.EXAMPLES, "SNG90003_t02:direct": 1})
        with self.assertRaisesRegex(ValueError, "1 with another mismatch_set"):
            self.corpus.audit()
        self.corpus.write_manifest()
        self.corpus.paths.context_manifest.write_bytes(self.corpus.paths.context_manifest.read_bytes() + b"x")
        with self.assertRaisesRegex(ValueError, "manifest_sha256"):
            self.corpus.audit()

    def test_failed_split_check_blocks_the_audit(self) -> None:
        (self.corpus.paths.multiwoz_dir / "testListFile.txt").write_text("PMUL9001.json\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "split check failed"):
            self.corpus.audit()
        self.assertFalse(self.corpus.paths.audit.exists())

    def test_cli_audit_and_verify(self) -> None:
        paths = self.corpus.paths
        mw = paths.multiwoz_dir
        pins = {split: (name, sa.file_sha256(mw / name)) for split, (name, _) in sa.LIST_FILES.items()}
        args = ["audit", "--items", str(paths.items), "--dialogues", str(paths.dialogues), "--multiwoz-dir", str(mw),
                "--registry", str(paths.registry), "--context-manifest", str(paths.context_manifest),
                "--audit-dir", str(paths.audit.parent)]
        with mock.patch.object(sa, "LIST_FILES", pins), self.assertLogs(sa.logger, "INFO"):
            self.assertEqual(sa.main(args), 0)
            self.assertEqual(sa.main([*args, "--verify"]), 0)
            paths.audit.write_bytes(paths.audit.read_bytes().replace(b",1,1,", b",1,0,", 1))
            self.assertEqual(sa.main([*args, "--verify"]), 1)


if __name__ == "__main__":
    unittest.main()
