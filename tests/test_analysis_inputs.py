"""Inputs file, panel mapping and run-directory checks (spec 007 T3, FR5–FR6, AC-007-3)."""

from __future__ import annotations

import hashlib
import unittest
from typing import Any
from unittest import mock

from src.analysis import inputs as inputs_module
from src.analysis.files import AnalysisError, read_verified
from src.analysis.inputs import load_inputs, train_condition_for
from src.data.direct_dataset import CONDITIONS
from tests.analysis_fixtures import Workspace, analysis_config, stage1_entries

GENUINE = ("none", "one", "full")


class InputsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.ws = Workspace()
        self.addCleanup(self.ws.cleanup)
        self.config = analysis_config()
        for train in GENUINE:
            for seed in (1, 2):
                self.ws.stage1_run("enc", train, seed)
        self.ws.stage1_run("tfidf", "full", 1)
        for train in GENUINE:
            self.ws.write_jsonl(f"outputs/stage2/pipe/{train}/routed.jsonl", [])
            self.ws.write_jsonl(f"outputs/stage2/pipe/{train}/oracle.jsonl", [])

    def systems(self, **changes: Any) -> dict[str, Any]:
        systems: dict[str, Any] = {
            "enc": {"stage1": stage1_entries("enc", GENUINE, (1, 2))},
            "tfidf": {"stage1": stage1_entries("tfidf", ["full"], [1])},
            "pipe": {"stage2": [{"train_condition": t, "seed": 0, "routed": f"outputs/stage2/pipe/{t}/routed.jsonl",
                                 "oracle": f"outputs/stage2/pipe/{t}/oracle.jsonl"} for t in GENUINE]},
        }
        systems.update(changes)
        return {name: table for name, table in systems.items() if table is not None}

    def load(self, systems: dict[str, Any], *, split: str = "dev", file_split: str | None = None):
        path = self.ws.inputs(systems, split=file_split or split)
        return load_inputs(path, self.config, split, base=self.ws.root)

    def assert_code(self, code: str, systems: dict[str, Any], **kwargs: Any) -> None:
        with self.assertRaises(AnalysisError) as caught:
            self.load(systems, **kwargs)
        self.assertEqual(caught.exception.code, code)


class PanelMappingTest(InputsTestCase):
    def test_valid_inputs_resolve_every_panel_system(self) -> None:
        resolved = self.load(self.systems())
        self.assertEqual(list(resolved.systems), ["enc", "tfidf", "llm", "pipe"])
        statuses = {name: s.status for name, s in resolved.systems.items()}
        self.assertEqual(statuses, {"enc": "run", "tfidf": "run", "llm": "not_run", "pipe": "run"})
        enc = resolved.systems["enc"]
        self.assertEqual(sorted((r.train_condition, r.seed) for r in enc.stage1),
                         sorted((t, s) for t in GENUINE for s in (1, 2)))
        self.assertEqual(enc.lines, ("matched", "test_time"))
        self.assertEqual(resolved.systems["tfidf"].lines, ("test_time",))

    def test_extra_system_fails_and_missing_one_is_not_run(self) -> None:
        # FR5 / AC-007-7: the panel, not the inputs file, decides who is in the analysis.
        self.ws.stage1_run("gpt", "full", 1)
        self.assert_code("system_outside_panel", self.systems(gpt={"stage1": stage1_entries("gpt", ["full"], [1])}))
        self.assertEqual(self.load(self.systems(tfidf=None)).systems["tfidf"].status, "not_run")
        self.assertEqual(self.load(self.systems(tfidf={})).systems["tfidf"].status, "not_run")

    def test_streams_must_match_the_panel(self) -> None:
        stage2 = self.systems()["pipe"]["stage2"]
        self.assert_code("undeclared_stream", self.systems(enc={**self.systems()["enc"], "stage2": stage2}))
        self.ws.write("outputs/transfer/llm.json", "{}")
        self.assert_code("missing_stream", self.systems(llm={"transfer": "outputs/transfer/llm.json"}))


class DesignTest(InputsTestCase):
    """AC-007-3: designs are checked against what each run recorded."""

    def test_matched_none_file_from_a_full_trained_run_fails(self) -> None:
        self.ws.stage1_run("enc", "none", 3, recorded_train="full")
        entries = stage1_entries("enc", GENUINE, (1, 2))
        entries[0] = {"train_condition": "none", "seed": 3, "run_dir": "outputs/stage1/enc/train-none/seed3"}
        self.assert_code("train_condition_mismatch", self.systems(enc={"stage1": entries}))

    def test_matched_system_needs_every_genuine_training_condition(self) -> None:
        self.assert_code("missing_train_condition",
                         self.systems(enc={"stage1": stage1_entries("enc", ["one", "full"], (1, 2))}))

    def test_runs_the_design_never_uses_are_rejected(self) -> None:
        self.ws.stage1_run("enc", "mismatched", 1)
        self.ws.stage1_run("tfidf", "one", 1)
        self.assert_code("unused_train_condition",
                         self.systems(enc={"stage1": stage1_entries("enc", [*GENUINE, "mismatched"], [1])}))
        self.assert_code("unused_train_condition",
                         self.systems(tfidf={"stage1": stage1_entries("tfidf", ["one", "full"], [1])}))

    def test_untrained_llm_declares_untrained(self) -> None:
        self.ws.write_jsonl("outputs/stage2/llm/routed.jsonl", [])
        self.ws.write_jsonl("outputs/stage2/llm/oracle.jsonl", [])
        entry = {"train_condition": "untrained", "seed": 0, "routed": "outputs/stage2/llm/routed.jsonl",
                 "oracle": "outputs/stage2/llm/oracle.jsonl"}
        self.assertEqual(self.load(self.systems(llm={"stage2": [entry]})).systems["llm"].status, "run")
        self.assert_code("unused_train_condition", self.systems(llm={"stage2": [{**entry, "train_condition": "full"}]}))
        # A trained Stage 1 run cannot be passed off as untrained: the run records its training.
        self.assert_code("train_condition_mismatch",
                         self.systems(tfidf={"stage1": [{**stage1_entries("tfidf", ["full"], [1])[0],
                                                         "train_condition": "untrained"}]}))
        self.assert_code("same_file", self.systems(llm={"stage2": [{**entry, "oracle": entry["routed"]}]}))

    def test_duplicate_run_fails(self) -> None:
        entries = stage1_entries("enc", GENUINE, (1, 2))
        self.assert_code("duplicate_run", self.systems(enc={"stage1": [*entries, entries[0]]}))

    def test_test_time_line_uses_full_training_for_every_condition(self) -> None:
        resolved = self.load(self.systems())
        for name in ("enc", "tfidf"):
            system = resolved.systems[name]
            self.assertEqual({system.train_condition("test_time", c) for c in CONDITIONS}, {"full"})
        enc = resolved.systems["enc"]
        self.assertEqual([enc.train_condition("matched", c) for c in CONDITIONS],
                         ["none", "one", "full", "full", "full"])  # mismatch controls stay full-trained
        self.assertEqual(len(enc.runs("stage1", enc.train_condition("test_time", "none"))), 2)
        llm = self.config.system("llm")
        self.assertEqual({train_condition_for(llm, "test_time", c) for c in CONDITIONS}, {"untrained"})
        with self.assertRaises(AnalysisError):
            train_condition_for(self.config.system("tfidf"), "matched", "none")


class RunDirectoryTest(InputsTestCase):
    def test_split_must_match_everywhere(self) -> None:
        self.assert_code("split_mismatch", self.systems(), split="test", file_split="dev")
        # A dev run named in a test inputs file: the start of a test-gate bypass.
        self.assert_code("run_split_mismatch", self.systems(), split="test")

    def test_recorded_seed_smoke_and_name_are_checked(self) -> None:
        self.ws.stage1_run("tfidf", "full", 5, smoke=True)
        self.assert_code("smoke_run", self.systems(tfidf={"stage1": stage1_entries("tfidf", ["full"], [5])}))
        self.ws.stage1_run("tfidf", "full", 6, recorded_name="tfidf-other")
        self.assert_code("run_name_mismatch", self.systems(tfidf={"stage1": stage1_entries("tfidf", ["full"], [6])}))
        entry = {**stage1_entries("tfidf", ["full"], [1])[0], "seed": 9}
        self.assert_code("seed_mismatch", self.systems(tfidf={"stage1": [entry]}))

    def test_missing_files_and_paths_fail_with_named_errors(self) -> None:
        (self.ws.root / "outputs/stage1/tfidf/train-full/seed1/predictions.jsonl").unlink()
        self.assert_code("not_a_file", self.systems())
        self.assert_code("missing_path",
                         self.systems(tfidf={"stage1": stage1_entries("tfidf", ["full"], [42])}))
        self.ws.write("outputs/stage1/flat.txt", "")
        entry = {"train_condition": "full", "seed": 1, "run_dir": "outputs/stage1/flat.txt"}
        self.assert_code("not_a_directory", self.systems(tfidf={"stage1": [entry]}))

    def test_oversized_file_fails(self) -> None:
        self.ws.write_jsonl("outputs/stage2/pipe/full/routed.jsonl", [{"example_id": "x"}] * 50)
        with mock.patch.object(inputs_module, "MAX_PREDICTION_BYTES", 64):
            self.assert_code("file_too_large", self.systems())

    def test_malformed_run_records_fail(self) -> None:
        self.ws.write("outputs/stage1/tfidf/train-full/seed1/metrics.json", '{"seed": 1}')
        self.assert_code("malformed_run", self.systems())
        self.ws.write("outputs/stage1/tfidf/train-full/seed1/metrics.json", "{not json")
        self.assert_code("invalid_json", self.systems())

    def test_file_level_validation(self) -> None:
        cases = {
            "unknown_key": {"tfidf": {"stage1": stage1_entries("tfidf", ["full"], [1]), "notes": "x"}},
            "missing_key": {"tfidf": {"stage1": [{"train_condition": "full", "seed": 1}]}},
            "unknown_train_condition": {"tfidf": {"stage1": [{**stage1_entries("tfidf", ["full"], [1])[0],
                                                              "train_condition": "half"}]}},
            "wrong_type": {"tfidf": {"stage1": []}},
        }
        for code, systems in cases.items():
            with self.subTest(code):
                self.assert_code(code, self.systems(**systems))
        path = self.ws.root / self.ws.write("bad.toml", 'version = "analysis-inputs-v9"\nsplit = "dev"\n[systems]\n')
        with self.assertRaises(AnalysisError) as caught:
            load_inputs(path, self.config, "dev", base=self.ws.root)
        self.assertEqual(caught.exception.code, "unknown_version")


class ProvenanceTest(InputsTestCase):
    def test_every_file_is_hashed_and_paths_are_repository_relative(self) -> None:
        resolved = self.load(self.systems())
        files = resolved.files(self.ws.root)
        self.assertEqual(len(files), 6 * 3 + 1 * 3 + 3 * 2)
        for display, digest in files.items():
            self.assertFalse(display.startswith("/") or ":" in display, display)
            self.assertEqual(hashlib.sha256((self.ws.root / display).read_bytes()).hexdigest(), digest)
        self.assertEqual(resolved.sha256, hashlib.sha256(resolved.path.read_bytes()).hexdigest())

    def test_a_file_changed_after_hashing_is_refused(self) -> None:
        run = self.load(self.systems()).systems["tfidf"].stage1[0]
        self.assertEqual(read_verified(run.predictions), b"")
        run.predictions.path.write_text('{"example_id": "swapped"}\n', encoding="utf-8")
        with self.assertRaises(AnalysisError) as caught:
            read_verified(run.predictions)
        self.assertEqual(caught.exception.code, "file_changed")


if __name__ == "__main__":
    unittest.main()
