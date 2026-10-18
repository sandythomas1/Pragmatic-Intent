"""Tests for ``validate`` (spec 003 T12, FR12, AC-003-9). Invented fixtures only."""

from __future__ import annotations

import json
import unittest
from collections.abc import Callable
from pathlib import Path

from src.annotation import context as ctx
from src.annotation import context_items as ci
from src.annotation import context_passes as cp
from src.annotation import context_schema as cs
from src.annotation import context_validate as vd
from src.annotation.levels import read_csv, write_csv
from tests.test_context_corrections import CorrectionCase
from tests.test_context_passes import FormPassCase
from tests.test_context_sealed_passes import SealedCase, dialogue_labels

Rows = list[dict[str, str]]


def rewrite(path: Path, change: Callable[[Rows], None]) -> None:
    rows = read_csv(path)
    change(rows)
    write_csv(path, list(rows[0]), rows)


def rewrite_text_records(path: Path, change: Callable[[dict], None]) -> None:
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for record in records:
        change(record)
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")


class ValidateMixin(unittest.TestCase):
    dirs: ctx.Dirs

    def findings(self) -> list[vd.Finding]:
        return ctx.validate(self.dirs)

    def rules_for(self, subject_part: str = "") -> set[str]:
        return {finding.rule for finding in self.findings() if subject_part in finding.subject}

    def assertRule(self, rule: str, subject_part: str = "") -> None:
        findings = self.findings()
        self.assertTrue(
            any(finding.rule == rule and subject_part in finding.subject for finding in findings),
            f"expected [{rule}] on {subject_part!r}; got:\n" + "\n".join(map(str, findings)),
        )


class FullWorkspaceCase(CorrectionCase, ValidateMixin):
    """All three passes exported for A1, then a form correction made after the later passes."""

    def setUp(self) -> None:
        super().setUp()
        self.seal_context()
        self.assertEqual(self.build("reveal"), 0)
        self.fill_pass("reveal", lambda entry: {"future_dependence": "corroborates"})
        self.assertEqual(self.export_pass("reveal"), 0)
        self.assertEqual(self.prepare("form"), 0)
        self.edit("form", form="L2")
        self.assertEqual(self.apply("form"), 0)
        self.other = next(item for item in self.item_ids("dialogue") if item != self.item)

    def committed(self, pass_name: str) -> Path:
        return self.pass_paths(pass_name).committed


class CleanWorkspaceTests(FullWorkspaceCase):
    def test_fresh_export_with_a_correction_passes(self) -> None:
        self.assertEqual(self.findings(), [])
        self.assertEqual(self.cli("validate"), 0)

    def test_a_paraphrase_only_context_correction_still_passes(self) -> None:
        self.assertEqual(self.prepare("context", item=self.other), 0)
        self.edit("context", paraphrase="Find me a different hotel")
        self.assertEqual(self.apply("context", item=self.other), 0)
        self.assertEqual(self.findings(), [])

    def test_rows_built_on_the_superseded_form_row_are_accepted(self) -> None:
        old = next(row for row in cp.load_committed(self.paths) if row["item_id"] == self.item and row["status"] == "superseded")
        context = next(row for row in cp.load_committed(self.pass_paths("context")) if row["item_id"] == self.item)
        self.assertEqual(context["prior_sha256"], cs.canonical_hash(old))
        self.assertEqual(self.findings(), [])


class EditedFileTests(FullWorkspaceCase):
    """AC-003-9: each edit fails with a named rule."""

    def test_edited_committed_label(self) -> None:
        def edit(rows: Rows) -> None:
            row = next(row for row in rows if row["item_id"] == self.other)
            row["form"] = "L3"

        rewrite(self.committed("form"), edit)
        self.assertRule("row-hash", self.other)
        self.assertRule("prior-chain", f"{self.other} (context A1")
        self.assertEqual(self.cli("validate"), 1)

    def test_edited_reveal_label_alone_is_caught(self) -> None:
        rewrite(self.committed("reveal"), lambda rows: rows[0].update(future_dependence="none", confirmatory_eligible="true"))
        self.assertRule("row-hash", rows_item(self.committed("reveal")))

    def test_edited_prior_sha256(self) -> None:
        rewrite(self.committed("context"), lambda rows: rows[0].update(prior_sha256="0" * 64))
        self.assertRule("prior-chain", rows_item(self.committed("context")))

    def test_edited_registry_target_sha256(self) -> None:
        rewrite(self.dirs.registry, lambda rows: rows[0].update(target_sha256="a" * 64))
        item = read_csv(self.dirs.registry)[0]["item_id"]
        self.assertRule("target-hash", item)
        self.assertRule("prior-chain", f"{item} (form")

    def test_edited_group_split(self) -> None:
        literary = self.item_ids("literary")[0]
        rewrite(self.dirs.registry, lambda rows: next(row for row in rows if row["item_id"] == literary).update(split="test"))
        self.assertRule("registry", literary)
        self.assertRule("group-split", literary)

    def test_group_spanning_splits(self) -> None:
        findings = vd.check_registry(
            [{**read_csv(self.dirs.registry)[0], "split": "dev"}, {**read_csv(self.dirs.registry)[0], "item_id": "d:X:t02", "split": "test"}],
            None,
            {},
        )
        self.assertIn("group-split", {finding.rule for finding in findings})

    def test_edited_local_paraphrase(self) -> None:
        def edit(record: dict) -> None:
            if record["item_id"] == self.other:
                record["paraphrase"] = "something else entirely"

        rewrite_text_records(self.pass_paths("context").text, edit)
        self.assertRule("local-text", self.other)

    def test_missing_local_text_file(self) -> None:
        self.pass_paths("context").text.unlink()
        self.assertRule("local-text", "context_A1_text.jsonl")

    def test_malformed_local_text_file(self) -> None:
        self.pass_paths("form").text.write_text("not json\n", encoding="utf-8")
        self.assertRule("local-text", "form_A1_text.jsonl")

    def test_screening_row_flipped_to_exclude_after_registration(self) -> None:
        literary = self.item_ids("literary")[0]

        def flip(rows: Rows) -> None:
            next(row for row in rows if row["candidate_id"] == literary).update(status="exclude", exclusion_reason="no_context")

        rewrite(self.dirs.literary.log, flip)
        self.assertRule("screening-log", literary)

    def test_bad_enum_in_a_committed_file(self) -> None:
        rewrite(self.committed("context"), lambda rows: rows[0].update(confidence="sure"))
        self.assertRule("labels", rows_item(self.committed("context")))

    def test_unknown_item_in_a_pass_file(self) -> None:
        rewrite(self.dirs.registry, lambda rows: rows.remove(next(row for row in rows if row["item_id"] == self.other)))
        self.assertRule("foreign-id", f"{self.other} (form")

    def test_two_live_rows_for_one_item(self) -> None:
        rewrite(self.committed("form"), lambda rows: [row.update(status="") for row in rows if row["item_id"] == self.item])
        self.assertRule("duplicate-id", self.item)
        self.assertRule("corrections", self.item)

    def test_dialogue_source_missing(self) -> None:
        self.dirs.dialogues.unlink()
        self.assertRule("target-hash", "dialogues.jsonl")


class CorrectionLogTests(FullWorkspaceCase):
    def test_deleted_log_entry(self) -> None:
        rows = read_csv(self.dirs.corrections)
        write_csv(self.dirs.corrections, cp.CORRECTION_FIELDS, rows[1:])
        self.assertRule("corrections", self.item)
        self.assertRule("prior-chain", f"{self.item} (context")

    def test_later_passes_sealed_flipped_to_false(self) -> None:
        rewrite(self.dirs.corrections, lambda rows: rows[0].update(later_passes_sealed="false"))
        self.assertRule("corrections", self.item)

    def test_hashes_that_match_no_row(self) -> None:
        rewrite(self.dirs.corrections, lambda rows: rows[0].update(old_sha256="b" * 64, new_sha256="c" * 64))
        messages = [finding.message for finding in self.findings() if finding.rule == "corrections"]
        self.assertTrue(any("old_sha256" in message for message in messages))
        self.assertTrue(any("new_sha256" in message for message in messages))

    def test_log_entry_for_an_unknown_item(self) -> None:
        rewrite(self.dirs.corrections, lambda rows: rows.append({**rows[0], "item_id": "d:NOPE:t02"}))
        self.assertRule("foreign-id", "d:NOPE:t02")


class TaxonomyTests(FullWorkspaceCase):
    def test_version_edited_in_place(self) -> None:
        rewrite(self.dirs.taxonomy, lambda rows: rows[0].update(optional_slots="price;stars"))
        self.assertRule("taxonomy")
        self.assertIn("edited in place", "\n".join(finding.message for finding in self.findings()))

    def test_version_used_by_labels_removed(self) -> None:
        rewrite(self.dirs.taxonomy, lambda rows: rows.__setitem__(slice(None), [row for row in rows if row["taxonomy_version"] != "ctx-tax-v0"]))
        self.assertRule("taxonomy", "intent_taxonomy.csv")

    def test_taxonomy_file_deleted(self) -> None:
        self.dirs.taxonomy.unlink()
        self.assertRule("taxonomy", "intent_taxonomy.csv")


class SnapshotTamperTests(SealedCase, ValidateMixin):
    """The deferred T9 note: a local snapshot edited before export is caught by recomputation."""

    def test_inflated_segment_count_is_caught(self) -> None:
        self.assertEqual(self.build("context", "--taxonomy", "ctx-tax-v0"), 0)
        snapshot = json.loads(self.pass_paths("context").snapshot.read_text(encoding="utf-8"))
        target = next(entry for entry in snapshot["rows"] if entry["stratum"] == "dialogue")
        target["n_segments"] = 50
        self.pass_paths("context").snapshot.write_text(json.dumps(snapshot), encoding="utf-8")
        self.fill_context(**{target["item_id"]: {"evidence": "40"}})
        self.assertEqual(self.export_pass("context"), 0)
        self.assertRule("evidence", target["item_id"])

    def test_relabelled_stratum_is_caught(self) -> None:
        self.assertEqual(self.build("context", "--taxonomy", "ctx-tax-v0"), 0)
        snapshot = json.loads(self.pass_paths("context").snapshot.read_text(encoding="utf-8"))
        target = next(entry for entry in snapshot["rows"] if entry["stratum"] == "literary")
        target["stratum"] = "dialogue"
        self.pass_paths("context").snapshot.write_text(json.dumps(snapshot), encoding="utf-8")
        self.fill_context(**{target["item_id"]: {**dialogue_labels(), "evidence": "0"}})
        self.assertEqual(self.export_pass("context"), 0)
        self.assertRule("labels", target["item_id"])


class SmallWorkspaceTests(FormPassCase, ValidateMixin):
    def test_registry_only_passes(self) -> None:
        self.assertEqual(self.findings(), [])

    def test_form_only_passes_without_a_taxonomy(self) -> None:
        self.assertEqual(self.sheet(), 0)
        self.fill()
        self.assertEqual(self.export(), 0)
        self.assertEqual(self.findings(), [])

    def test_empty_workspace_passes(self) -> None:
        self.dirs.registry.unlink()
        self.dirs.literary.log.unlink()
        self.assertEqual(self.findings(), [])

    def test_dialogue_split_disagreeing_with_items_jsonl(self) -> None:
        dialogue = self.item_ids_of("dialogue")[0]
        stem = dialogue.split(":")[1]
        items = [json.loads(line) for line in self.dirs.items.read_text(encoding="utf-8").splitlines()]
        for item in items:
            if item["dialogue_id"] == f"{stem}.json":
                item["split"] = "test"
        self.dirs.items.write_text("".join(json.dumps(item) + "\n" for item in items), encoding="utf-8")
        self.assertRule("group-split", dialogue)

    def test_pass_file_with_an_invalid_annotator_name(self) -> None:
        (self.dirs.annotations_dir / "context_form_bad name.csv").write_text("item_id\n", encoding="utf-8")
        self.assertRule("foreign-id", "context_form_bad name.csv")

    def item_ids_of(self, stratum: str) -> list[str]:
        return [row["item_id"] for row in ci.load_registry(self.dirs.registry) if row["stratum"] == stratum]


class FindingTests(unittest.TestCase):
    def test_unknown_rule_is_a_programming_error(self) -> None:
        with self.assertRaises(ValueError):
            vd.Finding("nope", "x", "y")

    def test_malformed_cells_never_reach_the_terminal_raw(self) -> None:
        row = dict.fromkeys(ci.REGISTRY_FIELDS, "\x1b[2J")
        findings = vd.check_registry([row], {}, {})
        self.assertTrue(findings)
        self.assertFalse(any("\x1b" in str(finding) for finding in findings))
        self.assertEqual(vd.shown("d:PMUL0001:t02"), "d:PMUL0001:t02")

    def test_findings_print_rule_subject_and_message(self) -> None:
        self.assertEqual(str(vd.Finding("labels", "d:X:t02", "bad")), "[labels] d:X:t02: bad")


def rows_item(path: Path) -> str:
    return read_csv(path)[0]["item_id"]


if __name__ == "__main__":
    unittest.main()
