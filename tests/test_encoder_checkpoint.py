"""Encoder checkpoint/resume: an interrupted run resumes to the same weights as an uninterrupted one.

The training tests use a tiny CPU model with dropout and need torch and transformers
(the GPU environment); the fingerprint test is stdlib only.
"""

from __future__ import annotations

import argparse
import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from src.stage1.config import load_config
from src.stage1.encoder import Checkpointer, checkpoint_fingerprint, train

HAS_TORCH = all(importlib.util.find_spec(name) for name in ("torch", "transformers"))
VOCAB, CLASSES, EXAMPLES = 20, 3, 37
# 37 examples / micro-batch 4 = 10 micro-batches per epoch; accumulation 2 gives 5 steps per epoch, 10 in all.
SETTINGS = SimpleNamespace(micro_batch_size=4, grad_accum_steps=2, epochs=2, weight_decay=0.01,
                           learning_rate=1e-2, warmup_ratio=0.1, max_grad_norm=1.0)
TOTAL_STEPS = 10


class Interrupted(Exception):
    pass


def make_model(fail_after: int | None = None) -> Any:
    import torch

    class Tiny(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.embed = torch.nn.Embedding(VOCAB, 8)
            self.dropout = torch.nn.Dropout(0.3)
            self.head = torch.nn.Linear(8, CLASSES)
            self.calls, self.fail_after = 0, fail_after

        def forward(self, input_ids: Any, attention_mask: Any) -> SimpleNamespace:
            if self.fail_after is not None and self.calls >= self.fail_after:
                raise Interrupted
            self.calls += 1
            mask = attention_mask.unsqueeze(-1).float()
            pooled = (self.embed(input_ids) * mask).sum(1) / mask.sum(1)
            return SimpleNamespace(logits=self.head(self.dropout(pooled)))

    torch.manual_seed(0)  # same initial weights for every model
    return Tiny()


def features() -> tuple[list[dict[str, list[int]]], list[int]]:
    rows = []
    for i in range(EXAMPLES):
        ids = [1 + (i * 7 + j * 3) % (VOCAB - 1) for j in range(1 + i % 5)]
        rows.append({"input_ids": ids, "attention_mask": [1] * len(ids)})
    return rows, [i % CLASSES for i in range(EXAMPLES)]


def run(model: Any, checkpointer: Checkpointer | None, global_seed: int = 0) -> dict[str, Any]:
    import torch

    torch.manual_seed(global_seed)  # the dropout stream; a resume must restore it, not reuse this
    rows, labels = features()
    return train(model, rows, labels, SETTINGS, 0, torch.device("cpu"), False, 13, checkpointer)


def same_weights(a: Any, b: Any) -> bool:
    import torch

    return all(torch.equal(x, y) for x, y in zip(a.state_dict().values(), b.state_dict().values(), strict=True))


@unittest.skipUnless(HAS_TORCH, "torch/transformers not installed (uv group 'gpu')")
class CheckpointResumeTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "run" / "checkpoint.pt"
        self.reference = make_model()
        self.assertEqual(run(self.reference, None)["optimizer_steps"], TOTAL_STEPS)

    def checkpointer(self, every: int, fingerprint: dict[str, Any] | None = None) -> Checkpointer:
        return Checkpointer(self.path, every, fingerprint or {"run": "tiny", "seed": 13})

    def test_interrupted_run_resumes_to_identical_weights(self) -> None:
        # (every, micro-batches before the crash, step the resume starts from)
        cases = {"mid epoch 2": (2, 13, 6), "epoch boundary": (5, 12, 5), "first steps": (1, 3, 1)}
        for name, (every, fail_after, resume_step) in cases.items():
            with self.subTest(name):
                self.checkpointer(every).remove()
                with self.assertRaises(Interrupted):
                    run(make_model(fail_after), self.checkpointer(every))
                resumed = make_model()
                training = run(resumed, self.checkpointer(every), global_seed=999)
                self.assertEqual(training, {"optimizer_steps": TOTAL_STEPS, "resumed_at_steps": [resume_step]})
                self.assertTrue(same_weights(resumed, self.reference))

    def test_repeated_interruptions_are_all_recorded(self) -> None:
        with self.assertRaises(Interrupted):
            run(make_model(4), self.checkpointer(1))  # steps 1-2 done
        with self.assertRaises(Interrupted):
            run(make_model(6), self.checkpointer(1), global_seed=5)  # 3 more steps, to step 5
        resumed = make_model()
        self.assertEqual(run(resumed, self.checkpointer(1), global_seed=7)["resumed_at_steps"], [2, 5])
        self.assertTrue(same_weights(resumed, self.reference))

    def test_finished_training_resumes_straight_to_prediction(self) -> None:
        run(make_model(), self.checkpointer(4))
        resumed = make_model(fail_after=0)  # any forward pass would raise
        self.assertEqual(run(resumed, self.checkpointer(4))["optimizer_steps"], TOTAL_STEPS)
        self.assertTrue(same_weights(resumed, self.reference))

    def test_without_checkpointer_nothing_is_written(self) -> None:
        run(make_model(), None)
        self.assertFalse(self.path.parent.exists())

    def test_checkpoint_from_another_run_is_refused(self) -> None:
        run(make_model(), self.checkpointer(5))
        with self.assertRaisesRegex(ValueError, "different run configuration"):
            run(make_model(), self.checkpointer(5, {"run": "tiny", "seed": 42}))

    def test_corrupt_checkpoint_is_refused(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(b"not a checkpoint")
        with self.assertRaisesRegex(ValueError, "unreadable"):
            self.checkpointer(5).load()

    def test_arbitrary_pickled_objects_are_not_loaded(self) -> None:
        import torch

        self.path.parent.mkdir(parents=True)
        torch.save({"fingerprint": {"run": "tiny", "seed": 13}, "payload": argparse.Namespace(x=1)}, self.path)
        with self.assertRaisesRegex(ValueError, "unreadable"):
            self.checkpointer(5).load()

    def test_remove_deletes_checkpoint_and_partial_write(self) -> None:
        run(make_model(), self.checkpointer(5))
        self.path.with_suffix(".tmp").write_bytes(b"partial")
        self.checkpointer(5).remove()
        self.assertEqual(list(self.path.parent.iterdir()), [])


class CheckpointSettingsTest(unittest.TestCase):
    def test_context_changes_invalidate_a_checkpoint_even_if_items_do_not_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            items, dialogues = root / "items.jsonl", root / "dialogues.jsonl"
            items.write_text('{}\n', encoding="utf-8")
            dialogues.write_text('{"context": "first"}\n', encoding="utf-8")
            config_path = root / "config.toml"
            config_path.write_text('[run]\nname = "x"\nkind = "encoder"\n'
                                   '[data]\ntrain_condition = "full"\n'
                                   f'items = "{items.as_posix()}"\ndialogues = "{dialogues.as_posix()}"\n'
                                   '[encoder]\npretrained = "m"\n', encoding="utf-8")
            config = load_config(config_path)
            args = argparse.Namespace(seed=13, smoke=False)
            before = checkpoint_fingerprint(args, config, config.encoder, 100)
            dialogues.write_text('{"context": "changed"}\n', encoding="utf-8")
            self.assertNotEqual(before, checkpoint_fingerprint(args, config, config.encoder, 100))

    def test_nonpositive_interval_is_rejected(self) -> None:
        for every in (0, -5):
            with self.subTest(every), self.assertRaises(ValueError):
                Checkpointer(Path("unused.pt"), every, {})

    def test_fingerprint_separates_runs_and_batch_layouts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            items = Path(directory) / "items.jsonl"
            items.write_text('{"item_id": "a"}\n', encoding="utf-8")
            dialogues = Path(directory) / "dialogues.jsonl"
            dialogues.write_text('{}\n', encoding="utf-8")
            path = Path(directory) / "config.toml"
            path.write_text('[run]\nname = "x"\nkind = "encoder"\n[data]\ntrain_condition = "full"\n'
                            f'items = "{items.as_posix()}"\n'
                            f'dialogues = "{dialogues.as_posix()}"\n'
                            '[encoder]\npretrained = "m"\nbatch_size = 32\nmicro_batch_size = 16\n', encoding="utf-8")

            def fingerprint(seed: int = 13, micro_batch: int = 16, n_train: int = 100) -> dict[str, Any]:
                config = load_config(path, {"encoder": {"micro_batch_size": micro_batch}})
                return checkpoint_fingerprint(argparse.Namespace(seed=seed, smoke=False), config,
                                              config.encoder, n_train)

            self.assertEqual(fingerprint(), fingerprint())
            for changed in (fingerprint(seed=42), fingerprint(micro_batch=4), fingerprint(n_train=99)):
                self.assertNotEqual(changed, fingerprint())
            before = fingerprint()
            items.write_text('{"item_id": "b"}\n', encoding="utf-8")
            self.assertNotEqual(fingerprint(), before)


if __name__ == "__main__":
    unittest.main()
