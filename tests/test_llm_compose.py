"""Spec 009 T9: the hybrid composer (FR11 composition, FR12 coverage and role checks).

Fixtures are invented (PMUL9xxx IDs) and live in a temporary repository root.
"""

import hashlib
import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from src.data.direct_dataset import CONDITIONS
from src.evaluation.interpretation import validate_predictions
from src.llm import compose as lc

E1, E2 = "PMUL9001_t02:direct", "PMUL9002_t04:indirect"
SEEDS = (13, 42)
TRAIN = ("none", "one", "full")
ROUTER_ROOT = Path("outputs/stage1/deberta-v3-large")
INTERPRETER_DIR = Path("outputs/stage2/qwen-zq/dev")
HYBRID_DIR = Path("outputs/stage2/hybrid/dev")


def valid(example_id, condition, category="booking", slots=None, requested=()):
    return {"example_id": example_id, "condition": condition, "prediction": "indirect", "category": category,
            "slots": dict(slots or {"hotel.people": "two"}), "requested_slots": list(requested)}


def invalid(example_id, condition):
    return {"example_id": example_id, "condition": condition, "invalid": True}


def routed(example_id, condition, label):
    return {"example_id": example_id, "condition": condition, "prediction": label,
            "probs": {"direct": 0.4, "indirect": 0.3, "no_request": 0.3}}


# Every (example, condition): E2 under "one" and E1 under "mismatched" failed to parse.
INTERPRETATION = [
    invalid(e, c) if (e, c) in {(E2, "one"), (E1, "mismatched")}
    else valid(e, c, category="info_seeking" if e == E2 else "booking",
               slots={"hotel.area": "zq-north"} if e == E2 else None,
               requested=["hotel.phone"] if e == E2 else ())
    for e in (E1, E2) for c in CONDITIONS
]
ORACLE = [row for row in INTERPRETATION if row["example_id"] == E2]


def router_label(train_condition, example_id, condition):
    """Each train condition routes differently, so per-run outputs must differ."""
    if train_condition == "none":
        return "no_request" if example_id == E2 else "direct"
    if train_condition == "one":
        return "indirect"
    return "no_request" if condition in ("none", "mismatched") else "direct"


def jsonl(rows):
    return "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_router_run(root, train_condition, seed, *, rows=None, smoke=False, **overrides):
    run_dir = root / ROUTER_ROOT / f"train-{train_condition}" / f"seed{seed}{'-smoke' if smoke else ''}"
    run_dir.mkdir(parents=True, exist_ok=True)
    if rows is None:
        rows = [routed(e, c, router_label(train_condition, e, c)) for e in (E1, E2) for c in CONDITIONS]
    predictions = jsonl(rows)
    (run_dir / "predictions.jsonl").write_bytes(predictions)
    config = {"name": overrides.get("name", "deberta-v3-large"),
              "data": {"train_condition": overrides.get("config_train", train_condition),
                       "eval_split": overrides.get("config_split", "dev")}}
    run = {"train_condition": overrides.get("run_train", train_condition),
           "eval_split": overrides.get("run_split", "dev"), "seed": overrides.get("run_seed", seed),
           "smoke": overrides.get("smoke_flag", smoke),
           "predictions_sha256": overrides.get("predictions_sha256", sha(predictions))}
    (run_dir / "config.resolved.json").write_text(json.dumps(config), encoding="utf-8")
    (run_dir / "metrics.json").write_text(json.dumps({"run": run, "metrics": {}}), encoding="utf-8")
    return run_dir


def write_interpreter(root, *, interpretation=INTERPRETATION, **overrides):
    directory = root / INTERPRETER_DIR
    directory.mkdir(parents=True, exist_ok=True)
    files = {"interpretation.jsonl": jsonl(interpretation), "oracle.jsonl": jsonl(ORACLE),
             "routed.jsonl": jsonl([])}
    for name, data in files.items():
        (directory / name).write_bytes(data)
    provenance = {"version": "llm-run-v1", "task": "main", "split": "dev", "system": "qwen-zq",
                  "variant": "p1", "selected_variant": True, "conditions": None, "model": "zq/model@abc",
                  "outputs": {name: sha(data) for name, data in files.items()}}
    provenance.update(overrides)
    (directory / "provenance.main.json").write_text(json.dumps(provenance), encoding="utf-8")
    return directory


def write_inputs(root):
    for condition in TRAIN:
        for seed in SEEDS:
            write_router_run(root, condition, seed)
    write_interpreter(root)


class ComposeRowsTest(unittest.TestCase):
    """AC-009-7: the four FR11 cases, by hand."""

    def test_the_four_fr11_cases(self):
        router = [routed(E1, "none", "no_request"),       # valid interpretation, router says no request
                  routed(E1, "mismatched", "no_request"),  # invalid interpretation, router says no request
                  routed(E2, "none", "direct"),            # valid interpretation, router says request
                  routed(E2, "one", "indirect")]           # invalid interpretation, router says request
        keys = {(row["example_id"], row["condition"]) for row in router}
        interpretation = [row for row in INTERPRETATION if (row["example_id"], row["condition"]) in keys]
        self.assertEqual(lc.compose_rows(router, interpretation), [
            {"example_id": E1, "condition": "none", "prediction": "no_request", "category": None,
             "slots": {}, "requested_slots": []},
            {"example_id": E1, "condition": "mismatched", "prediction": "no_request", "category": None,
             "slots": {}, "requested_slots": []},
            {"example_id": E2, "condition": "none", "prediction": "direct", "category": "info_seeking",
             "slots": {"hotel.area": "zq-north"}, "requested_slots": ["hotel.phone"]},
            {"example_id": E2, "condition": "one", "invalid": True},
        ])

    def test_the_route_is_the_routers_not_the_interpreters(self):
        row = lc.compose_rows([routed(E1, "none", "direct")], [valid(E1, "none")])[0]
        self.assertEqual(row["prediction"], "direct")
        self.assertNotIn("probs", row)

    def test_rows_keep_router_order(self):
        router = [routed(E2, "full", "direct"), routed(E1, "none", "direct")]
        rows = lc.compose_rows(router, [valid(E1, "none"), valid(E2, "full")])
        self.assertEqual([row["example_id"] for row in rows], [E2, E1])

    def test_a_conditions_filter_composes_only_those_conditions(self):
        router = [routed(e, c, "direct") for e in (E1, E2) for c in CONDITIONS]
        interpretation = [valid(e, c) for e in (E1, E2) for c in ("none", "full")]
        rows = lc.compose_rows(router, interpretation, conditions=("none", "full"))
        self.assertEqual({(r["example_id"], r["condition"]) for r in rows},
                         {(e, c) for e in (E1, E2) for c in ("none", "full")})
        with self.assertRaises(lc.ComposeError) as caught:
            lc.compose_rows(router, interpretation, conditions=("zq-unknown",))
        self.assertEqual(caught.exception.code, "unknown_condition")

    def test_composed_rows_satisfy_the_prediction_contract(self):
        router = [routed(e, c, router_label("none", e, c)) for e in (E1, E2) for c in CONDITIONS]
        rows = lc.compose_rows(router, INTERPRETATION)
        expected = {c: {E1, E2} for c in CONDITIONS}
        validate_predictions(rows, expected)

    def test_router_train_condition(self):
        for condition in ("none", "one", "full"):
            self.assertEqual(lc.router_train_condition(condition), condition)
        self.assertEqual(lc.router_train_condition("mismatched"), "full")
        self.assertEqual(lc.router_train_condition("mismatched_one"), "full")
        with self.assertRaises(lc.ComposeError):
            lc.router_train_condition("zq-other")


class CoverageTest(unittest.TestCase):
    """AC-009-8: router and interpreter must cover exactly the same (example, condition) set."""

    def setUp(self):
        self.router = [routed(E1, "none", "direct"), routed(E2, "none", "no_request")]
        self.interpretation = [valid(E1, "none"), valid(E2, "none")]

    def assert_refused(self, code, router=None, interpretation=None):
        with self.assertRaises(lc.ComposeError) as caught:
            lc.compose_rows(self.router if router is None else router,
                            self.interpretation if interpretation is None else interpretation)
        self.assertEqual(caught.exception.code, code)
        self.assertNotIn("PMUL", str(caught.exception))
        return caught.exception

    def test_a_missing_interpretation_is_refused(self):
        error = self.assert_refused("coverage", interpretation=self.interpretation[:1])
        self.assertIn("1 without an interpretation", str(error))

    def test_an_extra_interpretation_is_refused(self):
        error = self.assert_refused("coverage", interpretation=[*self.interpretation, valid(E1, "full")])
        self.assertIn("1 without a router prediction", str(error))

    def test_a_duplicated_interpretation_is_refused(self):
        self.assert_refused("coverage", interpretation=[*self.interpretation, valid(E1, "none")])

    def test_a_duplicated_router_row_is_refused(self):
        self.assert_refused("router_row", router=[*self.router, routed(E1, "none", "indirect")])

    def test_malformed_router_rows_are_refused(self):
        for bad in ({"example_id": E1, "condition": "none", "prediction": "zq-maybe"},
                    {"example_id": E1, "condition": "zq-cond", "prediction": "direct"},
                    {"example_id": "", "condition": "none", "prediction": "direct"},
                    {"condition": "none", "prediction": "direct"}, ["not", "an", "object"]):
            with self.subTest(bad=bad):
                self.assert_refused("router_row", router=[bad])

    def test_malformed_interpretation_rows_are_refused(self):
        for bad in ({"example_id": ["zq"], "condition": "none"}, "zq-string",
                    {**valid(E1, "none"), "slots": "zq"}, {**valid(E1, "none"), "zq_extra": 1},
                    {**invalid(E1, "none"), "category": "booking"}):
            with self.subTest(bad=bad):
                self.assert_refused("interpretation_row", interpretation=[bad, self.interpretation[1]])

    def test_a_valid_interpretation_without_a_request_category_is_refused(self):
        for category in (None, "no_request"):
            with self.subTest(category=category):
                self.assert_refused("interpretation_row",
                                    interpretation=[valid(E1, "none", category=category), self.interpretation[1]])


class ComposeCommandTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        patches = [mock.patch.object(lc, "source_sha256", return_value="zq-source"),
                   mock.patch.object(lc, "git_state", return_value={"git_commit": "zq", "git_dirty": False})]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        write_inputs(self.root)

    def run_compose(self, root=None):
        return lc.compose(split="dev", router_root=ROUTER_ROOT, interpreter_dir=INTERPRETER_DIR,
                          root=root or self.root)

    def assert_refused(self, code):
        with self.assertRaises(lc.ComposeError) as caught:
            self.run_compose()
        self.assertEqual(caught.exception.code, code)
        self.assertNotIn("PMUL", str(caught.exception))
        self.assertFalse((self.root / HYBRID_DIR).exists(), "a refusal must write nothing")

    def test_every_router_run_is_composed_with_its_own_routes(self):
        provenance = self.run_compose()
        out = self.root / HYBRID_DIR
        interpretation = {(r["example_id"], r["condition"]): r for r in INTERPRETATION}
        for condition in TRAIN:
            for seed in SEEDS:
                rows = [json.loads(line) for line in
                        (out / f"train-{condition}" / f"seed{seed}" / "routed.jsonl").read_text("utf-8").splitlines()]
                validate_predictions(rows, {c: {E1, E2} for c in CONDITIONS})
                for row in rows:
                    key = (row["example_id"], row["condition"])
                    label = router_label(condition, *key)
                    if label == "no_request":
                        self.assertEqual(row["prediction"], "no_request")
                        self.assertIsNone(row["category"])
                    elif interpretation[key].get("invalid"):
                        self.assertEqual(row, invalid(*key))
                    else:
                        self.assertEqual(row, {**interpretation[key], "prediction": label})
                self.assertEqual((out / f"train-{condition}" / f"seed{seed}" / "oracle.jsonl").read_bytes(),
                                 (self.root / INTERPRETER_DIR / "oracle.jsonl").read_bytes())
        self.assertEqual(len(provenance["counts"]), len(TRAIN) * len(SEEDS))
        self.assertEqual(provenance["counts"]["train-none/seed13"],
                         {"rows": 10, "router_no_request": 5, "invalid": 1})
        self.assertEqual(provenance["counts"]["train-one/seed13"],
                         {"rows": 10, "router_no_request": 0, "invalid": 2})

    def test_provenance_records_both_inputs_and_every_output(self):
        provenance = self.run_compose()
        out = self.root / HYBRID_DIR
        on_disk = json.loads((out / "provenance.compose.json").read_text("utf-8"))
        self.assertEqual(on_disk, provenance)
        self.assertEqual(provenance["router"]["root"], ROUTER_ROOT.as_posix())
        self.assertEqual(provenance["interpreter"]["dir"], INTERPRETER_DIR.as_posix())
        self.assertEqual(provenance["interpreter"]["interpretation_sha256"],
                         sha((self.root / INTERPRETER_DIR / "interpretation.jsonl").read_bytes()))
        self.assertEqual(provenance["interpreter"]["provenance_sha256"],
                         sha((self.root / INTERPRETER_DIR / "provenance.main.json").read_bytes()))
        run = provenance["router"]["runs"][0]
        self.assertEqual(run["predictions_sha256"], sha((self.root / ROUTER_ROOT / "train-none" / "seed13" /
                                                         "predictions.jsonl").read_bytes()))
        for relative, digest in provenance["outputs"].items():
            self.assertEqual(sha((out / relative).read_bytes()), digest)
        self.assertNotIn("PMUL", json.dumps(provenance))

    def test_two_runs_give_identical_bytes(self):
        self.run_compose()
        other = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, other, ignore_errors=True)
        write_inputs(other)
        self.run_compose(root=other)
        first = sorted(p.relative_to(self.root) for p in (self.root / HYBRID_DIR).rglob("*") if p.is_file())
        second = sorted(p.relative_to(other) for p in (other / HYBRID_DIR).rglob("*") if p.is_file())
        self.assertEqual(first, second)
        for relative in first:
            self.assertEqual((self.root / relative).read_bytes(), (other / relative).read_bytes(), relative)

    def test_smoke_runs_are_skipped(self):
        smoke = write_router_run(self.root, "none", 7, smoke=True)
        (smoke / "predictions.jsonl").write_bytes(b"zq-not-json\n")
        provenance = self.run_compose()
        self.assertNotIn(7, {run["seed"] for run in provenance["router"]["runs"]})

    def test_a_coverage_mismatch_writes_nothing(self):
        write_interpreter(self.root, interpretation=INTERPRETATION[:-1])
        self.assert_refused("coverage")

    def test_a_late_coverage_mismatch_still_writes_nothing(self):
        rows = [routed(e, c, "direct") for e in (E1, E2) for c in CONDITIONS][:-1]
        write_router_run(self.root, "full", SEEDS[-1], rows=rows)  # the last run composed
        self.assert_refused("coverage")

    def test_router_runs_that_contradict_their_role_are_refused(self):
        cases = {"run_name_mismatch": {"name": "zq-other-router"},
                 "train_condition_mismatch": {"config_train": "full"},
                 "run_split_mismatch": {"run_split": "test"},
                 "seed_mismatch": {"run_seed": 99},
                 "smoke_run": {"smoke_flag": True},
                 "predictions_changed": {"predictions_sha256": "0" * 64}}
        for code, override in cases.items():
            with self.subTest(code=code):
                write_router_run(self.root, "one", SEEDS[0], **override)
                self.assert_refused(code)
                write_router_run(self.root, "one", SEEDS[0])
        with self.subTest(code="metrics train condition"):
            write_router_run(self.root, "one", SEEDS[0], run_train="none")
            self.assert_refused("train_condition_mismatch")

    def test_a_boolean_seed_is_not_seed_one(self):
        write_router_run(self.root, "none", 1, run_seed=True)
        write_router_run(self.root, "one", 1)
        write_router_run(self.root, "full", 1)
        self.assert_refused("seed_mismatch")

    def test_malformed_router_metadata_is_refused(self):
        run_dir = write_router_run(self.root, "full", SEEDS[0])
        (run_dir / "metrics.json").write_text(json.dumps({"metrics": {}}), encoding="utf-8")
        self.assert_refused("malformed_run")
        (run_dir / "metrics.json").write_text("zq{", encoding="utf-8")
        self.assert_refused("invalid_json")
        (run_dir / "metrics.json").unlink()
        self.assert_refused("not_a_file")

    def test_a_missing_train_condition_is_refused(self):
        shutil.rmtree(self.root / ROUTER_ROOT / "train-one")
        self.assert_refused("missing_train_condition")

    def test_differing_seed_sets_are_refused(self):
        shutil.rmtree(self.root / ROUTER_ROOT / "train-full" / f"seed{SEEDS[0]}")
        self.assert_refused("seed_sets_differ")

    def test_an_interpreter_that_is_not_the_selected_complete_run_is_refused(self):
        cases = {"interpreter_partial": [{"selected_variant": False}, {"conditions": ["none", "full"]}],
                 "interpreter_mismatch": [{"split": "test"}, {"task": "transfer"}, {"version": "zq-v0"}],
                 "malformed_interpreter": [{"model": None}, {"outputs": []}]}
        for code, overrides in cases.items():
            for override in overrides:
                with self.subTest(override=override):
                    write_interpreter(self.root, **override)
                    self.assert_refused(code)
        write_interpreter(self.root)

    def test_a_changed_interpreter_file_is_refused(self):
        for name in ("interpretation.jsonl", "oracle.jsonl"):
            with self.subTest(name=name):
                write_interpreter(self.root)
                path = self.root / INTERPRETER_DIR / name
                path.write_bytes(path.read_bytes() + b"\n")
                self.assert_refused("interpreter_changed")

    def test_an_unknown_split_is_refused(self):
        with self.assertRaises(lc.ComposeError):
            lc.compose(split="zq-split", router_root=ROUTER_ROOT, interpreter_dir=INTERPRETER_DIR, root=self.root)


class CliTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        for patch in (mock.patch.object(lc, "REPO_ROOT", self.root),
                      mock.patch.object(lc, "source_sha256", return_value="zq-source"),
                      mock.patch.object(lc, "git_state", return_value={"git_commit": "zq", "git_dirty": False})):
            patch.start()
            self.addCleanup(patch.stop)
        write_inputs(self.root)

    def run_main(self, *argv):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = lc.main(["compose", *argv])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_compose_prints_counts_only(self):
        code, stdout, stderr = self.run_main("--split", "dev", "--router-root", str(ROUTER_ROOT),
                                             "--interpreter", str(INTERPRETER_DIR))
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("Composed 6 hybrid runs on dev: 60 rows", stdout)
        self.assertNotIn("PMUL", stdout)
        self.assertTrue((self.root / HYBRID_DIR / "provenance.compose.json").is_file())

    def test_a_refusal_exits_1_without_naming_examples(self):
        write_interpreter(self.root, interpretation=INTERPRETATION[1:])
        code, stdout, stderr = self.run_main("--split", "dev", "--router-root", str(ROUTER_ROOT),
                                             "--interpreter", str(INTERPRETER_DIR))
        self.assertEqual((code, stdout), (1, ""))
        self.assertIn("Compose stopped: coverage", stderr)
        self.assertNotIn("PMUL", stderr)


if __name__ == "__main__":
    unittest.main()
