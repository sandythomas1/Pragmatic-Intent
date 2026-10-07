"""Evaluation contracts using invented labels and identifiers only."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from src.evaluation.run import Example, build_report, load_examples, majority_predictions, main


def example(item_id: str, dialogue: str, label: str, variant: str = "target") -> Example:
    return Example(item_id, dialogue, label, variant, "dev", "hotel")


class EvaluationTest(unittest.TestCase):
    def test_majority_holds_out_every_variant_of_the_dialogue(self) -> None:
        examples = [example("a1", "a", "L0"), example("a2", "a", "L0", "direct"),
                    example("b1", "b", "NR"), example("c1", "c", "NR")]
        rows = majority_predictions(examples)
        self.assertEqual(len(rows), 20)  # five contexts per item
        predicted = {row["item_id"]: row["prediction"] for row in rows}
        self.assertEqual(predicted["a1"], "NR")
        self.assertEqual(predicted["a2"], "NR")
        self.assertEqual(predicted["b1"], "L0")
        self.assertEqual(rows, majority_predictions(examples))

    def test_accuracy_macro_f1_and_context_slices(self) -> None:
        examples = [example("a", "d1", "L0"), example("b", "d2", "L1")]
        predictions = [{"item_id": e.item_id, "condition": c, "prediction": "L0"}
                       for c in ("none", "full") for e in examples]
        report = build_report(examples, predictions, bootstrap_samples=20, seed=7)
        self.assertEqual(report["conditions"]["none"]["accuracy"], 0.5)
        self.assertAlmostEqual(report["conditions"]["none"]["macro_f1"], (2 / 3) / 6)
        self.assertEqual(report["conditions"]["none"]["confusion"]["L1"]["L0"], 1)
        self.assertEqual(report["conditions"]["full"]["by_level"]["L1"]["accuracy"], 0)
        self.assertEqual(report, build_report(examples, predictions, bootstrap_samples=20, seed=7))

    def test_prediction_validation_prevents_silent_partial_scores(self) -> None:
        examples = [example("a", "d1", "L0"), example("b", "d2", "NR")]
        valid = [{"item_id": "a", "condition": "none", "prediction": "L0"},
                 {"item_id": "b", "condition": "none", "prediction": "NR"}]
        for predictions in (valid[:1], valid + valid[:1],
                            valid + [{"item_id": "extra", "condition": "none", "prediction": "NR"}],
                            [{**valid[0], "prediction": "?"}, valid[1]],
                            [{**row, "condition": "bad"} for row in valid]):
            with self.subTest(predictions=predictions), self.assertRaises(ValueError):
                build_report(examples, predictions)

    def test_single_dialogue_cannot_be_used_as_training_and_evaluation(self) -> None:
        with self.assertRaises(ValueError):
            majority_predictions([example("a", "d1", "L0")])

    def test_bootstrap_resamples_whole_dialogues_including_unequal_groups(self) -> None:
        examples = [example(f"a{n}", "d1", "L0") for n in range(10)] + [example("b", "d2", "NR")]
        predictions = [{"item_id": e.item_id, "condition": "none", "prediction": "L0"} for e in examples]
        report = build_report(examples, predictions)
        self.assertEqual(report["conditions"]["none"]["accuracy_ci95"], [0.0, 1.0])

    def test_cli_joins_labels_to_metadata_and_writes_reproducible_pilot(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            annotations, items = root / "labels.csv", root / "items.jsonl"
            fields = ["item_id", "dialogue_id", "turn_index", "variant", "label_final", "annotator"]
            rows = [dict(zip(fields, values)) for values in [
                ("a", "d1", 2, "target", "L0", "A1"),
                ("b", "d2", 2, "indirect", "NR", "A1"),
                ("c", "d3", 2, "direct", "?", "A1"),
            ]]
            with annotations.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            items.write_text("".join(json.dumps({"dialogue_id": d, "turn_index": 2,
                "split": "dev", "turn_domains": ["hotel"]}) + "\n" for d in ("d1", "d2", "d3")))
            examples, excluded = load_examples(annotations, items, "A1", "dev")
            self.assertEqual(len(examples), 2)
            self.assertEqual(excluded, {"undecidable": 1})
            argv = ["--annotations", str(annotations), "--items", str(items),
                    "--out-dir", str(root / "out"), "--bootstrap-samples", "20"]
            self.assertEqual(main(argv), 0)
            report_path = root / "out" / "metrics.json"
            first = report_path.read_bytes()
            report = json.loads(first)
            self.assertEqual(report["status"], "development_pilot")
            self.assertEqual(report["validation"], "leave_one_dialogue_out")
            self.assertEqual(report["excluded"], excluded)
            self.assertIsInstance(report["git_dirty"], bool)
            self.assertNotIn("utterance", report_path.read_text())
            self.assertEqual(main(argv), 0)
            self.assertEqual(first, report_path.read_bytes())
            # A requested split must never silently accept a label from another split.
            with self.assertRaises(ValueError):
                load_examples(annotations, items, "A1", "test")
            rows.append(rows[0])
            with annotations.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaises(ValueError):
                load_examples(annotations, items, "A1", "dev")


if __name__ == "__main__":
    unittest.main()
