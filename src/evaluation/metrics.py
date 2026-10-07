"""Label-set-agnostic classification metrics with dialogue-level bootstrap intervals.

Every interval resamples whole dialogues, because the variants and turns of one
dialogue are correlated. Intervals are descriptive; they do not replace the
planned mixed-effects analysis.
"""

from __future__ import annotations

import collections
import random
from collections.abc import Hashable, Sequence
from typing import Any


def classification_metrics(pairs: Sequence[tuple[str, str]], labels: Sequence[str]) -> dict[str, Any]:
    """Accuracy, macro-F1 over the fixed ``labels`` (absent classes score 0), and confusion."""
    if not pairs:
        raise ValueError("no (gold, prediction) pairs")
    confusion = {gold: {predicted: 0 for predicted in labels} for gold in labels}
    for gold, predicted in pairs:
        confusion[gold][predicted] += 1
    f1 = []
    for label in labels:
        tp = confusion[label][label]
        predicted_count = sum(confusion[gold][label] for gold in labels)
        gold_count = sum(confusion[label].values())
        f1.append(2 * tp / (predicted_count + gold_count) if predicted_count + gold_count else 0.0)
    correct = sum(confusion[label][label] for label in labels)
    return {"n": len(pairs), "accuracy": correct / len(pairs),
            "macro_f1": sum(f1) / len(labels), "confusion": confusion}


def _percentile_interval(scores: list[float]) -> list[float]:
    scores.sort()
    last = len(scores) - 1
    return [scores[int(last * 0.025)], scores[int(last * 0.975)]]


def bootstrap_accuracy_ci(outcomes: Sequence[tuple[Hashable, bool]], samples: int, seed: int) -> list[float]:
    """95% percentile interval for accuracy; ``outcomes`` are (dialogue, correct) pairs."""
    grouped: dict[Hashable, list[bool]] = collections.defaultdict(list)
    for dialogue, correct in outcomes:
        grouped[dialogue].append(correct)
    groups = [grouped[key] for key in sorted(grouped)]
    rng = random.Random(seed)
    scores = []
    for _ in range(samples):
        draw = [correct for group in rng.choices(groups, k=len(groups)) for correct in group]
        scores.append(sum(draw) / len(draw))
    return _percentile_interval(scores)


def paired_bootstrap_difference(
    outcomes: Sequence[tuple[Hashable, bool, bool]], samples: int, seed: int
) -> dict[str, Any]:
    """Accuracy of A minus accuracy of B on the same examples, resampling dialogues.

    ``outcomes`` are (dialogue, A correct, B correct) triples for identical examples,
    so each draw scores both conditions on exactly the same resampled dialogues.
    """
    if not outcomes:
        raise ValueError("no paired outcomes")
    grouped: dict[Hashable, list[tuple[bool, bool]]] = collections.defaultdict(list)
    for dialogue, a_correct, b_correct in outcomes:
        grouped[dialogue].append((a_correct, b_correct))
    groups = [grouped[key] for key in sorted(grouped)]
    rng = random.Random(seed)
    differences = []
    for _ in range(samples):
        draw = [pair for group in rng.choices(groups, k=len(groups)) for pair in group]
        differences.append(sum(a - b for a, b in draw) / len(draw))
    observed = sum(a - b for _, a, b in outcomes) / len(outcomes)
    return {"n": len(outcomes), "difference": observed, "ci95": _percentile_interval(differences)}
