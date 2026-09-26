"""Tests for the DIRECT + MultiWOZ join and context derivation.

Tiny hand-made fixture dialogues only: no network and no real DIRECT/MultiWOZ text.
"""

from __future__ import annotations

import contextlib
import copy
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.data import build_direct_dataset as bd
from src.data.direct_dataset import CONDITIONS, Turn, build_context, is_social_only, load_dialogues, load_items


def turn(text: str, acts: dict | None = None, belief: dict | None = None) -> dict:
    return {"text": text, "dialog_act": acts or {}, "metadata": belief or {}}


def belief(**domains: dict) -> dict:
    return {domain: {"semi": slots, "book": {"booked": []}} for domain, slots in domains.items()}


def dialogue(goal_domains: list[str], turns: list[dict]) -> dict:
    return {"goal": {domain: {"info": {"x": "y"}} for domain in goal_domains}, "log": turns}


def single_domain(domain: str, n_turns: int) -> dict:
    """A dialogue that only ever talks about ``domain``."""
    act = domain.capitalize()
    turns = []
    for index in range(n_turns):
        if index % 2 == 0:
            turns.append(turn(f"{domain} user {index}", {f"{act}-Inform": [["Area", "north"]]}))
        else:
            turns.append(turn(f"{domain} system {index}", {f"{act}-Request": [["Area", "?"]]}, belief(**{domain: {"area": "north"}})))
    return dialogue([domain], turns)


RES001 = dialogue(
    ["restaurant"],
    [
        turn("I need a cheap restaurant.", {"Restaurant-Inform": [["Price", "cheap"]]}),
        turn("What food would you like?", {"Restaurant-Request": [["Food", "?"]]}, belief(restaurant={"pricerange": "cheap"})),
        turn("  Italian please.  ", {"Restaurant-Inform": [["Food", "italian"]]}),
        turn("Pizza Hut fits. Shall I book?", {"Booking-Inform": [["none", "none"]]}, belief(restaurant={"food": "italian"})),
        turn("No thanks, that is all.", {"general-thank": [["none", "none"]]}),
        turn("Goodbye.", {"general-bye": [["none", "none"]]}),
    ],
)
MUL001 = dialogue(
    ["restaurant", "train"],
    [
        turn("A restaurant in the centre.", {"Restaurant-Inform": [["Area", "centre"]]}),
        turn("Any cuisine?", {"Restaurant-Request": [["Food", "?"]]}, belief(restaurant={"area": "centre"})),
        turn("Any is fine. I also need a train.", {"Train-Inform": [["none", "none"]]}),
        turn("Where from?", {"Train-Request": [["Depart", "?"]]}, belief(restaurant={"area": "centre"}, train={"day": "monday"})),
        turn("From Ely, arriving by noon.", {"Train-Inform": [["Depart", "ely"]]}),
        turn("TR123 arrives 11:50.", {"Train-Inform": [["Id", "tr123"]]}, belief(train={"departure": "ely"})),
    ],
)

FIXTURE_DIALOGUES = {
    "RES001.json": RES001,
    "TRA001.json": single_domain("train", 6),
    "ATT001.json": single_domain("attraction", 6),
    "HOT001.json": single_domain("hotel", 4),
    "TAX001.json": single_domain("taxi", 4),
    "MUL001.json": MUL001,
    "HOS001.json": single_domain("hospital", 6),
    "POL001.json": single_domain("police", 2),
}
DEV_IDS = {"HOT001.json", "TAX001.json"}

TRAIN_ROWS = [
    ("RES001.json", 0, "I need a cheap restaurant."),
    ("RES001.json", 2, "Italian please."),
    ("RES001.json", 4, "No thanks, that is all."),
    ("TRA001.json", 2, "train user 2"),
    ("ATT001.json", 2, "attraction user 2"),
    ("HOT001.json", 2, "hotel user 2"),
    ("TAX001.json", 2, "taxi user 2"),
    ("ATT001.json", 4, "attraction user 2"),  # turn_index points at the wrong turn: rejected
    ("TRA001.json", 3, "train system 3"),  # a system turn: rejected
]
TEST_ROWS = [
    ("MUL001.json", 4, "From Ely, arriving by noon."),
    ("HOS001.json", 2, "hospital user 2"),
    ("POL001.json", 0, "police user 0"),
]


def parsed_dialogues() -> dict[str, bd.Dialogue]:
    return {dialogue_id: bd.parse_multiwoz_dialogue(dialogue_id, raw) for dialogue_id, raw in FIXTURE_DIALOGUES.items()}


def direct_row(dialogue_id: str, turn_index: int, target: str, source_file: str = "train.csv") -> bd.DirectRow:
    return bd.DirectRow(source_file, 0, dialogue_id, turn_index, target, f"direct {target}", f"indirect {target}", None)


def write_fixture_inputs(root: Path) -> tuple[Path, Path]:
    direct_dir, multiwoz_dir = root / "direct", root / "multiwoz"
    direct_dir.mkdir()
    multiwoz_dir.mkdir()
    for name, rows, with_quality in (("train.csv", TRAIN_ROWS, False), ("test.csv", TEST_ROWS, True)):
        with (direct_dir / name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            header = ["", "dialogue_id", "turn_index", "target_utterance", "direct_utterance", "indirect_utterance"]
            writer.writerow(header + (["isacceptable_direct", "isacceptable_indirect", "quality"] if with_quality else []))
            for index, (dialogue_id, turn_index, target) in enumerate(rows):
                extra = ["True", "False", "Good"] if with_quality else []
                writer.writerow([index, dialogue_id, turn_index, target, f"direct {target}", f"indirect {target}", *extra])
    (multiwoz_dir / "data.json").write_text(json.dumps(FIXTURE_DIALOGUES), encoding="utf-8")
    (multiwoz_dir / "valListFile.txt").write_text("\n".join(sorted(DEV_IDS)) + "\n", encoding="utf-8")
    return direct_dir, multiwoz_dir


def build_items(seed: int = 7) -> tuple[list[dict], dict[str, list[Turn]]]:
    """Run the in-memory pipeline over the fixtures (warnings for rejected rows silenced)."""
    with tempfile.TemporaryDirectory() as tmp:
        direct_dir, multiwoz_dir = write_fixture_inputs(Path(tmp))
        with contextlib.redirect_stderr(io.StringIO()), unittest.TestCase().assertLogs(bd.logger, "WARNING"):
            items, dialogues, _ = bd.build(direct_dir, multiwoz_dir, seed)
    return items, {dialogue_id: d.turns for dialogue_id, d in dialogues.items()}


# --------------------------------------------------------------------------- join


class JoinTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dialogues = parsed_dialogues()

    def test_exact_stripped_and_normalized_matches(self) -> None:
        cases = {
            "Italian please.": "exact",  # MultiWOZ's outer whitespace is stripped on load
            "  Italian please. ": "stripped",
            "italian   PLEASE.": "normalized",
        }
        for target, expected in cases.items():
            with self.subTest(target=target):
                self.assertEqual(bd.match_row(direct_row("RES001.json", 2, target), self.dialogues), (expected, "ok"))

    def test_row_whose_turn_index_points_at_another_turn_is_rejected(self) -> None:
        row = direct_row("ATT001.json", 4, "attraction user 2")
        self.assertEqual(bd.match_row(row, self.dialogues), (None, "text_mismatch"))

    def test_other_rejections(self) -> None:
        cases = [
            (direct_row("NOPE.json", 0, "x"), "dialogue_not_found"),
            (direct_row("RES001.json", 6, "x"), "turn_index_out_of_range"),
            (direct_row("RES001.json", 1, "What food would you like?"), "not_a_user_turn"),
        ]
        for row, reason in cases:
            with self.subTest(reason=reason):
                self.assertEqual(bd.match_row(row, self.dialogues), (None, reason))

    def test_build_reports_and_skips_rejected_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            direct_dir, multiwoz_dir = write_fixture_inputs(Path(tmp))
            with self.assertLogs(bd.logger, "WARNING") as logs:
                items, _, report = bd.build(direct_dir, multiwoz_dir, seed=7)
        self.assertEqual(report["rows_read"], len(TRAIN_ROWS) + len(TEST_ROWS))
        self.assertEqual(report["rejected"], {"not_a_user_turn": 1, "text_mismatch": 1})
        self.assertEqual(len(items), len(TRAIN_ROWS) + len(TEST_ROWS) - 2)
        self.assertEqual(len(logs.output), 2)

    def test_item_fields(self) -> None:
        items, _ = build_items()
        by_id = {item["item_id"]: item for item in items}
        res = by_id["RES001_t02"]
        self.assertEqual(res["dialogue_id"], "RES001.json")
        self.assertEqual(res["turn_domains"], ["restaurant"])
        self.assertEqual(res["user_acts"], {"Restaurant-Inform": [["Food", "italian"]]})
        self.assertEqual((res["direct_utterance"], res["indirect_utterance"]), ("direct Italian please.", "indirect Italian please."))
        self.assertIsNone(res["quality_labels"])
        mul = by_id["MUL001_t04"]
        self.assertEqual(mul["quality_labels"], {"isacceptable_direct": True, "isacceptable_indirect": False, "quality": "Good"})
        self.assertEqual(mul["active_domains"], ["restaurant", "train"])
        self.assertTrue(is_social_only(by_id["RES001_t04"]))
        self.assertFalse(is_social_only(res))


# --------------------------------------------------------------------------- contexts


class ContextConditionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.items, cls.dialogues = build_items()
        cls.by_id = {item["item_id"]: item for item in cls.items}

    def test_exact_context_for_each_condition(self) -> None:
        item = self.by_id["RES001_t04"]
        res_turns = [Turn("user" if i % 2 == 0 else "system", raw["text"].strip()) for i, raw in enumerate(RES001["log"])]
        self.assertEqual(build_context(item, self.dialogues, "none"), [])
        self.assertEqual(build_context(item, self.dialogues, "one"), [Turn("system", "Pizza Hut fits. Shall I book?")])
        self.assertEqual(build_context(item, self.dialogues, "full"), res_turns[:4])
        self.assertEqual(build_context(item, self.dialogues, "full")[2].text, "Italian please.")  # whitespace stripped

    def test_mismatched_contexts_come_from_the_donor(self) -> None:
        item = self.by_id["MUL001_t04"]  # only HOS001 qualifies (POL001 is too short)
        self.assertEqual(item["mismatch"], {"donor_dialogue_id": "HOS001.json", "start": 0, "length": 4})
        donor = self.dialogues["HOS001.json"]
        self.assertEqual(build_context(item, self.dialogues, "mismatched"), donor[:4])
        self.assertEqual(build_context(item, self.dialogues, "mismatched_one"), [donor[3]])

    def test_first_turn_has_empty_context_in_every_condition(self) -> None:
        item = self.by_id["RES001_t00"]
        self.assertEqual(item["mismatch_status"], "not_needed")
        for condition in CONDITIONS:
            with self.subTest(condition=condition):
                self.assertEqual(build_context(item, self.dialogues, condition), [])

    def test_unknown_condition_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_context(self.by_id["RES001_t02"], self.dialogues, "half")


# --------------------------------------------------------------------------- mismatch rules


class MismatchRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.items, cls.dialogues = build_items()
        cls.parsed = parsed_dialogues()
        cls.split_of = {item["dialogue_id"]: item["split"] for item in cls.items}

    def test_every_pairing_obeys_the_rules(self) -> None:
        paired = [item for item in self.items if item["turn_index"] > 0]
        self.assertTrue(paired)
        for item in paired:
            with self.subTest(item=item["item_id"]):
                self.assertEqual(item["mismatch_status"], "ok")
                donor_id = item["mismatch"]["donor_dialogue_id"]
                t = item["turn_index"]
                window = build_context(item, self.dialogues, "mismatched")
                self.assertNotEqual(donor_id, item["dialogue_id"])
                self.assertEqual(self.split_of[donor_id], item["split"])
                donor_domains = set(bd._domains_of(self.parsed[donor_id].prefix_masks[t]))
                self.assertFalse(donor_domains & set(item["active_domains"]))
                self.assertEqual(len(window), t)
                self.assertEqual(len(window), len(build_context(item, self.dialogues, "full")))
                self.assertEqual(window[-1].speaker, "system")
                self.assertEqual(build_context(item, self.dialogues, "mismatched_one"), window[-1:])

    def test_pairing_is_deterministic_under_a_seed(self) -> None:
        first, _ = build_items(seed=11)
        second, _ = build_items(seed=11)
        self.assertEqual([item["mismatch"] for item in first], [item["mismatch"] for item in second])

    def test_seed_changes_the_choice_among_valid_donors(self) -> None:
        items, _ = build_items()
        target = next(copy.deepcopy(item) for item in items if item["item_id"] == "RES001_t02")
        donors = set()
        for seed in range(30):
            bd.pair_mismatches([target], self.parsed, self.split_of, seed)
            donors.add(target["mismatch"]["donor_dialogue_id"])
        self.assertEqual(donors, {"TRA001.json", "ATT001.json"})  # the two valid train-split donors

    def test_no_valid_donor_is_marked_unavailable(self) -> None:
        dialogues = {
            "A.json": bd.parse_multiwoz_dialogue("A.json", single_domain("hotel", 4)),
            "B.json": bd.parse_multiwoz_dialogue("B.json", single_domain("hotel", 4)),  # same domain
            "C.json": bd.parse_multiwoz_dialogue("C.json", single_domain("taxi", 4)),  # other split
        }
        item = bd.make_item(direct_row("A.json", 2, "hotel user 2"), dialogues["A.json"], "train", "exact")
        bd.pair_mismatches([item], dialogues, {"A.json": "train", "B.json": "train", "C.json": "test"}, seed=1)
        self.assertEqual(item["mismatch_status"], "unavailable")
        self.assertIsNone(item["mismatch"])
        self.assertIsNone(build_context(item, {k: v.turns for k, v in dialogues.items()}, "mismatched"))


# --------------------------------------------------------------------------- splits


class SplitTests(unittest.TestCase):
    def test_splits_are_grouped_by_dialogue(self) -> None:
        items, _ = build_items()
        dialogue_split = bd.check_split_grouping(items)
        self.assertEqual({d for d, s in dialogue_split.items() if s == "dev"}, DEV_IDS)
        self.assertEqual({d for d, s in dialogue_split.items() if s == "test"}, {"MUL001.json", "HOS001.json", "POL001.json"})
        self.assertEqual({d for d, s in dialogue_split.items() if s == "train"}, {"RES001.json", "TRA001.json", "ATT001.json"})

    def test_dialogue_in_two_splits_is_fatal(self) -> None:
        items = [{"dialogue_id": "X.json", "split": "train"}, {"dialogue_id": "X.json", "split": "test"}]
        with self.assertRaisesRegex(bd.BuildError, "X.json"):
            bd.check_split_grouping(items)


# --------------------------------------------------------------------------- CLI end to end


class EndToEndTests(unittest.TestCase):
    def run_cli(self, root: Path, out_dir: Path) -> int:
        direct_dir, multiwoz_dir = root / "direct", root / "multiwoz"
        args = ["--direct-dir", str(direct_dir), "--multiwoz-dir", str(multiwoz_dir), "--out-dir", str(out_dir), "--seed", "3"]
        # Patch basicConfig so the CLI doesn't reconfigure root logging for later tests.
        with contextlib.redirect_stdout(io.StringIO()), mock.patch("logging.basicConfig"), self.assertLogs(bd.logger, "INFO"):
            return bd.main(args)

    def test_cli_writes_loadable_and_reproducible_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture_inputs(root)
            self.assertEqual(self.run_cli(root, root / "out1"), 0)
            self.assertEqual(self.run_cli(root, root / "out2"), 0)

            items = load_items(root / "out1" / "items.jsonl")
            dialogues = load_dialogues(root / "out1" / "dialogues.jsonl")
            self.assertEqual(len(items), len(TRAIN_ROWS) + len(TEST_ROWS) - 2)
            self.assertEqual(set(dialogues), {item["dialogue_id"] for item in items})
            info = json.loads((root / "out1" / "build_info.json").read_text(encoding="utf-8"))
            self.assertEqual(info["stats"]["rows_per_split"], {"dev": 2, "test": 3, "train": 5})
            for name in ("items.jsonl", "dialogues.jsonl", "build_info.json"):
                with self.subTest(file=name):
                    self.assertEqual((root / "out1" / name).read_bytes(), (root / "out2" / name).read_bytes())


if __name__ == "__main__":
    unittest.main()
