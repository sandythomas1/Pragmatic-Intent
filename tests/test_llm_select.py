"""Spec 009 T11: prompt selection (FR9, AC-009-6) and the dialogue-level selection sample.

Fixtures are invented (PMUL9xxx IDs, "zq-" sentinel values) and live in a temporary repository root.
"""

import io
import json
import math
import random
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from src.analysis.outcomes import load_evaluation_set
from src.data.direct_dataset import CONDITIONS
from src.evaluation import stage2
from src.llm import compose as lc
from src.llm import prompt, schema
from src.llm import run as lr
from src.llm import sample as ls
from src.llm import select as sel
from tests import test_llm_compose as composetests
from tests import test_llm_run as runtests
from tests.analysis_fixtures import Workspace, write_corpus

SEEDS = (13, 42)
ROUTER_ROOT = Path("outputs/stage1/deberta-v3-large")
SELECTION = Path("outputs/llm/selection/fake-llm")
DIALOGUES = 30


def router_label(example, condition, train, seed):
    """train-full routes everything correctly; train-none drops every third dialogue to no_request,
    and seed 42 also misroutes every fifth; train-one is never used by selection."""
    number = int(example.dialogue_id[4:8])
    if train == "none" and (number % 3 == 0 or (seed == 42 and number % 5 == 0)):
        return "no_request"
    return example.label


def interpretation_row(evaluation, example, condition, exact=True):
    gold = evaluation.gold[example.example_id]
    slots = dict(gold.slots) if exact else {"hotel.area": "zq-south"}
    return {"example_id": example.example_id, "condition": condition, "prediction": example.label,
            "category": gold.category or "booking", "slots": slots, "requested_slots": sorted(gold.requested_slots)}


def jsonl(rows):
    return "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows).encode()


class Lab(unittest.TestCase):
    """A repository root holding a corpus, a recipe, five-ish router runs and two variants' runs."""

    def setUp(self):
        self.ws = Workspace()
        self.root = self.ws.root
        self.items, self.dialogues = write_corpus(self.ws, DIALOGUES)
        self.run_root = runtests.Root(self.root)
        self.recipe = self.run_root.recipe()
        self.evaluation = load_evaluation_set(self.items, self.dialogues, "dev", "auto-v1")
        for train in ("none", "one", "full"):
            for seed in SEEDS:
                rows = [{"example_id": e.example_id, "condition": c, "prediction": router_label(e, c, train, seed)}
                        for c in CONDITIONS for e in self.evaluation.members(c)]
                composetests.write_router_run(self.root, train, seed, rows=rows)

    def tearDown(self):
        self.ws.cleanup()

    def write_variant(self, variant, *, inexact=lambda e, c: False, ids=None, sample="all", drop=0,
                      invalid_calls=0, distinct_inputs=100):
        rows, oracle = [], []
        for condition in lr.SELECTION_CONDITIONS:
            for e in self.evaluation.members(condition):
                if ids is None or e.example_id in ids:
                    rows.append(interpretation_row(self.evaluation, e, condition, not inexact(e, condition)))
            oracle += [row for row in rows[-len(self.evaluation.members(condition)):]
                       if row["condition"] == condition and self._oracle(row["example_id"], condition)]
        rows = rows[drop:]
        directory = self.root / SELECTION / variant / "dev"
        directory.mkdir(parents=True, exist_ok=True)
        files = {"interpretation.jsonl": jsonl(rows), "oracle.jsonl": jsonl(oracle), "routed.jsonl": jsonl([])}
        for name, data in files.items():
            (directory / name).write_bytes(data)
        rendered = prompt.main_instructions(self.recipe.prompt_path(variant),
                                            schema.load_slot_keys(self.recipe.slot_keys)).sha256
        provenance = {"version": "llm-run-v1", "task": "main", "split": "dev", "system": "fake-llm",
                      "variant": variant, "selected_variant": variant == "p1", "conditions": ["none", "full"],
                      "sample": sample, "model": "fake-model", "prompt": {"rendered_sha256": rendered},
                      "counts": {"invalid_calls_by_reason": {"parse": invalid_calls} if invalid_calls else {},
                                 "distinct_inputs": distinct_inputs},
                      "outputs": {name: composetests.sha(data) for name, data in files.items()}}
        (directory / "provenance.main.json").write_text(json.dumps(provenance), encoding="utf-8")
        return directory

    def _oracle(self, example_id, condition):
        return any(e.example_id == example_id for e in self.evaluation.oracle_members(condition))

    def select(self, **kwargs):
        return sel.select_prompt(self.recipe, split="dev", router_root=ROUTER_ROOT, items=self.items,
                                 dialogues=self.dialogues, root=self.root, **kwargs)

    def assertRefused(self, code):
        with self.assertRaises(sel.SelectError) as caught:
            self.select()
        self.assertEqual(caught.exception.code, code)
        self.assertFalse((self.root / SELECTION / "report.json").exists())

    def independent_rates(self, variant, evaluation=None):
        """Compose both conditions at once through T9, then score with stage2's own routed formula."""
        evaluation = evaluation or self.evaluation
        directory = self.root / SELECTION / variant / "dev"
        interpretation = [json.loads(line) for line in (directory / "interpretation.jsonl").read_text().splitlines()]
        oracle = [json.loads(line) for line in (directory / "oracle.jsonl").read_text().splitlines()]
        ids = {e.example_id for e in evaluation.examples}
        rates = {}
        for condition in lr.SELECTION_CONDITIONS:
            for seed in SEEDS:
                path = self.root / ROUTER_ROOT / f"train-{condition}" / f"seed{seed}" / "predictions.jsonl"
                router = [row for row in map(json.loads, path.read_text().splitlines()) if row["example_id"] in ids]
                composed = lc.compose_rows(router, interpretation, conditions=set(lr.SELECTION_CONDITIONS))
                report = stage2.build_report(
                    list(evaluation.examples), dict(evaluation.gold),
                    [r for r in composed if r["condition"] == condition],
                    [r for r in oracle if r["condition"] == condition],
                    conditions=[condition], sets=evaluation.sets, bootstrap_samples=1, seed=0)
                rates[(condition, seed)] = report["conditions"][condition]["routed_interpretation"]["success"]
        return rates


class ChooseTest(unittest.TestCase):
    def test_higher_mean_wins(self):
        self.assertEqual(sel.choose({"p1": 0.40, "p2": 0.45}), ("p2", "higher_mean"))
        self.assertEqual(sel.choose({"p1": 0.45, "p2": 0.40}), ("p1", "higher_mean"))

    def test_p1_wins_a_tie_within_the_margin(self):
        self.assertEqual(sel.choose({"p1": 0.40, "p2": 0.41}), ("p1", "tie_within_margin"))
        self.assertEqual(sel.choose({"p1": 0.40, "p2": 0.40}), ("p1", "higher_mean"))
        self.assertEqual(sel.choose({"p1": 0.40, "p2": 0.4101}), ("p2", "higher_mean"))

    def test_the_preferred_variant_must_exist(self):
        with self.assertRaises(sel.SelectError) as caught:
            sel.choose({"p2": 0.5, "p3": 0.4})
        self.assertEqual(caught.exception.code, "no_preferred_variant")


class SampleDrawTest(unittest.TestCase):
    def setUp(self):
        self.ws = Workspace()
        self.items, self.dialogues = write_corpus(self.ws, DIALOGUES)
        self.examples = load_evaluation_set(self.items, self.dialogues, "dev", "auto-v1").examples

    def tearDown(self):
        self.ws.cleanup()

    def test_draw_is_deterministic(self):
        first, second = ls.draw(self.items, "dev", 10, 7), ls.draw(self.items, "dev", 10, 7)
        self.assertEqual(first, second)
        self.assertEqual(first.ids_sha256, second.ids_sha256)
        self.assertNotEqual(first.example_ids, ls.draw(self.items, "dev", 10, 8).example_ids)

    def test_draw_is_dialogue_level(self):
        sample = ls.draw(self.items, "dev", 10, 7)
        chosen = {e.dialogue_id for e in self.examples if e.example_id in sample.example_ids}
        self.assertEqual(len(chosen), 10)
        whole = {e.example_id for e in self.examples if e.dialogue_id in chosen}
        self.assertEqual(sample.example_ids, whole)  # every turn and variant of a drawn dialogue

    def test_draw_ignores_pool_order(self):
        pool = [f"PMUL{9100 + d}.json" for d in range(1, 21)]
        shuffled = pool[:]
        random.Random(3).shuffle(shuffled)
        self.assertEqual(ls.draw_dialogues(pool, 5, 1), ls.draw_dialogues(shuffled, 5, 1))

    def test_bad_sizes_are_refused(self):
        for dialogues in (0, DIALOGUES + 1, True):
            with self.subTest(dialogues), self.assertRaises(ls.SampleError):
                ls.draw(self.items, "dev", dialogues, 7)

    def test_provenance_holds_counts_and_a_hash_only(self):
        block = ls.draw(self.items, "dev", 10, 7).as_provenance()
        self.assertEqual(set(block), {"version", "unit", "dialogues", "seed", "examples", "example_ids_sha256"})
        self.assertNotIn("PMUL", json.dumps(block))


class SelectPromptTest(Lab):
    def test_the_better_variant_is_selected_and_written(self):
        self.write_variant("p1")
        self.write_variant("p2", inexact=lambda e, c: e.variant == "indirect")
        report = self.select()
        self.assertEqual((report["selected"], report["reason"], report["recipe_needs_update"]),
                         ("p1", "higher_mean", False))
        self.assertGreater(report["variants"]["p1"]["mean"], report["variants"]["p2"]["mean"] + sel.TIE_MARGIN)
        self.assertEqual(report["variants"]["p1"]["runs"], 2 * len(SEEDS))
        self.assertEqual(json.loads((self.root / SELECTION / "report.json").read_text()), report)

    def test_selection_equals_independent_compose_and_score(self):
        self.write_variant("p1")
        self.write_variant("p2", inexact=lambda e, c: e.turn_index == 2)
        report = self.select()
        for variant in ("p1", "p2"):
            independent = self.independent_rates(variant)
            reported = report["variants"][variant]["rates"]
            for (condition, seed), rate in independent.items():
                with self.subTest(variant=variant, condition=condition, seed=seed):
                    self.assertTrue(math.isclose(reported[condition][str(seed)], rate, abs_tol=1e-12))
            self.assertTrue(math.isclose(report["variants"][variant]["mean"],
                                         sum(independent.values()) / len(independent), abs_tol=1e-12))
        # the routers differ by seed under none, so the per-seed rates are not all equal
        self.assertNotEqual(report["variants"]["p1"]["rates"]["none"]["13"],
                            report["variants"]["p1"]["rates"]["none"]["42"])

    def test_p2_wins_when_clearly_better_and_the_recipe_must_change(self):
        self.write_variant("p1", inexact=lambda e, c: e.variant == "direct")
        self.write_variant("p2")
        report = self.select()
        self.assertEqual((report["selected"], report["reason"], report["recipe_needs_update"]),
                         ("p2", "higher_mean", True))

    def test_p1_wins_a_near_tie(self):
        one = sorted(self.evaluation.members("none"), key=lambda e: e.example_id)[1]
        self.write_variant("p1", inexact=lambda e, c: e.example_id == one.example_id and c == "none")
        self.write_variant("p2")
        report = self.select()
        difference = report["variants"]["p2"]["mean"] - report["variants"]["p1"]["mean"]
        self.assertTrue(0 < difference <= sel.TIE_MARGIN)
        self.assertEqual((report["selected"], report["reason"]), ("p1", "tie_within_margin"))

    def test_report_has_no_ids_or_text(self):
        self.write_variant("p1")
        self.write_variant("p2")
        self.select()
        text = (self.root / SELECTION / "report.json").read_text()
        for forbidden in ("PMUL", "zq-", "Book the hotel", "Could you", "line 0", "example_id"):
            self.assertNotIn(forbidden, text)

    def test_invalid_rate_is_reported_and_flagged(self):
        self.write_variant("p1", invalid_calls=3, distinct_inputs=100)
        self.write_variant("p2")
        variants = self.select()["variants"]
        self.assertEqual((variants["p1"]["invalid_rate"], variants["p1"]["invalid_rate_over_limit"]), (0.03, True))
        self.assertFalse(variants["p2"]["invalid_rate_over_limit"])


class SelectRefusalTest(Lab):
    def test_test_and_unknown_splits_are_refused(self):
        for split, code in (("test", "refused"), ("train", "unknown_split")):
            with self.subTest(split), self.assertRaises(sel.SelectError) as caught:
                sel.select_prompt(self.recipe, split=split, router_root=ROUTER_ROOT, items=self.items,
                                  dialogues=self.dialogues, root=self.root)
            self.assertEqual(caught.exception.code, code)

    def test_a_missing_variant_run_is_refused(self):
        self.write_variant("p1")
        self.assertRefused("missing_run")

    def test_a_changed_stream_is_refused(self):
        self.write_variant("p1")
        directory = self.write_variant("p2")
        with (directory / "interpretation.jsonl").open("ab") as handle:
            handle.write(b"\n")
        self.assertRefused("run_changed")

    def test_a_changed_prompt_is_refused(self):
        self.write_variant("p1")
        self.write_variant("p2")
        self.run_root.write("outputs/llm/prompts/p2.txt", "A different prompt.\nSlots:\n{{slot_keys}}\n")
        self.assertRefused("prompt_changed")

    def test_a_run_of_another_shape_is_refused(self):
        self.write_variant("p1")
        directory = self.write_variant("p2")
        provenance = json.loads((directory / "provenance.main.json").read_text())
        for field, value in (("conditions", None), ("split", "test"), ("model", "other-model"), ("variant", "p1")):
            with self.subTest(field):
                (directory / "provenance.main.json").write_text(json.dumps({**provenance, field: value}))
                self.assertRefused("not_a_selection_run")

    def test_incomplete_coverage_is_refused(self):
        self.write_variant("p1")
        self.write_variant("p2", drop=1)
        self.assertRefused("coverage")

    def test_variants_on_different_inputs_are_refused(self):
        sample = ls.draw(self.items, "dev", 10, 7)
        self.write_variant("p1")
        self.write_variant("p2", ids=sample.example_ids, sample=sample.as_provenance())
        self.assertRefused("samples_differ")


class SampledSelectionTest(Lab):
    def setUp(self):
        super().setUp()
        self.sample = ls.draw(self.items, "dev", 10, 7)

    def test_selection_on_the_sample_scores_only_sampled_examples(self):
        block = self.sample.as_provenance()
        self.write_variant("p1", ids=self.sample.example_ids, sample=block)
        self.write_variant("p2", ids=self.sample.example_ids, sample=block,
                           inexact=lambda e, c: e.variant == "indirect")
        report = self.select()
        self.assertEqual(report["sample"], block)
        self.assertEqual(report["selected"], "p1")
        cut = sel.restrict(self.evaluation, self.sample.example_ids)
        for condition in lr.SELECTION_CONDITIONS:
            population = [e for e in cut.members(condition) if e.label != "no_request"]
            self.assertEqual(report["variants"]["p1"]["scored_examples"][condition], len(population))
        independent = self.independent_rates("p2", cut)
        for (condition, seed), rate in independent.items():
            self.assertTrue(math.isclose(report["variants"]["p2"]["rates"][condition][str(seed)], rate, abs_tol=1e-12))

    def test_a_tampered_sample_block_is_refused(self):
        block = {**self.sample.as_provenance(), "seed": 8}
        self.write_variant("p1", ids=self.sample.example_ids, sample=block)
        self.write_variant("p2", ids=self.sample.example_ids, sample=block)
        self.assertRefused("sample_changed")


class RunnerSampleTest(runtests.Fixture):
    SAMPLE = ls.Sample(1, 7, frozenset({"PMUL9001_t02:direct"}))

    def test_a_sampled_run_calls_only_sampled_inputs_and_records_the_sample(self):
        provenance, factory = self.run_task(variant="p2", conditions=["none", "full"], sample=self.SAMPLE)
        self.assertEqual(provenance["sample"], self.SAMPLE.as_provenance())
        self.assertEqual(factory.calls, 2)  # the sampled example under none and full
        rows = self.root.rows("outputs/llm/selection/fake-llm/p2/dev/interpretation.jsonl")
        self.assertEqual({row["example_id"] for row in rows}, {"PMUL9001_t02:direct"})

    def test_an_unsampled_run_records_all(self):
        provenance, _ = self.run_task(variant="p2", conditions=["none", "full"])
        self.assertEqual(provenance["sample"], "all")

    def test_the_sample_needs_a_dev_main_selection_run(self):
        for kwargs in (dict(), dict(task="transfer")):
            with self.subTest(kwargs), self.assertRaises(lr.RunRefused):
                self.run_task(sample=self.SAMPLE, **kwargs)

    def test_the_sample_is_refused_once_a_selection_report_exists(self):
        self.root.write("outputs/llm/selection/fake-llm/report.json", "{}")
        factory = runtests.Factory()
        with self.assertRaises(lr.RunRefused):
            self.run_task(variant="p2", conditions=["none", "full"], sample=self.SAMPLE, factory=factory)
        self.assertEqual(factory.built, [])

    def test_a_sample_outside_the_inputs_is_refused(self):
        with self.assertRaises(lr.RunRefused):
            self.run_task(variant="p2", conditions=["none"], sample=ls.Sample(1, 7, frozenset({"PMUL9999_t02:direct"})))


class CliTest(unittest.TestCase):
    def test_test_split_is_refused_before_anything_is_read(self):
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = sel.main(["select-prompt", "--recipe", "missing/recipe.toml", "--split", "test",
                             "--router-root", "missing"])
        self.assertEqual(code, 1)
        self.assertIn("dev only", err.getvalue())

    def test_run_sample_flag_is_refused_without_conditions(self):
        """Refused before the corpus is read or a backend is built, so the real recipe is safe to name."""
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = lr.main(["run", "--recipe", "configs/llm/qwen2.5-7b-instruct.toml", "--split", "dev",
                            "--task", "main", "--sample"])
        self.assertEqual(code, 1)
        self.assertIn("selection sample", err.getvalue())


if __name__ == "__main__":
    unittest.main()
