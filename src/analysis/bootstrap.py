"""One shared dialogue bootstrap for every statistic of an analysis run (spec 007 FR10).

Each replicate draws as many dialogues as the index holds, with replacement, from the sorted
dialogue list, using ``random.Random(seed).choices`` exactly as ``metrics.py`` does. The draw is
kept as a multiplicity vector ``w``. Every statistic is an example-weighted ratio
``sum(w * num) / sum(w * den)`` over per-dialogue vectors, so levels, conditions, systems and
endpoints are all evaluated on the same draw. That is what gives differences between them
(H2's difference-in-differences, H3, H4) honest joint intervals.

A replicate that draws none of a statistic's dialogues has a zero denominator. It is excluded
for that statistic only and recorded as NaN. Derived statistics are linear combinations of base
statistics, and NaN propagates through the arithmetic, so a derived value exists only on
replicates where every input is defined.
"""

from __future__ import annotations

import math
import operator
import random
from array import array
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import repeat

_NAN = float("nan")


class DialogueIndex:
    """The sorted, unique dialogue IDs that every statistic vector is aligned to."""

    def __init__(self, dialogue_ids: Iterable[str]) -> None:
        self.ids = tuple(sorted(set(dialogue_ids)))
        if not self.ids:
            raise ValueError("a bootstrap needs at least one dialogue")
        self._position = {dialogue: i for i, dialogue in enumerate(self.ids)}

    def __len__(self) -> int:
        return len(self.ids)

    def vector(self, rows: Iterable[tuple[str, float, float]]) -> StatVector:
        """Sum per-example ``(dialogue_id, numerator, denominator)`` rows into a dense vector."""
        num = [0.0] * len(self.ids)
        den = [0.0] * len(self.ids)
        for dialogue, numerator, denominator in rows:
            if dialogue not in self._position:
                raise ValueError("an example's dialogue is not in the bootstrap index")
            i = self._position[dialogue]
            num[i] += numerator
            den[i] += denominator
        return StatVector(tuple(num), tuple(den))


@dataclass(frozen=True)
class StatVector:
    """Per-dialogue numerator and denominator sums, aligned to a ``DialogueIndex``."""

    num: tuple[float, ...]
    den: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.num) != len(self.den):
            raise ValueError("numerator and denominator lengths differ")
        if any(d < 0 or not math.isfinite(d) for d in self.den) or not all(map(math.isfinite, self.num)):
            raise ValueError("denominators must be non-negative and values finite")
        if any(n != 0 and d == 0 for n, d in zip(self.num, self.den)):
            raise ValueError("a dialogue has a numerator but no examples")
        if not any(self.den):
            raise ValueError("a statistic has no examples")

    @property
    def point(self) -> float:
        return sum(self.num) / sum(self.den)


@dataclass(frozen=True)
class Derived:
    """A linear combination of base statistics, as (statistic name, coefficient) terms."""

    terms: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class Estimate:
    """A statistic's point estimate, interval and bootstrap p (None when it may not be tested)."""

    point: float
    ci: tuple[float, float] | None
    p: float | None
    replicates: int
    excluded: int
    unstable: bool


@dataclass(frozen=True)
class BootstrapResult:
    samples: int
    seed: int
    points: dict[str, float]
    replicates: dict[str, array]  # one value per replicate; NaN where the statistic is undefined

    def estimate(self, name: str, *, confidence: float, max_excluded_share: float) -> Estimate:
        return summarize(self.points[name], self.replicates[name], confidence=confidence,
                         max_excluded_share=max_excluded_share)


def shared_bootstrap(index: DialogueIndex, stats: Mapping[str, StatVector], *, samples: int, seed: int,
                     derived: Mapping[str, Derived] | None = None) -> BootstrapResult:
    """Evaluate every statistic on the same ``samples`` dialogue draws.

    The values a statistic gets do not depend on which other statistics are present or on
    their order, because the draw sequence depends only on the index, ``samples`` and ``seed``.
    """
    if samples < 1:
        raise ValueError("samples must be positive")
    derived = dict(derived or {})
    if not stats:
        raise ValueError("no statistics to bootstrap")
    if set(stats) & set(derived):
        raise ValueError("a derived statistic reuses a base statistic's name")
    n = len(index)
    if any(len(vector.num) != n for vector in stats.values()):
        raise ValueError("a statistic vector is not aligned to the dialogue index")
    combinations = {name: _check_terms(name, derived[name], stats) for name in sorted(derived)}
    compiled = _Compiled(stats)
    columns = {name: array("d") for name in stats}
    rng = random.Random(seed)
    for _ in range(samples):
        weights = [0] * n
        for i in rng.choices(range(n), k=n):
            weights[i] += 1
        for name, value in compiled.evaluate(weights).items():
            columns[name].append(value)
    points = {name: stats[name].point for name in sorted(stats)}
    replicates = {name: columns[name] for name in sorted(stats)}
    for name, terms in combinations.items():
        points[name] = sum(coefficient * points[base] for base, coefficient in terms)
        replicates[name] = _combine(terms, replicates, samples)
    return BootstrapResult(samples=samples, seed=seed, points=points, replicates=replicates)


def summarize(point: float, values: Sequence[float], *, confidence: float, max_excluded_share: float) -> Estimate:
    """Interval and p over the defined replicates; an unstable statistic is never tested."""
    defined = [v for v in values if not math.isnan(v)]
    excluded = len(values) - len(defined)
    unstable = not defined or excluded / len(values) > max_excluded_share
    return Estimate(point=point,
                    ci=percentile_interval(defined, confidence) if defined else None,
                    p=None if unstable else bootstrap_p(defined),
                    replicates=len(defined), excluded=excluded, unstable=unstable)


def percentile_interval(values: Sequence[float], confidence: float) -> tuple[float, float]:
    """Percentile interval with ``metrics._percentile_interval``'s order statistics.

    At confidence 0.95 the tails are exactly 0.025 and 0.975, so the indices match it.
    """
    if not values:
        raise ValueError("no replicate values")
    if not 0 < confidence < 1:
        raise ValueError("confidence must lie strictly between 0 and 1")
    ordered = sorted(values)
    last = len(ordered) - 1
    tail = round((1 - confidence) / 2, 12)
    return ordered[int(last * tail)], ordered[int(last * (1 - tail))]


def bootstrap_p(values: Sequence[float]) -> float:
    """Two-sided bootstrap p: min(1, 2 * min(#<=0, #>=0) / B'), floored at 1 / B'."""
    if not values:
        raise ValueError("no replicate values")
    at_or_below = sum(v <= 0 for v in values)
    at_or_above = sum(v >= 0 for v in values)
    count = len(values)
    return max(1 / count, min(1.0, 2 * min(at_or_below, at_or_above) / count))


def holm(pvalues: Sequence[float]) -> list[float]:
    """Holm step-down adjusted p-values, in input order and monotone in the raw p order.

    Ties are ranked by input position; the running maximum gives tied raw p-values the same
    adjusted value.
    """
    if any(math.isnan(p) or not 0 <= p <= 1 for p in pvalues):
        raise ValueError("p-values must lie in [0, 1]")
    count = len(pvalues)
    adjusted = [0.0] * count
    running = 0.0
    for rank, i in enumerate(sorted(range(count), key=lambda i: (pvalues[i], i))):
        running = max(running, min(1.0, (count - rank) * pvalues[i]))
        adjusted[i] = running
    return adjusted


class _Compiled:
    """Statistic vectors reduced to their support, with shared supports and denominators.

    Most statistics touch a subset of dialogues (one level, one category). Picking the
    supported weights with ``itemgetter`` and multiplying with ``map`` keeps the inner loop in
    C, and statistics that share a support or a denominator (same examples, other systems or
    conditions) reuse one pick and one denominator sum per replicate.
    """

    def __init__(self, stats: Mapping[str, StatVector]) -> None:
        self._pickers: dict[tuple[int, ...], Callable[[list[int]], tuple[int, ...]]] = {}
        self._dens: dict[tuple[tuple[int, ...], tuple[float, ...]], int] = {}
        self._plan: list[tuple[str, tuple[int, ...], tuple[float, ...], int]] = []
        den_keys: list[tuple[tuple[int, ...], tuple[float, ...]]] = []
        for name in sorted(stats):
            vector = stats[name]
            support = tuple(i for i, d in enumerate(vector.den) if d)
            if support not in self._pickers:
                self._pickers[support] = _picker(support)
            den_key = (support, tuple(vector.den[i] for i in support))
            if den_key not in self._dens:
                self._dens[den_key] = len(den_keys)
                den_keys.append(den_key)
            self._plan.append((name, support, tuple(vector.num[i] for i in support), self._dens[den_key]))
        self._den_keys = den_keys

    def evaluate(self, weights: list[int]) -> dict[str, float]:
        picked = {support: picker(weights) for support, picker in self._pickers.items()}
        den_sums = [sum(map(operator.mul, picked[support], den)) for support, den in self._den_keys]
        values = {}
        for name, support, num, den_slot in self._plan:
            denominator = den_sums[den_slot]
            values[name] = sum(map(operator.mul, picked[support], num)) / denominator if denominator else _NAN
        return values


def _picker(support: tuple[int, ...]) -> Callable[[list[int]], tuple[int, ...]]:
    if len(support) == 1:  # itemgetter with one index returns a bare value, not a tuple
        only = support[0]
        return lambda weights: (weights[only],)
    return operator.itemgetter(*support)


def _check_terms(name: str, spec: Derived, stats: Mapping[str, StatVector]) -> tuple[tuple[str, float], ...]:
    terms = tuple((base, coefficient) for base, coefficient in spec.terms if coefficient != 0)
    if not terms:
        raise ValueError(f"derived statistic {name!r} has no non-zero terms")
    unknown = sorted({base for base, _ in terms} - set(stats))
    if unknown:
        raise ValueError(f"derived statistic {name!r} uses unknown statistics {unknown}")
    if len({base for base, _ in terms}) != len(terms):
        raise ValueError(f"derived statistic {name!r} repeats a term")
    return terms


def _combine(terms: Sequence[tuple[str, float]], replicates: Mapping[str, array], samples: int) -> array:
    total = [0.0] * samples
    for base, coefficient in terms:
        total = list(map(operator.add, total, map(operator.mul, repeat(coefficient), replicates[base])))
    return array("d", total)
