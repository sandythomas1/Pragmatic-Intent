"""H1–H5, the primary test, the Holm family and sensitivity lines on one shared bootstrap.

Spec 007 FR10–FR18. Every interval of a run comes from one ``shared_bootstrap`` call over all
evaluated dialogues.

**Statistics.** The builder registers two kinds of base statistic:

- **Rates:** seed-averaged endpoint values (``OutcomeTable.average``) summed per dialogue.
- **Paired differences:** for a contrast a − b, ``v_a − v_b`` on the examples both conditions
  score.

Contrasts of contrasts are linear combinations of those bases, flattened to base terms. Examples:
the linear and quadratic trends of a level benefit, a level's benefit minus L0's, H3's
cross-system difference, H4's drop contrast, the intent-standardized line.

**Testing.** Only the prespecified tests carry a p-value: the primary test and the Holm
members. Everything else gets an interval and stays descriptive.

**Cells.**
- A statistic is ``sparse`` when its smallest cell has fewer dialogues than the config's minimum.
- It is ``unstable`` when more than the configured share of replicates is excluded.
- Neither is ever tested.
- The primary test touching one fails the run, as does a ``not_run`` primary system on test.

**Lines.** For trained systems the primary line is ``matched``. H3's tested differences and the
mismatch controls use the ``test_time`` line, the design every family shares (Sandy, 2026-10-20).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from src.analysis.bootstrap import BootstrapResult, Derived, DialogueIndex, StatVector, holm, shared_bootstrap
from src.analysis.config import TREND_WEIGHTS, AnalysisConfig, FamilyMember
from src.analysis.files import AnalysisError
from src.analysis.outcomes import OutcomeTable, seed_variation
from src.data.auto_levels import LEVELS
from src.data.contexts import MISMATCH_CONDITIONS
from src.data.direct_dataset import CONDITIONS
from src.evaluation.stage1 import CONTRASTS

OVERALL = "overall"
ENDPOINT_ORDER = ("request_interpretation", "type_exact", "stage1_correct")
GENUINE_PAIRS = tuple((a, b) for a, b in CONTRASTS if b not in MISMATCH_CONDITIONS)
MISMATCH_PAIRS = tuple((a, b) for a, b in CONTRASTS if b in MISMATCH_CONDITIONS)
MAIN_EFFECT_LABEL = "main effect, no interaction"
H3_CAPTION = "design differs across families"
PRECISION_TOLERANCE = 0.002  # FR16 Monte Carlo check: the two seeds' interval endpoints must agree to this


def contrast_name(a: str, b: str) -> str:
    return f"{a}_minus_{b}"


PAIRS = {contrast_name(a, b): (a, b) for a, b in CONTRASTS}


class _Book:
    """Registered statistics, their cell sizes, and the one bootstrap they share."""

    def __init__(self, table: OutcomeTable) -> None:
        examples = table.evaluation.examples
        self.index = DialogueIndex(e.dialogue_id for e in examples)
        self.dialogue = {e.example_id: e.dialogue_id for e in examples}
        self.stats: dict[str, StatVector] = {}
        self.derived: dict[str, Derived] = {}
        self.cells: dict[str, tuple[int, int]] = {}  # name -> (examples, dialogues) of its smallest cell
        self.result: BootstrapResult | None = None

    def values(self, name: str, values: Mapping[str, float], ids: Iterable[str],
               baseline: Mapping[str, float] | None = None) -> str | None:
        """A rate (or, with ``baseline``, a paired difference) over ``ids``; None if no example."""
        kept = [i for i in ids if i in values and (baseline is None or i in baseline)]
        if not kept:
            return None
        if name not in self.stats:
            rows = ((self.dialogue[i], values[i] - (baseline[i] if baseline is not None else 0.0), 1) for i in kept)
            self.stats[name] = self.index.vector(rows)
            self.cells[name] = (len(kept), len({self.dialogue[i] for i in kept}))
        return name

    def combine(self, name: str, terms: Sequence[tuple[str | None, float]]) -> str | None:
        """A linear combination, flattened to base statistics; None if a weighted input is missing."""
        if any(base is None and weight for base, weight in terms):
            return None
        flat: dict[str, float] = defaultdict(float)
        for base, weight in terms:
            if not weight or base is None:
                continue
            for leaf, leaf_weight in (self.derived[base].terms if base in self.derived else ((base, 1.0),)):
                flat[leaf] += weight * leaf_weight
        kept = tuple((leaf, weight) for leaf, weight in sorted(flat.items()) if weight)
        if not kept:
            return None
        self.derived[name] = Derived(kept)
        cells = [self.cells[leaf] for leaf, _ in kept]
        self.cells[name] = min(cells, key=lambda cell: (cell[1], cell[0]))
        return name

    def run(self, samples: int, seed: int) -> None:
        self.result = shared_bootstrap(self.index, self.stats, samples=samples, seed=seed, derived=self.derived)

    def rerun(self, names: Sequence[str], seed: int, samples: int) -> BootstrapResult:
        """The named statistics alone under another seed (their values do not depend on the others)."""
        derived = {n: self.derived[n] for n in names if n in self.derived}
        bases = {leaf for n in derived for leaf, _ in derived[n].terms} | {n for n in names if n in self.stats}
        return shared_bootstrap(self.index, {b: self.stats[b] for b in sorted(bases)}, samples=samples, seed=seed,
                                derived=derived)


class _Analysis:
    def __init__(self, table: OutcomeTable, config: AnalysisConfig, split: str) -> None:
        self.table, self.config, self.split = table, config, split
        self.book = _Book(table)
        self.levels = table.evaluation.slices.get("rule_level", {})
        self.categories = table.evaluation.slices.get("category", {})
        self.rows: dict[str, list[tuple[dict[str, Any], str | None]]] = defaultdict(list)
        self.tested: set[str] = set()
        self._averages: dict[tuple[str, str, str, str], dict[str, float]] = {}
        primary = config.primary
        self.primary_system = primary.system
        self.run_systems = [name for name, s in table.systems.items() if s.status == "run"]

    # ------------------------------------------------------------------ helpers

    def average(self, system: str, line: str, condition: str, endpoint: str) -> dict[str, float]:
        key = (system, line, condition, endpoint)
        if key not in self._averages:
            self._averages[key] = self.table.average(system, line, condition, endpoint)
        return self._averages[key]

    def endpoints(self, system: str) -> tuple[str, ...]:
        return tuple(e for e in ENDPOINT_ORDER if self.config.system(system).provides(e))

    def main_endpoint(self, system: str) -> str:
        """The primary endpoint where the system can give it, else detection (Stage 1-only systems)."""
        return self.config.primary.endpoint if self.config.system(system).provides(self.config.primary.endpoint) \
            else "stage1_correct"

    def primary_line(self, system: str) -> str:
        return self.table.systems[system].primary_line

    def level_ids(self, ids: Iterable[str], level: str) -> list[str]:
        return [i for i in ids if level == OVERALL or self.levels.get(i) == level]

    def present_levels(self, ids: Iterable[str]) -> list[str]:
        found = {self.levels.get(i) for i in ids}
        return [level for level in LEVELS if level in found]

    def add(self, section: str, fields: dict[str, Any], name: str | None) -> str | None:
        self.rows[section].append((fields, name))
        return name

    # ------------------------------------------------------------------ H2 (T6)

    def benefits(self, system: str, line: str, endpoint: str, pair: tuple[str, str], *, section: str = "h2",
                 exclude: frozenset[str] = frozenset(), tag: str = "") -> dict[str, str | None]:
        """Per-level and overall a − b benefits; returns level -> statistic name."""
        a, b = pair
        first, second = self.average(system, line, a, endpoint), self.average(system, line, b, endpoint)
        ids = [i for i in sorted(first) if i in second and i not in exclude]
        name = contrast_name(a, b)
        out = {}
        for level in [OVERALL, *self.present_levels(ids)]:
            stat = self.book.values(f"benefit|{system}|{line}|{endpoint}|{name}|{level}{tag}",
                                    first, self.level_ids(ids, level), second)
            fields = {"system": system, "line": line, "endpoint": endpoint, "contrast": name, "level": level}
            out[level] = self.add(section, fields, stat) if section else stat
        return out

    def trend(self, name: str, by_level: Mapping[str, str | None], weights: Sequence[float],
              levels: Sequence[str]) -> str | None:
        return self.book.combine(name, [(by_level.get(level), w) for level, w in zip(levels, weights)])

    def build_h2(self) -> None:
        primary = self.config.primary
        for system in self.run_systems:
            for line in self.table.systems[system].lines:
                for endpoint in self.endpoints(system):
                    for pair in GENUINE_PAIRS:
                        by_level = self.benefits(system, line, endpoint, pair)
                        key = f"{system}|{line}|{endpoint}|{contrast_name(*pair)}"
                        fields = {"system": system, "line": line, "endpoint": endpoint, "contrast": contrast_name(*pair)}
                        for trend in ("linear", "quadratic"):
                            self.add("h2_trends", {**fields, "trend": trend, "levels": list(primary.levels)},
                                     self.trend(f"trend|{key}|{trend}", by_level, TREND_WEIGHTS[trend], primary.levels))
                        for level in by_level:
                            if level not in (OVERALL, "L0"):
                                self.add("h2_trends", {**fields, "trend": "level_minus_L0", "levels": [level, "L0"]},
                                         self.book.combine(f"minus_l0|{key}|{level}",
                                                           [(by_level[level], 1.0), (by_level.get("L0"), -1.0)]))
            for endpoint in self.endpoints(system):
                for pair in MISMATCH_PAIRS:  # mismatch controls always use the full-trained model (FR6)
                    self.benefits(system, "test_time", endpoint, pair, section="mismatch")

    def primary_names(self, system: str, endpoint: str) -> tuple[str, str]:
        key = f"{system}|{self.primary_line(system)}|{endpoint}|{self.config.primary.contrast}"
        return f"trend|{key}|linear", f"trend|{key}|quadratic"

    # ------------------------------------------------------------------ H1, H3, H4, H5 (T7)

    def build_h1(self) -> None:
        primary = self.config.primary
        for system in self.run_systems:
            line = self.primary_line(system)
            for endpoint in self.endpoints(system):
                for condition in self.condition_order():
                    values = self.average(system, line, condition, endpoint)
                    by_level = {}
                    for level in [OVERALL, *self.present_levels(values)]:
                        fields = {"system": system, "line": line, "endpoint": endpoint, "condition": condition,
                                  "level": level}
                        by_level[level] = self.add("h1", fields, self.book.values(
                            f"rate|{system}|{line}|{endpoint}|{condition}|{level}", values,
                            self.level_ids(sorted(values), level)))
                    self.add("h1_trends", {"system": system, "line": line, "endpoint": endpoint,
                                           "condition": condition, "trend": "linear", "levels": list(primary.levels)},
                             self.trend(f"h1_trend|{system}|{line}|{endpoint}|{condition}", by_level,
                                        TREND_WEIGHTS["linear"], primary.levels))

    def condition_order(self) -> tuple[str, ...]:
        return CONDITIONS

    def build_h3(self) -> None:
        reference = self.primary_system
        if reference not in self.run_systems:
            return
        contrast = self.config.primary.contrast
        pair = PAIRS[contrast]
        for system in self.run_systems:
            if system == reference:
                continue
            for endpoint in (e for e in self.endpoints(system) if e in self.endpoints(reference)):
                fields = {"system": system, "reference": reference, "endpoint": endpoint, "contrast": contrast}
                own = self.benefits(system, "test_time", endpoint, pair, section="")
                ref = self.benefits(reference, "test_time", endpoint, pair, section="")
                self.add("h3_tested", {**fields, "line": "test_time", "level": OVERALL},
                         self.book.combine(f"h3|{system}|{reference}|{endpoint}|{contrast}|test_time",
                                           [(own[OVERALL], 1.0), (ref.get(OVERALL), -1.0)]))
                own_line, ref_line = self.primary_line(system), self.primary_line(reference)
                own = self.benefits(system, own_line, endpoint, pair, section="")
                ref = self.benefits(reference, ref_line, endpoint, pair, section="")
                for level in own:
                    self.add("h3_descriptive", {**fields, "line": f"{own_line} vs {ref_line}", "level": level,
                                                "caption": H3_CAPTION},
                             self.book.combine(f"h3|{system}|{reference}|{endpoint}|{contrast}|primary|{level}",
                                               [(own[level], 1.0), (ref.get(level), -1.0)]))

    def build_h4(self) -> None:
        primary = self.config.primary
        first, last = primary.levels[0], primary.levels[-1]
        for system in self.run_systems:
            if not self.config.system(system).provides("request_interpretation"):
                continue
            line = self.primary_line(system)
            names: dict[tuple[str, str, str], str | None] = {}
            for condition in self.condition_order():
                ids = [e.example_id for e in self.table.population("oracle_exact", condition)]
                streams = {"detection": self.average(system, line, condition, "request_detected"),
                           "oracle": self.average(system, line, condition, "oracle_exact"),
                           "routed": self.average(system, line, condition, "request_interpretation")}
                for level in [OVERALL, *self.present_levels(ids)]:
                    level_ids = self.level_ids(ids, level)
                    for measure, values in streams.items():
                        fields = {"system": system, "line": line, "condition": condition, "level": level,
                                  "measure": measure}
                        names[(condition, level, measure)] = self.add("h4", fields, self.book.values(
                            f"h4|{system}|{line}|{condition}|{level}|{measure}", values, level_ids))
            terms = [(names.get(("full", first, "detection")), 1.0), (names.get(("full", last, "detection")), -1.0),
                     (names.get(("full", first, "oracle")), -1.0), (names.get(("full", last, "oracle")), 1.0)]
            self.add("h4_contrast", {"system": system, "line": line, "condition": "full",
                                     "definition": f"drop(detection) - drop(oracle), drop = rate_{first} - rate_{last}"},
                     self.book.combine(f"h4_contrast|{system}", terms))

    def build_h5(self) -> None:
        primary = self.config.primary
        pair = PAIRS[primary.contrast]
        for system in self.run_systems:
            line, endpoint = self.primary_line(system), self.main_endpoint(system)
            first, second = (self.average(system, line, c, endpoint) for c in pair)
            ids = [i for i in sorted(first) if i in second]
            found = sorted({self.categories[i] for i in ids if i in self.categories})
            for category in found:
                in_category = [i for i in ids if self.categories.get(i) == category]
                fields = {"system": system, "line": line, "endpoint": endpoint, "category": category}
                for condition in (c for c in self.condition_order() if c not in MISMATCH_CONDITIONS):
                    values = self.average(system, line, condition, endpoint)
                    self.add("h5_rates", {**fields, "condition": condition},
                             self.book.values(f"h5_rate|{system}|{endpoint}|{condition}|{category}", values,
                                              [i for i in in_category if i in values]))
                self.add("h5_benefits", {**fields, "contrast": primary.contrast},
                         self.book.values(f"h5_benefit|{system}|{endpoint}|{category}", first, in_category, second))
            self.build_standardized(system, line, endpoint, first, second, ids)

    def build_standardized(self, system: str, line: str, endpoint: str, first: Mapping[str, float],
                           second: Mapping[str, float], ids: Sequence[str]) -> None:
        """Each level's benefit reweighted to the pooled category mix over categories at every level."""
        primary = self.config.primary
        considered = [i for i in ids if self.levels.get(i) in primary.levels and i in self.categories]
        by_level = {level: {self.categories[i] for i in considered if self.levels[i] == level} for level in primary.levels}
        included = sorted(set.intersection(*by_level.values())) if all(by_level.values()) else []
        pooled = [i for i in considered if self.categories[i] in included]
        weights = {c: sum(self.categories[i] == c for i in pooled) / len(pooled) for c in included} if pooled else {}
        standardized = {}
        for level in primary.levels:
            terms = [(self.book.values(f"h5_cell|{system}|{endpoint}|{level}|{c}", first,
                                       [i for i in pooled if self.levels[i] == level and self.categories[i] == c],
                                       second), w) for c, w in weights.items()]
            standardized[level] = self.book.combine(f"h5_std|{system}|{endpoint}|{level}", terms) if terms else None
            self.add("h5_standardized", {"system": system, "line": line, "endpoint": endpoint, "level": level,
                                         "kind": "standardized_benefit"}, standardized[level])
        self.add("h5_standardized", {"system": system, "line": line, "endpoint": endpoint, "level": "trend",
                                     "kind": "standardized_linear_trend"},
                 self.trend(f"h5_std_trend|{system}|{endpoint}", standardized, TREND_WEIGHTS["linear"], primary.levels))
        excluded = sorted({self.categories[i] for i in considered} - set(included))
        share = (len(considered) - len(pooled)) / len(considered) if considered else None
        self.rows["h5_exclusions"].append(({"system": system, "endpoint": endpoint, "included": included,
                                            "excluded": excluded, "excluded_share": share,
                                            "weights": {c: weights[c] for c in included}}, None))

    # ------------------------------------------------------------------ Holm and sensitivity (T8)

    def member_statistic(self, member: FamilyMember) -> str | None:
        """The member's statistic name, for systems that ran; it may still fail to form (empty cell)."""
        if member.kind == "h1_trend":
            line = self.primary_line(member.system)
            return f"h1_trend|{member.system}|{line}|{member.endpoint}|{member.condition}"
        if member.kind == "h2_trend":
            return f"trend|{member.system}|{self.primary_line(member.system)}|{member.endpoint}|{member.contrast}|linear"
        if member.kind == "h3_difference":
            pair = PAIRS[member.contrast]
            own = self.benefits(member.system, "test_time", member.endpoint, pair, section="")
            ref = self.benefits(member.reference, "test_time", member.endpoint, pair, section="")
            return self.book.combine(f"h3|{member.system}|{member.reference}|{member.endpoint}|{member.contrast}|test_time",
                                     [(own.get(OVERALL), 1.0), (ref.get(OVERALL), -1.0)])
        if member.kind == "h4_contrast":
            return f"h4_contrast|{member.system}"
        pair = PAIRS[member.contrast]  # mismatch_control, on the test-time line
        return self.benefits(member.system, "test_time", member.endpoint, pair, section="")[OVERALL]

    def build_holm(self) -> None:
        """Members come from the config, never the inputs; an uncomputable one keeps its place (FR17)."""
        for member in self.config.family:
            ran = all(s in self.run_systems for s in (member.system, member.reference) if s)
            name = self.member_statistic(member) if ran else None
            if name is not None and name not in self.book.stats and name not in self.book.derived:
                name = None  # e.g. an empty level cell: the systems ran, the statistic cannot form
            fields = {"name": member.name, "kind": member.kind, "system": member.system,
                      "endpoint": member.endpoint, "contrast": member.contrast, "condition": member.condition,
                      "reference": member.reference, "status": "ok" if ran else "not_run"}
            self.rows["holm"].append(({k: v for k, v in fields.items() if v is not None}, name))
            if name:
                self.tested.add(name)

    def build_sensitivity(self) -> None:
        """FR18: each line alone, never crossed, on the headline contrasts and the primary contrast."""
        evaluation = self.table.evaluation
        lines: list[tuple[str, frozenset[str], tuple[tuple[str, str], ...]]] = []
        if evaluation.dup_ids is not None:
            lines.append(("primary_minus_dup", frozenset(evaluation.dup_ids), (*GENUINE_PAIRS, *MISMATCH_PAIRS)))
        for system in self.run_systems:
            for endpoint in self.endpoints(system):
                for label, excluded, pairs in lines:
                    for pair in pairs:
                        line = "test_time" if pair in MISMATCH_PAIRS else self.primary_line(system)
                        self.sensitivity_row(system, line, endpoint, pair, label, excluded)
                for pair in MISMATCH_PAIRS:
                    donors = frozenset().union(*(evaluation.sets.cue_donor_ids.get(c, frozenset()) for c in pair))
                    self.sensitivity_row(system, "test_time", endpoint, pair, "without_cue_donors", donors)
        if self.primary_system in self.run_systems and evaluation.dup_ids is not None:
            primary = self.config.primary
            line = self.primary_line(self.primary_system)
            by_level = self.benefits(self.primary_system, line, primary.endpoint, PAIRS[primary.contrast], section="",
                                     exclude=frozenset(evaluation.dup_ids), tag="|primary_minus_dup")
            self.add("sensitivity", {"system": self.primary_system, "line": line, "endpoint": primary.endpoint,
                                     "contrast": primary.contrast, "statistic": "primary_linear_trend",
                                     "sensitivity": "primary_minus_dup"},
                     self.trend(f"trend|{self.primary_system}|{primary.contrast}|primary_minus_dup", by_level,
                                primary.weights, primary.levels))

    def sensitivity_row(self, system: str, line: str, endpoint: str, pair: tuple[str, str], label: str,
                        excluded: frozenset[str]) -> None:
        stat = self.benefits(system, line, endpoint, pair, section="", exclude=excluded, tag=f"|{label}")[OVERALL]
        self.add("sensitivity", {"system": system, "line": line, "endpoint": endpoint,
                                 "contrast": contrast_name(*pair), "statistic": "overall_benefit",
                                 "sensitivity": label}, stat)

    # ------------------------------------------------------------------ seed variation

    def build_seed_variation(self) -> list[dict[str, Any]]:
        rows = []
        primary = self.config.primary
        for system in self.run_systems:
            line = self.primary_line(system)
            for endpoint in self.endpoints(system):
                for condition in self.condition_order():
                    rows.append({"system": system, "line": line, "endpoint": endpoint, "metric": f"rate:{condition}",
                                 **seed_variation(self.table.seed_rates(system, line, condition, endpoint))})
                for a, b in GENUINE_PAIRS:
                    rows.append({"system": system, "line": line, "endpoint": endpoint,
                                 "metric": f"benefit:{contrast_name(a, b)}",
                                 **seed_variation(self.table.seed_contrasts(system, line, a, b, endpoint))})
            endpoint = self.main_endpoint(system)
            per_seed = self.seed_trends(system, line, endpoint, PAIRS[primary.contrast])
            if per_seed:
                rows.append({"system": system, "line": line, "endpoint": endpoint,
                             "metric": f"primary_contrast:{primary.contrast}:{primary.trend}", **seed_variation(per_seed)})
        return rows

    def seed_trends(self, system: str, line: str, endpoint: str, pair: tuple[str, str]) -> dict[int, float]:
        primary = self.config.primary
        first = self.table.seed_values(system, line, pair[0], endpoint)
        second = self.table.seed_values(system, line, pair[1], endpoint)
        out = {}
        for seed in sorted(first):
            benefits = []
            for level in primary.levels:
                ids = [i for i in first[seed] if i in second[seed] and self.levels.get(i) == level]
                if not ids:
                    break
                benefits.append(sum(first[seed][i] - second[seed][i] for i in ids) / len(ids))
            else:
                out[seed] = sum(w * b for w, b in zip(primary.weights, benefits))
        return out

    # ------------------------------------------------------------------ assembly

    def summary(self, name: str | None, *, tested: bool = False) -> dict[str, Any]:
        if name is None:
            return {"status": "empty", "point": None, "ci": None, "examples": 0, "dialogues": 0}
        cells = self.config.cells
        estimate = self.book.result.estimate(name, confidence=self.config.bootstrap.confidence,
                                             max_excluded_share=cells.max_excluded_share)
        examples, dialogues = self.book.cells[name]
        status = "sparse" if dialogues < cells.min_dialogues else ("unstable" if estimate.unstable else "ok")
        out = {"point": estimate.point, "ci": list(estimate.ci) if estimate.ci else None, "examples": examples,
               "dialogues": dialogues, "excluded_replicates": estimate.excluded, "status": status}
        if tested:
            out["p"] = estimate.p if status == "ok" else None
        return out

    def section(self, name: str) -> list[dict[str, Any]]:
        return [{**fields, **self.summary(stat, tested=stat in self.tested)} for fields, stat in self.rows.get(name, [])]

    def primary_test(self) -> dict[str, Any]:
        primary = self.config.primary
        fields = {"system": primary.system, "endpoint": primary.endpoint, "contrast": primary.contrast,
                  "trend": primary.trend, "levels": list(primary.levels), "weights": list(primary.weights)}
        if primary.system not in self.run_systems:
            if self.split == "test":
                raise AnalysisError("primary_not_run", f"the primary system {primary.system} has no test outputs")
            return {**fields, "status": "not_run"}
        linear, quadratic = self.primary_names(primary.system, primary.endpoint)
        if linear not in self.book.derived:
            raise AnalysisError("primary_untestable", "the primary contrast lacks a level cell")
        estimate = self.summary(linear, tested=True)
        if estimate["status"] != "ok":
            raise AnalysisError("primary_untestable",
                                f"the primary contrast touches a {estimate['status']} cell "
                                f"({estimate['dialogues']} dialogues in its smallest cell)")
        low, high = estimate["ci"]
        return {**fields, "line": self.primary_line(primary.system), "status": "ok", "estimate": estimate,
                "decision": "interval_excludes_0" if low > 0 or high < 0 else "interval_includes_0",
                "quadratic": self.summary(quadratic)}

    def labels(self) -> list[dict[str, Any]]:
        """AC-09: a positive overall benefit without an interaction is labelled, never sold as one."""
        out = []
        for fields, stat in self.rows["h2_trends"]:
            if fields["trend"] != "linear" or stat is None:
                continue
            overall = self.summary(f"benefit|{fields['system']}|{fields['line']}|{fields['endpoint']}|"
                                   f"{fields['contrast']}|{OVERALL}")
            trend = self.summary(stat)
            if overall["ci"] and trend["ci"] and _excludes_zero(overall["ci"]) and not _excludes_zero(trend["ci"]):
                out.append({k: fields[k] for k in ("system", "line", "endpoint", "contrast")} | {"label": MAIN_EFFECT_LABEL})
        return out

    def holm_section(self) -> dict[str, Any]:
        rows = []
        for fields, stat in self.rows["holm"]:
            if stat is None:
                status = "not_run" if fields["status"] == "not_run" else "untestable"
                rows.append({**fields, "status": status, "cell_status": "empty" if status == "untestable" else None,
                             "p": 1.0, "point": None, "ci": None})
                continue
            summary = self.summary(stat, tested=True)
            if summary["status"] != "ok":
                rows.append({**fields, **summary, "status": "untestable", "cell_status": summary["status"], "p": 1.0})
            else:
                rows.append({**fields, **summary})
        adjusted = holm([row["p"] for row in rows])
        for row, value in zip(rows, adjusted):
            row["p_holm"] = value
            row["reject_at_alpha"] = row["status"] == "ok" and value <= self.config.alpha
        return {"alpha": self.config.alpha, "family_size": len(rows), "members": rows}

    def precision(self) -> list[dict[str, Any]]:
        """FR16 dev precision report: the primary design's interval, cells, and a second-seed check."""
        primary = self.config.primary
        bootstrap = self.config.bootstrap
        rows, names = [], []
        for system in self.run_systems:
            endpoint = self.main_endpoint(system)
            linear, _ = self.primary_names(system, endpoint)
            if linear in self.book.derived:
                names.append((system, endpoint, linear))
        second = self.book.rerun([n for _, _, n in names], bootstrap.seed + 1, bootstrap.samples) if names else None
        for system, endpoint, linear in names:
            first = self.summary(linear)
            other = second.estimate(linear, confidence=bootstrap.confidence,
                                    max_excluded_share=self.config.cells.max_excluded_share)
            line = self.primary_line(system)
            cells = []
            for level in (*primary.levels, *self.config.exploratory_levels):
                for condition in PAIRS[primary.contrast]:
                    stat = f"rate|{system}|{line}|{endpoint}|{condition}|{level}"
                    examples, dialogues = self.book.cells.get(stat, (0, 0))
                    cells.append({"level": level, "condition": condition, "examples": examples, "dialogues": dialogues})
            agreement = max(abs(x - y) for x, y in zip(first["ci"], other.ci)) if first["ci"] and other.ci else None
            rows.append({"system": system, "line": line, "endpoint": endpoint, "configured_primary": system == primary.system,
                         "contrast": primary.contrast, "trend": primary.trend, "estimate": first,
                         "half_width": (first["ci"][1] - first["ci"][0]) / 2 if first["ci"] else None,
                         "second_seed": {"seed": bootstrap.seed + 1, "ci": list(other.ci) if other.ci else None},
                         "monte_carlo_max_difference": agreement,
                         "monte_carlo_ok": agreement is not None and agreement <= PRECISION_TOLERANCE,
                         "cells": cells})
        return rows


def _excludes_zero(interval: Sequence[float]) -> bool:
    return interval[0] > 0 or interval[1] < 0


def analyse(table: OutcomeTable, config: AnalysisConfig, *, split: str) -> dict[str, Any]:
    """Build every estimand, run the shared bootstrap once, and assemble the report body."""
    analysis = _Analysis(table, config, split)
    analysis.build_h2()
    analysis.build_h1()
    analysis.build_h3()
    analysis.build_h4()
    analysis.build_h5()
    analysis.build_holm()
    analysis.build_sensitivity()
    primary = config.primary
    if primary.system in analysis.run_systems:
        analysis.tested.add(analysis.primary_names(primary.system, primary.endpoint)[0])
    analysis.book.run(config.bootstrap.samples, config.bootstrap.seed)
    statuses = [analysis.summary(n)["status"] for n in sorted({*analysis.book.stats, *analysis.book.derived})]
    report = {
        "systems": {name: s.status for name, s in table.systems.items()},
        "primary_test": analysis.primary_test(),
        "h1": {"rates": analysis.section("h1"), "trends": analysis.section("h1_trends")},
        "h2": {"benefits": analysis.section("h2"), "trends": analysis.section("h2_trends"), "labels": analysis.labels()},
        "mismatch_controls": analysis.section("mismatch"),
        "h3": {"tested": analysis.section("h3_tested"), "descriptive": analysis.section("h3_descriptive"),
               "caption": H3_CAPTION},
        "h4": {"rates": analysis.section("h4"), "contrasts": analysis.section("h4_contrast")},
        "h5": {"rates": analysis.section("h5_rates"), "benefits": analysis.section("h5_benefits"),
               "standardized": analysis.section("h5_standardized"),
               "exclusions": [fields for fields, _ in analysis.rows["h5_exclusions"]]},
        "holm": analysis.holm_section(),
        "sensitivity": analysis.section("sensitivity"),
        "seed_variation": analysis.build_seed_variation(),
        "statistics": {"count": len(statuses), "sparse": statuses.count("sparse"),
                       "unstable": statuses.count("unstable")},
    }
    if split == "dev":
        report["precision"] = analysis.precision()
    return report
