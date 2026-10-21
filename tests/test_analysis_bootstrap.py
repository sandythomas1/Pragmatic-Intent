"""Shared dialogue bootstrap and Holm (spec 007 T2, AC-007-6, AC-007-7 Holm part)."""

from __future__ import annotations

import math
import random
import unittest
from fractions import Fraction

from src.analysis.bootstrap import (
    Derived,
    DialogueIndex,
    StatVector,
    bootstrap_p,
    holm,
    percentile_interval,
    shared_bootstrap,
    summarize,
)
from src.evaluation.metrics import _percentile_interval, bootstrap_accuracy_ci, paired_bootstrap_difference


def draws(n: int, samples: int, seed: int) -> list[list[int]]:
    """Multiplicity vectors from the same draw sequence the engine (and metrics.py) uses."""
    rng = random.Random(seed)
    out = []
    for _ in range(samples):
        weights = [0] * n
        for i in rng.choices(range(n), k=n):
            weights[i] += 1
        out.append(weights)
    return out


def paired_fixture() -> list[tuple[str, bool, bool]]:
    """Uneven dialogue sizes: (dialogue, A correct, B correct) per example (PMUL9xxx IDs)."""
    rng = random.Random(4)
    outcomes = []
    for d in range(40):
        for _ in range(1 + d % 5):
            outcomes.append((f"PMUL9{d:03d}", rng.random() < 0.7, rng.random() < 0.5))
    return outcomes


class MetricsEquivalenceTest(unittest.TestCase):
    """AC-007-6: one statistic over all dialogues reproduces the per-run scorer's bootstrap."""

    def test_paired_difference_interval_matches_metrics(self) -> None:
        outcomes = paired_fixture()
        expected = paired_bootstrap_difference(outcomes, samples=500, seed=13)
        index = DialogueIndex(d for d, _, _ in outcomes)
        stats = {"diff": index.vector((d, int(a) - int(b), 1) for d, a, b in outcomes)}
        result = shared_bootstrap(index, stats, samples=500, seed=13)
        estimate = result.estimate("diff", confidence=0.95, max_excluded_share=0.01)
        self.assertAlmostEqual(estimate.point, expected["difference"], delta=1e-12)
        for ours, theirs in zip(estimate.ci, expected["ci95"]):
            self.assertAlmostEqual(ours, theirs, delta=1e-12)
        self.assertEqual((estimate.excluded, estimate.unstable), (0, False))

    def test_difference_as_a_derived_statistic_matches_too(self) -> None:
        outcomes = paired_fixture()
        expected = paired_bootstrap_difference(outcomes, samples=300, seed=5)
        index = DialogueIndex(d for d, _, _ in outcomes)
        stats = {"a": index.vector((d, int(a), 1) for d, a, _ in outcomes),
                 "b": index.vector((d, int(b), 1) for d, _, b in outcomes)}
        result = shared_bootstrap(index, stats, samples=300, seed=5,
                                  derived={"a_minus_b": Derived((("a", 1.0), ("b", -1.0)))})
        estimate = result.estimate("a_minus_b", confidence=0.95, max_excluded_share=0.01)
        for ours, theirs in zip(estimate.ci, expected["ci95"]):
            self.assertAlmostEqual(ours, theirs, delta=1e-12)

    def test_single_rate_matches_bootstrap_accuracy_ci(self) -> None:
        outcomes = [(d, a) for d, a, _ in paired_fixture()]
        index = DialogueIndex(d for d, _ in outcomes)
        result = shared_bootstrap(index, {"acc": index.vector((d, int(a), 1) for d, a in outcomes)},
                                  samples=400, seed=21)
        ci = result.estimate("acc", confidence=0.95, max_excluded_share=0.01).ci
        for ours, theirs in zip(ci, bootstrap_accuracy_ci(outcomes, samples=400, seed=21)):
            self.assertAlmostEqual(ours, theirs, delta=1e-12)

    def test_percentile_order_statistics_match_metrics(self) -> None:
        rng = random.Random(3)
        for size in (1, 2, 39, 40, 41, 1000, 9999, 10000):
            values = [rng.random() for _ in range(size)]
            with self.subTest(size=size):
                self.assertEqual(list(percentile_interval(values, 0.95)), _percentile_interval(list(values)))


class HandComputedTest(unittest.TestCase):
    """A 3-dialogue example small enough to check by hand."""

    def setUp(self) -> None:
        self.index = DialogueIndex(["PMUL9003", "PMUL9001", "PMUL9002"])  # sorted by the index
        # Per dialogue (num, den): PMUL9001 (1, 2), PMUL9002 (0, 1), PMUL9003 (3, 3).
        rows = [("PMUL9001", 1, 1), ("PMUL9001", 0, 1), ("PMUL9002", 0, 1),
                ("PMUL9003", 1, 1), ("PMUL9003", 1, 1), ("PMUL9003", 1, 1)]
        self.stats = {"rate": self.index.vector(rows)}

    def test_vector_point_and_each_replicate(self) -> None:
        self.assertEqual(self.index.ids, ("PMUL9001", "PMUL9002", "PMUL9003"))
        self.assertEqual(self.stats["rate"], StatVector((1.0, 0.0, 3.0), (2.0, 1.0, 3.0)))
        result = shared_bootstrap(self.index, self.stats, samples=6, seed=11)
        self.assertEqual(result.points["rate"], 4 / 6)
        num, den = (1, 0, 3), (2, 1, 3)
        for weights, value in zip(draws(3, 6, 11), result.replicates["rate"]):
            expected = Fraction(sum(w * x for w, x in zip(weights, num)), sum(w * x for w, x in zip(weights, den)))
            self.assertAlmostEqual(value, float(expected), delta=1e-15)

    def test_interval_and_p_on_known_replicates(self) -> None:
        values = [float(v) for v in range(-2, 9)]  # 11 values: -2 .. 8
        estimate = summarize(0.5, values, confidence=0.8, max_excluded_share=0.01)
        # last = 10; tails 0.1 and 0.9 give order statistics 1 and 9.
        self.assertEqual(estimate.ci, (-1.0, 7.0))
        # #(<= 0) = 3 (-2, -1, 0), #(>= 0) = 9, so p = 2 * 3 / 11.
        self.assertAlmostEqual(estimate.p, 6 / 11)
        self.assertEqual((estimate.replicates, estimate.excluded, estimate.unstable), (11, 0, False))

    def test_p_is_floored_at_one_over_b_and_capped_at_one(self) -> None:
        self.assertEqual(bootstrap_p([0.1, 0.2, 0.3, 0.4]), 0.25)
        self.assertEqual(bootstrap_p([0.0, 0.0, 0.0]), 1.0)
        self.assertEqual(bootstrap_p([-0.3, -0.1]), 0.5)


class SparseStatisticTest(unittest.TestCase):
    """A statistic present in 1 of 3 dialogues loses every replicate that misses it."""

    def setUp(self) -> None:
        self.index = DialogueIndex(["PMUL9001", "PMUL9002", "PMUL9003"])
        self.stats = {"all": self.index.vector([("PMUL9001", 1, 1), ("PMUL9002", 0, 1), ("PMUL9003", 1, 1)]),
                      "rare": self.index.vector([("PMUL9003", 1, 2)])}
        self.result = shared_bootstrap(self.index, self.stats, samples=1000, seed=2,
                                       derived={"rare_minus_all": Derived((("rare", 1.0), ("all", -1.0)))})

    def test_excluded_replicates_are_counted_and_make_it_unstable(self) -> None:
        missing = sum(weights[2] == 0 for weights in draws(3, 1000, 2))
        self.assertGreater(missing, 10)
        estimate = self.result.estimate("rare", confidence=0.95, max_excluded_share=0.01)
        self.assertEqual((estimate.excluded, estimate.replicates), (missing, 1000 - missing))
        self.assertTrue(estimate.unstable)
        self.assertIsNone(estimate.p)
        self.assertIsNotNone(estimate.ci)  # an unstable statistic still gets its interval
        self.assertFalse(self.result.estimate("all", confidence=0.95, max_excluded_share=0.01).unstable)

    def test_threshold_decides_stability(self) -> None:
        share = self.result.estimate("rare", confidence=0.95, max_excluded_share=0.01).excluded / 1000
        self.assertFalse(self.result.estimate("rare", confidence=0.95, max_excluded_share=share).unstable)

    def test_derived_contrast_uses_only_replicates_where_every_input_is_defined(self) -> None:
        rare, total = self.result.replicates["rare"], self.result.replicates["all"]
        derived = self.result.replicates["rare_minus_all"]
        for r, a, d in zip(rare, total, derived):
            if math.isnan(r):
                self.assertTrue(math.isnan(d))
            else:
                self.assertAlmostEqual(d, r - a, delta=1e-15)
        self.assertEqual(self.result.estimate("rare_minus_all", confidence=0.95, max_excluded_share=0.01).excluded,
                         self.result.estimate("rare", confidence=0.95, max_excluded_share=0.01).excluded)
        self.assertAlmostEqual(self.result.points["rare_minus_all"], 0.5 - 2 / 3)

    def test_a_statistic_never_drawn_has_no_interval(self) -> None:
        estimate = summarize(0.5, [math.nan] * 5, confidence=0.95, max_excluded_share=0.01)
        self.assertEqual((estimate.ci, estimate.p, estimate.replicates, estimate.unstable), (None, None, 0, True))


class CompiledEvaluationTest(unittest.TestCase):
    """The support/denominator sharing gives the same values as a naive dense computation."""

    def test_matches_dense_recomputation_for_mixed_supports(self) -> None:
        rng = random.Random(8)
        n = 25
        index = DialogueIndex(f"PMUL9{i:03d}" for i in range(n))
        stats = {}
        for s in range(12):
            support = rng.sample(range(n), k=[1, 2, 5, n][s % 4])
            den = [float(rng.randint(1, 4)) if i in support else 0.0 for i in range(n)]
            num = [float(rng.randint(0, int(d))) for d in den]
            stats[f"s{s:02d}"] = StatVector(tuple(num), tuple(den))
        stats["shared_den"] = StatVector(tuple(0.0 for _ in range(n)), stats["s03"].den)  # same examples as s03
        result = shared_bootstrap(index, stats, samples=60, seed=9)
        for r, weights in enumerate(draws(n, 60, 9)):
            for name, vector in stats.items():
                den = sum(w * d for w, d in zip(weights, vector.den))
                expected = sum(w * x for w, x in zip(weights, vector.num)) / den if den else math.nan
                value = result.replicates[name][r]
                with self.subTest(name=name, replicate=r):
                    if math.isnan(expected):
                        self.assertTrue(math.isnan(value))
                    else:
                        self.assertAlmostEqual(value, expected, delta=1e-12)


class DeterminismTest(unittest.TestCase):
    def setUp(self) -> None:
        self.index = DialogueIndex(f"PMUL9{i:03d}" for i in range(10))
        self.stats = {name: self.index.vector((f"PMUL9{i:03d}", (i + k) % 2, 1) for i in range(k, 10))
                      for k, name in enumerate(["b", "a", "c"], start=1)}

    def test_same_inputs_and_seed_give_identical_replicates(self) -> None:
        first = shared_bootstrap(self.index, self.stats, samples=200, seed=4)
        second = shared_bootstrap(self.index, self.stats, samples=200, seed=4)
        self.assertEqual({k: v.tobytes() for k, v in first.replicates.items()},
                         {k: v.tobytes() for k, v in second.replicates.items()})
        other_seed = shared_bootstrap(self.index, self.stats, samples=200, seed=5)
        self.assertNotEqual(first.replicates["a"].tobytes(), other_seed.replicates["a"].tobytes())

    def test_statistic_order_and_neighbours_do_not_change_values(self) -> None:
        full = shared_bootstrap(self.index, self.stats, samples=200, seed=4)
        reordered = shared_bootstrap(self.index, dict(reversed(list(self.stats.items()))), samples=200, seed=4)
        alone = shared_bootstrap(self.index, {"a": self.stats["a"]}, samples=200, seed=4)
        self.assertEqual(list(full.replicates), ["a", "b", "c"])
        self.assertEqual(list(reordered.replicates), ["a", "b", "c"])
        self.assertEqual(full.replicates["a"].tobytes(), reordered.replicates["a"].tobytes())
        self.assertEqual(full.replicates["a"].tobytes(), alone.replicates["a"].tobytes())


class InvalidInputTest(unittest.TestCase):
    def test_bad_inputs_fail_loudly(self) -> None:
        index = DialogueIndex(["PMUL9001", "PMUL9002"])
        good = index.vector([("PMUL9001", 1, 1)])
        cases = {
            "empty index": lambda: DialogueIndex([]),
            "unknown dialogue": lambda: index.vector([("PMUL9999", 1, 1)]),
            "length mismatch": lambda: StatVector((1.0,), (1.0, 1.0)),
            "numerator without examples": lambda: StatVector((1.0, 0.0), (0.0, 1.0)),
            "negative denominator": lambda: StatVector((0.0, 0.0), (-1.0, 1.0)),
            "nan numerator": lambda: StatVector((math.nan, 0.0), (1.0, 1.0)),
            "no examples": lambda: StatVector((0.0, 0.0), (0.0, 0.0)),
            "misaligned vector": lambda: shared_bootstrap(index, {"x": StatVector((1.0,), (1.0,))}, samples=5, seed=1),
            "zero samples": lambda: shared_bootstrap(index, {"x": good}, samples=0, seed=1),
            "no statistics": lambda: shared_bootstrap(index, {}, samples=5, seed=1),
            "derived name clash": lambda: shared_bootstrap(index, {"x": good}, samples=5, seed=1,
                                                           derived={"x": Derived((("x", 1.0),))}),
            "derived unknown input": lambda: shared_bootstrap(index, {"x": good}, samples=5, seed=1,
                                                              derived={"d": Derived((("y", 1.0),))}),
            "derived all-zero terms": lambda: shared_bootstrap(index, {"x": good}, samples=5, seed=1,
                                                               derived={"d": Derived((("x", 0.0),))}),
            "derived repeated term": lambda: shared_bootstrap(index, {"x": good}, samples=5, seed=1,
                                                              derived={"d": Derived((("x", 1.0), ("x", -1.0)))}),
            "bad confidence": lambda: percentile_interval([0.1], 1.0),
            "empty replicates": lambda: bootstrap_p([]),
        }
        for name, call in cases.items():
            with self.subTest(name), self.assertRaises(ValueError):
                call()

    def test_zero_weight_term_is_dropped(self) -> None:
        # The linear contrast gives L1 weight 0; an undefined L1 must not void the contrast.
        index = DialogueIndex(["PMUL9001", "PMUL9002", "PMUL9003"])
        stats = {"l0": index.vector([("PMUL9001", 1, 1), ("PMUL9002", 0, 1)]),
                 "l1": index.vector([("PMUL9003", 1, 1)]),
                 "l2": index.vector([("PMUL9001", 0, 1), ("PMUL9002", 1, 1)])}
        trend = Derived((("l0", -1.0), ("l1", 0.0), ("l2", 1.0)))
        result = shared_bootstrap(index, stats, samples=300, seed=6, derived={"trend": trend})
        replicates = result.replicates
        l1_missing = [math.isnan(v) for v in replicates["l1"]]
        ends_missing = [math.isnan(a) or math.isnan(b) for a, b in zip(replicates["l0"], replicates["l2"])]
        self.assertTrue(any(m and not e for m, e in zip(l1_missing, ends_missing)))
        self.assertEqual([math.isnan(v) for v in replicates["trend"]], ends_missing)


class HolmTest(unittest.TestCase):
    def test_four_values_with_a_tie(self) -> None:
        # Sorted: 0.01 (x4 = 0.04), 0.03 (x3 = 0.09), 0.04 (x2 = 0.08 -> 0.09), 0.04 (x1 -> 0.09).
        adjusted = holm([0.01, 0.04, 0.03, 0.04])
        for ours, expected in zip(adjusted, [0.04, 0.09, 0.09, 0.09]):
            self.assertAlmostEqual(ours, expected)

    def test_not_run_members_at_p_one_keep_the_family_size(self) -> None:
        # Sorted: 0.01 (x4), 0.02 (x3 = 0.06), 0.02 (x2 = 0.04 -> 0.06), 1.0 (x1).
        adjusted = holm([0.01, 1.0, 0.02, 0.02])
        for ours, expected in zip(adjusted, [0.04, 1.0, 0.06, 0.06]):
            self.assertAlmostEqual(ours, expected)

    def test_adjusted_values_are_capped_and_monotone(self) -> None:
        self.assertEqual(holm([0.5, 0.6]), [1.0, 1.0])
        self.assertEqual(holm([]), [])
        rng = random.Random(1)
        raw = [rng.random() / 10 for _ in range(9)]
        adjusted = holm(raw)
        ranked = sorted(range(9), key=lambda i: raw[i])
        self.assertEqual([adjusted[i] for i in ranked], sorted(adjusted))
        self.assertTrue(all(a >= r for a, r in zip(adjusted, raw)))

    def test_invalid_p_values_fail(self) -> None:
        for bad in ([math.nan], [-0.1], [1.5]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                holm(bad)


if __name__ == "__main__":
    unittest.main()
