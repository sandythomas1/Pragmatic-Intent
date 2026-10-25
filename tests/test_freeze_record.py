"""The freeze record: ``write``, ``verify``, ``require_freeze`` and the run grid (spec 008 T5)."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any
from unittest import TestCase, main, mock

from src.analysis import freeze as analysis_freeze
from src.data import freeze
from src.data import split_audit as sa
from src.data.freeze import FreezeError, RunIdentity
from tests.freeze_fixtures import (
    ENCODER_TOML,
    FREEZE_ON,
    INPUTS,
    INSPECTED,
    PRIMARY,
    TFIDF_TOML,
    TODAY,
    FreezeRepo,
    clean_git,
    registry_row,
)


class RecordTestCase(TestCase):
    def setUp(self) -> None:
        self.repo = FreezeRepo().build()
        self.addCleanup(self.repo.cleanup)

    @property
    def path(self) -> Path:
        return self.repo.root / sa.FREEZE_FILE

    def assert_fails(self, code: str, keys: tuple[str, ...] | None = None, **options: Any) -> FreezeError:
        with self.assertRaises(FreezeError) as caught:
            freeze.require_freeze(self.repo.root, **options)
        self.assertEqual(caught.exception.code, code)
        if keys is not None:
            self.assertEqual(caught.exception.keys, keys)
        return caught.exception

    def edit_record(self, change: Any) -> None:
        record = json.loads(self.path.read_text(encoding="utf-8"))
        change(record)
        self.path.write_text(json.dumps(record), encoding="utf-8")

    def recipe(self, name: str) -> str:
        toml = {"enc": "configs/stage1/enc.toml", "tfidf": "configs/stage1/tfidf.toml"}[name]
        return freeze.recipe_sha256(freeze.stage1_recipe(self.repo.root, Path(toml)))


class WriteTest(RecordTestCase):
    def test_write_creates_a_verifying_record(self) -> None:
        record = self.repo.freeze()
        self.assertTrue(self.path.is_file())
        self.assertEqual(record["freeze_date"], FREEZE_ON.isoformat())
        self.assertEqual(record["pins"], record["original_pins"])
        self.assertEqual(record["amendments"], [])
        self.assertEqual(record["written_at_commit"], "a" * 40)
        self.assertEqual(record["inputs_path"], INPUTS.as_posix())
        frozen = freeze.require_freeze(self.repo.root)
        self.assertEqual(frozen.freeze_date, FREEZE_ON)
        self.assertEqual(frozen.content_sha256, record["content_sha256"])

    def test_the_bytes_are_deterministic_across_repositories(self) -> None:
        self.repo.freeze()
        other = FreezeRepo().build()
        self.addCleanup(other.cleanup)
        other.freeze()
        first = self.path.read_bytes()
        self.assertEqual((other.root / sa.FREEZE_FILE).read_bytes(), first)
        self.assertTrue(first.endswith(b"}\n"))
        self.assertNotIn(b"\r\n", first)
        self.assertNotIn(str(self.repo.root).encode(), first)

    def test_existing_readers_accept_the_record_unchanged(self) -> None:
        record = self.repo.freeze()
        self.assertEqual(analysis_freeze.freeze_date(self.path), FREEZE_ON)
        self.assertEqual(analysis_freeze.require_frozen_config(self.path, record["pins"]["analysis.config"]),
                         record["analysis_config_sha256"])
        self.assertEqual(sa.resolve_freeze_date(None, self.path), FREEZE_ON.isoformat())

    def test_a_refused_write_leaves_no_file(self) -> None:
        self.repo.write_analysis_config(draft=True)
        with self.assertRaises(FreezeError) as caught:
            self.repo.freeze()
        self.assertEqual((caught.exception.code, caught.exception.keys), ("not_ready", ("analysis_draft",)))
        self.assertFalse(self.path.exists())
        self.assertFalse(self.path.with_name("freeze.json.tmp").exists())

    def test_a_second_write_is_refused_and_the_record_kept(self) -> None:
        self.repo.freeze()
        before = self.path.read_bytes()
        with self.assertRaises(FreezeError) as caught:
            self.repo.freeze()
        self.assertIn("freeze_exists", caught.exception.keys)
        self.assertEqual(self.path.read_bytes(), before)

    def test_an_oversized_record_is_refused(self) -> None:
        with mock.patch.object(freeze, "MAX_RECORD_BYTES", 200), self.assertRaises(FreezeError) as caught:
            self.repo.freeze()
        self.assertEqual(caught.exception.code, "record_too_large")
        self.assertFalse(self.path.exists())


class VerifyDetectsTest(RecordTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.repo.freeze()

    def assert_moved(self, key: str) -> None:
        error = self.assert_fails("freeze_mismatch")
        self.assertIn(key, error.keys)

    def test_items(self) -> None:
        with (self.repo.root / sa.DEFAULT_ITEMS).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"item_id": "SNG9004_t1", "dialogue_id": "SNG9004.json", "split": "dev"}) + "\n")
        self.assert_moved("data.items")

    def test_registry_pre_freeze_rows(self) -> None:
        self.repo.write_registry([registry_row(INSPECTED, "2026-10-01"), registry_row(PRIMARY, "2026-10-02")])
        self.assert_moved("membership.registry_pre_freeze")

    def test_manifest(self) -> None:
        self.repo.write(sa.DEFAULT_CONTEXT_MANIFEST, "example_id\nother\n")
        self.assert_moved("membership.context_manifest")

    def test_code(self) -> None:
        self.repo.write("src/tool.py", "VALUE = 2\n")
        self.assert_fails("freeze_mismatch", ("code.src/tool.py",))

    def test_a_new_code_file_under_a_glob(self) -> None:
        self.repo.write("src/data/new_module.py", "X = 1\n")
        self.assert_fails("freeze_mismatch", ("code.src/data/new_module.py",))

    def test_analysis_config_content(self) -> None:
        text = (self.repo.root / "configs/analysis/analysis-v1.toml").read_text(encoding="utf-8")
        self.assertIn("samples = 50", text)
        self.repo.write("configs/analysis/analysis-v1.toml", text.replace("samples = 50", "samples = 51"))
        self.assert_moved("analysis.config")

    def test_prompt_file(self) -> None:
        self.repo.write("prompts/llm.txt", "Classify the request carefully.\n")
        self.assert_fails("freeze_mismatch", ("recipe.llm.file.prompts/llm.txt",))

    def test_stage1_semantic_field(self) -> None:
        self.repo.write("configs/stage1/tfidf.toml", TFIDF_TOML + "ngram_max = 3\n")
        self.assert_fails("freeze_mismatch", ("recipe.tfidf.stage1",))

    def test_uv_lock(self) -> None:
        self.repo.write("uv.lock", "version = 2\n")
        self.assert_fails("freeze_mismatch", ("env.uv_lock",))

    def test_missing_data_counts_as_moved(self) -> None:
        (self.repo.root / sa.DEFAULT_DIALOGUES).unlink()
        self.assert_moved("data.dialogues")

    def test_record_edits(self) -> None:
        edits = {
            "a pin": lambda r: r["pins"].__setitem__("data.items", "0" * 64),
            "the freeze date": lambda r: r.__setitem__("freeze_date", "2026-11-01"),
            "an original pin": lambda r: r["original_pins"].__setitem__("env.uv_lock", "0" * 64),
            "the inputs path": lambda r: r.__setitem__("inputs_path", "configs/other.toml"),
        }
        original = self.path.read_bytes()
        for name, edit in edits.items():
            with self.subTest(edit=name):
                self.path.write_bytes(original)
                self.edit_record(edit)
                self.assert_fails("freeze_tampered")

    def test_a_consistently_rehashed_edit_still_fails_on_the_files(self) -> None:
        # Someone edits a pin AND recomputes content_sha256: integrity passes, the recomputation does not.
        def rehash(record: dict[str, Any]) -> None:
            for name in ("pins", "original_pins"):
                record[name]["env.uv_lock"] = "0" * 64
            record["content_sha256"] = freeze.canonical_sha256(freeze._without_content(record))

        self.edit_record(rehash)
        self.assert_fails("freeze_mismatch", ("env.uv_lock",))

    def test_malformed_records(self) -> None:
        cases = {
            "not json": b"{",
            "not an object": b"[]",
            "missing key": json.dumps({"freeze_date": "2026-11-07"}).encode(),
            "not utf-8": b"\xff\xfe",
        }
        for name, data in cases.items():
            with self.subTest(case=name):
                self.path.write_bytes(data)
                self.assert_fails("freeze_malformed")

    def test_malformed_fields(self) -> None:
        self.path.unlink()
        record = self.repo.freeze()
        fields = {"schema_version": "freeze-record-v0", "freeze_date": "2026-11-7", "pins": {"a": 1},
                  "content_sha256": "XYZ", "analysis_config_sha256": "0" * 63, "amendments": [1],
                  "written_at_commit": 5, "inputs_path": 7}
        for key, value in fields.items():
            with self.subTest(field=key):
                self.path.write_text(json.dumps({**record, key: value}), encoding="utf-8")
                self.assert_fails("freeze_malformed")

    def test_an_oversized_record(self) -> None:
        self.path.write_bytes(b" " * (freeze.MAX_RECORD_BYTES + 1))
        self.assert_fails("file_too_large")

    def test_no_record(self) -> None:
        self.path.unlink()
        self.assert_fails("freeze_missing")

    def test_unsafe_inputs_path_in_a_rehashed_record(self) -> None:
        def escape(record: dict[str, Any]) -> None:
            record["inputs_path"] = "../outside.toml"
            record["content_sha256"] = freeze.canonical_sha256(freeze._without_content(record))

        self.edit_record(escape)
        self.assert_fails("path_escape")


class VerifyToleratesTest(RecordTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.repo.freeze()

    def test_post_scoring_rows_and_disclosure(self) -> None:
        self.repo.write_registry([registry_row(INSPECTED, "2026-10-01"),
                                  registry_row(PRIMARY, "2026-11-20", phase="post_scoring")])
        self.repo.write_audit(post_scoring_dialogues=1)
        freeze.require_freeze(self.repo.root)

    def test_crlf_code(self) -> None:
        for relative in ("src/tool.py", "prompts/llm.txt", "uv.lock"):
            path = self.repo.root / relative
            path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        freeze.require_freeze(self.repo.root)

    def test_comment_only_config_and_recipe_changes(self) -> None:
        for relative in ("configs/analysis/analysis-v1.toml", "configs/stage1/enc.toml"):
            path = self.repo.root / relative
            path.write_text("# reviewed 2026-11-08\n" + path.read_text(encoding="utf-8"), encoding="utf-8")
        freeze.require_freeze(self.repo.root)

    def test_run_outputs(self) -> None:
        self.repo.write("results/stage1.jsonl", "{}\n")
        self.repo.write("outputs/stage1/enc/train-full/seed13/metrics.json", "{}\n")
        freeze.require_freeze(self.repo.root)


class RunGridTest(RecordTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.repo.freeze()

    def run_identity(self, **changes: Any) -> RunIdentity:
        fields = {"system": "enc", "recipe_sha256": self.recipe("enc"), "seed": 13, "train_condition": "none"}
        return RunIdentity(**{**fields, **changes})

    def test_frozen_runs_pass(self) -> None:
        for condition in ("none", "one", "full"):
            for seed in (13, 42):
                freeze.require_freeze(self.repo.root, run=self.run_identity(seed=seed, train_condition=condition))
        freeze.require_freeze(self.repo.root, run=RunIdentity("tfidf", self.recipe("tfidf"), 13, "full"))

    def test_runs_off_the_grid_are_refused(self) -> None:
        cases = {
            "recipe_not_frozen": self.run_identity(recipe_sha256="0" * 64),
            "seed_not_frozen": self.run_identity(seed=7),
            "condition_not_frozen": self.run_identity(train_condition="mismatched"),
            "system_not_frozen": self.run_identity(system="ghost"),
        }
        for code, run in cases.items():
            with self.subTest(code=code):
                self.assert_fails(code, run=run)
        self.assert_fails("condition_not_frozen", run=RunIdentity("tfidf", self.recipe("tfidf"), 13, "none"))
        self.assert_fails("recipe_not_frozen", run=RunIdentity("llm", self.recipe("enc"), 0, "untrained"))

    def test_a_recipe_edited_after_the_freeze_fails_before_the_grid_check(self) -> None:
        self.repo.write("configs/stage1/enc.toml", ENCODER_TOML.replace('kind = "encoder"', 'kind = "encoder"\nbootstrap_seed = 1'))
        self.assert_fails("freeze_mismatch", ("recipe.enc.stage1",), run=self.run_identity())


class CliTest(RecordTestCase):
    def cli(self, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        with redirect_stdout(out), mock.patch.object(freeze, "git_probe", clean_git), \
                mock.patch.object(freeze.datetime, "date", wraps=freeze.datetime.date) as date:
            date.today.return_value = TODAY
            code = freeze.main([*argv, "--root", str(self.repo.root), "--inputs", INPUTS.as_posix()])
        return code, out.getvalue()

    def test_write_then_verify(self) -> None:
        code, out = self.cli("write", "--on", FREEZE_ON.isoformat())
        self.assertEqual(code, 0)
        self.assertIn("wrote data/manifests/freeze.json", out)
        code, out = self.cli("verify")
        self.assertEqual(code, 0)
        self.assertIn("verified:", out)
        self.repo.write("src/tool.py", "VALUE = 9\n")
        code, out = self.cli("verify")
        self.assertEqual(code, 1)
        self.assertIn("freeze_mismatch", out)
        self.assertIn("code.src/tool.py", out)

    def test_write_needs_on(self) -> None:
        with redirect_stdout(io.StringIO()), mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            freeze.main(["write", "--root", str(self.repo.root)])

    def test_write_refusal_lists_codes(self) -> None:
        self.repo.write_analysis_config(draft=True)
        code, out = self.cli("write", "--on", FREEZE_ON.isoformat())
        self.assertEqual(code, 1)
        self.assertIn("not_ready", out)
        self.assertIn("analysis_draft", out)


if __name__ == "__main__":
    main()
