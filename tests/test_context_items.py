"""Tests for the contextual item registry, dialogue pilot draw and literary registration (spec 003 T2, T3).

Tiny invented dialogues only: no real DIRECT/MultiWOZ text.
"""

from __future__ import annotations

import io
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from src.annotation import context_items as ci
from src.annotation import context_schema as cs
from src.literary import screening as sc
from src.data.direct_dataset import Turn
from tests import context_fixtures as fx

DATE = fx.DATE
make_dialogue, make_item, corpus = fx.make_dialogue, fx.make_item, fx.corpus


def draw_rows(pool: dict, dialogues: dict, *, count: int = 4, seed: int = 7, batch: str = "pilot1") -> list[dict[str, str]]:
    return ci.draw_dialogues(
        pool, dialogues, count=count, seed=seed, batch=batch, inputs_sha256="a" * 64, registered_on=DATE
    )


def literary_row(candidate: str = "lit-0123456789", family: str = "aesop:the-owl-and-the-kettle") -> dict[str, str]:
    return {
        "item_id": candidate,
        "stratum": "literary",
        "batch": "pilot1",
        "split": "dev",
        "group_id": family,
        "source_ref": "aesop_jones1912",
        "target_sha256": "b" * 64,
        "draw": "screened",
        "seed": "",
        "pool_size": "",
        "inputs_sha256": "",
        "registered_on": DATE,
        "protocol_version": cs.PROTOCOL_VERSION,
    }


class PoolTests(unittest.TestCase):
    def test_pool_keeps_only_dev_turns_after_the_first(self) -> None:
        items, _ = corpus(dev=3)
        pool = ci.dialogue_pool(items, set(), set())
        self.assertEqual(sorted(pool), ["DEV000.json", "DEV001.json", "DEV002.json"])
        self.assertTrue(all(turns == [2, 4] for turns in pool.values()))

    def test_pool_excludes_labeled_and_registered_dialogues(self) -> None:
        items, _ = corpus(dev=4)
        pool = ci.dialogue_pool(items, {"DEV000.json"}, {"DEV001.json"})
        self.assertEqual(sorted(pool), ["DEV002.json", "DEV003.json"])

    def test_dialogue_with_only_a_first_turn_never_enters_the_pool(self) -> None:
        items = [make_item("ONE000.json", 0), make_item("TWO000.json", 0), make_item("TWO000.json", 2)]
        self.assertEqual(list(ci.dialogue_pool(items, set(), set())), ["TWO000.json"])

    def test_missing_mismatch_donor_does_not_exclude_a_turn(self) -> None:
        # Spec 001 AC-06: donor coverage is spec 004's concern, never a selection criterion.
        items = [make_item("DEV000.json", 2, mismatch_status="unavailable")]
        self.assertEqual(ci.dialogue_pool(items, set(), set()), {"DEV000.json": [2]})


class DrawTests(unittest.TestCase):
    def setUp(self) -> None:
        self.items, self.dialogues = corpus(dev=12)
        self.pool = ci.dialogue_pool(self.items, {"DEV000.json"}, set())

    def test_same_seed_and_inputs_give_identical_rows(self) -> None:
        self.assertEqual(draw_rows(self.pool, self.dialogues), draw_rows(self.pool, self.dialogues))

    def test_different_seed_gives_a_different_draw(self) -> None:
        self.assertNotEqual(draw_rows(self.pool, self.dialogues, seed=7), draw_rows(self.pool, self.dialogues, seed=8))

    def test_drawn_rows_respect_the_draw_rule(self) -> None:
        rows = draw_rows(self.pool, self.dialogues, count=len(self.pool))
        self.assertEqual(len({row["group_id"] for row in rows}), len(self.pool))  # one turn per dialogue
        for row in rows:
            with self.subTest(item=row["item_id"]):
                dialogue_id, turn = row["source_ref"].split("#")
                self.assertNotEqual(dialogue_id, "DEV000.json")
                self.assertIn(dialogue_id, self.pool)
                self.assertGreater(int(turn), 0)
                self.assertEqual(row["split"], "dev")
                self.assertEqual(row["pool_size"], str(len(self.pool)))
                self.assertEqual(row["seed"], "7")
        self.assertEqual(ci.validate_registry(rows), [])
        self.assertEqual([row["item_id"] for row in rows], sorted(row["item_id"] for row in rows))

    def test_count_larger_than_pool_is_rejected_with_the_pool_size(self) -> None:
        with self.assertRaises(ci.RegistryError) as raised:
            draw_rows(self.pool, self.dialogues, count=len(self.pool) + 1)
        self.assertIn(str(len(self.pool)), str(raised.exception))

    def test_non_positive_count_and_bad_batch_are_rejected(self) -> None:
        with self.assertRaises(ci.RegistryError):
            draw_rows(self.pool, self.dialogues, count=0)
        with self.assertRaises(cs.SchemaError):
            draw_rows(self.pool, self.dialogues, batch="../x")

    def test_target_hash_comes_from_the_original_dialogue_text(self) -> None:
        dialogues = {"DEV001.json": [Turn("user", "hi"), Turn("system", "yes?"), Turn("user", "  a table for two  ")]}
        rows = draw_rows({"DEV001.json": [2]}, dialogues, count=1)
        self.assertEqual(rows[0]["target_sha256"], ci.target_sha256("  a table for two  "))
        self.assertNotEqual(rows[0]["target_sha256"], ci.target_sha256("a table for two"))

    def test_a_social_turn_can_be_drawn(self) -> None:
        dialogues = {"DEV001.json": [Turn("user", "a train please"), Turn("system", "booked"), Turn("user", "thanks, bye")]}
        rows = draw_rows({"DEV001.json": [2]}, dialogues, count=1)
        self.assertEqual(rows[0]["item_id"], "d:DEV001:t02")

    def test_inconsistent_dialogue_data_is_an_error(self) -> None:
        with self.assertRaises(ci.RegistryError):
            draw_rows({"DEV001.json": [2]}, {"DEV001.json": [Turn("user", "x")]}, count=1)  # turn missing
        with self.assertRaises(ci.RegistryError):
            draw_rows({"DEV001.json": [1]}, {"DEV001.json": make_dialogue("DEV001", 2)}, count=1)  # system turn


class RegistryValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        items, dialogues = corpus(dev=4)
        self.rows = draw_rows(ci.dialogue_pool(items, set(), set()), dialogues, count=2) + [literary_row()]

    def assert_problem(self, rows: list[dict[str, str]], fragment: str) -> None:
        problems = ci.validate_registry(rows)
        self.assertTrue(any(fragment in problem for problem in problems), problems)

    def test_valid_rows_pass(self) -> None:
        self.assertEqual(ci.validate_registry(self.rows), [])

    def test_duplicate_item(self) -> None:
        self.assert_problem([*self.rows, dict(self.rows[0])], "duplicate item_id")

    def test_test_split_and_cross_split_group_are_rejected(self) -> None:
        moved = dict(self.rows[0], split="test", item_id=self.rows[0]["item_id"][:-2] + "98", source_ref=self.rows[0]["source_ref"].split("#")[0] + "#98")
        problems = ci.validate_registry([*self.rows, moved])
        self.assertTrue(any("split 'test'" in problem for problem in problems), problems)
        self.assertTrue(any("spans splits" in problem for problem in problems), problems)

    def test_bad_batch(self) -> None:
        self.assert_problem([dict(self.rows[0], batch="../x")], "batch")

    def test_item_id_must_match_source_ref_and_group(self) -> None:
        self.assert_problem([dict(self.rows[0], item_id="d:OTHER:t02")], "does not match source_ref")
        self.assert_problem([dict(self.rows[0], group_id="OTHER")], "group_id is not the dialogue")

    def test_turn_zero_and_wrong_draw_kind(self) -> None:
        zero = dict(self.rows[0], item_id="d:DEV000:t00", group_id="DEV000", source_ref="DEV000.json#0")
        self.assert_problem([zero], "turn 0")
        self.assert_problem([dict(self.rows[0], draw="screened")], "must be 'drawn'")
        self.assert_problem([dict(literary_row(), draw="drawn")], "must be 'screened'")

    def test_literary_shape(self) -> None:
        self.assert_problem([dict(literary_row(), item_id="d:X:t02")], "candidate_id")
        self.assert_problem([dict(literary_row(), group_id="=HYPERLINK(x)")], "family ID")
        self.assert_problem([dict(literary_row(), source_ref="=cmd|' /C calc'!A0")], "source key")
        self.assert_problem([dict(literary_row(), source_ref="the fox said hello")], "source key")
        self.assert_problem([dict(literary_row(), seed="99")], "seed must be blank")

    def test_dialogue_stem_cannot_start_with_a_formula_prefix(self) -> None:
        row = dict(self.rows[0], item_id="d:-X1:t02", group_id="-X1", source_ref="-X1.json#2")
        self.assert_problem([row], "source_ref")

    def test_field_shapes(self) -> None:
        self.assert_problem([dict(self.rows[0], target_sha256="abc")], "target_sha256")
        self.assert_problem([dict(self.rows[0], seed="-1")], "seed")
        self.assert_problem([dict(self.rows[0], registered_on="11/10/2026")], "registered_on")
        self.assert_problem([dict(self.rows[0], protocol_version="ctx-v9")], "protocol_version")
        self.assert_problem([{**self.rows[0], "extra": "x"}], "columns")


class RegistryFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / ci.REGISTRY_FILE
        items, dialogues = corpus(dev=6)
        self.rows = draw_rows(ci.dialogue_pool(items, set(), set()), dialogues, count=3) + [literary_row()]

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_missing_file_is_an_empty_registry(self) -> None:
        self.assertEqual(ci.load_registry(self.path), [])

    def test_round_trip_is_byte_identical(self) -> None:
        ci.write_registry(self.path, list(reversed(self.rows)))
        first = self.path.read_bytes()
        ci.write_registry(self.path, ci.load_registry(self.path))
        self.assertEqual(self.path.read_bytes(), first)
        self.assertEqual(ci.load_registry(self.path), sorted(self.rows, key=lambda row: row["item_id"]))

    def test_invalid_rows_never_reach_disk(self) -> None:
        with self.assertRaises(ci.RegistryError):
            ci.write_registry(self.path, [*self.rows, dict(self.rows[0])])
        self.assertFalse(self.path.exists())

    def test_load_rejects_a_reordered_header_and_a_bad_row(self) -> None:
        ci.write_registry(self.path, self.rows)
        text = self.path.read_text(encoding="utf-8")
        header, rest = text.split("\n", 1)
        fields = header.split(",")
        swapped = ",".join([fields[1], fields[0], *fields[2:]])
        self.path.write_text(swapped + "\n" + rest, encoding="utf-8")
        with self.assertRaises(ci.RegistryError):
            ci.load_registry(self.path)
        self.path.write_text(text.replace(",dev,", ",test,", 1), encoding="utf-8")
        with self.assertRaises(ci.RegistryError) as raised:
            ci.load_registry(self.path)
        self.assertIn("split", str(raised.exception))

    def test_load_accepts_an_excel_byte_order_mark(self) -> None:
        ci.write_registry(self.path, self.rows)
        self.path.write_bytes(b"\xef\xbb\xbf" + self.path.read_bytes())
        self.assertEqual(len(ci.load_registry(self.path)), len(self.rows))


class DrawCommandTests(fx.ContextCase):
    """End to end through ``python -m src.annotation.context draw`` (round 2 labeled DEV003)."""

    def run_draw(self, *args: str) -> int:
        return self.cli("draw", "--date", DATE, *args)

    @property
    def annotations(self) -> Path:
        return self.dirs.annotations_dir

    @property
    def direct(self) -> Path:
        return self.dirs.direct_dir

    def registry(self) -> list[dict[str, str]]:
        return ci.load_registry(self.annotations / ci.REGISTRY_FILE)

    def test_draw_writes_a_valid_registry_without_labeled_dialogues(self) -> None:
        self.assertEqual(self.run_draw("--batch", "pilot1", "--count", "4", "--seed", "11"), 0)
        rows = self.registry()
        self.assertEqual(len(rows), 4)
        self.assertNotIn("DEV003", {row["group_id"] for row in rows})
        self.assertTrue(all(row["pool_size"] == "9" and row["registered_on"] == DATE for row in rows))
        self.assertEqual(rows[0]["inputs_sha256"], ci.file_sha256(self.direct / "items.jsonl"))

    def test_same_seed_in_a_fresh_registry_reproduces_the_draw(self) -> None:
        self.run_draw("--batch", "pilot1", "--count", "4", "--seed", "11")
        first = (self.annotations / ci.REGISTRY_FILE).read_bytes()
        (self.annotations / ci.REGISTRY_FILE).unlink()
        self.run_draw("--batch", "pilot1", "--count", "4", "--seed", "11")
        self.assertEqual((self.annotations / ci.REGISTRY_FILE).read_bytes(), first)

    def test_a_second_draw_into_the_same_batch_is_refused(self) -> None:
        self.run_draw("--batch", "pilot1", "--count", "4")
        before = (self.annotations / ci.REGISTRY_FILE).read_bytes()
        self.assertEqual(self.run_draw("--batch", "pilot1", "--count", "2"), 1)
        self.assertEqual((self.annotations / ci.REGISTRY_FILE).read_bytes(), before)

    def test_a_new_batch_never_redraws_a_registered_dialogue(self) -> None:
        self.run_draw("--batch", "pilot1", "--count", "4")
        self.assertEqual(self.run_draw("--batch", "pilot2", "--count", "5"), 0)
        groups = [row["group_id"] for row in self.registry()]
        self.assertEqual(len(groups), 9)
        self.assertEqual(len(set(groups)), 9)
        self.assertEqual(self.run_draw("--batch", "pilot3", "--count", "1"), 1)  # pool exhausted

    def test_cli_rejects_a_path_like_batch(self) -> None:
        with self.assertRaises(SystemExit), unittest.mock.patch("sys.stderr", io.StringIO()):
            self.run_draw("--batch", "../x", "--count", "1")
        self.assertFalse((self.annotations / ci.REGISTRY_FILE).exists())


if __name__ == "__main__":
    unittest.main()


class LiteraryRegistrationTests(fx.ContextCase):
    INCLUDE = {"night is long": ("Owl", "Badger"), "fetch some sticks": ("Badger", "Owl")}

    def register(self, batch: str = "pilot1") -> int:
        return self.cli("register-literary", "--batch", batch, "--date", DATE)

    def registry(self) -> list[dict[str, str]]:
        return ci.load_registry(self.dirs.registry)

    def test_only_include_rows_are_registered(self) -> None:
        log = self.screen(self.INCLUDE, exclude=("Oh, dear",))
        included = {row["candidate_id"] for row in log if row["status"] == "include"}
        self.assertEqual(len(included), 2)
        self.assertTrue(any(row["status"] == "exclude" for row in log))
        self.assertTrue(any(row["status"] == "pending" for row in log))
        self.assertEqual(self.register(), 0)
        rows = self.registry()
        self.assertEqual({row["item_id"] for row in rows}, included)
        by_id = {row["candidate_id"]: row for row in log}
        for row in rows:
            with self.subTest(item=row["item_id"]):
                self.assertEqual(row["stratum"], "literary")
                self.assertEqual(row["group_id"], "fables")
                self.assertEqual(row["source_ref"], "aesop_jones1912")
                self.assertEqual(row["draw"], "screened")
                self.assertEqual(row["target_sha256"], by_id[row["item_id"]]["target_sha256"])

    def test_registration_is_idempotent(self) -> None:
        self.screen(self.INCLUDE)
        self.register()
        first = self.dirs.registry.read_bytes()
        self.assertEqual(self.register(), 0)
        self.assertEqual(self.register("pilot2"), 0)  # already registered under pilot1: no new rows
        self.assertEqual(self.dirs.registry.read_bytes(), first)

    def test_coexists_with_drawn_dialogues(self) -> None:
        self.cli("draw", "--batch", "pilot1", "--count", "3", "--date", DATE)
        self.screen(self.INCLUDE)
        self.register()
        strata = sorted(row["stratum"] for row in self.registry())
        self.assertEqual(strata, ["dialogue"] * 3 + ["literary"] * 2)

    def test_no_screening_log_registers_nothing(self) -> None:
        self.assertEqual(self.register(), 0)
        self.assertFalse(self.dirs.registry.exists())

    def test_non_dev_family_is_rejected(self) -> None:
        log = self.screen(self.INCLUDE)
        families = sc.load_families(self.dirs.literary)
        families[0]["split"] = "test"
        with self.assertRaises(ci.RegistryError) as raised:
            ci.literary_rows(log, {f["family_id"]: f for f in families}, [], batch="pilot1", registered_on=DATE)
        self.assertIn("not a dev family", str(raised.exception))

    def test_unknown_family_and_bad_ids_are_rejected(self) -> None:
        log = self.screen(self.INCLUDE)
        families = {f["family_id"]: f for f in sc.load_families(self.dirs.literary)}
        included = [row for row in log if row["status"] == "include"]
        cases = {
            "not in the families file": dict(included[0], family_id="ghosts"),
            "malformed candidate_id": dict(included[0], candidate_id="=HYPERLINK(1)"),
            "malformed target_sha256": dict(included[0], target_sha256="zz"),
        }
        for fragment, row in cases.items():
            with self.subTest(fragment=fragment), self.assertRaises(ci.RegistryError) as raised:
                ci.literary_rows([row], families, [], batch="pilot1", registered_on=DATE)
            self.assertIn(fragment, str(raised.exception))

    def test_bad_batch_is_rejected(self) -> None:
        with self.assertRaises(cs.SchemaError):
            ci.literary_rows([], {}, [], batch="../x", registered_on=DATE)
        with self.assertRaises(SystemExit), unittest.mock.patch("sys.stderr", io.StringIO()):
            self.register("../x")

    def test_rescreened_target_after_registration_is_an_error(self) -> None:
        log = self.screen(self.INCLUDE)
        families = {f["family_id"]: f for f in sc.load_families(self.dirs.literary)}
        registry = ci.literary_rows(log, families, [], batch="pilot1", registered_on=DATE)
        changed = [dict(row, target_sha256="c" * 64) if row["status"] == "include" else row for row in log]
        with self.assertRaises(ci.RegistryError) as raised:
            ci.literary_rows(changed, families, registry, batch="pilot1", registered_on=DATE)
        self.assertIn("target changed since registration", str(raised.exception))
