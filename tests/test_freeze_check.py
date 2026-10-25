"""Write preconditions and ``check`` (spec 008 T4): reason codes, fail-closed git, no test IDs."""

from __future__ import annotations

import datetime
import io
import logging
import os
import shutil
import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any
from unittest import mock

from src.data import freeze
from src.data import split_audit as sa
from tests.freeze_fixtures import INPUTS, INSPECTED, PRIMARY, FreezeRepo, registry_row

TODAY = datetime.date(2026, 11, 8)
CLEAN = {"git_commit": "a" * 40, "git_dirty": False}


def clean_git(root: Path) -> dict[str, Any]:
    return dict(CLEAN)


class CheckTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = FreezeRepo().build()
        self.addCleanup(self.repo.cleanup)

    def state(self, *, on: datetime.date = TODAY, git: freeze.GitProbe = clean_git) -> freeze.PinState:
        return freeze.check_state(self.repo.inputs(), self.repo.root, on=on, today=TODAY, git=git)

    def codes(self, **options: Any) -> set[str]:
        return {finding.code for finding in self.state(**options).findings}

    def run_check(self, *argv: str, git: freeze.GitProbe = clean_git) -> tuple[int, str, str, list[str]]:
        stdout, stderr = io.StringIO(), io.StringIO()
        records: list[str] = []

        class Collect(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record.getMessage())

        handler = Collect(level=logging.DEBUG)
        logging.getLogger().addHandler(handler)
        self.addCleanup(logging.getLogger().removeHandler, handler)
        with redirect_stdout(stdout), redirect_stderr(stderr), mock.patch.object(freeze, "git_probe", git), \
                mock.patch.object(freeze.datetime, "date", wraps=datetime.date) as date:
            date.today.return_value = TODAY
            code = freeze.main(["check", "--root", str(self.repo.root), "--inputs", INPUTS.as_posix(), *argv])
        return code, stdout.getvalue(), stderr.getvalue(), records


class ReadyTest(CheckTestCase):
    def test_a_ready_repository_has_no_findings(self) -> None:
        state = self.state()
        self.assertEqual(state.findings, [])
        self.assertEqual(state.git_commit, "a" * 40)

    def test_check_exits_zero_when_ready(self) -> None:
        code, out, _, _ = self.run_check()
        self.assertEqual(code, 0)
        self.assertIn("ready to write", out)

    def test_check_is_read_only(self) -> None:
        def snapshot() -> dict[str, tuple[bytes, int]]:
            return {p.relative_to(self.repo.root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
                    for p in self.repo.root.rglob("*") if p.is_file() and "__pycache__" not in p.parts}

        before = snapshot()
        self.run_check("--verbose")
        self.repo.write("configs/analysis/analysis-v1.toml", "broken")
        before["configs/analysis/analysis-v1.toml"] = snapshot()["configs/analysis/analysis-v1.toml"]
        self.run_check()
        self.assertEqual(snapshot(), before)
        self.assertFalse((self.repo.root / sa.FREEZE_FILE).exists())

    def test_verbose_lists_pin_keys_but_never_values(self) -> None:
        state = self.state()
        _, out, _, _ = self.run_check("--verbose")
        self.assertIn("ready    data.items", out)
        self.assertNotIn(state.pins["data.items"], out)


class PreconditionTest(CheckTestCase):
    def test_an_existing_record_is_refused(self) -> None:
        self.repo.write(sa.FREEZE_FILE, "{}\n")
        self.assertIn("freeze_exists", self.codes())

    def test_a_draft_analysis_config(self) -> None:
        self.repo.write_analysis_config(draft=True)
        self.assertEqual(self.codes(), {"analysis_draft"})

    def test_a_stale_test_audit(self) -> None:
        self.repo.ws.write_jsonl(sa.DEFAULT_DIALOGUES.as_posix(), [{"dialogue_id": "x", "turns": [1]}])
        self.assertEqual(self.codes(), {"test_audit_failed"})

    def test_missing_data_is_reported_once_not_as_an_audit_crash(self) -> None:
        (self.repo.root / sa.DEFAULT_DIALOGUES).unlink()
        self.assertEqual(self.codes(), {"file_missing"})

    def test_git_unavailable_or_unknown_is_never_clean(self) -> None:
        for info in ({"git_commit": None, "git_dirty": None}, {"git_commit": "a" * 40, "git_dirty": None}, {}):
            with self.subTest(info=info):
                self.assertEqual(self.codes(git=lambda root, info=info: info), {"git_unavailable"})

    def test_a_dirty_tree(self) -> None:
        self.assertEqual(self.codes(git=lambda root: {"git_commit": "a" * 40, "git_dirty": True}), {"tree_dirty"})

    def test_a_future_date(self) -> None:
        self.assertEqual(self.codes(on=TODAY + datetime.timedelta(days=1)), {"date_in_future"})

    def test_the_date_must_be_strictly_after_every_pre_freeze_inspection(self) -> None:
        self.repo.write_registry([registry_row(INSPECTED, "2026-11-07")])
        self.repo.write_audit()
        self.assertEqual(self.codes(on=datetime.date(2026, 11, 7)), {"date_not_after_inspection"})
        self.assertEqual(self.codes(on=datetime.date(2026, 11, 6)), {"date_not_after_inspection"})
        self.assertEqual(self.codes(on=datetime.date(2026, 11, 8)), set())

    def test_post_scoring_rows_do_not_hold_the_date_back(self) -> None:
        self.repo.write_registry([registry_row(INSPECTED, "2026-10-01"),
                                  registry_row(PRIMARY, "2026-12-01", phase="post_scoring")])
        self.repo.write_audit()
        self.assertEqual(self.codes(), set())

    def test_every_finding_reaches_check_and_fails_it(self) -> None:
        self.repo.write_analysis_config(draft=True)
        code, out, _, _ = self.run_check(git=lambda root: {"git_commit": None, "git_dirty": None})
        self.assertEqual(code, 1)
        self.assertIn("analysis_draft", out)
        self.assertIn("git_unavailable", out)
        self.assertIn("not ready: 2 item(s)", out)

    def test_invalid_inputs_fail_check_with_their_code(self) -> None:
        self.repo.write(INPUTS, "version = 'freeze-inputs-v0'\n")
        code, out, _, _ = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("missing_key", out)

    def test_a_bad_on_date_is_a_usage_error(self) -> None:
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            freeze.main(["check", "--on", "2026-11-8"])


class NoTestIdsTest(CheckTestCase):
    def test_an_unregistered_sheet_is_counted_and_its_id_never_printed_or_logged(self) -> None:
        self.repo.write("data/interim/labeling/round9/sheet.csv", f"dialogue_id,label\n{PRIMARY},L1\n")
        self.assertIn("scan_unregistered", self.codes())
        code, out, err, logs = self.run_check("--verbose")
        self.assertEqual(code, 1)
        self.assertIn("1 unregistered test dialogue(s) in 1 file(s): data/interim/labeling/round9/sheet.csv", out)
        for text in (out, err, *logs):
            self.assertNotIn("9002", text)

    def test_an_invalid_registry_never_prints_its_rows(self) -> None:
        self.repo.write_registry([registry_row("PMUL9876.json", "2026-10-01")])
        code, out, err, logs = self.run_check()
        self.assertEqual(code, 1)
        for text in (out, err, *logs):
            self.assertNotIn("9876", text)

    def test_printed_lines_mask_anything_shaped_like_an_id(self) -> None:
        self.assertEqual(freeze.mask_ids("see PMUL1234 and SNG01234.json, not XPMUL1234"),
                         "see <id> and <id>.json, not XPMUL1234")


@unittest.skipUnless(shutil.which("git"), "git is not on PATH (expected on native Windows without GitHub Desktop's git)")
class RealGitTest(CheckTestCase):
    def git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.repo.root, check=True, capture_output=True,
                       env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
                            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"})

    def setUp(self) -> None:
        super().setUp()
        self.git("init", "-q")
        self.git("config", "core.autocrlf", "false")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "fixture")

    def test_clean_then_dirty_then_outputs_ignored(self) -> None:
        state = self.state(git=freeze.git_probe)
        self.assertEqual(state.findings, [])
        self.assertRegex(state.git_commit or "", r"[0-9a-f]{40}")
        self.repo.write("results/stage1.jsonl", "{}\n")
        self.repo.write("outputs/run/metrics.json", "{}\n")
        self.assertEqual(self.codes(git=freeze.git_probe), set())
        self.repo.write("src/tool.py", "VALUE = 3\n")
        self.assertIn("tree_dirty", self.codes(git=freeze.git_probe))

    def test_an_untracked_file_is_dirty(self) -> None:
        self.repo.write("configs/analysis/inputs-test.toml", "x = 1\n")
        self.assertEqual(self.codes(git=freeze.git_probe), {"tree_dirty"})


if __name__ == "__main__":
    unittest.main()
