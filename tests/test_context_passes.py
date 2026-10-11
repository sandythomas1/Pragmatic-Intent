"""Tests for sealed-pass sheets and exports (spec 003 T4: form pass). Invented fixtures only."""

from __future__ import annotations

import io
import json
import random
import unittest
import unittest.mock

from src.annotation import context_items as ci
from src.annotation import context_passes as cp
from src.annotation import context_schema as cs
from src.annotation.levels import read_csv, write_csv
from src.data.direct_dataset import Turn
from tests import context_fixtures as fx

INCLUDE = {"night is long": ("Owl", "Badger"), "fetch some sticks": ("Badger", "Owl")}


class FormPassCase(fx.ContextCase):
    """Five drawn dialogues and two screened-in fables, all in batch pilot1."""

    def setUp(self) -> None:
        super().setUp()
        self.assertEqual(self.cli("draw", "--batch", "pilot1", "--count", "5", "--date", fx.DATE), 0)
        self.screen(INCLUDE)
        self.assertEqual(self.cli("register-literary", "--batch", "pilot1", "--date", fx.DATE), 0)
        self.paths = cp.PassPaths(self.dirs.work_dir, self.dirs.annotations_dir, "pilot1", "form", "A1")

    def sheet(self, seed: int = 5, annotator: str = "A1") -> int:
        return self.cli("sheet", "--pass", "form", "--batch", "pilot1", "--annotator", annotator, "--seed", str(seed))

    def export(self, annotator: str = "A1", rubric: str = "v2") -> int:
        return self.cli("export", "--pass", "form", "--batch", "pilot1", "--annotator", annotator, "--rubric", rubric)

    def fill(self, **overrides: dict[str, str]) -> list[dict[str, str]]:
        """Label every sheet row L1 (fragment 0) unless overridden per row_id; save; return rows."""
        rows = read_csv(self.paths.sheet)
        for row in rows:
            row.update(form="L1", fragment="0")
            row.update(overrides.get(row["row_id"], {}))
        write_csv(self.paths.sheet, cp.SHEET_FIELDS["form"], rows, excel=True)
        return rows

    def snapshot(self) -> dict:
        return json.loads(self.paths.snapshot.read_text(encoding="utf-8"))

    def registry(self) -> list[dict[str, str]]:
        return ci.load_registry(self.dirs.registry)

    def export_problems(self) -> str:
        with self.assertRaises(cp.PassError) as raised:
            self.export_direct()
        return "\n".join(raised.exception.problems)

    def export_direct(self) -> int:
        from src.annotation import context as ctx

        return ctx.export_pass(self.dirs, self.paths, rubric="v2")


class FormSheetTests(FormPassCase):
    def test_sheet_shows_only_opaque_ids_and_utterances(self) -> None:
        self.assertEqual(self.sheet(), 0)
        rows = read_csv(self.paths.sheet)
        self.assertEqual(list(rows[0]), list(cp.SHEET_FIELDS["form"]))
        self.assertEqual(len(rows), 7)
        text = self.paths.sheet.read_text(encoding="utf-8-sig")
        for forbidden in ("d:", "lit-", ".json", "aesop", "fables", "dialogue", "literary", "system line"):
            self.assertNotIn(forbidden, text)
        identifiers = {value for row in self.registry() for value in (row["item_id"], row["group_id"], row["source_ref"])}
        for row in rows:
            self.assertTrue(cs.FORM_ROW_RE.fullmatch(row["row_id"]))
            self.assertFalse({row["row_id"], row["form"], row["fragment"], row["notes"]} & identifiers)

    def test_order_is_the_seeded_shuffle_of_registry_order(self) -> None:
        self.sheet(seed=5)
        expected = [row["item_id"] for row in self.registry()]
        random.Random(5).shuffle(expected)
        self.assertEqual([entry["item_id"] for entry in self.snapshot()["rows"]], expected)
        self.assertNotEqual(expected, [row["item_id"] for row in self.registry()])  # 7 items: not the identity here

    def test_literary_target_across_a_line_break_is_one_clean_line(self) -> None:
        self.sheet()
        utterances = [row["utterance"] for row in read_csv(self.paths.sheet)]
        self.assertIn('"The night is long, and my feathers are thin."', utterances)
        self.assertFalse(any("\n" in utterance or "\r" in utterance for utterance in utterances))

    def test_snapshot_records_prior_hashes_of_registry_rows(self) -> None:
        self.sheet()
        registry = {row["item_id"]: row for row in self.registry()}
        snapshot = self.snapshot()
        self.assertEqual((snapshot["pass"], snapshot["annotator"], snapshot["batch"]), ("form", "A1", "pilot1"))
        for entry in snapshot["rows"]:
            self.assertEqual(entry["prior_sha256"], cs.canonical_hash(registry[entry["item_id"]]))

    def test_refuses_to_overwrite_an_unexported_sheet(self) -> None:
        self.sheet()
        self.fill()
        before = self.paths.sheet.read_bytes()
        self.assertEqual(self.sheet(), 1)
        self.assertEqual(self.paths.sheet.read_bytes(), before)

    def test_nothing_eligible_writes_nothing(self) -> None:
        self.assertEqual(self.cli("sheet", "--pass", "form", "--batch", "empty", "--annotator", "A1"), 0)
        self.assertFalse((self.dirs.work_dir / "empty").exists())

    def test_annotators_have_independent_sheets(self) -> None:
        self.sheet(annotator="A1")
        self.sheet(annotator="A2")
        self.assertTrue((self.dirs.work_dir / "pilot1" / "form_A2.csv").exists())

    def test_changed_source_text_is_refused_at_sheet_time(self) -> None:
        dialogue_id, turn = next(row for row in self.registry() if row["stratum"] == "dialogue")["source_ref"].split("#")
        self.dialogue_turns[dialogue_id][int(turn)] = Turn("user", "edited after registration")
        fx.write_direct(self.dirs.direct_dir, self.items, self.dialogue_turns)
        self.assertEqual(self.sheet(), 1)
        self.assertFalse(self.paths.sheet.exists())

    def test_only_form_is_available_until_later_tasks(self) -> None:
        with self.assertRaises(SystemExit), unittest.mock.patch("sys.stderr", io.StringIO()):
            self.cli("sheet", "--pass", "context", "--batch", "pilot1", "--annotator", "A1")

    def test_utterance_starting_with_a_formula_character_is_escaped(self) -> None:
        stem = next(row for row in self.registry() if row["stratum"] == "dialogue")
        dialogue_id, turn = stem["source_ref"].split("#")
        text = "=1+1 tickets please"
        self.dialogue_turns[dialogue_id][int(turn)] = Turn("user", text)
        fx.write_direct(self.dirs.direct_dir, self.items, self.dialogue_turns)
        rows = self.registry()
        for row in rows:
            if row["item_id"] == stem["item_id"]:
                row["target_sha256"] = ci.target_sha256(text)
        ci.write_registry(self.dirs.registry, rows)
        self.sheet()
        raw = self.paths.sheet.read_text(encoding="utf-8-sig")
        self.assertIn("'=1+1 tickets please", raw)


class FormExportTests(FormPassCase):
    def setUp(self) -> None:
        super().setUp()
        self.sheet()
        self.row_ids = [entry["row_id"] for entry in self.snapshot()["rows"]]

    def test_export_writes_text_free_chained_rows(self) -> None:
        first = self.row_ids[0]
        self.fill(**{first: {"form": "inf", "fragment": "1", "notes": "'=looks like a hint"}})
        self.assertEqual(self.export(), 0)
        rows = cp.load_committed(self.paths)
        self.assertEqual(len(rows), 7)
        self.assertEqual(list(rows[0]), list(cp.COMMITTED_FIELDS["form"]))
        registry = {row["item_id"]: row for row in self.registry()}
        for row in rows:
            self.assertEqual(row["prior_sha256"], cs.canonical_hash(registry[row["item_id"]]))
            self.assertEqual((row["annotator"], row["rubric_version"], row["status"]), ("A1", "v2", ""))
        first_item = self.snapshot()["rows"][0]["item_id"]
        self.assertEqual(next(r for r in rows if r["item_id"] == first_item)["form"], "INF")
        notes = {json.loads(line)["item_id"]: json.loads(line)["notes"] for line in self.paths.text.read_text(encoding="utf-8").splitlines()}
        self.assertEqual(notes[first_item], "=looks like a hint")

    def test_committed_file_holds_no_source_or_note_text(self) -> None:
        self.fill(**{self.row_ids[0]: {"notes": "secret annotator musing"}})
        self.export()
        committed = self.paths.committed.read_text(encoding="utf-8")
        for fragment in ("user line", "night is long", "feathers", "sticks", "secret annotator musing"):
            self.assertNotIn(fragment, committed)

    def test_every_problem_is_reported_and_nothing_is_written(self) -> None:
        rows = self.fill(**{self.row_ids[0]: {"form": ""}, self.row_ids[1]: {"form": "L4"}, self.row_ids[2]: {"fragment": "yes"}})
        rows.append(dict(rows[3]))  # duplicate row
        rows.append(dict(rows[4], row_id="f-999"))  # unknown row
        del rows[5]  # deleted row
        write_csv(self.paths.sheet, cp.SHEET_FIELDS["form"], rows, excel=True)
        problems = self.export_problems()
        for fragment in (self.row_ids[0], "L4", "fragment 'yes'", "duplicates sheet line", "f-999", "missing from the sheet"):
            self.assertIn(fragment, problems)
        self.assertFalse(self.paths.committed.exists())

    def test_multiline_notes_are_rejected(self) -> None:
        self.fill(**{self.row_ids[0]: {"notes": "line one\nline two"}})
        self.assertIn("newline", self.export_problems())

    def test_identical_re_export_is_a_no_op(self) -> None:
        self.fill()
        self.export()
        before = self.paths.committed.read_bytes()
        self.assertEqual(self.export(), 0)
        self.assertEqual(self.paths.committed.read_bytes(), before)

    def test_changed_label_after_export_points_to_correct(self) -> None:
        self.fill()
        self.export()
        before = self.paths.committed.read_bytes()
        self.fill(**{self.row_ids[0]: {"form": "L3"}})
        self.assertIn("correct", self.export_problems())
        self.assertEqual(self.paths.committed.read_bytes(), before)

    def test_items_registered_later_go_into_the_next_sheet(self) -> None:
        self.assertEqual(self.cli("draw", "--batch", "pilot1b", "--count", "2", "--date", fx.DATE), 0)
        rows = self.registry()
        for row in rows:
            if row["batch"] == "pilot1b":
                row["batch"] = "pilot1"  # as if registered into pilot1 after the sheet was built
        ci.write_registry(self.dirs.registry, rows)
        self.fill()
        self.assertEqual(self.export(), 0)  # the snapshot's 7 items export without the 2 new ones
        self.assertEqual(len(cp.load_committed(self.paths)), 7)
        self.assertEqual(self.sheet(seed=9), 0)
        self.assertEqual(len(read_csv(self.paths.sheet)), 2)
        self.fill()
        self.assertEqual(self.export(), 0)
        self.assertEqual(len(cp.load_committed(self.paths)), 9)

    def test_registry_row_changed_after_the_sheet_was_built(self) -> None:
        target = self.snapshot()["rows"][0]["item_id"]
        rows = self.registry()
        for row in rows:
            if row["item_id"] == target:
                row["registered_on"] = "2026-10-12"
        ci.write_registry(self.dirs.registry, rows)
        self.fill()
        self.assertIn("registry row changed", self.export_problems())

    def test_bad_rubric_and_missing_sheet(self) -> None:
        self.fill()
        self.assertEqual(self.export(rubric="2"), 1)
        self.assertFalse(self.paths.committed.exists())
        self.assertEqual(self.export(annotator="A2"), 1)  # no snapshot for A2

    def test_tampered_snapshot_is_rejected(self) -> None:
        snapshot = self.snapshot()
        snapshot["rows"][0]["item_id"] = "../../etc"
        self.paths.snapshot.write_text(json.dumps(snapshot), encoding="utf-8")
        self.fill()
        self.assertIn("snapshot row", self.export_problems())


class CommittedFileTests(unittest.TestCase):
    PATHS = cp.PassPaths(fx.Path("w"), fx.Path("a"), "pilot1", "form", "A1")

    def row(self, **changes: str) -> dict[str, str]:
        base = {
            "item_id": "d:DEV001:t02",
            "annotator": "A1",
            "form": "L1",
            "fragment": "0",
            "rubric_version": "v2",
            "protocol_version": cs.PROTOCOL_VERSION,
            "status": "",
            "prior_sha256": "a" * 64,
        }
        return {**base, **changes}

    def test_validation_rules(self) -> None:
        self.assertEqual(cp.validate_committed([self.row()], self.PATHS), [])
        cases = {
            "annotator": self.row(annotator="A2"),
            "form": self.row(form="L9"),
            "status": self.row(status="deleted"),
            "prior_sha256": self.row(prior_sha256="x"),
            "rubric_version": self.row(rubric_version="2"),
        }
        for fragment, row in cases.items():
            with self.subTest(fragment=fragment):
                self.assertTrue(any(fragment in problem for problem in cp.validate_committed([row], self.PATHS)))
        two_live = cp.validate_committed([self.row(), self.row(form="L2")], self.PATHS)
        self.assertTrue(any("more than one live" in problem for problem in two_live))
        self.assertEqual(cp.validate_committed([self.row(status="superseded"), self.row(form="L2")], self.PATHS), [])

    def test_paths_reject_bad_ids_before_building_paths(self) -> None:
        for kwargs in ({"batch": "../x"}, {"annotator": "../A1"}, {"pass_name": "draft"}):
            args = {"work_dir": fx.Path("w"), "annotations_dir": fx.Path("a"), "batch": "pilot1", "pass_name": "form", "annotator": "A1", **kwargs}
            with self.subTest(kwargs=kwargs), self.assertRaises(cs.SchemaError):
                cp.PassPaths(**args)


if __name__ == "__main__":
    unittest.main()
