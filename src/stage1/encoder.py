"""Fine-tune a transformer cross-encoder for Stage 1 (GPU).

Input is ``[CLS] context [SEP] utterance [SEP]``, or the utterance alone when the
context is empty. Context is truncated from the left, so the turns nearest the
target survive; the utterance is never truncated. Training uses fp32 master
weights with bf16 autocast, which the RTX 5060 and RTX 5090 (both sm_120) and
the RTX 4090 (sm_89) support. The effective batch size comes from the config. On
a smaller GPU, lower ``--micro-batch-size``; gradient accumulation keeps the
optimization the same.

With ``--checkpoint-every N`` the full training state is saved to the run's output
folder every N optimizer steps and once training ends. Rerunning the same command
resumes from it with the same batches and dropout stream; the checkpoint is
deleted once the run's outputs are written.

    python -m src.stage1.encoder --config configs/stage1/encoder_deberta_v3_large.toml \\
        --seed 13 --train-condition full --machine lab-5090 --checkpoint-every 250
    python -m src.stage1.encoder --config configs/stage1/encoder_deberta_v3_base.toml \\
        --seed 13 --train-condition full --machine rtx5060-wsl --micro-batch-size 8 --smoke
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import pickle
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from src.stage1 import provenance, runner
from src.stage1.config import EncoderConfig, RunConfig
from src.stage1.data import STAGE1_LABELS

logger = logging.getLogger(__name__)
Features = dict[str, list[int]]
PAD_MULTIPLE = 8
TOKENIZE_CHUNK = 4096
CHECKPOINT_NAME = "checkpoint.pt"


class Checkpointer:
    """Atomic save/restore of training state at optimizer-step boundaries.

    The fingerprint names the run (recipe, seed, data and batch layout); a checkpoint
    with a different fingerprint is refused, never silently resumed.
    """

    def __init__(self, path: Path, every: int, fingerprint: dict[str, Any]) -> None:
        if every < 1:
            raise ValueError("--checkpoint-every must be a positive number of optimizer steps")
        self.path, self.every, self.fingerprint = path, every, fingerprint

    def due(self, step: int, total_steps: int) -> bool:
        return step % self.every == 0 or step == total_steps

    def load(self) -> dict[str, Any] | None:
        import torch

        if not self.path.exists():
            return None
        try:  # weights_only: tensors and plain containers only, no arbitrary unpickling
            state = torch.load(self.path, map_location="cpu", weights_only=True)
        except (RuntimeError, EOFError, pickle.UnpicklingError) as exc:
            raise ValueError(f"checkpoint {self.path} is unreadable ({exc}); delete it to restart the run") from exc
        if not isinstance(state, dict) or state.get("fingerprint") != self.fingerprint:
            raise ValueError(f"checkpoint {self.path} was written by a different run configuration; "
                             "delete it to restart the run")
        return state

    def save(self, state: dict[str, Any]) -> None:
        import torch

        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        torch.save({**state, "fingerprint": self.fingerprint}, temporary)
        os.replace(temporary, self.path)  # a crash mid-write leaves the previous checkpoint intact

    def remove(self) -> None:
        self.path.unlink(missing_ok=True)
        self.path.with_suffix(".tmp").unlink(missing_ok=True)


def rng_state(generator: Any) -> dict[str, Any]:
    import torch

    return {"data": generator.get_state(), "torch": torch.get_rng_state(),
            "cuda": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else []}


def restore_rng(generator: Any, state: dict[str, Any]) -> None:
    import torch

    generator.set_state(state["data"])
    torch.set_rng_state(state["torch"])
    if state["cuda"]:
        torch.cuda.set_rng_state_all(state["cuda"])


def encode(tokenizer: Any, pairs: Sequence[runner.Pair], max_length: int) -> list[Features]:
    """Tokenize without padding; pairs with empty context become single sequences."""
    encoded: list[Features | None] = [None] * len(pairs)
    for has_context in (True, False):
        indices = [i for i, (context, _) in enumerate(pairs) if bool(context) == has_context]
        for start in range(0, len(indices), TOKENIZE_CHUNK):
            chunk = indices[start : start + TOKENIZE_CHUNK]
            utterances = [pairs[i][1] for i in chunk]
            if has_context:
                batch = tokenizer([pairs[i][0] for i in chunk], utterances,
                                  truncation="only_first", max_length=max_length)
            else:
                batch = tokenizer(utterances, truncation=True, max_length=max_length)
            for offset, i in enumerate(chunk):
                encoded[i] = {key: batch[key][offset] for key in batch.keys()}
    return encoded  # type: ignore[return-value]


def collate(features: Sequence[Features], pad_id: int, labels: Sequence[int] | None = None) -> dict[str, Any]:
    """Right-pad to a multiple of 8 so bf16 tensor cores get aligned shapes."""
    import torch

    width = math.ceil(max(len(f["input_ids"]) for f in features) / PAD_MULTIPLE) * PAD_MULTIPLE
    batch = {}
    for key in features[0]:
        fill = pad_id if key == "input_ids" else 0
        batch[key] = torch.tensor([f[key] + [fill] * (width - len(f[key])) for f in features])
    if labels is not None:
        batch["labels"] = torch.tensor(labels)
    return batch


def train(model: Any, features: list[Features], labels: list[int], settings: EncoderConfig,
          pad_id: int, device: Any, use_bf16: bool, seed: int,
          checkpointer: Checkpointer | None = None) -> dict[str, Any]:
    import torch
    import torch.nn.functional as F
    from transformers import get_linear_schedule_with_warmup

    generator = torch.Generator().manual_seed(seed)
    accumulation = settings.grad_accum_steps
    micro_batches_per_epoch = math.ceil(len(features) / settings.micro_batch_size)
    steps_per_epoch = math.ceil(micro_batches_per_epoch / accumulation)
    total_steps = steps_per_epoch * settings.epochs
    decay = [p for p in model.parameters() if p.ndim >= 2]
    no_decay = [p for p in model.parameters() if p.ndim < 2]  # biases and norms
    optimizer = torch.optim.AdamW([{"params": decay, "weight_decay": settings.weight_decay},
                                   {"params": no_decay, "weight_decay": 0.0}], lr=settings.learning_rate)
    scheduler = get_linear_schedule_with_warmup(optimizer, int(settings.warmup_ratio * total_steps), total_steps)
    logger.info("training: %d examples, %d epochs, %d optimizer steps (micro-batch %d x %d accumulation)",
                len(features), settings.epochs, total_steps, settings.micro_batch_size, accumulation)

    step, start_epoch, start_micro, order, resumed_at = 0, 0, 0, None, []
    saved = checkpointer.load() if checkpointer else None
    if saved is not None:
        model.load_state_dict(saved["model"])
        optimizer.load_state_dict(saved["optimizer"])
        scheduler.load_state_dict(saved["scheduler"])
        restore_rng(generator, saved["rng"])
        step, start_epoch, start_micro, order = saved["step"], saved["epoch"], saved["micro"], saved["order"]
        resumed_at = [*saved["resumed_at"], step]
        logger.info("resumed from %s at optimizer step %d/%d", checkpointer.path, step, total_steps)

    model.train()
    window_examples, window_start = 0, time.time()
    window_loss = torch.zeros((), device=device)  # summed on device; read only when logging
    for epoch in range(start_epoch, settings.epochs):
        if order is None:
            order = torch.randperm(len(features), generator=generator).tolist()
        for micro in range(start_micro, micro_batches_per_epoch):
            chunk = order[micro * settings.micro_batch_size : (micro + 1) * settings.micro_batch_size]
            batch = collate([features[i] for i in chunk], pad_id, [labels[i] for i in chunk])
            batch = {key: value.to(device, non_blocking=True) for key, value in batch.items()}
            targets = batch.pop("labels")
            with torch.autocast(device_type=device.type, dtype=torch.bfloat16, enabled=use_bf16):
                logits = model(**batch).logits
            loss = F.cross_entropy(logits.float(), targets)
            (loss / accumulation).backward()
            window_loss += loss.detach() * len(chunk)
            window_examples += len(chunk)
            if (micro + 1) % accumulation and micro + 1 != micro_batches_per_epoch:
                continue
            torch.nn.utils.clip_grad_norm_(model.parameters(), settings.max_grad_norm)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad(set_to_none=True)
            step += 1
            if step % 100 == 0 or step == total_steps:
                elapsed = time.time() - window_start
                logger.info("epoch %d step %d/%d loss %.4f lr %.2e %.0f ex/s", epoch + 1, step, total_steps,
                            window_loss.item() / window_examples, scheduler.get_last_lr()[0],
                            window_examples / elapsed)
                window_loss.zero_()
                window_examples, window_start = 0, time.time()
            if checkpointer and checkpointer.due(step, total_steps):
                epoch_done = micro + 1 == micro_batches_per_epoch
                saved_at = time.time()
                checkpointer.save({
                    "model": model.state_dict(), "optimizer": optimizer.state_dict(),
                    "scheduler": scheduler.state_dict(), "rng": rng_state(generator), "step": step,
                    "epoch": epoch + 1 if epoch_done else epoch, "micro": 0 if epoch_done else micro + 1,
                    "order": None if epoch_done else order, "resumed_at": resumed_at})
                logger.info("checkpoint at step %d/%d (%.1f s)", step, total_steps, time.time() - saved_at)
        order, start_micro = None, 0
    return {"optimizer_steps": step, "resumed_at_steps": resumed_at}


def predict(model: Any, features: list[Features], batch_size: int, pad_id: int,
            device: Any, use_bf16: bool) -> list[list[float]]:
    """Class probabilities in input order; batches are length-sorted for speed."""
    import torch

    model.eval()
    order = sorted(range(len(features)), key=lambda i: len(features[i]["input_ids"]))
    probabilities: list[list[float] | None] = [None] * len(features)
    with torch.inference_mode():
        for start in range(0, len(order), batch_size):
            chunk = order[start : start + batch_size]
            batch = {key: value.to(device) for key, value in collate([features[i] for i in chunk], pad_id).items()}
            with torch.autocast(device_type=device.type, dtype=torch.bfloat16, enabled=use_bf16):
                logits = model(**batch).logits
            for i, row in zip(chunk, torch.softmax(logits.float(), dim=-1).tolist()):
                probabilities[i] = row
    return probabilities  # type: ignore[return-value]


def checkpoint_fingerprint(args: argparse.Namespace, config: RunConfig, settings: EncoderConfig,
                           n_train: int) -> dict[str, Any]:
    """Everything that determines the batch sequence and weights, so a resume cannot cross runs."""
    return {"run": config.name, "config_sha256": config.sha256(), "seed": args.seed,
            "train_condition": config.data.train_condition, "smoke": args.smoke,
            "items_sha256": provenance.sha256(Path(config.data.items)), "n_train": n_train,
            "micro_batch_size": settings.micro_batch_size, "grad_accum_steps": settings.grad_accum_steps}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    runner.add_common_args(parser)
    parser.add_argument("--micro-batch-size", type=int, help="override [encoder] micro_batch_size")
    parser.add_argument("--gradient-checkpointing", action="store_const", const=True,
                        help="trade compute for memory (useful on 8 GB)")
    parser.add_argument("--allow-cpu", action="store_true", help="permit CPU (only sensible with --smoke)")
    parser.add_argument("--save-model", action="store_true", help="save weights to the run's output folder")
    parser.add_argument("--checkpoint-every", type=int, metavar="STEPS",
                        help="save resumable training state every STEPS optimizer steps; "
                             "rerunning the same command resumes from it")
    args = parser.parse_args(argv)
    runner.configure_logging()
    started = time.time()
    try:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer, set_seed
    except ImportError as exc:
        logger.error("%s; install the GPU environment with: uv sync --group gpu", exc)
        return 1
    try:
        config = runner.load(args, {"encoder": {"micro_batch_size": args.micro_batch_size,
                                                "gradient_checkpointing": args.gradient_checkpointing}})
        if config.kind != "encoder" or config.encoder is None:
            raise ValueError("this trainer needs kind = 'encoder' and an [encoder] table")
        settings = config.encoder
        if torch.cuda.is_available():
            device = torch.device("cuda")
        elif args.allow_cpu:
            device = torch.device("cpu")
        else:
            raise ValueError("no CUDA device visible; run python -m src.stage1.env_check")
        use_bf16 = settings.bf16 and device.type == "cuda"
        if use_bf16 and not torch.cuda.is_bf16_supported():
            raise ValueError("bf16 requested but unsupported on this GPU")
        torch.set_float32_matmul_precision("high")  # TF32 for the remaining fp32 matmuls

        prepared = runner.prepare(config, args.smoke)
        tokenizer = AutoTokenizer.from_pretrained(settings.pretrained, revision=settings.revision)
        tokenizer.truncation_side = "left"  # drop the oldest context first
        pad_id = tokenizer.pad_token_id
        train_features = encode(tokenizer, prepared.train_inputs, settings.max_length)
        train_labels = [STAGE1_LABELS.index(e.label) for e in prepared.train]

        set_seed(args.seed)  # before loading so the classifier head is seeded too
        model = AutoModelForSequenceClassification.from_pretrained(
            settings.pretrained, revision=settings.revision, num_labels=len(STAGE1_LABELS),
            id2label=dict(enumerate(STAGE1_LABELS)), label2id={l: i for i, l in enumerate(STAGE1_LABELS)})
        if settings.gradient_checkpointing:
            model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
        model.to(device)
        if device.type == "cuda":
            torch.cuda.reset_peak_memory_stats()
        checkpointer = None
        if args.checkpoint_every is not None:
            checkpointer = Checkpointer(
                runner.output_dir(args, config) / CHECKPOINT_NAME, args.checkpoint_every,
                checkpoint_fingerprint(args, config, settings, len(train_features)))
        training = train(model, train_features, train_labels, settings, pad_id, device, use_bf16, args.seed,
                         checkpointer)

        predictions = []
        eval_at_max_length = {}
        for condition, pairs in prepared.eval_inputs.items():
            features = encode(tokenizer, pairs, settings.max_length)
            eval_at_max_length[condition] = sum(len(f["input_ids"]) >= settings.max_length for f in features)
            probabilities = predict(model, features, settings.eval_batch_size, pad_id, device, use_bf16)
            predictions += runner.prediction_rows(prepared.eval_sets[condition], condition, probabilities)
        model_info = {
            "name": "cross_encoder", "pretrained": settings.pretrained,
            "resolved_revision": getattr(model.config, "_commit_hash", None),
            "bf16": use_bf16, "device": device.type,
            "train_inputs_at_max_length": sum(len(f["input_ids"]) >= settings.max_length for f in train_features),
            "eval_inputs_at_max_length": eval_at_max_length,
            "peak_memory_gib": round(torch.cuda.max_memory_allocated() / 2**30, 2) if device.type == "cuda" else None,
            **training,
        }
        if args.save_model:
            model_dir = runner.output_dir(args, config) / "model"
            model.save_pretrained(model_dir)
            tokenizer.save_pretrained(model_dir)
        runner.finish(args, config, prepared, predictions, model_info, started)
        if checkpointer:
            checkpointer.remove()  # only after the outputs exist, so a failed finish can still resume
        return 0
    except torch.cuda.OutOfMemoryError:
        logger.error("out of GPU memory: lower --micro-batch-size or add --gradient-checkpointing")
        return 1
    except (OSError, ValueError, KeyError) as exc:
        logger.error("encoder run failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
