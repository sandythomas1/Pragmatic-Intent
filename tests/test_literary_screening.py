"""Tests for literary family assignment, proposal, export and validation (spec 002, T3-T5).

Invented fixture text only (tests/literary_fixtures.py). The fixture Bible has three books, so
its parser is swapped in through ``PARSERS`` the same way ``load_edition`` looks it up.
"""

from __future__ import annotations

import tempfile
import unittest
from functools import partial
from pathlib import Path
from unittest import mock

from src.annotation.levels import read_csv, write_csv
from src.literary import proposals as lp
from src.literary import screening as sc
from src.literary import sources as ls
from tests import literary_fixtures as fx

OWL = "aesop:the-owl-and-the-kettle"
HEN = "aesop:the-hen-and-the-ladder"
DATE = "2026-10-10"


class ScreeningCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        raw_dir, manifest = fx.install_fixture_editions(root)
        self.dirs = sc.Dirs(raw_dir, manifest, root / "annotations", root / "work")
        patcher = mock.patch.dict(ls.PARSERS, {"kjv_pg10": partial(ls.parse_kjv, books=fx.KJV_BOOKS)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.editions = sc.Editions(self.dirs)

    def quietly(self, function, *args):
        with self.assertLogs(sc.logger, level="INFO"):
            return function(*args)

    def assign(self, source: str, family_id: str, episodes: list[str], reason: str = "test family") -> None:
        self.quietly(sc.assign_family, self.dirs, self.editions, source, family_id, episodes, reason, DATE)

    def sheet(self) -> list[dict[str, str]]:
        return read_csv(self.dirs.sheet)

    def save_sheet(self, rows: list[dict[str, str]]) -> None:
        write_csv(self.dirs.sheet, sc.SHEET_FIELDS, rows, excel=True)

    def row_with(self, rows: list[dict[str, str]], text: str) -> dict[str, str]:
        (row,) = [row for row in rows if text in row["target_text"]]
        return row

    def assert_problems(self, *fragments: str) -> None:
        with self.assertRaises(sc.ValidationFailed) as caught:
            sc.export(self.dirs, self.editions, "A1")
        joined = "\n".join(caught.exception.problems)
        for fragment in fragments:
            self.assertIn(fragment, joined)
        self.assertFalse(self.dirs.log.exists(), "nothing is written when export fails")


class FamiliesTest(ScreeningCase):
    def draw(self, source: str, count: int, seed: int = 7) -> list[str]:
        return self.quietly(sc.draw_families, self.dirs, self.editions, source, count, seed, DATE)

    def test_draw_is_deterministic_and_records_pool(self) -> None:
        first = self.draw("kjv_pg10", 2, seed=3)
        families = sc.load_families(self.dirs)
        self.assertEqual([family["family_id"] for family in families], first)
        self.assertEqual({family["pool_size"] for family in families}, {"3"})  # second:1 has no speech
        self.assertEqual({family["split"] for family in families}, {"dev"})
        self.dirs.families.unlink()
        self.assertEqual(self.draw("kjv_pg10", 2, seed=3), first)

    def test_draw_never_repeats_an_assigned_episode_and_rejects_oversize(self) -> None:
        self.assign("aesop_jones1912", "owl-family", [OWL])
        self.assertEqual(self.draw("aesop_jones1912", 1), [HEN])
        with self.assertRaisesRegex(sc.ScreeningError, "only 0 unassigned"):
            sc.draw_families(self.dirs, self.editions, "aesop_jones1912", 1, 7, DATE)
        with self.assertRaisesRegex(sc.ScreeningError, "at least 1"):
            sc.draw_families(self.dirs, self.editions, "kjv_pg10", 0, 7, DATE)

    def test_episodes_without_proposals_are_not_drawn(self) -> None:
        with self.assertRaisesRegex(sc.ScreeningError, "only 3 unassigned"):
            sc.draw_families(self.dirs, self.editions, "kjv_pg10", 4, 7, DATE)

    def test_assign_validates_ids_episodes_reason_and_clashes(self) -> None:
        self.assign("kjv_pg10", "kjv:garden-gate", ["kjv:first:1", "kjv:first:2"])
        cases = {
            "already exists": ("kjv:garden-gate", ["kjv:third:1"], "r"),
            "already in another family": ("kjv:other", ["kjv:first:2"], "r"),
            "no episode": ("kjv:other", ["kjv:fourth:1"], "r"),
            "listed twice": ("kjv:other", ["kjv:third:1", "kjv:third:1"], "r"),
            "must match": ("Bad Id!", ["kjv:third:1"], "r"),
            "required": ("kjv:other", ["kjv:third:1"], "  "),
            "newline": ("kjv:other", ["kjv:third:1"], "two\nlines"),
        }
        for message, (family_id, episodes, reason) in cases.items():
            with self.subTest(message), self.assertRaisesRegex(sc.ScreeningError, message):
                sc.assign_family(self.dirs, self.editions, "kjv_pg10", family_id, episodes, reason, DATE)
        self.assertEqual(len(sc.load_families(self.dirs)), 1)

    def test_malformed_committed_family_id_stops_propose(self) -> None:
        self.assign("aesop_jones1912", "owl", [OWL])
        rows = read_csv(self.dirs.families)
        rows[0]["family_id"] = '=HYPERLINK("https://example.invalid","x")'
        write_csv(self.dirs.families, sc.FAMILY_FIELDS, rows)
        with self.assertRaisesRegex(sc.ScreeningError, "malformed family id"):
            sc.propose(self.dirs, self.editions)
        self.assertFalse(self.dirs.sheet.exists())

    def test_bad_date_rejected(self) -> None:
        with self.assertRaisesRegex(sc.ScreeningError, "YYYY-MM-DD"):
            sc.assign_family(self.dirs, self.editions, "kjv_pg10", "x", ["kjv:third:1"], "r", "10/10/2026")


class ProposeTest(ScreeningCase):
    def test_quotes_are_proposed_exhaustively_with_interrupted_speech_merged(self) -> None:
        self.assign("aesop_jones1912", "fables", [OWL, HEN])
        self.assertEqual(self.quietly(sc.propose, self.dirs, self.editions), 5)
        targets = [row["target_text"] for row in self.sheet()]
        self.assertEqual(
            targets,
            [
                '"The night is long, and my feathers are thin."',
                '"Then fetch some sticks."',
                '"Oh, dear," said the Hen to the Goat, "what a fine loft that is."',
                '"It is,"',
                '"Ladders are heavy," said the Hen to herself, "and so is my',
            ],
        )
        flags = [row["flags"] for row in self.sheet()]
        self.assertEqual(flags, ["", "", "merged", "", "merged;unclosed_quote"])

    def test_moral_and_title_are_never_proposed(self) -> None:
        self.assign("aesop_jones1912", "fables", [OWL])
        self.quietly(sc.propose, self.dirs, self.editions)
        self.assertFalse(any("Cold owls" in row["target_text"] for row in self.sheet()))
        self.assertNotIn("Cold owls", " ".join(row["unit_text"] for row in self.sheet()))

    def test_bible_verses_with_speech_verbs_need_trimming(self) -> None:
        self.assign("kjv_pg10", "kjv:garden-gate", ["kjv:first:1", "kjv:first:2"])
        self.quietly(sc.propose, self.dirs, self.editions)
        rows = self.sheet()
        self.assertEqual([row["locator"] for row in rows], ["First 1:2", "First 2:1"])
        self.assertEqual({row["flags"] for row in rows}, {"needs_trim"})
        self.assertEqual(rows[0]["target_text"], "And the gardener saith unto the keeper, The gate is shut.")

    def test_rerun_appends_only_new_families_and_preserves_edits(self) -> None:
        self.assign("aesop_jones1912", "owl", [OWL])
        self.quietly(sc.propose, self.dirs, self.editions)
        rows = self.sheet()
        rows[0]["speaker"], rows[0]["notes"] = "Owl", "hint about the cold"
        self.save_sheet(rows)
        with self.assertLogs(sc.logger, level="INFO") as logs:
            self.assertEqual(sc.propose(self.dirs, self.editions), 0)
        self.assertIn("nothing new", "\n".join(logs.output))
        self.assign("aesop_jones1912", "hen", [HEN])
        self.assertEqual(self.quietly(sc.propose, self.dirs, self.editions), 3)
        rows = self.sheet()
        self.assertEqual(len(rows), 5)
        self.assertEqual((rows[0]["speaker"], rows[0]["notes"]), ("Owl", "hint about the cold"))
        self.assertEqual(len(sc.load_proposals(self.dirs)), 5)

    def test_candidate_ids_are_stable_span_hashes(self) -> None:
        self.assign("aesop_jones1912", "owl", [OWL])
        self.quietly(sc.propose, self.dirs, self.editions)
        for proposal in sc.load_proposals(self.dirs).values():
            self.assertEqual(proposal.candidate_id, lp.candidate_id(proposal.source, proposal.start, proposal.end))
            self.assertRegex(proposal.candidate_id, r"^lit-[0-9a-f]{10}$")

    def test_propose_requires_families(self) -> None:
        with self.assertRaisesRegex(sc.ScreeningError, "no families"):
            sc.propose(self.dirs, self.editions)

    def test_corrupt_sidecar_is_reported(self) -> None:
        self.assign("aesop_jones1912", "owl", [OWL])
        self.dirs.work_dir.mkdir(parents=True)
        self.dirs.proposals.write_text('{"candidate_id": "lit-0"}\n', encoding="utf-8")
        with self.assertRaisesRegex(sc.ScreeningError, "corrupt"):
            sc.propose(self.dirs, self.editions)

    def test_formula_cells_are_escaped_and_unescaped(self) -> None:
        for value in ("=HYPERLINK(1)", "+1", "-2", "@x", "\tx"):
            self.assertEqual(sc.escape_cell(value), "'" + value)
            self.assertEqual(sc.unescape_cell(sc.escape_cell(value)), value)
        self.assertEqual(sc.escape_cell("plain"), "plain")
        self.assertEqual(sc.unescape_cell("'tis the season"), "'tis the season")


class ExportTest(ScreeningCase):
    def setUp(self) -> None:
        super().setUp()
        self.assign("aesop_jones1912", "fables", [OWL, HEN])
        self.assign("kjv_pg10", "kjv:garden-gate", ["kjv:first:1", "kjv:first:2"])
        self.quietly(sc.propose, self.dirs, self.editions)
        self.rows = self.sheet()

    def screen(self, text: str, **changes: str) -> None:
        self.row_with(self.rows, text).update(changes)
        self.save_sheet(self.rows)

    def export(self) -> list[dict[str, str]]:
        self.quietly(sc.export, self.dirs, self.editions, "A1")
        return read_csv(self.dirs.log)

    def test_every_candidate_is_logged_text_free_and_sorted(self) -> None:
        self.screen("night is long", speaker="Owl", addressee="Badger", status="include")
        self.screen("fetch some sticks", status="exclude", exclusion_reason="uncertain_reading")
        log = self.export()
        self.assertEqual(len(log), 7)
        self.assertEqual([row["status"] for row in log[:2]], ["include", "exclude"])
        self.assertEqual({row["status"] for row in log[2:]}, {"pending"})
        self.assertEqual([row["source"] for row in log], ["aesop_jones1912"] * 5 + ["kjv_pg10"] * 2)
        committed = self.dirs.log.read_text(encoding="utf-8") + self.dirs.families.read_text(encoding="utf-8")
        for sentence in ("feathers are thin", "fetch some sticks", "fine loft", "gate is shut", "seekest thou"):
            self.assertNotIn(sentence, committed)

    def test_offsets_and_hash_reconstruct_a_trimmed_target(self) -> None:
        self.screen("gate is shut", target_text="The gate is shut.", speaker="gardener", addressee="keeper", status="include")
        (row,) = [row for row in self.export() if row["status"] == "include"]
        edition = self.editions.get("kjv_pg10")
        self.assertEqual(edition.text[int(row["target_start"]) : int(row["target_end"])], "The gate is shut.")
        self.assertEqual((row["episode_id"], row["locator"], row["origin"]), ("kjv:first:1", "First 1:2", "proposed"))

    def test_status_aliases_and_case(self) -> None:
        self.screen("night is long", speaker="Owl", addressee="Badger", status="Included")
        self.screen("fetch some sticks", status="EXCLUDE", exclusion_reason="Out_Of_Scope")
        log = self.export()
        self.assertEqual((log[0]["status"], log[1]["status"], log[1]["exclusion_reason"]), ("include", "exclude", "out_of_scope"))

    def test_labeling_rule_violations_are_named(self) -> None:
        self.screen("night is long", status="include", speaker="Owl")
        self.screen("fetch some sticks", status="exclude")
        self.screen("It is", status="maybe")
        self.screen("Ladders", exclusion_reason="no_context")
        self.assert_problems("include needs the addressee", "exclude needs an exclusion_reason", "status must be include",
                             "only allowed when status is exclude")  # fmt: skip

    def test_role_names_are_bounded_single_line_text(self) -> None:
        self.screen("night is long", status="include", speaker="O" * 61, addressee="=cmd()")
        self.assert_problems("longer than 60", "formula character")

    def test_target_text_must_occur_exactly_once(self) -> None:
        self.screen("night is long", target_text="the gardener")
        self.screen("Oh, dear", target_text="said the Hen")
        self.screen("It is", target_text="  ")
        self.assert_problems("does not occur", "more than once", "is empty")

    def test_unknown_changed_deleted_and_duplicate_rows_are_rejected(self) -> None:
        self.row_with(self.rows, "night is long")["candidate_id"] = "lit-0000000000"
        self.row_with(self.rows, "fetch some sticks")["family_id"] = "kjv:garden-gate"
        self.rows = [row for row in self.rows if "It is" not in row["target_text"]]
        self.rows.append(dict(self.row_with(self.rows, "Ladders")))
        self.save_sheet(self.rows)
        self.assert_problems("unknown candidate_id", "family_id was changed", "missing from the sheet", "duplicates the candidate")

    def test_manual_addition_in_a_dev_family(self) -> None:
        manual = dict.fromkeys(sc.SHEET_FIELDS, "")
        manual.update(family_id="fables", target_text="The Badger answered,", speaker="Badger", addressee="Owl", status="include")
        self.save_sheet([*self.rows, manual])
        (row,) = [row for row in self.export() if row["origin"] == "manual"]
        self.assertEqual(row["candidate_id"], lp.candidate_id("aesop_jones1912", int(row["target_start"]), int(row["target_end"])))
        self.assertEqual(row["episode_id"], OWL)

    def test_manual_rows_outside_dev_families_or_duplicating_a_proposal_are_rejected(self) -> None:
        stray = dict.fromkeys(sc.SHEET_FIELDS, "")
        stray.update(family_id="aesop:somewhere-else", target_text="The Badger answered,")
        duplicate = dict.fromkeys(sc.SHEET_FIELDS, "")
        duplicate.update(family_id="fables", target_text='"Then fetch some sticks."')
        self.save_sheet([*self.rows, stray, duplicate])
        self.assert_problems("not an assigned dev family", "duplicates proposed candidate")

    def test_included_moral_is_blocked_but_excluded_moral_is_logged(self) -> None:
        moral = dict.fromkeys(sc.SHEET_FIELDS, "")
        moral.update(family_id="fables", target_text="Cold owls hint; warm badgers act.", speaker="narrator",
                     addressee="reader", status="include")  # fmt: skip
        self.save_sheet([*self.rows, moral])
        self.assert_problems("narrator moral")
        moral.update(status="exclude", exclusion_reason="narrator_moral")
        self.save_sheet([*self.rows, moral])
        self.assertIn("narrator_moral", {row["exclusion_reason"] for row in self.export()})

    def test_bad_screener_id(self) -> None:
        with self.assertRaisesRegex(sc.ScreeningError, "pseudonym"):
            sc.export(self.dirs, self.editions, "Sandy Thomas")


class ValidateTest(ScreeningCase):
    def setUp(self) -> None:
        super().setUp()
        self.assign("aesop_jones1912", "fables", [OWL, HEN])
        self.quietly(sc.propose, self.dirs, self.editions)
        rows = self.sheet()
        self.row_with(rows, "night is long").update(speaker="Owl", addressee="Badger", status="include")
        self.save_sheet(rows)
        self.quietly(sc.export, self.dirs, self.editions, "A1")

    def edit(self, path: Path, fields: tuple[str, ...], **changes: str) -> None:
        rows = read_csv(path)
        rows[0].update(changes)
        write_csv(path, fields, rows)

    def assert_invalid(self, fragment: str) -> None:
        with self.assertRaises(sc.ValidationFailed) as caught:
            sc.validate(self.dirs, sc.Editions(self.dirs))  # fresh load, as each CLI run does
        self.assertIn(fragment, "\n".join(caught.exception.problems))

    def test_fresh_export_validates(self) -> None:
        self.assertEqual(self.quietly(sc.validate, self.dirs, self.editions), 5)

    def test_edited_offset_fails_hash_check(self) -> None:
        row = read_csv(self.dirs.log)[0]
        self.edit(self.dirs.log, sc.LOG_FIELDS, target_start=str(int(row["target_start"]) + 1))
        self.assert_invalid("no longer matches target_sha256")

    def test_offsets_outside_episode_or_not_integers(self) -> None:
        self.edit(self.dirs.log, sc.LOG_FIELDS, target_start="0")
        self.assert_invalid("outside its episode")
        self.edit(self.dirs.log, sc.LOG_FIELDS, target_start="x")
        self.assert_invalid("not integers")

    def test_family_split_change_fails(self) -> None:
        self.edit(self.dirs.families, sc.FAMILY_FIELDS, split="test")
        self.assert_invalid("split must be one of")

    def test_episode_in_two_families_fails(self) -> None:
        rows = read_csv(self.dirs.families)
        rows.append({**rows[0], "family_id": "copy"})
        write_csv(self.dirs.families, sc.FAMILY_FIELDS, rows)
        self.assert_invalid("is already in family")

    def test_changed_source_file_fails(self) -> None:
        path = self.dirs.raw_dir / "aesop_jones1912" / "pg11339.txt"
        path.write_bytes(path.read_bytes().replace(b"Owl", b"Emu"))
        self.assert_invalid("does not match the pinned")

    def test_truncated_row_reports_instead_of_crashing(self) -> None:
        text = self.dirs.log.read_text(encoding="utf-8").splitlines()
        self.dirs.log.write_text("\n".join([text[0], "lit-0123456789,aesop_jones1912", *text[2:]]) + "\n", encoding="utf-8")
        self.assert_invalid("malformed sha256")


class CliTest(ScreeningCase):
    def run_cli(self, *args: str) -> int:
        common = ["--raw-dir", str(self.dirs.raw_dir), "--manifest", str(self.dirs.manifest),
                  "--annotations-dir", str(self.dirs.annotations_dir), "--work-dir", str(self.dirs.work_dir)]  # fmt: skip
        with self.assertLogs(sc.logger, level="INFO") as logs:
            code = sc.main([*common, *args])
        self.output = "\n".join(logs.output)
        return code

    def test_full_flow_and_error_exit_code(self) -> None:
        self.assertEqual(self.run_cli("families", "draw", "--source", "aesop_jones1912", "--count", "1", "--seed", "1", "--date", DATE), 0)
        self.assertEqual(self.run_cli("propose"), 0)
        self.assertEqual(self.run_cli("export", "--screener", "A1"), 0)
        self.assertEqual(self.run_cli("validate"), 0)
        self.assertEqual(self.run_cli("families", "draw", "--source", "aesop_jones1912", "--count", "5", "--seed", "1"), 1)
        self.assertIn("only 1 unassigned", self.output)


if __name__ == "__main__":
    unittest.main()
