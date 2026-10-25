"""``compute_pins``: every key family, stable hashes and readiness findings (spec 008 T3)."""

from __future__ import annotations

import json
import unittest

from src.data import freeze
from src.data import split_audit as sa
from tests.freeze_fixtures import ENCODER_TOML, INSPECTED, PRIMARY, FreezeRepo, registry_row


class PinsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = FreezeRepo().build()
        self.addCleanup(self.repo.cleanup)

    def codes(self, state: freeze.PinState) -> dict[str, str]:
        return {f.key: f.code for f in state.findings}


class ReadyStateTest(PinsTestCase):
    def test_a_ready_repository_has_no_findings_and_every_key_family(self) -> None:
        state = self.repo.state()
        self.assertEqual(state.findings, [])
        families = {key.split(".")[0] for key in state.pins}
        self.assertEqual(families, {"data", "env", "membership", "labels", "code", "analysis", "recipe"})
        for key in ("data.items", "data.dialogues", "data.sources_toml", "env.uv_lock",
                    "membership.split_audit", "membership.split_audit_content", "membership.registry_pre_freeze",
                    "membership.context_manifest", "membership.renderer_version", "membership.budget_words",
                    "labels.rules_version", "analysis.config", "analysis.version",
                    "code.src/data/auto_levels.py", "code.src/tool.py",
                    "recipe.enc.stage1", "recipe.enc.revision", "recipe.enc.pretrained", "recipe.enc.seeds",
                    "recipe.tfidf.stage1", "recipe.llm.llm_model", "recipe.llm.file.prompts/llm.txt",
                    "recipe.pipe.file.prompts/pipe.txt"):
            self.assertIn(key, state.pins)
        self.assertEqual(state.pins["recipe.enc.seeds"], "13,42")
        self.assertEqual(state.pins["membership.primary"], "genuine=2;mismatch=0")

    def test_pins_reuse_the_existing_hashes(self) -> None:
        state = self.repo.state()
        summary = json.loads((self.repo.root / sa.DEFAULT_AUDIT_SUMMARY).read_text(encoding="utf-8"))
        self.assertEqual(state.pins["data.items"], summary["inputs"]["items_sha256"])
        self.assertEqual(state.pins["membership.registry_pre_freeze"], summary["inputs"]["registry_pre_freeze_sha256"])
        self.assertEqual(state.pins["membership.split_audit_content"], summary["content_sha256"])
        self.assertEqual(state.pins["analysis.config"],
                         freeze.load_analysis_config(self.repo.root / "configs/analysis/analysis-v1.toml").sha256)

    def test_pins_are_deterministic(self) -> None:
        self.assertEqual(self.repo.state().pins, self.repo.state().pins)


class StabilityTest(PinsTestCase):
    def test_crlf_and_lf_checkouts_pin_code_and_locks_identically(self) -> None:
        before = self.repo.state().pins
        for relative in ("src/tool.py", "uv.lock", "data/sources.toml", "prompts/llm.txt"):
            path = self.repo.root / relative
            path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        self.assertEqual(self.repo.state().pins, before)

    def test_a_code_edit_moves_only_its_pin(self) -> None:
        before = self.repo.state().pins
        self.repo.write("src/tool.py", "VALUE = 2\n")
        after = self.repo.state().pins
        self.assertEqual({k for k in before if before[k] != after.get(k)}, {"code.src/tool.py"})

    def test_post_scoring_registry_rows_do_not_move_the_pre_freeze_pin(self) -> None:
        before = self.repo.state().pins["membership.registry_pre_freeze"]
        self.repo.write_registry([registry_row(INSPECTED, "2026-10-01"),
                                  registry_row(PRIMARY, "2026-11-15", phase="post_scoring")])
        self.assertEqual(self.repo.state().pins["membership.registry_pre_freeze"], before)

    def test_a_new_pre_freeze_row_moves_it(self) -> None:
        before = self.repo.state().pins["membership.registry_pre_freeze"]
        self.repo.write_registry([registry_row(INSPECTED, "2026-10-01"), registry_row(PRIMARY, "2026-10-02")])
        self.assertNotEqual(self.repo.state().pins["membership.registry_pre_freeze"], before)

    def test_disclosure_growth_does_not_move_the_audit_content_pin(self) -> None:
        before = self.repo.state().pins["membership.split_audit_content"]
        self.repo.write_audit(post_scoring_dialogues=3)
        state = self.repo.state()
        self.assertEqual(state.findings, [])
        self.assertEqual(state.pins["membership.split_audit_content"], before)


class FindingsTest(PinsTestCase):
    def test_draft_config_is_missing_work(self) -> None:
        self.repo.write_analysis_config(draft=True)
        state = self.repo.state()
        self.assertIn(freeze.Finding("missing", "analysis_draft", "analysis.config",
                                     "set draft = false once the primary system is named"), state.findings)

    def test_branch_or_tag_revisions_are_unpinned(self) -> None:
        for revision in ("main", "v1.0", "0123456"):
            with self.subTest(revision=revision):
                self.repo.write("configs/stage1/enc.toml", ENCODER_TOML.replace(
                    "0123456789abcdef0123456789abcdef01234567", revision))
                self.assertEqual(self.codes(self.repo.state())["recipe.enc.revision"], "revision_unpinned")

    def test_floating_or_missing_llm_models(self) -> None:
        for model in ("", "model-latest", "Model-LATEST"):
            with self.subTest(model=model):
                raw = self.repo.inputs_raw()
                raw["systems"]["llm"]["llm_model"] = model
                self.repo.write_inputs(raw)
                self.assertEqual(self.codes(self.repo.state())["recipe.llm.llm_model"], "llm_model_floating")
        raw = self.repo.inputs_raw()
        del raw["systems"]["llm"]["llm_model"]
        self.repo.write_inputs(raw)
        self.assertEqual(self.codes(self.repo.state())["recipe.llm.llm_model"], "llm_model_missing")

    def test_systems_without_recipes(self) -> None:
        raw = self.repo.inputs_raw()
        raw["systems"]["pipe"] = {"files": [], "seeds": [13]}
        raw["systems"]["tfidf"] = {"files": ["prompts/llm.txt"], "seeds": [13]}
        self.repo.write_inputs(raw)
        codes = self.codes(self.repo.state())
        self.assertEqual(codes["recipe.pipe"], "recipe_missing")
        self.assertEqual(codes["recipe.tfidf.stage1"], "recipe_missing")

    def test_a_recipe_named_for_another_system(self) -> None:
        self.repo.write("configs/stage1/enc.toml", ENCODER_TOML.replace('name = "enc"', 'name = "other"'))
        self.assertEqual(self.codes(self.repo.state())["recipe.enc.stage1"], "recipe_name_mismatch")

    def test_an_invalid_recipe_is_a_problem_not_a_crash(self) -> None:
        self.repo.write("configs/stage1/enc.toml", "[run\n")
        self.assertEqual(self.codes(self.repo.state())["recipe.enc.stage1"], "invalid_recipe")

    def test_manifest_disagreements(self) -> None:
        self.repo.write(sa.DEFAULT_CONTEXT_MANIFEST, "example_id\nchanged\n")
        self.assertEqual(self.codes(self.repo.state())["membership.context_manifest"], "manifest_mismatch")

    def test_a_stale_or_edited_audit_summary(self) -> None:
        path = self.repo.root / sa.DEFAULT_AUDIT_SUMMARY
        summary = json.loads(path.read_text(encoding="utf-8"))
        summary["primary"]["genuine"] = 3
        path.write_text(json.dumps(summary), encoding="utf-8")
        self.assertEqual(self.codes(self.repo.state())["membership.split_audit_content"], "split_audit_stale")
        self.repo.write_audit()
        (self.repo.root / sa.DEFAULT_AUDIT).write_bytes(b"example_id\n")
        self.assertEqual(self.codes(self.repo.state())["membership.split_audit_content"], "split_audit_stale")

    def test_missing_generated_data_is_reported_missing(self) -> None:
        (self.repo.root / sa.DEFAULT_ITEMS).unlink()
        state = self.repo.state()
        self.assertEqual(self.codes(state)["data.items"], "file_missing")
        self.assertEqual(self.codes(state)["membership.registry_pre_freeze"], "file_missing")
        self.assertTrue(all(f.status == "missing" for f in state.findings if f.key.startswith("data.")))

    def test_an_invalid_registry_never_echoes_its_rows(self) -> None:
        self.repo.write_registry([registry_row("PMUL9876.json", "2026-10-01")])  # not in the corpus
        finding = next(f for f in self.repo.state().findings if f.key == "membership.registry_pre_freeze")
        self.assertEqual(finding.code, "registry_invalid")
        self.assertNotIn("9876", finding.detail)

    def test_an_invalid_analysis_config(self) -> None:
        self.repo.write("configs/analysis/analysis-v1.toml", "version = 'analysis-v1'\n")
        state = self.repo.state()
        self.assertEqual(self.codes(state)["analysis.config"], "analysis_config_invalid")
        self.assertNotIn("analysis.config", state.pins)

    def test_panel_mismatch(self) -> None:
        raw = self.repo.inputs_raw()
        raw["systems"]["extra"] = {"files": ["prompts/llm.txt"], "seeds": [1]}
        self.repo.write_inputs(raw)
        self.assertEqual(self.codes(self.repo.state())["analysis.panel"], "panel_mismatch")


class AutoV2Test(PinsTestCase):
    def test_auto_v2_pins_its_sealed_rules(self) -> None:
        self.repo.write_analysis_config(rules_version="auto-v2")
        state = self.repo.state()
        self.assertEqual(state.findings, [])
        self.assertEqual(state.pins["labels.rules_version"], "auto-v2")
        self.assertIn("labels.auto_v2_rules", state.pins)

    def test_auto_v2_source_that_moved_since_its_seal(self) -> None:
        self.repo.write_analysis_config(rules_version="auto-v2")
        self.repo.write("src/data/auto_levels_v2.py", "RULES_VERSION = 'auto-v2'\nCHANGED = True\n")
        self.assertEqual(self.codes(self.repo.state())["labels.auto_v2_rules"], "auto_v2_unfrozen")

    def test_auto_v1_has_no_auto_v2_pin(self) -> None:
        self.assertNotIn("labels.auto_v2_rules", self.repo.state().pins)


if __name__ == "__main__":
    unittest.main()
