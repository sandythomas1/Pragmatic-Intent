"""Spec 004 check rules and manifest, using invented data only."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from typing import Any

from src.data import context_manifest as cm
from src.data.contexts import render_all
from src.data.direct_dataset import Turn
from src.stage1.data import build_examples

TEXTS = ("hello there", "how can I help", "SECRETTARGET the original", "SECRETLATER reply", "SECRETLATER bye")


def corpus_records() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    def dialogue(did: str, texts: list[str], domain: str) -> dict[str, Any]:
        return {"dialogue_id": did, "goal_domains": [domain],
                "turns": [{"speaker": "user" if i % 2 == 0 else "system", "text": t, "domains": [domain]}
                          for i, t in enumerate(texts)]}

    dialogues = [dialogue("d1.json", list(TEXTS), "hotel"),
                 dialogue("d2.json", ["a taxi please", "where to", "the station", "booked"], "taxi"),
                 dialogue("d3.json", ["a taxi please", "where to", "x", "y"], "taxi"),
                 dialogue("d4.json", ["a hotel please", "which area", "x", "y"], "hotel")]

    def item(item_id: str, did: str, turn: int, split: str = "dev", donor: str | None = None) -> dict[str, Any]:
        return {"item_id": item_id, "dialogue_id": did, "turn_index": turn, "split": split,
                "target_utterance": "SECRETTARGET the original", "direct_utterance": "Find a hotel on monday.",
                "indirect_utterance": "SECRETVARIANT a hotel would be nice.", "turn_domains": ["hotel"],
                "active_domains": ["hotel"], "user_acts": {"Hotel-Inform": [["Day", "monday"]]},
                "quality_labels": None,
                "mismatch": {"donor_dialogue_id": donor, "start": 0, "length": turn} if donor else None,
                "mismatch_status": "ok" if donor else ("not_needed" if turn == 0 else "unavailable")}

    items = [item("d1_t02", "d1.json", 2, donor="d2.json"), item("d1_t04", "d1.json", 4),
             item("d2_t00", "d2.json", 0), item("d3_t00", "d3.json", 0, split="test"), item("d4_t00", "d4.json", 0)]
    return items, dialogues


def corpus(items: list[dict[str, Any]] | None = None) -> cm.Corpus:
    default_items, dialogues = corpus_records()
    return cm.Corpus(items or default_items,
                     {d["dialogue_id"]: [Turn(t["speaker"], t["text"]) for t in d["turns"]] for d in dialogues},
                     {d["dialogue_id"]: [t["domains"] for t in d["turns"]] for d in dialogues})


def examples(source: cm.Corpus, split: str = "dev") -> list:
    return build_examples(source.items, split, require_context=True)[0]


class CheckTest(unittest.TestCase):
    def test_clean_corpus_passes_every_rule(self) -> None:
        source = corpus()
        report = cm.check_split(examples(source), source)
        self.assertEqual(report["examples"], 4)  # d1_t02 and d1_t04, two variants each
        self.assertEqual(report["failures"], dict.fromkeys(cm.RULES, 0))
        self.assertEqual(report["donor_domain_check"], "acts_only")

    def test_each_donor_corruption_fails_its_named_rule(self) -> None:
        cases = {"d3.json": "donor_split", "d1.json": "donor_distinct", "d4.json": "donor_domains",
                 "missing.json": "donor_window"}
        for donor, rule in cases.items():
            with self.subTest(rule=rule):
                items, _ = corpus_records()
                items[0]["mismatch"]["donor_dialogue_id"] = donor
                source = corpus(items)
                report = cm.check_split(examples(source), source)
                self.assertEqual(report["failures"][rule], 2, report)
                self.assertTrue(report["first"][rule].startswith("d1_t02:"))
        items, _ = corpus_records()
        items[0]["mismatch"]["length"] = 1
        source = corpus(items)
        self.assertEqual(cm.check_split(examples(source), source)["failures"]["donor_window"], 2)

    def test_a_context_containing_the_target_turn_fails_no_future(self) -> None:
        def leaky(item, target, dialogues):
            rendered = render_all(item, target, dialogues)
            full = rendered["full"]
            extra = dialogues[item["dialogue_id"]][item["turn_index"]]
            rendered["full"] = type(full)((*full.turns, extra), full.context + "\n" + extra.text, target, 0)
            return rendered

        source = corpus()
        report = cm.check_split(examples(source), source, renderer=leaky)
        self.assertEqual(report["failures"]["no_future"], 4)

    def test_a_changed_target_and_an_ignored_budget_fail(self) -> None:
        def retargeted(item, target, dialogues):
            return render_all(item, target + " SECRETLATER", dialogues)

        source = corpus()
        self.assertEqual(cm.check_split(examples(source), source, renderer=retargeted)["failures"]["target_identical"],
                         16)  # one per example and defined condition: 2 x 5 + 2 x 3
        unbudgeted = cm.check_split(examples(source), source, budget=6,
                                    renderer=lambda item, target, dialogues: render_all(item, target, dialogues))
        self.assertGreater(unbudgeted["failures"]["budget"], 0)
        self.assertEqual(cm.check_split(examples(source), source, budget=6)["failures"]["budget"], 0)


class ManifestTest(unittest.TestCase):
    def test_rows_sets_flags_and_hashes(self) -> None:
        source = corpus()
        rows, counts = cm.build_manifest(examples(source), source)
        by_id = {row["example_id"]: row for row in rows}
        self.assertEqual(list(by_id), sorted(by_id))
        self.assertEqual((by_id["d1_t02:direct"]["mismatch_set"], by_id["d1_t02:direct"]["donor_dialogue_id"]),
                         (1, "d2.json"))
        no_donor = by_id["d1_t04:direct"]
        self.assertEqual((no_donor["mismatch_set"], no_donor["exclusion"], no_donor["sha256_mismatched"]),
                         (0, "no_donor", ""))
        self.assertTrue(no_donor["sha256_full"])
        self.assertEqual((counts["genuine"], counts["mismatch"], counts["mismatch_excluded"]), (4, 2, {"no_donor": 2}))
        self.assertEqual(counts["lengths_words"]["mismatched"]["n"], 2)

    def test_bytes_are_deterministic_lf_only_and_change_with_one_character(self) -> None:
        source = corpus()
        first = cm.manifest_bytes(cm.build_manifest(examples(source), source)[0])
        self.assertEqual(first, cm.manifest_bytes(cm.build_manifest(examples(source), source)[0]))
        self.assertNotIn(b"\r", first)
        self.assertFalse(first.startswith(b"\xef\xbb\xbf"))
        changed = corpus()
        changed.dialogues["d1.json"][0] = Turn("user", "hello therE")
        rows_a = {r["example_id"]: r for r in cm.build_manifest(examples(source), source)[0]}
        rows_b = {r["example_id"]: r for r in cm.build_manifest(examples(changed), changed)[0]}
        self.assertNotEqual(rows_a["d1_t02:direct"]["sha256_full"], rows_b["d1_t02:direct"]["sha256_full"])
        self.assertEqual(rows_a["d1_t02:direct"]["sha256_mismatched"], rows_b["d1_t02:direct"]["sha256_mismatched"])
        self.assertNotEqual(first, cm.manifest_bytes(list(rows_b.values())))

    def test_a_target_that_differs_between_conditions_fails_the_build(self) -> None:
        source = corpus()
        original = cm.render_all

        def retarget_one(item, target, dialogues, budget):
            rendered = original(item, target, dialogues, budget)
            one = rendered["one"]
            rendered["one"] = type(one)(one.turns, one.context, target + "!", one.dropped)
            return rendered

        with mock.patch.object(cm, "render_all", retarget_one), self.assertRaises(ValueError):
            cm.build_manifest(examples(source), source)

    def test_target_over_budget_and_dropped_counts(self) -> None:
        source = corpus()
        counts = cm.build_manifest(examples(source), source, budget=4)[1]
        self.assertEqual(counts["target_over_budget"], 4)  # both targets (5 and 6 words) exceed 4
        self.assertEqual(counts["dropped"]["full"]["examples"], 4)

    def test_cli_writes_verifies_and_holds_no_text(self) -> None:
        items, dialogues = corpus_records()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "items.jsonl").write_text("".join(json.dumps(i) + "\n" for i in items), encoding="utf-8")
            (root / "dialogues.jsonl").write_text("".join(json.dumps(d) + "\n" for d in dialogues), encoding="utf-8")
            args = ["--split", "dev", "--items", str(root / "items.jsonl"), "--dialogues", str(root / "dialogues.jsonl"),
                    "--out-dir", str(root / "out")]
            with self.assertLogs(cm.logger, "INFO"):
                self.assertEqual(cm.main(["check", *args]), 0)
                self.assertEqual(cm.main(["manifest", *args]), 0)
                self.assertEqual(cm.main(["manifest", *args, "--verify"]), 0)
            csv_path, summary_path = root / "out" / "contexts_dev.csv", root / "out" / "contexts_dev_summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual((summary["renderer_version"], summary["budget_words"]), ("render-v1", 350))
            self.assertEqual(summary["manifest_sha256"], cm.hashlib.sha256(csv_path.read_bytes()).hexdigest())
            committed = csv_path.read_text(encoding="utf-8") + summary_path.read_text(encoding="utf-8")
            texts = [t["text"] for d in dialogues for t in d["turns"]] + [
                v for i in items for v in (i["direct_utterance"], i["indirect_utterance"], i["target_utterance"])]
            for text in [*(t for t in texts if len(t) >= 5), "monday", "SECRET"]:  # skip "x", "y"
                self.assertNotIn(text, committed)
            csv_path.write_bytes(csv_path.read_bytes().replace(b"d1_t02", b"d1_t03", 1))
            with self.assertLogs(cm.logger, "ERROR"):
                self.assertEqual(cm.main(["manifest", *args, "--verify"]), 1)
            bad = copy.deepcopy(items)
            bad[0]["mismatch"]["donor_dialogue_id"] = "d4.json"
            (root / "items.jsonl").write_text("".join(json.dumps(i) + "\n" for i in bad), encoding="utf-8")
            with self.assertLogs(cm.logger, "ERROR") as logs:
                self.assertEqual(cm.main(["check", *args]), 1)
            self.assertTrue(any("donor_domains failed" in line for line in logs.output))


if __name__ == "__main__":
    unittest.main()
