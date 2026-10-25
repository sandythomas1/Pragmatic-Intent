"""Amendments and ``show`` (spec 008 T6): dated, reasoned, chained, and never the test set."""

from __future__ import annotations

import datetime
import io
import json
from contextlib import redirect_stdout
from typing import Any
from unittest import TestCase, main, mock

from src.analysis import freeze as analysis_freeze
from src.data import freeze
from src.data import split_audit as sa
from src.data.freeze import FreezeError
from tests.freeze_fixtures import FREEZE_ON, INSPECTED, PRIMARY, TODAY, FreezeRepo, clean_git, registry_row

LATER = datetime.date(2026, 11, 8)


class AmendTestCase(TestCase):
    def setUp(self) -> None:
        self.repo = FreezeRepo().build()
        self.addCleanup(self.repo.cleanup)
        self.record = self.repo.freeze()

    @property
    def path(self) -> Any:
        return self.repo.root / sa.FREEZE_FILE

    def amend(self, reason: str = "Fix an off-by-one in the renderer", on: datetime.date = LATER,
              today: datetime.date = TODAY, git: Any = clean_git) -> dict[str, Any]:
        return freeze.amend_freeze(self.repo.root, on=on, reason=reason, today=today, git=git)

    def assert_refused(self, code: str, **options: Any) -> FreezeError:
        before = self.path.read_bytes()
        with self.assertRaises(FreezeError) as caught:
            self.amend(**options)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(self.path.read_bytes(), before, "a refused amendment must leave the record untouched")
        return caught.exception


class AmendTest(AmendTestCase):
    def test_an_amendment_is_recorded_and_verifies_on_the_new_state_only(self) -> None:
        self.repo.write("src/tool.py", "VALUE = 2\n")
        with self.assertRaises(FreezeError):
            freeze.require_freeze(self.repo.root)
        amended = self.amend()
        freeze.require_freeze(self.repo.root)
        [amendment] = amended["amendments"]
        self.assertEqual(amendment["on"], LATER.isoformat())
        self.assertEqual(amendment["reason"], "Fix an off-by-one in the renderer")
        self.assertEqual(amendment["commit"], "a" * 40)
        self.assertEqual(amendment["previous_content_sha256"], self.record["content_sha256"])
        self.assertEqual(list(amendment["changes"]), ["code.src/tool.py"])
        self.assertEqual(amendment["changes"]["code.src/tool.py"]["old"], self.record["pins"]["code.src/tool.py"])
        self.assertEqual(amended["freeze_date"], FREEZE_ON.isoformat())
        self.assertEqual(amended["original_pins"], self.record["original_pins"])
        self.repo.write("src/tool.py", "VALUE = 1\n")  # the old state no longer verifies
        self.assertEqual(self.verify_code(), "freeze_mismatch")

    def verify_code(self) -> str:
        with self.assertRaises(FreezeError) as caught:
            freeze.require_freeze(self.repo.root)
        return caught.exception.code

    def test_added_and_removed_pins(self) -> None:
        self.repo.write("src/data/new_module.py", "X = 1\n")
        (self.repo.root / "prompts/pipe.txt").write_text("v2\n", encoding="utf-8")
        changes = self.amend()["amendments"][0]["changes"]
        self.assertEqual(changes["code.src/data/new_module.py"]["old"], None)
        (self.repo.root / "src/data/new_module.py").unlink()
        changes = self.amend(on=LATER)["amendments"][1]["changes"]
        self.assertEqual(changes["code.src/data/new_module.py"]["new"], None)
        freeze.require_freeze(self.repo.root)

    def test_two_amendments_chain_and_tampering_with_the_first_breaks_verify(self) -> None:
        self.repo.write("src/tool.py", "VALUE = 2\n")
        first = self.amend(on=FREEZE_ON)
        self.repo.write("prompts/llm.txt", "Classify the request carefully.\n")
        second = self.amend(on=LATER, reason="Clarify the LLM prompt wording")
        self.assertEqual(second["amendments"][1]["previous_content_sha256"], first["content_sha256"])
        freeze.require_freeze(self.repo.root)
        # Each edit is rehashed at the top level, so only the chain or the order can catch it.
        edits = {"reason": (lambda a: a.__setitem__("reason", "something else"), "freeze_tampered"),
                 "chain": (lambda a: a.__setitem__("previous_content_sha256", "0" * 64), "freeze_tampered"),
                 "date order": (lambda a: a.__setitem__("on", "2026-11-09"), "freeze_malformed"),
                 "missing field": (lambda a: a.pop("commit"), "freeze_malformed")}
        for name, (edit, code) in edits.items():
            with self.subTest(edit=name):
                record = json.loads(json.dumps(second))
                edit(record["amendments"][0])
                record["content_sha256"] = freeze.canonical_sha256(freeze._without_content(record))
                self.path.write_text(json.dumps(record), encoding="utf-8")
                self.assertEqual(self.verify_code(), code)

    def test_an_analysis_config_amendment_moves_the_top_level_hash(self) -> None:
        text = (self.repo.root / "configs/analysis/analysis-v1.toml").read_text(encoding="utf-8")
        self.repo.write("configs/analysis/analysis-v1.toml", text.replace("samples = 50", "samples = 60"))
        amended = self.amend(reason="Raise bootstrap samples after the Monte Carlo check")
        self.assertEqual(amended["analysis_config_sha256"], amended["pins"]["analysis.config"])
        self.assertNotEqual(amended["analysis_config_sha256"], self.record["analysis_config_sha256"])
        new_hash = freeze.load_analysis_config(self.repo.root / "configs/analysis/analysis-v1.toml").sha256
        self.assertEqual(analysis_freeze.require_frozen_config(self.path, new_hash), new_hash)
        self.assertEqual(analysis_freeze.freeze_date(self.path), FREEZE_ON)

    def test_an_environment_lock_change_is_amendable(self) -> None:
        self.repo.write("uv.lock", "version = 2\n")
        self.assertEqual(list(self.amend()["amendments"][0]["changes"]), ["env.uv_lock"])


class RefusalTest(AmendTestCase):
    def test_no_record(self) -> None:
        self.path.unlink()
        with self.assertRaises(FreezeError) as caught:
            self.amend()
        self.assertEqual(caught.exception.code, "freeze_missing")

    def test_a_tampered_record(self) -> None:
        record = json.loads(self.path.read_text(encoding="utf-8"))
        record["pins"]["code.src/tool.py"] = "0" * 64
        self.path.write_text(json.dumps(record), encoding="utf-8")
        self.assert_refused("freeze_tampered")

    def test_nothing_changed(self) -> None:
        self.assert_refused("nothing_changed")

    def test_the_test_set_cannot_be_amended(self) -> None:
        self.repo.write_registry([registry_row(INSPECTED, "2026-10-01"), registry_row(PRIMARY, "2026-10-02")])
        self.repo.write_audit()
        error = self.assert_refused("frozen_set_immutable")
        self.assertIn("membership.registry_pre_freeze", error.keys)

    def test_data_cannot_be_amended(self) -> None:
        self.repo.write("data/sources.toml", "schema_version = 2\n")
        self.assertEqual(self.assert_refused("frozen_set_immutable").keys, ("data.sources_toml",))

    def test_bad_reasons(self) -> None:
        self.repo.write("src/tool.py", "VALUE = 2\n")
        for reason in ("", "   ", "x" * 501, "two\nlines", "café", "fix PMUL9002", "fix pmul9002_t1", "see SNG01234.json"):
            with self.subTest(reason=reason):
                self.assert_refused("bad_reason", reason=reason)
        self.amend(reason="x" * 500)

    def test_dates(self) -> None:
        self.repo.write("src/tool.py", "VALUE = 2\n")
        self.assert_refused("amend_before_freeze", on=FREEZE_ON - datetime.timedelta(days=1))
        self.assertIn("date_in_future", self.assert_refused("not_ready", on=TODAY + datetime.timedelta(days=1)).keys)
        self.amend(on=LATER)
        self.repo.write("src/tool.py", "VALUE = 3\n")
        self.assert_refused("amend_out_of_order", on=FREEZE_ON)

    def test_write_preconditions_still_hold(self) -> None:
        self.repo.write("src/tool.py", "VALUE = 2\n")
        self.assertEqual(self.assert_refused("not_ready", git=lambda root: {"git_commit": "a" * 40, "git_dirty": True}).keys,
                         ("tree_dirty",))
        self.repo.write_analysis_config(draft=True)
        self.assertIn("analysis_draft", self.assert_refused("not_ready").keys)

    def test_the_size_cap(self) -> None:
        self.repo.write("src/tool.py", "VALUE = 2\n")
        size = len(self.path.read_bytes())
        with mock.patch.object(freeze, "MAX_RECORD_BYTES", size + 50):
            self.assert_refused("record_too_large")


class ShowTest(AmendTestCase):
    def cli(self, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        with redirect_stdout(out), mock.patch.object(freeze, "git_probe", clean_git), \
                mock.patch.object(freeze.datetime, "date", wraps=freeze.datetime.date) as date:
            date.today.return_value = TODAY
            code = freeze.main([*argv, "--root", str(self.repo.root)])
        return code, out.getvalue()

    def test_show_lists_pins_and_amendments(self) -> None:
        self.repo.write("src/tool.py", "VALUE = 2\n")
        code, out = self.cli("amend", "--on", LATER.isoformat(), "--reason", "Fix the tool constant")
        self.assertEqual(code, 0)
        self.assertIn("amended data/manifests/freeze.json on 2026-11-08: code.src/tool.py", out)
        code, out = self.cli("show")
        self.assertEqual(code, 0)
        self.assertIn(f"freeze_date {FREEZE_ON.isoformat()}", out)
        self.assertIn("1 amendment(s)", out)
        self.assertIn("1. 2026-11-08: Fix the tool constant", out)
        self.assertIn("changed: code.src/tool.py", out)
        self.assertIn("data.items = ", out)
        self.assertNotIn("9001", out)
        self.assertNotIn("9002", out)

    def test_amend_needs_on_and_reason(self) -> None:
        for argv in (["amend", "--reason", "x"], ["amend", "--on", "2026-11-08"]):
            with self.subTest(argv=argv), mock.patch("sys.stderr"), self.assertRaises(SystemExit):
                freeze.main([*argv, "--root", str(self.repo.root)])

    def test_show_refuses_a_tampered_record(self) -> None:
        record = json.loads(self.path.read_text(encoding="utf-8"))
        record["freeze_date"] = "2026-11-01"
        self.path.write_text(json.dumps(record), encoding="utf-8")
        code, out = self.cli("show")
        self.assertEqual(code, 1)
        self.assertIn("freeze_tampered", out)


if __name__ == "__main__":
    main()
