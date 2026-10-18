"""Tests for the context and reveal passes (spec 003 T9, T10). Invented fixtures only."""

from __future__ import annotations

import json
from collections.abc import Callable

from src.annotation import context as ctx
from src.annotation import context_items as ci
from src.annotation import context_passes as cp
from src.annotation import context_schema as cs
from src.annotation import context_taxonomy as ct
from src.annotation.levels import read_csv, write_csv
from tests import context_fixtures as fx
from tests.test_context_passes import FormPassCase

TAXONOMY = [
    {"taxonomy_version": "ctx-tax-v0", "intent_id": "find_hotel", "stratum": "dialogue", "required_slots": "area", "optional_slots": "price", "description": "Hotel"},
    {"taxonomy_version": "ctx-tax-v0", "intent_id": "book_taxi", "stratum": "dialogue", "required_slots": "destination", "optional_slots": "", "description": "Taxi"},
    {"taxonomy_version": "ctx-tax-v0", "intent_id": "give", "stratum": "literary", "required_slots": "", "optional_slots": "object", "description": "Give"},
    {"taxonomy_version": "ctx-tax-v0", "intent_id": "joint_action", "stratum": "both", "required_slots": "", "optional_slots": "action", "description": "Let us"},
    {"taxonomy_version": "ctx-tax-v1", "intent_id": "find_hotel", "stratum": "dialogue", "required_slots": "area;price", "optional_slots": "", "description": "Hotel"},
    {"taxonomy_version": "ctx-tax-v1", "intent_id": "give", "stratum": "literary", "required_slots": "", "optional_slots": "object", "description": "Give"},
]  # fmt: skip
PARAPHRASE = "Find me a hotel in the quiet quarter"
SLOT_VALUE = "the quiet quarter"
NOTE = "private musing about the heron"

Labels = dict[str, str]


def dialogue_labels() -> Labels:
    return {"function": "request", "intent": "find_hotel", "slots": f"area={SLOT_VALUE}", "paraphrase": PARAPHRASE,
            "evidence": "0", "confidence": "certain", "notes": NOTE}  # fmt: skip


def literary_labels() -> Labels:
    return {"function": "request", "intent": "give", "slots": "", "paraphrase": "Give me warmth", "evidence": "0", "confidence": "probable"}


class SealedCase(FormPassCase):
    """Seven items with A1's form pass exported and the fixture taxonomy written."""

    def setUp(self) -> None:
        super().setUp()
        write_csv(self.dirs.taxonomy, ct.TAXONOMY_FIELDS, TAXONOMY)
        self.seal_form()

    def seal_form(self, annotator: str = "A1") -> None:
        paths = self.paths if annotator == "A1" else cp.PassPaths(self.dirs.work_dir, self.dirs.annotations_dir, "pilot1", "form", annotator)
        self.assertEqual(self.sheet(annotator=annotator), 0)
        rows = read_csv(paths.sheet)
        for row in rows:
            row.update(form="INF", fragment="0")
        write_csv(paths.sheet, cp.SHEET_FIELDS["form"], rows, excel=True)
        self.assertEqual(self.export(annotator=annotator), 0)

    def pass_paths(self, pass_name: str, annotator: str = "A1") -> cp.PassPaths:
        return cp.PassPaths(self.dirs.work_dir, self.dirs.annotations_dir, "pilot1", pass_name, annotator)

    def build(self, pass_name: str, *extra: str) -> int:
        return self.cli("sheet", "--pass", pass_name, "--batch", "pilot1", "--annotator", "A1", "--seed", "3", *extra)

    def entries(self, pass_name: str) -> list[dict]:
        return json.loads(self.pass_paths(pass_name).snapshot.read_text(encoding="utf-8"))["rows"]

    def fill_pass(self, pass_name: str, labels: Callable[[dict], Labels]) -> list[dict[str, str]]:
        """Fill every row with ``labels(snapshot_entry)``; save and return the sheet rows."""
        paths = self.pass_paths(pass_name)
        by_row = {entry["row_id"]: entry for entry in self.entries(pass_name)}
        rows = read_csv(paths.sheet)
        for row in rows:
            row.update(labels(by_row[row["row_id"]]))
        write_csv(paths.sheet, cp.SHEET_FIELDS[pass_name], rows, excel=True)
        return rows

    def fill_context(self, **per_item: Labels) -> list[dict[str, str]]:
        def labels(entry: dict) -> Labels:
            base = dialogue_labels() if entry["stratum"] == "dialogue" else literary_labels()
            return {**base, **per_item.get(entry["item_id"], {})}

        return self.fill_pass("context", labels)

    def export_pass(self, pass_name: str) -> int:
        return self.cli("export", "--pass", pass_name, "--batch", "pilot1", "--annotator", "A1")

    def export_problems(self, pass_name: str) -> str:
        with self.assertRaises(cp.PassError) as raised:
            ctx.export_pass(self.dirs, self.pass_paths(pass_name))
        return "\n".join(raised.exception.problems)

    def seal_context(self) -> None:
        self.assertEqual(self.build("context", "--taxonomy", "ctx-tax-v0"), 0)
        self.fill_context()
        self.assertEqual(self.export_pass("context"), 0)

    def item_ids(self, stratum: str) -> list[str]:
        return [row["item_id"] for row in ci.load_registry(self.dirs.registry) if row["stratum"] == stratum]


class ContextSheetTests(SealedCase):
    def test_only_items_with_a_sealed_form_row_are_included(self) -> None:
        self.assertEqual(self.cli("draw", "--batch", "pilot1b", "--count", "2", "--date", fx.DATE), 0)
        rows = ci.load_registry(self.dirs.registry)
        for row in rows:
            if row["batch"] == "pilot1b":
                row["batch"] = "pilot1"  # registered after the form export: no form row yet
        ci.write_registry(self.dirs.registry, rows)
        self.assertEqual(self.build("context"), 0)
        sealed = {row["item_id"] for row in cp.load_committed(self.paths)}
        self.assertEqual({entry["item_id"] for entry in self.entries("context")}, sealed)
        self.assertEqual(len(sealed), 7)

    def test_no_sealed_form_row_means_no_context_sheet(self) -> None:
        self.assertEqual(self.cli("sheet", "--pass", "context", "--batch", "pilot1", "--annotator", "A2"), 0)
        self.assertFalse(self.pass_paths("context", "A2").sheet.exists())

    def test_sheet_shows_numbered_prior_and_target_but_nothing_after(self) -> None:
        self.build("context")
        rows = {row["row_id"]: row for row in read_csv(self.pass_paths("context").sheet)}
        self.assertEqual(list(next(iter(rows.values()))), list(cp.SHEET_FIELDS["context"]))
        registry = {row["item_id"]: row for row in ci.load_registry(self.dirs.registry)}
        for entry in self.entries("context"):
            row = rows[entry["row_id"]]
            self.assertTrue(cs.ROW_ID_RES["context"].fullmatch(entry["row_id"]))
            if entry["stratum"] == "dialogue":
                dialogue_id, turn = registry[entry["item_id"]]["source_ref"].split("#")
                turns = self.dialogue_turns[dialogue_id]
                self.assertEqual(entry["n_segments"], int(turn))
                self.assertTrue(row["context"].startswith(f"[0] USER: {turns[0].text}"))
                self.assertEqual(row["target"], turns[int(turn)].text)
                for later in turns[int(turn) + 1 :]:
                    self.assertNotIn(later.text, row["context"] + row["target"])
                self.assertEqual(row["speakers"], ctx.DIALOGUE_SPEAKERS)
            else:
                self.assertTrue(row["context"].startswith("[0] An Owl sat by a cold Kettle"))
                self.assertNotIn("Cold owls hint", row["context"] + row["target"])  # the moral
                self.assertNotIn("OWL AND THE KETTLE", row["context"])  # the title
        text = self.pass_paths("context").sheet.read_text(encoding="utf-8-sig")
        for forbidden in ("d:DEV", "lit-", ".json", "aesop"):
            self.assertNotIn(forbidden, text)

    def test_literary_target_never_sees_its_own_reply(self) -> None:
        self.build("context")
        rows = {row["row_id"]: row for row in read_csv(self.pass_paths("context").sheet)}
        owl = next(rows[e["row_id"]] for e in self.entries("context") if e["stratum"] == "literary" and "night" in rows[e["row_id"]]["target"])
        self.assertNotIn("fetch some sticks", owl["context"])
        self.assertEqual(owl["speakers"], "Owl → Badger")

    def test_snapshot_records_the_taxonomy_and_segment_counts(self) -> None:
        self.build("context")
        snapshot = json.loads(self.pass_paths("context").snapshot.read_text(encoding="utf-8"))
        self.assertEqual(snapshot["taxonomy_version"], "ctx-tax-v1")  # newest by default
        self.assertEqual(snapshot["taxonomy_sha256"], ct.version_sha256(TAXONOMY, "ctx-tax-v1"))
        self.assertEqual(snapshot["segmenter_version"], cs.SEGMENTER_VERSION)
        forms = cp.live_rows(cp.load_committed(self.paths))
        for entry in snapshot["rows"]:
            self.assertEqual(entry["prior_sha256"], cs.canonical_hash(forms[entry["item_id"]]))
            self.assertIn(entry["stratum"], cs.STRATA)

    def test_an_older_taxonomy_version_can_be_chosen(self) -> None:
        self.assertEqual(self.build("context", "--taxonomy", "ctx-tax-v9"), 1)  # not in the file
        self.assertFalse(self.pass_paths("context").sheet.exists())
        self.assertEqual(self.build("context", "--taxonomy", "ctx-tax-v0"), 0)
        self.assertEqual(json.loads(self.pass_paths("context").snapshot.read_text(encoding="utf-8"))["taxonomy_version"], "ctx-tax-v0")

    def test_missing_taxonomy_blocks_the_sheet(self) -> None:
        self.dirs.taxonomy.unlink()
        self.assertEqual(self.build("context"), 1)
        self.assertFalse(self.pass_paths("context").sheet.exists())


class ContextExportTests(SealedCase):
    def setUp(self) -> None:
        super().setUp()
        self.assertEqual(self.build("context", "--taxonomy", "ctx-tax-v0"), 0)
        self.dialogue = next(e["item_id"] for e in self.entries("context") if e["stratum"] == "dialogue")
        self.literary = next(e["item_id"] for e in self.entries("context") if e["stratum"] == "literary")

    def test_export_writes_text_free_chained_rows(self) -> None:
        self.fill_context(**{self.dialogue: {"slots": f"price=?; area={SLOT_VALUE}", "evidence": "1, 0", "depth": "one_step"}})
        self.assertEqual(self.export_pass("context"), 0)
        paths = self.pass_paths("context")
        rows = {row["item_id"]: row for row in cp.load_committed(paths)}
        self.assertEqual(len(rows), 7)
        forms = cp.live_rows(cp.load_committed(self.paths))
        for item, row in rows.items():
            self.assertEqual(row["prior_sha256"], cs.canonical_hash(forms[item]))
            self.assertEqual((row["taxonomy_version"], row["segmenter_version"]), ("ctx-tax-v0", cs.SEGMENTER_VERSION))
            self.assertEqual(row["taxonomy_sha256"], ct.version_sha256(TAXONOMY, "ctx-tax-v0"))
            self.assertEqual(row["request_status"], "present")
        row = rows[self.dialogue]
        self.assertEqual((row["slot_names"], row["unstated_slots"], row["evidence"], row["depth"]), ("area;price", "price", "0;1", "one_step"))
        texts = cp.load_text_records(paths)
        record = texts[(self.dialogue, cp.row_key(row))]
        self.assertEqual((record["slots"], record["paraphrase"], record["notes"]), (f"area={SLOT_VALUE};price=?", PARAPHRASE, NOTE))
        self.assertEqual(row["text_sha256"], cs.text_hash(self.dialogue, "context", "A1", record["slots"], record["paraphrase"]))

    def test_committed_file_holds_no_free_text(self) -> None:
        self.fill_context()
        self.export_pass("context")
        committed = self.pass_paths("context").committed.read_text(encoding="utf-8")
        for fragment in (PARAPHRASE, SLOT_VALUE, NOTE, "Give me warmth", "user line", "night is long"):
            self.assertNotIn(fragment, committed)

    def test_every_fr6_rejection_names_the_item(self) -> None:
        literary = self.item_ids("literary")
        other_literary = next(item for item in literary if item != self.literary)
        dialogues = [e["item_id"] for e in self.entries("context") if e["stratum"] == "dialogue"]
        cases = {
            dialogues[0]: ({"intent": "", "slots": ""}, "needs an intent"),
            dialogues[1]: ({"function": "inform"}, "must be blank"),
            dialogues[2]: ({"slots": "price=cheap"}, "required slot 'area' is missing"),
            dialogues[3]: ({"slots": "area=north;stars=4"}, "'stars' is not defined"),
            dialogues[4]: ({"evidence": "9"}, "out of range"),
            self.literary: ({"intent": "fly_away"}, "'fly_away' is not defined"),
            other_literary: ({"intent": "find_hotel", "slots": "area=?"}, "is a dialogue intent"),
        }
        self.fill_context(**{item: labels for item, (labels, _) in cases.items()})
        problems = self.export_problems("context").splitlines()
        for item, (_, fragment) in cases.items():
            with self.subTest(item=item):
                self.assertTrue(any(item in problem and fragment in problem for problem in problems), problems)
        self.assertFalse(self.pass_paths("context").committed.exists())

    def test_unlabeled_rows_and_bad_enums_are_rejected(self) -> None:
        self.fill_context(**{self.dialogue: {"function": "", "confidence": ""}, self.literary: {"depth": "deep", "confidence": "sure"}})
        problems = self.export_problems("context")
        for fragment in ("function is missing", "confidence is missing", "depth 'deep'", "confidence 'sure'"):
            self.assertIn(fragment, problems)

    def test_request_needs_a_paraphrase_and_free_text_is_single_line(self) -> None:
        self.fill_context(**{self.dialogue: {"paraphrase": ""}, self.literary: {"notes": "two\nlines"}})
        problems = self.export_problems("context")
        self.assertIn("needs a paraphrase", problems)
        self.assertIn("newline", problems)

    def test_malformed_evidence_is_rejected_cleanly(self) -> None:
        for bad in ("one", "9" * 5000, "-1", "٣"):  # word, huge number, sign, Arabic-Indic digit
            self.fill_context(**{self.dialogue: {"evidence": bad}})
            with self.subTest(bad=bad[:8]):
                self.assertIn("is not a segment number", self.export_problems("context"))

    def test_corrupt_local_text_file_is_reported(self) -> None:
        self.fill_context()
        self.export_pass("context")
        paths = self.pass_paths("context")
        paths.text.write_text('{"item_id": "x", "row_sha256": "y", "slots": ["not", "text"]}\n', encoding="utf-8")
        with self.assertRaises(cp.PassError) as raised:
            cp.load_text_records(paths)
        self.assertIn("not a text record", str(raised.exception))

    def test_unstated_value_satisfies_a_required_slot(self) -> None:
        self.fill_context(**{self.dialogue: {"slots": "area=?"}})
        self.assertEqual(self.export_pass("context"), 0)
        row = cp.live_rows(cp.load_committed(self.pass_paths("context")))[self.dialogue]
        self.assertEqual((row["slot_names"], row["unstated_slots"]), ("area", "area"))

    def test_non_requests_and_uncertain_readings(self) -> None:
        dialogues = [e["item_id"] for e in self.entries("context") if e["stratum"] == "dialogue"]
        blank = {"intent": "", "slots": "", "paraphrase": "", "evidence": ""}
        self.fill_context(**{
            dialogues[0]: {**blank, "function": "social"},
            dialogues[1]: {**blank, "function": "uncertain"},
            dialogues[2]: {"function": "uncertain", "alt_intent": "book_taxi"},  # a candidate reading
            self.literary: {"function": "request", "intent": "joint_action", "slots": "action=dig"},
        })  # fmt: skip
        self.assertEqual(self.export_pass("context"), 0)
        rows = cp.live_rows(cp.load_committed(self.pass_paths("context")))
        self.assertEqual((rows[dialogues[0]]["request_status"], rows[dialogues[0]]["intent"]), ("absent", ""))
        self.assertEqual(rows[dialogues[1]]["request_status"], "uncertain")
        self.assertEqual((rows[dialogues[2]]["intent"], rows[dialogues[2]]["alt_intent"]), ("find_hotel", "book_taxi"))
        self.assertEqual(rows[self.literary]["intent"], "joint_action")

    def test_out_of_taxonomy_takes_no_slots(self) -> None:
        self.fill_context(**{self.dialogue: {"intent": cs.OUT_OF_TAXONOMY, "slots": ""}, self.literary: {"intent": cs.OUT_OF_TAXONOMY, "slots": "object=fire"}})
        problems = self.export_problems("context")
        self.assertIn(self.literary, problems)
        self.assertNotIn(self.dialogue, problems)

    def test_taxonomy_edited_in_place_after_the_sheet_was_built(self) -> None:
        edited = [dict(row, required_slots="area;price", optional_slots="") if row["intent_id"] == "find_hotel" and row["taxonomy_version"] == "ctx-tax-v0" else row for row in TAXONOMY]  # fmt: skip
        write_csv(self.dirs.taxonomy, ct.TAXONOMY_FIELDS, edited)
        self.fill_context()
        self.assertIn("edited in place", self.export_problems("context"))

    def test_taxonomy_version_removed_after_the_sheet_was_built(self) -> None:
        write_csv(self.dirs.taxonomy, ct.TAXONOMY_FIELDS, [row for row in TAXONOMY if row["taxonomy_version"] != "ctx-tax-v0"])
        self.fill_context()
        self.assertIn("no longer in", self.export_problems("context"))

    def test_changed_paraphrase_after_export_points_to_correct(self) -> None:
        self.fill_context()
        self.export_pass("context")
        self.fill_context(**{self.dialogue: {"paraphrase": "Something else entirely"}})
        self.assertIn("correct", self.export_problems("context"))

    def test_identical_re_export_is_a_no_op(self) -> None:
        self.fill_context()
        self.export_pass("context")
        before = self.pass_paths("context").committed.read_bytes()
        self.assertEqual(self.export_pass("context"), 0)
        self.assertEqual(self.pass_paths("context").committed.read_bytes(), before)

    def test_form_corrected_after_the_sheet_was_built_requires_a_rebuild(self) -> None:
        rows = cp.load_committed(self.paths)
        rows = [dict(row, status="superseded") if row["item_id"] == self.dialogue else row for row in rows]
        rows.append(dict(next(row for row in rows if row["item_id"] == self.dialogue), form="L0", status=""))
        cp.write_committed(self.paths, cp.sort_rows(rows))
        self.fill_context()
        self.assertIn("rebuild the sheet", self.export_problems("context"))


class RevealPassTests(SealedCase):
    def setUp(self) -> None:
        super().setUp()
        self.seal_context()

    def fill_reveal(self, value: str | Callable[[dict], str] = "corroborates") -> None:
        self.fill_pass("reveal", lambda entry: {"future_dependence": value(entry) if callable(value) else value})

    def test_only_items_with_a_sealed_context_row_are_included(self) -> None:
        self.assertEqual(self.build("reveal"), 0)
        context = cp.live_rows(cp.load_committed(self.pass_paths("context")))
        entries = self.entries("reveal")
        self.assertEqual({entry["item_id"] for entry in entries}, set(context))
        for entry in entries:
            self.assertEqual(entry["prior_sha256"], cs.canonical_hash(context[entry["item_id"]]))
            self.assertTrue(cs.ROW_ID_RES["reveal"].fullmatch(entry["row_id"]))
        self.assertEqual(self.cli("sheet", "--pass", "reveal", "--batch", "pilot1", "--annotator", "A2"), 0)
        self.assertFalse(self.pass_paths("reveal", "A2").sheet.exists())

    def test_sheet_shows_the_continuation_and_the_sealed_reading(self) -> None:
        self.build("reveal")
        rows = {row["row_id"]: row for row in read_csv(self.pass_paths("reveal").sheet)}
        self.assertEqual(list(next(iter(rows.values()))), list(cp.SHEET_FIELDS["reveal"]))
        for entry in self.entries("reveal"):
            row = rows[entry["row_id"]]
            if entry["item_id"].startswith("lit-") and "night" in row["target"]:
                self.assertIn("fetch some sticks", row["continuation"])
                self.assertIn("MORAL: Cold owls hint; warm badgers act.", row["continuation"])
                self.assertEqual(row["reading"], 'request | give | "Give me warmth"')
            elif entry["item_id"].startswith("d:"):
                self.assertEqual(row["reading"], f'request | find_hotel | area={SLOT_VALUE} | "{PARAPHRASE}"')
                self.assertNotIn("[0]", row["continuation"])  # prior turns are not repeated

    def test_derived_flags_follow_the_t1_table(self) -> None:
        self.build("reveal")
        values = list(cs.FUTURE_DEPENDENCE)
        order = [entry["item_id"] for entry in self.entries("reveal")]
        self.fill_reveal(lambda entry: values[order.index(entry["item_id"]) % len(values)])
        self.assertEqual(self.export_pass("reveal"), 0)
        rows = cp.load_committed(self.pass_paths("reveal"))
        self.assertEqual({row["future_dependence"] for row in rows}, set(values))
        for row in rows:
            with self.subTest(value=row["future_dependence"]):
                self.assertEqual(row["confirmatory_eligible"], str(cs.confirmatory_eligible(row["future_dependence"])).lower())
                self.assertEqual(row["needs_adjudication"], str(cs.needs_adjudication(row["future_dependence"])).lower())

    def test_a_sheet_carrying_an_earlier_pass_column_is_rejected(self) -> None:
        self.build("reveal")
        paths = self.pass_paths("reveal")
        pristine = read_csv(paths.sheet)
        for column in ("function", "form"):
            rows = [dict(row) for row in pristine]
            for row in rows:
                row.update(future_dependence="none", **{column: "request"})
            write_csv(paths.sheet, (*cp.SHEET_FIELDS["reveal"], column), rows, excel=True)
            with self.subTest(column=column):
                self.assertIn(f"earlier-pass column(s) ['{column}']", self.export_problems("reveal"))
        self.assertFalse(paths.committed.exists())

    def test_missing_or_invalid_future_dependence(self) -> None:
        self.build("reveal")
        first, second = (entry["item_id"] for entry in self.entries("reveal")[:2])
        self.fill_reveal(lambda entry: {first: "", second: "maybe"}.get(entry["item_id"], "none"))
        problems = self.export_problems("reveal")
        self.assertIn(f"[{first}]: future_dependence is missing", problems)
        self.assertIn("'maybe'", problems)
