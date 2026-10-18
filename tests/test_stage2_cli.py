"""A complete CLI scoring round trip with invented records and no model execution."""

import json
import tempfile
import unittest
from pathlib import Path

from src.evaluation import stage2
from tests.test_auto_levels import item
from tests.test_interpretation import prediction


class CliTests(unittest.TestCase):
    def test_complete_score_roundtrip_and_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            row = item("D", 2, "PRIVATE ORIGINAL", "Reserve it.", "We could use a room.",
                       acts={"Hotel-Inform": [["People", "two"]]})
            row["mismatch"] = None
            items, dialogues = root / "items.jsonl", root / "dialogues.jsonl"
            items.write_text(json.dumps(row) + "\n", encoding="utf-8")
            dialogues.write_text(json.dumps({"dialogue_id": "D.json", "turns": [
                {"speaker": "user", "text": "Earlier"}, {"speaker": "system", "text": "Question"},
                {"speaker": "user", "text": "PRIVATE ORIGINAL"}, {"speaker": "system", "text": "PRIVATE FUTURE"}]}) + "\n", encoding="utf-8")
            routed = [prediction(f"D_t02:{v}", c, prediction=v) for c in ("none", "full") for v in ("direct", "indirect")]
            oracle = [r for r in routed if r["prediction"] == "indirect"]
            paths = {name: root / f"{name}.jsonl" for name in ("routed", "oracle")}
            for name, rows in (("routed", routed), ("oracle", oracle)):
                paths[name].write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
            out = root / "metrics.json"
            argv = ["score", "--items", str(items), "--dialogues", str(dialogues), "--conditions", "none", "full",
                    "--predictions", str(paths["routed"]), "--oracle-predictions", str(paths["oracle"]),
                    "--out", str(out), "--bootstrap-samples", "10"]
            self.assertEqual(stage2.main(argv), 0)
            report = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(report["conditions"]["full"]["end_to_end"]["success"], 1)
            self.assertEqual(report["conditions"]["none"]["oracle"]["n"], 1)
            self.assertEqual(report["contrasts"]["full-none"]["n"], 2)
            self.assertEqual(len(report["inputs"]["items_sha256"]), 64)
            self.assertNotIn("PRIVATE", out.read_text(encoding="utf-8"))
            self.assertNotIn(b"\r", out.read_bytes())
            # Atomic validation: an incomplete stream must not overwrite a previous good report.
            original = out.read_bytes()
            collision = argv.copy()
            collision[collision.index("--out") + 1] = str(paths["routed"])
            before = paths["routed"].read_bytes()
            self.assertEqual(stage2.main(collision), 1)
            self.assertEqual(paths["routed"].read_bytes(), before)
            paths["oracle"].write_text("", encoding="utf-8")
            self.assertEqual(stage2.main(argv), 1)
            self.assertEqual(out.read_bytes(), original)

    def test_test_split_is_opt_in(self):
        self.assertEqual(stage2.main(["inputs", "--split", "test", "--out", "outputs/test.jsonl"]), 1)
