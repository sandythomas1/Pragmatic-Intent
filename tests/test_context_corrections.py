"""Tests for logged corrections (spec 003 T11). Invented fixtures only."""

from __future__ import annotations

import io
import json
import unittest
import unittest.mock

from src.annotation import context as ctx
from src.annotation import context_passes as cp
from src.annotation import context_schema as cs
from src.annotation.levels import read_csv, write_csv
from tests import context_fixtures as fx
from tests.test_context_sealed_passes import SealedCase


class CorrectionCase(SealedCase):
    def setUp(self) -> None:
        super().setUp()
        self.item = next(row["item_id"] for row in cp.load_committed(self.paths))

    def prepare(self, pass_name: str = "form", item: str | None = None, annotator: str = "A1") -> int:
        return self.cli("correct", "--pass", pass_name, "--annotator", annotator, "--item", item or self.item, "--prepare")

    def apply(self, pass_name: str = "form", reason: str = "typo", item: str | None = None) -> int:
        return self.cli("correct", "--pass", pass_name, "--annotator", "A1", "--item", item or self.item, "--reason", reason, "--date", fx.DATE)

    def correction_paths(self, pass_name: str = "form") -> cp.PassPaths:
        return cp.PassPaths(self.dirs.work_dir, self.dirs.annotations_dir, "pilot1", pass_name, "A1", correction=True)

    def edit(self, pass_name: str = "form", **cells: str) -> dict[str, str]:
        paths = self.correction_paths(pass_name)
        rows = read_csv(paths.sheet)
        self.assertEqual(len(rows), 1)
        rows[0].update(cells)
        write_csv(paths.sheet, cp.SHEET_FIELDS[pass_name], rows, excel=True)
        return rows[0]

    def problems(self, pass_name: str = "form", reason: str = "typo", item: str | None = None) -> str:
        with self.assertRaises((cp.PassError, cs.SchemaError)) as raised:
            ctx.apply_correction(self.dirs, pass_name=pass_name, annotator="A1", item=item or self.item, reason=reason, date=fx.DATE)
        return str(raised.exception)

    def corrections(self) -> list[dict[str, str]]:
        return cp.load_corrections(self.dirs.corrections)


class FormCorrectionTests(CorrectionCase):
    def test_prepare_prefills_the_current_labels(self) -> None:
        self.assertEqual(self.prepare(), 0)
        row = read_csv(self.correction_paths().sheet)[0]
        self.assertEqual((row["form"], row["fragment"]), ("INF", "0"))
        self.assertTrue(cs.FORM_ROW_RE.fullmatch(row["row_id"]))
        self.assertNotIn("d:", self.correction_paths().sheet.read_text(encoding="utf-8-sig"))

    def test_correction_supersedes_and_logs_both_hashes(self) -> None:
        old = cp.live_rows(cp.load_committed(self.paths))[self.item]
        self.prepare()
        self.edit(form="L1", notes="fixed a slip")
        self.assertEqual(self.apply(), 0)
        rows = [row for row in cp.load_committed(self.paths) if row["item_id"] == self.item]
        self.assertEqual([(row["form"], row["status"]) for row in rows], [("INF", "superseded"), ("L1", "")])
        self.assertEqual(cs.canonical_hash(rows[0]), cs.canonical_hash(old))  # preserved unchanged
        self.assertEqual(rows[1]["prior_sha256"], old["prior_sha256"])
        [entry] = self.corrections()
        self.assertEqual(
            entry,
            {"item_id": self.item, "pass": "form", "annotator": "A1", "old_sha256": cs.canonical_hash(old),
             "new_sha256": cs.canonical_hash(rows[1]), "reason": "typo", "corrected_on": fx.DATE, "later_passes_sealed": "false"},
        )  # fmt: skip
        self.assertFalse(self.correction_paths().sheet.exists())
        self.assertFalse(self.correction_paths().snapshot.exists())
        texts = cp.load_text_records(self.paths)
        self.assertEqual(texts[(self.item, cp.row_key(rows[1]))]["notes"], "fixed a slip")
        self.assertIn((self.item, cp.row_key(rows[0])), texts)  # the first judgment's notes survive

    def test_later_passes_sealed_is_false_before_any_context_sheet(self) -> None:
        self.prepare()
        self.edit(form="L2")
        self.apply()
        self.assertEqual(self.corrections()[0]["later_passes_sealed"], "false")

    def test_later_passes_sealed_is_true_once_the_context_sheet_was_built(self) -> None:
        self.assertEqual(self.build("context", "--taxonomy", "ctx-tax-v0"), 0)  # seen, not yet exported
        self.prepare()
        self.edit(form="L2")
        self.apply()
        self.assertEqual(self.corrections()[0]["later_passes_sealed"], "true")

    def test_later_rows_keep_their_prior_hash_and_new_sheets_use_the_corrected_row(self) -> None:
        self.seal_context()
        context_paths = self.pass_paths("context")
        before = cp.live_rows(cp.load_committed(context_paths))[self.item]["prior_sha256"]
        self.prepare()
        self.edit(form="L3")
        self.apply(reason="rubric_misread")
        self.assertEqual(self.corrections()[0]["later_passes_sealed"], "true")
        after = cp.live_rows(cp.load_committed(context_paths))[self.item]
        self.assertEqual(after["prior_sha256"], before)  # built on the superseded row, still valid
        self.assertEqual(before, self.corrections()[0]["old_sha256"])

    def test_corrections_are_appended_in_order(self) -> None:
        for form, reason in (("L1", "typo"), ("L2", "other")):
            self.prepare()
            self.edit(form=form)
            self.assertEqual(self.apply(reason=reason), 0)
        log = self.corrections()
        self.assertEqual([entry["reason"] for entry in log], ["typo", "other"])
        self.assertEqual(log[0]["new_sha256"], log[1]["old_sha256"])
        statuses = [row["status"] for row in cp.load_committed(self.paths) if row["item_id"] == self.item]
        self.assertEqual(statuses, ["superseded", "superseded", ""])


class CorrectionFailureTests(CorrectionCase):
    def test_invalid_reason(self) -> None:
        self.prepare()
        self.edit(form="L1")
        self.assertIn("reason 'oops'", self.problems(reason="oops"))
        with self.assertRaises(SystemExit), unittest.mock.patch("sys.stderr", io.StringIO()):
            self.apply(reason="oops")

    def test_unknown_item(self) -> None:
        self.assertEqual(self.prepare(item="d:NOPE001:t02"), 1)
        self.assertIn("unknown item", self.problems(item="d:NOPE001:t02"))

    def test_no_row_to_correct(self) -> None:
        self.assertEqual(self.prepare(pass_name="reveal"), 1)
        self.assertEqual(self.prepare(annotator="A2"), 1)
        with self.assertRaises(cp.PassError) as raised:
            ctx.prepare_correction(self.dirs, pass_name="context", annotator="A1", item=self.item)
        self.assertIn("no exported context row", str(raised.exception))

    def test_apply_without_a_prepared_sheet(self) -> None:
        self.assertIn("no sheet snapshot", self.problems())

    def test_unchanged_sheet_is_refused(self) -> None:
        self.prepare()
        self.assertIn("changes no label", self.problems())
        self.assertEqual(self.corrections(), [])

    def test_invalid_correction_is_rejected_by_the_pass_rules(self) -> None:
        self.prepare()
        self.edit(form="L9")
        self.assertIn("rubric v2 label", self.problems())
        self.assertTrue(self.correction_paths().sheet.exists())  # nothing applied, sheet kept for fixing

    def test_row_changed_after_prepare(self) -> None:
        self.prepare()
        other = next(row["item_id"] for row in cp.load_committed(self.paths) if row["item_id"] != self.item)
        self.edit(form="L1")
        self.assertIn("not for", self.problems(item=other))
        rows = [dict(row, fragment="1") if row["item_id"] == self.item else row for row in cp.load_committed(self.paths)]
        write_csv(self.paths.committed, cp.COMMITTED_FIELDS["form"], rows)  # a hand edit after prepare
        self.assertIn("changed after the correction sheet was prepared", self.problems())

    def test_tampered_log_is_rejected(self) -> None:
        self.prepare()
        self.edit(form="L1")
        self.apply()
        rows = read_csv(self.dirs.corrections)
        rows[0]["later_passes_sealed"] = "maybe"
        write_csv(self.dirs.corrections, cp.CORRECTION_FIELDS, rows)
        with self.assertRaises(cp.PassError) as raised:
            self.corrections()
        self.assertIn("later_passes_sealed", str(raised.exception))


class ContextCorrectionTests(CorrectionCase):
    def setUp(self) -> None:
        super().setUp()
        self.seal_context()
        self.context_paths = self.pass_paths("context")
        self.dialogue = next(e["item_id"] for e in self.entries("context") if e["stratum"] == "dialogue")

    def test_prefill_includes_local_free_text(self) -> None:
        self.assertEqual(self.prepare("context", item=self.dialogue), 0)
        row = read_csv(self.correction_paths("context").sheet)[0]
        self.assertEqual((row["function"], row["intent"], row["slots"]), ("request", "find_hotel", "area=the quiet quarter"))
        self.assertTrue(row["context"].startswith("[0] USER:"))
        snapshot = json.loads(self.correction_paths("context").snapshot.read_text(encoding="utf-8"))
        self.assertEqual(snapshot["taxonomy_version"], "ctx-tax-v0")  # the corrected row's version

    def test_paraphrase_only_correction_gets_its_own_text_record(self) -> None:
        old = cp.live_rows(cp.load_committed(self.context_paths))[self.dialogue]
        self.prepare("context", item=self.dialogue)
        self.edit("context", paraphrase="Find a hotel in the quiet quarter, please")
        self.assertEqual(self.apply("context", item=self.dialogue), 0)
        new = cp.live_rows(cp.load_committed(self.context_paths))[self.dialogue]
        self.assertNotEqual(new["text_sha256"], old["text_sha256"])
        [entry] = self.corrections()
        self.assertEqual(entry["old_sha256"], entry["new_sha256"])  # FR10 chain hash excludes free text
        texts = cp.load_text_records(self.context_paths)
        self.assertEqual(texts[(self.dialogue, cp.row_key(new))]["paraphrase"], "Find a hotel in the quiet quarter, please")
        self.assertIn((self.dialogue, cp.row_key(old)), texts)

    def test_missing_local_text_blocks_a_context_correction(self) -> None:
        self.context_paths.text.unlink()
        self.assertEqual(self.prepare("context", item=self.dialogue), 1)
        with self.assertRaises(cp.PassError) as raised:
            ctx.prepare_correction(self.dirs, pass_name="context", annotator="A1", item=self.dialogue)
        self.assertIn("Google Drive", str(raised.exception))

    def test_context_correction_is_checked_against_the_taxonomy(self) -> None:
        self.prepare("context", item=self.dialogue)
        self.edit("context", intent="book_taxi", slots="area=north")
        problems = self.problems("context", item=self.dialogue)
        self.assertIn("required slot 'destination' is missing", problems)
        self.assertIn("'area' is not defined", problems)


if __name__ == "__main__":
    unittest.main()
