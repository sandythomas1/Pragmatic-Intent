"""Stage 1 policy, config, scoring and runner contracts, using invented data only."""

from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from src.data.direct_dataset import CONDITIONS, Turn
from src.evaluation.metrics import paired_bootstrap_difference
from src.evaluation.stage1 import build_report, load_levels
from src.stage1 import runner
from src.stage1.config import load_config
from src.stage1.data import Stage1Example, build_examples, model_inputs, render_context
from src.stage1.encoder import encode
from src.stage1.env_check import has_kernels

INFORM = {"Hotel-Inform": [["Area", "north"]]}
THANKS = {"general-thank": [["none", "none"]]}
DIALOGUES = {
    "d1": [Turn("user", "u0"), Turn("system", "s1"), Turn("user", "u2"), Turn("system", "s3"), Turn("user", "u4")],
    "d2": [Turn("user", "v0"), Turn("system", "w1"), Turn("user", "v2"), Turn("system", "w3")],
}


def item(item_id: str, dialogue: str = "d1", turn: int = 2, split: str = "dev", acts: Any = INFORM,
         direct: str = "Book the hotel.", indirect: str = "A hotel would be nice.",
         quality: Any = None, donor: bool = True) -> dict[str, Any]:
    return {"item_id": item_id, "dialogue_id": dialogue, "turn_index": turn, "split": split,
            "target_utterance": "original", "direct_utterance": direct, "indirect_utterance": indirect,
            "turn_domains": ["hotel"], "user_acts": acts, "quality_labels": quality,
            "mismatch": {"donor_dialogue_id": "d2", "start": 0, "length": turn} if donor and turn else None}


def example(example_id: str, dialogue: str, label: str, variant: str = "direct") -> Stage1Example:
    return Stage1Example(example_id, example_id.split(":")[0], dialogue, 2, variant, "text", label, "hotel")


class PolicyTest(unittest.TestCase):
    def test_weak_labels_follow_the_documented_policy(self) -> None:
        items = [item("a"), item("b", acts=THANKS), item("c", acts={}), item("d", direct="Same.", indirect=" same. "),
                 item("e", split="train"),
                 item("f", quality={"isacceptable_direct": True, "isacceptable_indirect": False})]
        examples, excluded = build_examples(items, "dev")
        self.assertEqual([(e.example_id, e.label) for e in examples],
                         [("a:direct", "direct"), ("a:indirect", "indirect"),
                          ("b:direct", "no_request"), ("b:indirect", "no_request"), ("f:direct", "direct")])
        self.assertEqual(excluded, {"identical_paraphrases": 1, "no_user_acts": 1, "unacceptable_indirect": 1})
        self.assertNotIn("original", {e.text for e in examples})

    def test_comparable_filter_drops_turn_zero_and_missing_donors(self) -> None:
        examples, excluded = build_examples([item("a"), item("b", turn=0), item("c", donor=False)], "dev",
                                            require_comparable=True)
        self.assertEqual({e.item_id for e in examples}, {"a"})
        self.assertEqual(excluded, {"not_comparable": 2})

    def test_unknown_policy_and_duplicate_items_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_examples([item("a")], "dev", policy="variants_v0")
        with self.assertRaises(ValueError):
            build_examples([item("a"), item("a")], "dev")

    def test_context_is_original_dialogue_and_utterance_is_the_paraphrase(self) -> None:
        items = [item("a", turn=4)]
        examples, _ = build_examples(items, "dev")
        by_id = {i["item_id"]: i for i in items}
        expected = {"none": "", "one": "System: s3", "full": "User: u0\nSystem: s1\nUser: u2\nSystem: s3",
                    "mismatched": "User: v0\nSystem: w1\nUser: v2\nSystem: w3", "mismatched_one": "System: w3"}
        for condition, context in expected.items():
            self.assertEqual(model_inputs(examples, by_id, DIALOGUES, condition)[1],
                             (context, "A hotel would be nice."))
        no_donor = [item("b", donor=False)]
        self.assertEqual(model_inputs(build_examples(no_donor, "dev")[0], {"b": no_donor[0]}, DIALOGUES,
                                      "mismatched"), [None, None])
        self.assertEqual(render_context([]), "")


class ConfigTest(unittest.TestCase):
    def write(self, text: str) -> Path:
        handle = tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False)
        handle.write(text)
        handle.close()
        self.addCleanup(Path(handle.name).unlink)
        return Path(handle.name)

    BASE = '[run]\nname = "x"\nkind = "encoder"\n[data]\ntrain_condition = "full"\n' \
           '[encoder]\npretrained = "m"\nbatch_size = 32\nmicro_batch_size = 16\n'

    def test_overrides_are_applied_and_accumulation_derived(self) -> None:
        config = load_config(self.write(self.BASE), {"data": {"train_condition": "one"},
                                                     "encoder": {"micro_batch_size": 4, "epochs": None}})
        self.assertEqual((config.data.train_condition, config.encoder.grad_accum_steps), ("one", 8))
        self.assertEqual(config.encoder.epochs, 2)
        self.assertEqual(config.data.eval_conditions, CONDITIONS)

    def test_invalid_configs_fail_loudly(self) -> None:
        cases = {
            "typo": self.BASE + "learning_rat = 1e-5\n",
            "unknown table": self.BASE + "[trainer]\nx = 1\n",
            "indivisible batch": self.BASE.replace("micro_batch_size = 16", "micro_batch_size = 12"),
            "bad condition": self.BASE.replace('"full"', '"half"'),
            "test without flag": self.BASE.replace('train_condition = "full"',
                                                   'train_condition = "full"\neval_split = "test"'),
            "same split": self.BASE.replace('train_condition = "full"', 'train_condition = "full"\neval_split = "train"'),
            "tfidf context without context": '[run]\nname = "t"\nkind = "tfidf"\n[data]\ntrain_condition = "none"\n'
                                             '[tfidf]\nuse_context = true\n',
            "missing section": '[run]\nname = "t"\nkind = "tfidf"\n[data]\ntrain_condition = "none"\n',
        }
        for name, text in cases.items():
            with self.subTest(name), self.assertRaises(ValueError):
                load_config(self.write(text))

    def test_test_split_needs_explicit_permission(self) -> None:
        path = self.write(self.BASE.replace('train_condition = "full"', 'train_condition = "full"\neval_split = "test"'))
        self.assertEqual(load_config(path, allow_test=True).data.eval_split, "test")

    def test_config_hash_tracks_resolved_values(self) -> None:
        path = self.write(self.BASE)
        self.assertEqual(load_config(path).sha256(), load_config(path).sha256())
        self.assertNotEqual(load_config(path).sha256(),
                            load_config(path, {"encoder": {"micro_batch_size": 8}}).sha256())


class ScoringTest(unittest.TestCase):
    EXAMPLES = [example("a:direct", "d1", "direct"), example("a:indirect", "d1", "indirect", "indirect"),
                example("b:direct", "d2", "no_request"), example("b:indirect", "d2", "no_request", "indirect")]

    def rows(self, condition: str, predictions: list[str]) -> list[dict[str, str]]:
        return [{"example_id": e.example_id, "condition": condition, "prediction": p}
                for e, p in zip(self.EXAMPLES, predictions)]

    def test_metrics_and_paired_context_contrast(self) -> None:
        predictions = (self.rows("none", ["direct", "direct", "direct", "no_request"])
                       + self.rows("full", ["direct", "indirect", "no_request", "no_request"]))
        report = build_report(self.EXAMPLES, predictions, bootstrap_samples=50, seed=3)
        self.assertEqual(report["conditions"]["none"]["accuracy"], 0.5)
        self.assertEqual(report["conditions"]["full"]["accuracy"], 1.0)
        self.assertEqual(report["conditions"]["none"]["by_variant"]["indirect"]["accuracy"], 0.5)
        contrast = report["contrasts"]["full-none"]
        self.assertEqual(contrast["difference"], 0.5)
        self.assertEqual(contrast["by_variant"]["direct"]["difference"], 0.5)
        self.assertEqual(contrast["by_variant"]["indirect"]["difference"], 0.5)
        self.assertEqual(list(report["contrasts"]), ["full-none"])
        self.assertEqual(report, build_report(self.EXAMPLES, predictions, bootstrap_samples=50, seed=3))

    def test_partial_duplicate_or_invalid_predictions_fail(self) -> None:
        valid = self.rows("none", ["direct"] * 4)
        for predictions in (valid[:3], valid + valid[:1], [{**valid[0], "prediction": "L0"}] + valid[1:],
                            [{**row, "condition": "half"} for row in valid],
                            valid + [{"example_id": "z:direct", "condition": "none", "prediction": "direct"}]):
            with self.subTest(predictions=predictions), self.assertRaises(ValueError):
                build_report(self.EXAMPLES, predictions)

    def test_identical_conditions_have_zero_difference(self) -> None:
        result = paired_bootstrap_difference([("d1", True, True), ("d2", False, False)], 20, 1)
        self.assertEqual((result["difference"], result["ci95"]), (0.0, [0.0, 0.0]))

    def test_human_levels_join_by_turn_variant_and_reject_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "levels.csv"
            header = "item_id,dialogue_id,turn_index,variant,label_initial,label_final,fragment,annotator,rubric_version\n"
            path.write_text(header + "r-1,d1,2,indirect,L2,l2,0,A1,v1\nr-2,d1,2,target,L0,L0,0,A1,v1\n"
                            "r-3,d2,2,direct,?,?,0,A1,v1\nr-4,d2,2,direct,L1,L1,0,A2,v1\n", encoding="utf-8")
            levels = load_levels([path])
            self.assertEqual(levels, {("d1", 2, "indirect"): "L2", ("d1", 2, "target"): "L0"})
            report = build_report(self.EXAMPLES, self.rows("none", ["direct"] * 4), levels, bootstrap_samples=5)
            self.assertEqual(report["n_with_human_level"], 1)
            self.assertEqual(report["conditions"]["none"]["by_human_level"]["L2"]["accuracy"], 0.0)
            conflict = Path(tmp) / "conflict.csv"
            conflict.write_text(header + "r-9,d1,2,indirect,L3,L3,0,A1,v1\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_levels([path, conflict])


class RunnerTest(unittest.TestCase):
    def test_prediction_rows_break_ties_toward_the_first_label(self) -> None:
        rows = runner.prediction_rows(ScoringTest.EXAMPLES[:2], "none", [[0.4, 0.4, 0.2], [0.1, 0.2, 0.7]])
        self.assertEqual([r["prediction"] for r in rows], ["direct", "no_request"])
        with self.assertRaises(ValueError):
            runner.prediction_rows(ScoringTest.EXAMPLES[:2], "none", [[1.0, 0.0, 0.0]])

    def test_prepare_and_finish_write_ids_only_and_log_one_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            items = [item("t1", split="train"), item("t2", split="train", acts=THANKS),
                     item("t3", split="train", turn=0), item("t4", split="train", donor=False),
                     item("e1", turn=4), item("e2", turn=0)]
            (root / "items.jsonl").write_text("".join(json.dumps(i) + "\n" for i in items), encoding="utf-8")
            (root / "dialogues.jsonl").write_text("".join(
                json.dumps({"dialogue_id": d, "turns": [{"speaker": t.speaker, "text": t.text} for t in turns]}) + "\n"
                for d, turns in DIALOGUES.items()), encoding="utf-8")
            config_path = root / "run.toml"
            config_path.write_text(f'[run]\nname = "probe"\nkind = "tfidf"\nbootstrap_samples = 10\n'
                                   f'[data]\ntrain_condition = "mismatched"\nitems = "{(root / "items.jsonl").as_posix()}"\n'
                                   f'dialogues = "{(root / "dialogues.jsonl").as_posix()}"\n[tfidf]\nuse_context = true\n',
                                   encoding="utf-8")
            args = argparse.Namespace(config=config_path, seed=1, train_condition=None, machine="test",
                                      out_root=root / "out", results=root / "results.jsonl",
                                      allow_test=False, smoke=False)
            config = runner.load(args, {})
            prepared = runner.prepare(config)
            self.assertEqual(len(prepared.train), 6)  # turn-0 train items keep their empty context
            self.assertEqual(prepared.counts["train_excluded"]["no_mismatch_donor"], 2)
            self.assertEqual([e.example_id for e in prepared.eval], ["e1:direct", "e1:indirect"])
            self.assertEqual(set(prepared.eval_inputs), set(CONDITIONS))
            predictions = [row for condition in CONDITIONS for row in
                           runner.prediction_rows(prepared.eval, condition, [[0.9, 0.1, 0.0]] * 2)]
            out = runner.finish(args, config, prepared, predictions, {"name": "fake"}, started=0.0)
            self.assertEqual(out, root / "out" / "probe" / "train-mismatched" / "seed1")
            written = (out / "predictions.jsonl").read_text(encoding="utf-8")
            self.assertNotIn("hotel would be nice", written)
            record = json.loads((root / "results.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(record["conditions"]["full"]["accuracy"], 0.5)
            self.assertEqual(record["machine"], "test")
            self.assertNotIn("hostname", json.dumps(record))
            self.assertIn("hostname", json.loads((out / "metrics.json").read_text(encoding="utf-8"))["local"])


class FakeTokenizer:
    def __call__(self, first: list[str], second: list[str] | None = None, **kwargs: Any) -> dict[str, list]:
        texts = first if second is None else [f"{a}|{b}" for a, b in zip(first, second)]
        return {"input_ids": [[len(t)] for t in texts], "text": texts}


class EncoderHelpersTest(unittest.TestCase):
    def test_encode_keeps_order_and_uses_single_sequences_without_context(self) -> None:
        encoded = encode(FakeTokenizer(), [("ctx", "a"), ("", "b"), ("c2", "d")], max_length=16)
        self.assertEqual([e["text"] for e in encoded], ["ctx|a", "b", "c2|d"])

    def test_kernel_compatibility_follows_cuda_binary_rules(self) -> None:
        cu128 = ["sm_75", "sm_80", "sm_86", "sm_90", "sm_100", "sm_120", "compute_120"]
        self.assertTrue(has_kernels((8, 9), cu128))  # RTX 4090 runs sm_86 code
        self.assertTrue(has_kernels((12, 0), cu128))  # RTX 5060
        self.assertFalse(has_kernels((12, 0), ["sm_80", "sm_86", "sm_90", "compute_90"]))


if __name__ == "__main__":
    unittest.main()
