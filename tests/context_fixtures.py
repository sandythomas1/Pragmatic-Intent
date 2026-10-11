"""Shared invented fixtures for the contextual-annotation tests (spec 003).

``ContextCase`` builds a complete temporary workspace: tiny invented MultiWOZ-shaped dialogues, a
round file, the invented Gutenberg editions from ``literary_fixtures`` and, on request, a real
spec 002 screening log produced by spec 002's own tooling. No real DIRECT, MultiWOZ or literary
text appears anywhere.
"""

from __future__ import annotations

import csv
import json
import logging
import tempfile
import unittest
from functools import partial
from pathlib import Path
from unittest import mock

from src.annotation import context as ctx
from src.annotation.levels import read_csv, write_csv
from src.data.direct_dataset import Turn
from src.literary import screening as sc
from src.literary import sources as ls
from tests import literary_fixtures as fx

DATE = "2026-10-11"
OWL = "aesop:the-owl-and-the-kettle"
HEN = "aesop:the-hen-and-the-ladder"
ROUND_HEADER = ["item_id", "dialogue_id", "turn_index", "variant", "label_initial", "label_final", "fragment", "annotator", "rubric_version"]


def make_dialogue(stem: str, user_turns: int) -> list[Turn]:
    turns: list[Turn] = []
    for n in range(user_turns):
        turns.append(Turn("user", f"{stem} user line {n}"))
        turns.append(Turn("system", f"{stem} system line {n}"))
    return turns


def make_item(dialogue_id: str, turn_index: int, split: str = "dev", mismatch_status: str = "ok") -> dict:
    stem = dialogue_id.removesuffix(".json")
    return {
        "item_id": f"{stem}_t{turn_index:02d}",
        "dialogue_id": dialogue_id,
        "turn_index": turn_index,
        "split": split,
        "mismatch_status": mismatch_status,
        "target_utterance": f"{stem} user line {turn_index // 2}",
    }


def corpus(dev: int = 12, user_turns: int = 3) -> tuple[list[dict], dict[str, list[Turn]]]:
    """``dev`` dev dialogues with ``user_turns`` user turns each, plus a train and a test dialogue."""
    items, dialogues = [], {}
    for n in range(dev):
        dialogue_id = f"DEV{n:03d}.json"
        dialogues[dialogue_id] = make_dialogue(f"DEV{n:03d}", user_turns)
        items += [make_item(dialogue_id, 2 * k) for k in range(user_turns)]
    for split in ("train", "test"):
        dialogue_id = f"{split.upper()}000.json"
        dialogues[dialogue_id] = make_dialogue(f"{split.upper()}000", user_turns)
        items += [make_item(dialogue_id, 2 * k, split=split) for k in range(user_turns)]
    return items, dialogues


def write_direct(direct_dir: Path, items: list[dict], dialogues: dict[str, list[Turn]]) -> None:
    direct_dir.mkdir(parents=True, exist_ok=True)
    with (direct_dir / "items.jsonl").open("w", encoding="utf-8") as handle:
        handle.writelines(json.dumps(item) + "\n" for item in items)
    with (direct_dir / "dialogues.jsonl").open("w", encoding="utf-8") as handle:
        for dialogue_id, turns in dialogues.items():
            record = {"dialogue_id": dialogue_id, "turns": [{"speaker": t.speaker, "text": t.text} for t in turns]}
            handle.write(json.dumps(record) + "\n")


def write_round(annotations_dir: Path, round_number: int, dialogue_id: str, turn_index: int) -> None:
    annotations_dir.mkdir(parents=True, exist_ok=True)
    with (annotations_dir / f"levels_round{round_number}.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(ROUND_HEADER)
        writer.writerow([f"r{round_number}-01", dialogue_id, str(turn_index), "target", "L1", "L1", "0", "A1", "v1"])


class ContextCase(unittest.TestCase):
    """A temporary workspace with dialogues, round 2 (DEV003 labeled) and fixture editions."""

    dev_dialogues = 10

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        raw_dir, manifest = fx.install_fixture_editions(self.root)
        self.dirs = ctx.Dirs(
            self.root / "annotations", self.root / "work", self.root / "direct", raw_dir, manifest, self.root / "literary-work"
        )
        self.items, self.dialogue_turns = corpus(dev=self.dev_dialogues)
        write_direct(self.dirs.direct_dir, self.items, self.dialogue_turns)
        write_round(self.dirs.annotations_dir, 2, "DEV003.json", 4)
        patcher = mock.patch.dict(ls.PARSERS, {"kjv_pg10": partial(ls.parse_kjv, books=fx.KJV_BOOKS)})
        patcher.start()
        self.addCleanup(patcher.stop)
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)

    def cli(self, *args: str) -> int:
        base = [
            "--annotations-dir", str(self.dirs.annotations_dir),
            "--work-dir", str(self.dirs.work_dir),
            "--direct-dir", str(self.dirs.direct_dir),
            "--raw-dir", str(self.dirs.raw_dir),
            "--manifest", str(self.dirs.manifest),
        ]  # fmt: skip
        return ctx.main([*base, *args])

    def screen(self, include: dict[str, tuple[str, str]], exclude: tuple[str, ...] = ()) -> list[dict[str, str]]:
        """Run spec 002 end to end on both fixture fables and return the committed log.

        ``include`` maps a phrase inside a proposed target to (speaker, addressee). Rows containing a
        phrase in ``exclude`` are excluded as ``no_context``. Everything else stays pending.
        """
        lit = self.dirs.literary
        editions = sc.Editions(lit)
        sc.assign_family(lit, editions, "aesop_jones1912", "fables", [OWL, HEN], "test family", DATE)
        sc.propose(lit, editions)
        rows = read_csv(lit.sheet)
        for row in rows:
            for phrase, (speaker, addressee) in include.items():
                if phrase in row["target_text"]:
                    row.update(speaker=speaker, addressee=addressee, status="include")
            if any(phrase in row["target_text"] for phrase in exclude):
                row.update(status="exclude", exclusion_reason="no_context")
        write_csv(lit.sheet, sc.SHEET_FIELDS, rows, excel=True)
        sc.export(lit, editions, "A1")
        return sc.load_log(lit)
