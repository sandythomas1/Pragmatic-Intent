"""Check that budgeted Stage 1 inputs fit an encoder without truncation (spec 004 FR4).

The D-06 budget is counted in whitespace tokens so it is the same for every model. Before the
freeze, this confirms that no budgeted input, in training or evaluation, under any condition,
is longer than the encoder's ``max_length`` in subword tokens. It loads only the tokenizer and
runs on CPU in a few minutes. If it reports any input over the limit, lower the budget for
every model under a new renderer version; never patch it per model.

Run in WSL with the GPU dependency group (the tokenizer is downloaded from Hugging Face)::

    uv run --group gpu python -m src.stage1.length_check --config configs/stage1/encoder_deberta_v3_base.toml
    uv run --group gpu python -m src.stage1.length_check --config configs/stage1/encoder_roberta_base.toml
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from src.data.contexts import BUDGET_WORDS, RENDERER_VERSION
from src.data.direct_dataset import CONDITIONS, load_dialogues, load_items
from src.stage1 import runner
from src.stage1.data import model_inputs

logger = logging.getLogger(__name__)
CHUNK = 4096


def token_lengths(tokenizer: Any, pairs: Sequence[runner.Pair]) -> list[int]:
    """Untruncated lengths, built as ``encoder.encode`` builds its inputs (pair, or utterance alone)."""
    lengths = [0] * len(pairs)
    for has_context in (True, False):
        indices = [i for i, (context, _) in enumerate(pairs) if bool(context) == has_context]
        for start in range(0, len(indices), CHUNK):
            chunk = indices[start : start + CHUNK]
            utterances = [pairs[i][1] for i in chunk]
            batch = (tokenizer([pairs[i][0] for i in chunk], utterances, truncation=False) if has_context
                     else tokenizer(utterances, truncation=False))
            for offset, i in enumerate(chunk):
                lengths[i] = len(batch["input_ids"][offset])
    return lengths


def summarize(lengths: dict[str, list[int]], max_length: int) -> dict[str, Any]:
    """Per input group: count, maximum, and how many exceed ``max_length`` (would be truncated)."""
    return {name: {"n": len(values), "max_tokens": max(values, default=0),
                   "over_max_length": sum(value > max_length for value in values)}
            for name, values in lengths.items()}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, required=True, help="an encoder config")
    parser.add_argument("--out", type=Path, help="also write the report as JSON here")
    args = parser.parse_args(argv)
    runner.configure_logging()
    try:
        from transformers import AutoTokenizer
    except ImportError as exc:
        logger.error("%s; install the GPU environment with: uv sync --group gpu", exc)
        return 1
    try:
        config = runner.load(argparse.Namespace(train_condition=None, config=args.config, allow_test=False), {})
        if config.encoder is None:
            raise ValueError("length_check needs an [encoder] table")
        settings = config.encoder
        tokenizer = AutoTokenizer.from_pretrained(settings.pretrained, revision=settings.revision)
        prepared = runner.prepare(config)
        items_by_id = {item["item_id"]: item for item in load_items(Path(config.data.items))}
        dialogues = load_dialogues(Path(config.data.dialogues))
        lengths = {f"eval/{c}": token_lengths(tokenizer, pairs) for c, pairs in prepared.eval_inputs.items()}
        for condition in CONDITIONS:
            pairs = model_inputs(prepared.train, items_by_id, dialogues, condition)
            lengths[f"train/{condition}"] = token_lengths(tokenizer, [p for p in pairs if p is not None])
        report = {"pretrained": settings.pretrained, "revision": settings.revision,
                  "max_length": settings.max_length, "renderer_version": RENDERER_VERSION,
                  "budget_words": BUDGET_WORDS, "groups": summarize(lengths, settings.max_length)}
    except (OSError, ValueError, KeyError) as exc:
        logger.error("length check failed: %s", exc)
        return 1
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    over = sum(group["over_max_length"] for group in report["groups"].values())
    if over:
        logger.error("%d inputs exceed %d tokens: lower the budget for all models under a new renderer version",
                     over, settings.max_length)
        return 1
    logger.info("every budgeted input fits %s at max_length %d", settings.pretrained, settings.max_length)
    return 0


if __name__ == "__main__":
    sys.exit(main())
