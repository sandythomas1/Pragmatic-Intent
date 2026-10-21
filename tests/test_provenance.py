"""Provenance git state: a run's own outputs never mark the tree dirty, real changes always do."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.stage1.provenance import git_state

# Hermetic git: no user or system config (signing, hooks, templates) leaks into the fixture repo.
GIT_ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}


@unittest.skipUnless(shutil.which("git"), "git is not on PATH")
class GitStateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.enterContext(mock.patch.dict(os.environ, GIT_ENV))
        base = Path(self.enterContext(tempfile.TemporaryDirectory()))
        os.environ["GIT_CEILING_DIRECTORIES"] = str(base)  # "outside" must not find an enclosing repo
        self.repo, self.outside = base / "repo", base / "outside"
        self.repo.mkdir()
        self.outside.mkdir()
        (self.repo / "src").mkdir()
        (self.repo / "src" / "model.py").write_text("x = 1\n", encoding="utf-8")
        (self.repo / "results").mkdir()
        (self.repo / "results" / "stage1.jsonl").write_text("{}\n", encoding="utf-8")
        self.git("init", "-q")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "init")
        cwd = Path.cwd()
        os.chdir(self.repo)
        self.addCleanup(os.chdir, cwd)
        self.log = Path("results/stage1.jsonl")

    def git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True)

    def append_result(self) -> None:
        with (self.repo / "results" / "stage1.jsonl").open("a", encoding="utf-8") as handle:
            handle.write("{}\n")

    def test_clean_checkout_reports_its_commit_and_clean(self) -> None:
        state = git_state(ignore=(self.log,))
        self.assertEqual(state["git_dirty"], False)
        self.assertRegex(state["git_commit"], r"^[0-9a-f]{40}$")

    def test_appended_results_log_counts_only_when_not_ignored(self) -> None:
        self.append_result()
        self.assertEqual(git_state()["git_dirty"], True)
        self.assertEqual(git_state(ignore=(self.log,))["git_dirty"], False)

    def test_absolute_ignore_path_and_untracked_output_dir_are_excluded(self) -> None:
        self.append_result()
        out = self.repo / "runs" / "seed1"
        out.mkdir(parents=True)
        (out / "metrics.json").write_text("{}\n", encoding="utf-8")
        self.assertEqual(git_state(ignore=(self.repo / "results" / "stage1.jsonl", out))["git_dirty"], False)

    def test_code_changes_still_count_beside_ignored_outputs(self) -> None:
        self.append_result()
        (self.repo / "src" / "model.py").write_text("x = 2\n", encoding="utf-8")
        self.assertEqual(git_state(ignore=(self.log,))["git_dirty"], True)

    def test_untracked_code_counts(self) -> None:
        (self.repo / "src" / "new.py").write_text("", encoding="utf-8")
        self.assertEqual(git_state(ignore=(self.log,))["git_dirty"], True)

    def test_ignore_paths_outside_the_worktree_do_not_break_the_check(self) -> None:
        elsewhere = self.outside / "stage1.jsonl"
        self.assertEqual(git_state(ignore=(elsewhere,))["git_dirty"], False)
        (self.repo / "src" / "model.py").write_text("x = 2\n", encoding="utf-8")
        self.assertEqual(git_state(ignore=(elsewhere,))["git_dirty"], True)

    def test_whole_tree_is_checked_from_a_subdirectory(self) -> None:
        (self.repo / "src" / "model.py").write_text("x = 2\n", encoding="utf-8")
        os.chdir(self.repo / "results")
        self.assertEqual(git_state(ignore=(Path("stage1.jsonl"),))["git_dirty"], True)

    def test_outside_any_repository_both_fields_are_unknown(self) -> None:
        os.chdir(self.outside)
        self.assertEqual(git_state(ignore=(self.log,)), {"git_commit": None, "git_dirty": None})


class MissingGitTest(unittest.TestCase):
    def test_no_git_binary_leaves_both_fields_unknown(self) -> None:
        # Native Windows often has git only inside GitHub Desktop, off PATH.
        with mock.patch("src.stage1.provenance.subprocess.run", side_effect=FileNotFoundError("git")):
            self.assertEqual(git_state(ignore=(Path("results.jsonl"),)), {"git_commit": None, "git_dirty": None})


if __name__ == "__main__":
    unittest.main()
