"""The FR9 prompt-selection sample: a deterministic, dialogue-level draw of dev examples (spec 009 T11).

If the smoke probe estimates that two full ``none``/``full`` passes would take more than
``run.SAMPLE_FALLBACK_HOURS``, both variants run on this sample instead. The fallback is decided
from throughput alone, before any variant output is scored. ``run`` therefore refuses a sample
once a selection report exists.

**How the draw works.**
- The pool is every dialogue that has a scored example: genuine dev examples, with context
  (``build_examples(require_context=True)``, as the scorers use).
- Dialogues are sorted, then ``random.Random(seed).sample`` picks ``dialogues`` of them.
- Every example of a drawn dialogue is in the sample. Turns of one dialogue are never split,
  which matches the analysis's dialogue-level resampling.

Provenance records the SHA-256 of the sorted example IDs, never the IDs themselves. A drift in
the corpus or in the draw then shows as a hash mismatch at selection time.
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.data.direct_dataset import load_items
from src.llm.paths import REPO_ROOT, under_outputs
from src.stage1.data import build_examples

SAMPLE_DIALOGUES = 300  # FR9
SAMPLE_SEED = 20261102  # FR9
SAMPLE_VERSION = "llm-sample-v1"
SELECTION_ROOT = Path("outputs/llm/selection")


class SampleError(ValueError):
    """The sample cannot be drawn or does not match what a run recorded."""


@dataclass(frozen=True)
class Sample:
    dialogues: int
    seed: int
    example_ids: frozenset[str]

    @property
    def ids_sha256(self) -> str:
        return hashlib.sha256("\n".join(sorted(self.example_ids)).encode("utf-8")).hexdigest()

    def as_provenance(self) -> dict[str, Any]:
        """Counts and a hash only: no example or dialogue ID is written."""
        return {"version": SAMPLE_VERSION, "unit": "dialogue", "dialogues": self.dialogues, "seed": self.seed,
                "examples": len(self.example_ids), "example_ids_sha256": self.ids_sha256}


def draw_dialogues(dialogue_ids: Collection[str], dialogues: int, seed: int) -> frozenset[str]:
    """``dialogues`` distinct IDs from the sorted pool, chosen by a seeded generator."""
    pool = sorted(set(dialogue_ids))
    if type(dialogues) is not int or type(seed) is not int or not 1 <= dialogues <= len(pool):
        raise SampleError(f"the sample needs between 1 and {len(pool)} dialogues and an integer seed")
    return frozenset(random.Random(seed).sample(pool, dialogues))


def draw(items_path: Path, split: str, dialogues: int = SAMPLE_DIALOGUES, seed: int = SAMPLE_SEED) -> Sample:
    """The examples of ``dialogues`` drawn dialogues of ``split`` (dev only; the caller checks)."""
    examples, _ = build_examples(load_items(items_path), split, require_context=True)
    if not examples:
        raise SampleError(f"no {split} examples to sample")
    chosen = draw_dialogues({example.dialogue_id for example in examples}, dialogues, seed)
    return Sample(dialogues, seed, frozenset(e.example_id for e in examples if e.dialogue_id in chosen))


def matches(recorded: Any, sample: Sample) -> bool:
    """Whether a run's recorded sample block describes ``sample``."""
    return isinstance(recorded, Mapping) and dict(recorded) == sample.as_provenance()


def report_path(system: str, root: Path = REPO_ROOT) -> Path:
    """Where ``select-prompt`` writes its report; its presence means a variant has been scored."""
    return under_outputs(SELECTION_ROOT / system / "report.json", root)
