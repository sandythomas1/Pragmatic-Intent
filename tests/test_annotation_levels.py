"""Tests for annotation round sampling, labeling, and export.

Tiny invented items only: no real DIRECT/MultiWOZ text.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.annotation import levels as lv


def item(dialogue_id: str, turn_index: int, split: str = "dev", mismatch_status: str = "ok") -> dict:
    stem = dialogue_id.removesuffix(".json")
    return {
        "item_id": f"{stem}_t{turn_index:02d}",
        "dialogue_id": dialogue_id,
        "turn_index": turn_index,
        "split": split,
        "mismatch_status": mismatch_status,
        "target_utterance": f"{stem} {turn_index} target",
        "direct_utterance": f"{stem} {turn_index} direct",
        "indirect_utterance": f"{stem} {turn_index} indirect",
    }


ITEMS = [item(f"D{n:03d}.json", 2 * (n % 3) + 2) for n in range(12)] + [
    item("ZERO.json", 0),
    item("NODONOR.json", 4, mismatch_status="unavailable"),
    item("TEST.json", 2, split="test"),
]


class RoundTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.items_path = root / "items.jsonl"
        self.items_path.write_text("".join(json.dumps(record) + "\n" for record in ITEMS), encoding="utf-8")
        self.labeling_dir = root / "labeling"
        self.annotations_dir = root / "annotations"
        self.annotations_dir.mkdir()
        self.common = ["--labeling-dir", str(self.labeling_dir), "--annotations-dir", str(self.annotations_dir)]

    def run_cli(self, *args: str) -> int:
        with self.assertLogs(lv.logger, level="INFO"):
            return lv.main([*self.common, *args])

    def sample(self, round_number: int = 2, triples: int = 4, seed: int = 1) -> int:
        return self.run_cli("sample", "--round", str(round_number), "--split", "dev", "--triples", str(triples), "--seed", str(seed), "--items", str(self.items_path))

    def paths(self, round_number: int = 2) -> lv.Paths:
        return lv.round_paths(round_number, self.labeling_dir, self.annotations_dir)

    def label_all(self, answers: list[str], round_number: int = 2, annotator: str = "A1") -> list[str]:
        args = lv._parse_args([*self.common, "label", "--round", str(round_number), "--annotator", annotator])
        feed = iter(answers)
        output: list[str] = []
        lv.label(args, read_line=lambda _prompt: next(feed), write=output.append)
        return output

    def test_sample_is_blinded_shuffled_and_whole_triples(self) -> None:
        self.assertEqual(self.sample(), 0)
        sheet = lv.read_csv(self.paths().sheet)
        key = lv.read_csv(self.paths().key)
        self.assertEqual(list(sheet[0]), ["item_id", "utterance"])
        self.assertEqual([row["item_id"] for row in sheet], [f"r2-{n:02d}" for n in range(1, 13)])
        triples: dict[tuple[str, str], set[str]] = {}
        for row in key:
            triples.setdefault((row["dialogue_id"], row["turn_index"]), set()).add(row["variant"])
        self.assertEqual(len(triples), 4)
        self.assertTrue(all(variants == set(lv.VARIANTS) for variants in triples.values()))
        self.assertNotEqual([row["variant"] for row in key], list(lv.VARIANTS) * 4, "variants should be shuffled")
        info = json.loads(self.paths().sample_info.read_text(encoding="utf-8"))
        self.assertEqual(info["eligible_triples"], 12)

    def test_sample_skips_turn_zero_missing_donor_other_split_and_labeled_turns(self) -> None:
        (self.annotations_dir / "levels_round1.csv").write_text(
            "item_id,dialogue_id,turn_index,variant,label_initial,label_final,fragment,annotator,rubric_version\n"
            "r1-01,D000.json,2,target,L0,L0,0,A1,v1\n",
            encoding="utf-8",
        )
        self.assertEqual(self.sample(triples=11), 0)
        dialogues = {row["dialogue_id"] for row in lv.read_csv(self.paths().key)}
        self.assertEqual(len(dialogues), 11)
        self.assertFalse(dialogues & {"ZERO.json", "NODONOR.json", "TEST.json", "D000.json"})

    def test_sample_is_deterministic(self) -> None:
        self.sample(round_number=2)
        self.sample(round_number=3)
        first = [row["dialogue_id"] for row in lv.read_csv(self.paths(2).key)]
        again = lv.draw_round(lv.eligible_items(ITEMS, "dev", set()), 2, 4, 1)[1]
        self.assertEqual(first, [row["dialogue_id"] for row in again])

    def test_sample_refuses_to_overwrite_a_round(self) -> None:
        self.assertEqual(self.sample(), 0)
        with self.assertLogs(lv.logger, level="ERROR"):
            self.assertEqual(lv.main([*self.common, "sample", "--round", "2", "--split", "dev", "--triples", "1", "--items", str(self.items_path)]), 1)

    def test_parse_answer(self) -> None:
        self.assertEqual(lv.parse_answer("2"), lv.Answer("L2", False, ""))
        self.assertEqual(lv.parse_answer("if"), lv.Answer("INF", True, ""))
        self.assertEqual(lv.parse_answer("? unclear 'it'"), lv.Answer("?", False, "unclear 'it'"))
        self.assertEqual(lv.parse_answer(" b "), "b")
        for invalid in ("", "4", "x", "ff", "L2"):
            self.assertIsNone(lv.parse_answer(invalid), invalid)

    def test_label_saves_resumes_and_goes_back(self) -> None:
        self.sample(triples=1)
        self.label_all(["0", "bogus", "1", "b", "3 a note", "q"])
        rows = lv.read_csv(self.paths().labels("A1"))
        self.assertEqual([row["label"] for row in rows], ["L0", "L3", ""])
        self.assertEqual(rows[1]["notes"], "a note")

        self.label_all(["nf"])
        rows = lv.read_csv(self.paths().labels("A1"))
        self.assertEqual([(row["label"], row["fragment"]) for row in rows], [("L0", "0"), ("L3", "0"), ("NR", "1")])

    def test_export_writes_ids_and_labels_without_text(self) -> None:
        self.sample(triples=1)
        self.label_all(["0", "if note quoting the utterance", "2"])
        self.assertEqual(self.run_cli("export", "--round", "2", "--annotator", "A1", "--rubric", "v1"), 0)
        exported = lv.read_csv(self.paths().export_csv)
        self.assertEqual(list(exported[0]), list(lv.EXPORT_FIELDS))
        self.assertEqual([row["label_initial"] for row in exported], ["L0", "INF", "L2"])
        self.assertEqual([row["label_final"] for row in exported], ["L0", "INF", "L2"])
        text = self.paths().export_csv.read_text(encoding="utf-8")
        for row in lv.read_csv(self.paths().sheet):
            self.assertNotIn(row["utterance"], text)
        self.assertNotIn("note", text)

        self.label_all(["1", "1", "1"], annotator="A2")
        self.assertEqual(self.run_cli("export", "--round", "2", "--annotator", "A2", "--rubric", "v1"), 0)
        self.assertEqual(len(lv.read_csv(self.paths().export_csv)), 6)
        with self.assertLogs(lv.logger, level="ERROR"):
            self.assertEqual(lv.main([*self.common, "export", "--round", "2", "--annotator", "A2", "--rubric", "v1"]), 1)

    def test_excel_sheet_round_trip(self) -> None:
        self.sample(triples=1)
        self.assertEqual(self.run_cli("sheet", "--round", "2", "--annotator", "A1"), 0)
        labels_path = self.paths().labels("A1")
        raw = labels_path.read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"), "Excel needs a BOM to decode UTF-8")
        rows = lv.read_csv(labels_path)
        self.assertEqual(list(rows[0]), list(lv.EXCEL_FIELDS))

        # As Excel saves it: CRLF, the utterance column kept, mixed-case labels, blank fragments.
        filled = ["item_id,utterance,label,fragment,notes"]
        for row, (value, fragment) in zip(rows, [("l2", ""), ("inf", "1"), ("2", "0")]):
            filled.append(f"{row['item_id']},{row['utterance']},{value},{fragment},")
        labels_path.write_bytes(b"\xef\xbb\xbf" + "\r\n".join(filled).encode("utf-8") + b"\r\n")

        self.assertEqual(self.run_cli("export", "--round", "2", "--annotator", "A1", "--rubric", "v1"), 0)
        exported = lv.read_csv(self.paths().export_csv)
        self.assertEqual([(row["label_initial"], row["fragment"]) for row in exported], [("L2", "0"), ("INF", "1"), ("L2", "0")])

        with self.assertLogs(lv.logger, level="ERROR"):
            self.assertEqual(lv.main([*self.common, "sheet", "--round", "2", "--annotator", "A1"]), 1)

    def test_export_rejects_invalid_and_non_utf8_sheets(self) -> None:
        self.sample(triples=1)
        self.run_cli("sheet", "--round", "2", "--annotator", "A1")
        labels_path = self.paths().labels("A1")
        rows = lv.read_csv(labels_path)
        for row in rows:
            row.update(label="L2", fragment="yes")
        lv.write_csv(labels_path, lv.EXCEL_FIELDS, rows, excel=True)
        with self.assertLogs(lv.logger, level="ERROR") as logs:
            self.assertEqual(lv.main([*self.common, "export", "--round", "2", "--annotator", "A1", "--rubric", "v1"]), 1)
        self.assertIn("fragment", logs.output[0])

        labels_path.write_bytes("item_id,label,fragment,notes\nr2-01,L2,,caf\xe9\n".encode("latin-1"))
        with self.assertLogs(lv.logger, level="ERROR") as logs:
            self.assertEqual(lv.main([*self.common, "export", "--round", "2", "--annotator", "A1", "--rubric", "v1"]), 1)
        self.assertIn("CSV UTF-8", logs.output[0])
        self.assertFalse(self.paths().export_csv.exists())

    def test_export_refuses_incomplete_labels(self) -> None:
        self.sample(triples=1)
        self.label_all(["0", "q"])
        with self.assertLogs(lv.logger, level="ERROR"):
            self.assertEqual(lv.main([*self.common, "export", "--round", "2", "--annotator", "A1", "--rubric", "v1"]), 1)
        self.assertFalse(self.paths().export_csv.exists())


if __name__ == "__main__":
    unittest.main()
