"""Analysis config (spec 007 T1): strict validation, canonical hash and the committed default."""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import tomllib
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.analysis.config import (
    DEFAULT_CONFIG,
    MAX_CONFIG_BYTES,
    AnalysisConfigError,
    load_config,
    parse_config,
)

BASE = """
version = "analysis-v1"
rules_version = "auto-v1"
draft = true
alpha = 0.05

[bootstrap]
samples = 200
seed = 7
confidence = 0.95

[cells]
min_dialogues = 30
max_excluded_share = 0.01

[primary]
system = "pipe"
endpoint = "request_interpretation"
contrast = "full_minus_none"
trend = "linear"
levels = ["L0", "L1", "L2"]

[exploratory]
levels = ["L3", "INF"]

[error_audit]
levels = ["L0", "L1", "L2", "L3"]
per_level = 15
seed = 7

[[panel]]
name = "enc"
family = "encoder"
design = "matched"
streams = ["stage1"]

[[panel]]
name = "pipe"
family = "hybrid"
design = "matched"
streams = ["routed", "oracle"]

[[family]]
name = "h1"
kind = "h1_trend"
system = "pipe"
endpoint = "request_interpretation"
condition = "none"

[[family]]
name = "h3-enc"
kind = "h3_difference"
system = "enc"
reference = "pipe"
endpoint = "stage1_correct"
contrast = "full_minus_none"
"""

# Same content as BASE: keys and tables reordered, comments added, spacing and number forms changed.
REFORMATTED = """
# a comment that must not move the hash
draft=true
alpha = 5e-2
rules_version = 'auto-v1'
version = "analysis-v1"

[[family]]
kind = "h1_trend"
condition = "none"   # trailing comment
endpoint = "request_interpretation"
system = "pipe"
name = "h1"

[[family]]
contrast = "full_minus_none"
endpoint = "stage1_correct"
reference = "pipe"
system = "enc"
kind = "h3_difference"
name = "h3-enc"

[primary]
levels = [ "L0",
           "L1",
           "L2" ]
trend = "linear"
contrast = "full_minus_none"
endpoint = "request_interpretation"
system = "pipe"

[cells]
max_excluded_share = 1e-2
min_dialogues = 30

[bootstrap]
confidence = 9.5e-1
seed = 7
samples = 200

[exploratory]
levels = ["L3", "INF"]

[error_audit]
seed = 7
per_level = 15
levels = ["L0", "L1", "L2", "L3"]

[[panel]]
streams = ["stage1"]
design = "matched"
family = "encoder"
name = "enc"

[[panel]]
streams = ["routed", "oracle"]
design = "matched"
family = "hybrid"
name = "pipe"
"""


def base() -> dict[str, Any]:
    return tomllib.loads(BASE)


def edited(change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    raw = copy.deepcopy(base())
    change(raw)
    return raw


def add_member(**fields: Any) -> Callable[[dict[str, Any]], None]:
    return lambda raw: raw["family"].append(fields)


class TempFiles(unittest.TestCase):
    def write(self, data: str | bytes) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "analysis.toml"
        if isinstance(data, str):
            path.write_text(data, encoding="utf-8")
        else:
            path.write_bytes(data)
        return path


class ValidationTest(unittest.TestCase):
    def test_base_fixture_is_valid(self) -> None:
        config = parse_config(base())
        self.assertEqual(config.primary.weights, (-1, 0, 1))
        self.assertEqual([m.name for m in config.family], ["h1", "h3-enc"])
        self.assertTrue(config.system("pipe").provides("request_interpretation"))
        self.assertTrue(config.system("pipe").provides("stage1_correct"))
        self.assertFalse(config.system("enc").provides("request_interpretation"))
        with self.assertRaises(KeyError):
            config.system("absent")

    def test_each_invalid_plan_fails_with_its_named_error(self) -> None:
        h2_primary = dict(name="dup-primary", kind="h2_trend", system="pipe",
                          endpoint="request_interpretation", contrast="full_minus_none")
        cases: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
            # AC-007-1 / FR2
            "unknown top-level key": ("unknown_key", lambda r: r.update(extra=1)),
            "unknown key in a table": ("unknown_key", lambda r: r["primary"].update(weights=[-1, 0, 1])),
            "unknown key in a member": ("unknown_key", lambda r: r["family"][0].update(contrast="full_minus_none")),
            "missing key": ("missing_key", lambda r: r["cells"].pop("min_dialogues")),
            "unknown level": ("unknown_level", lambda r: r["exploratory"].update(levels=["L4"])),
            "NR is not an analysis level": ("unknown_level", lambda r: r["exploratory"].update(levels=["NR"])),
            "unknown endpoint": ("unknown_endpoint", lambda r: r["primary"].update(endpoint="end_to_end")),
            "unknown contrast": ("unknown_contrast", lambda r: r["primary"].update(contrast="full_vs_none")),
            "primary on a mismatch contrast": ("wrong_contrast_kind",
                                               lambda r: r["primary"].update(contrast="full_minus_mismatched")),
            "unknown trend": ("unknown_trend", lambda r: r["primary"].update(trend="cubic")),
            "primary outside the panel": ("system_outside_panel", lambda r: r["primary"].update(system="gpt")),
            "member outside the panel": ("system_outside_panel", lambda r: r["family"][1].update(system="gpt")),
            "reference outside the panel": ("system_outside_panel", lambda r: r["family"][1].update(reference="gpt")),
            "primary without Stage 2 streams": ("missing_streams", lambda r: r["primary"].update(system="enc")),
            "primary without oracle": ("missing_streams", lambda r: r["panel"][1].update(streams=["routed"])),
            "member without its endpoint's streams": ("missing_streams",
                                                      lambda r: r["family"][1].update(endpoint="type_exact")),
            "h4 without Stage 2 streams": ("missing_streams", add_member(name="h4", kind="h4_contrast", system="enc")),
            "empty member": ("empty_member", add_member()),
            "member without kind": ("missing_key", add_member(name="x", system="pipe")),
            "unknown member kind": ("unknown_kind", add_member(name="x", kind="h6", system="pipe")),
            "empty family": ("empty_family", lambda r: r.update(family=[])),
            "duplicate member name": ("duplicate_member", lambda r: r["family"][1].update(name="h1")),
            "duplicate member test": ("duplicate_member",
                                      lambda r: r["family"].append({**r["family"][0], "name": "h1-again"})),
            "primary test inside the family": ("primary_in_family", add_member(**h2_primary)),
            "zero bootstrap samples": ("non_positive", lambda r: r["bootstrap"].update(samples=0)),
            "negative bootstrap samples": ("non_positive", lambda r: r["bootstrap"].update(samples=-5)),
            "zero minimum cell": ("non_positive", lambda r: r["cells"].update(min_dialogues=0)),
            "zero audit quota": ("non_positive", lambda r: r["error_audit"].update(per_level=0)),
            "negative seed": ("out_of_range", lambda r: r["bootstrap"].update(seed=-1)),
            # Type strictness: no coercion of a hand-edited file.
            "boolean sample count": ("wrong_type", lambda r: r["bootstrap"].update(samples=True)),
            "float sample count": ("wrong_type", lambda r: r["bootstrap"].update(samples=1e4)),
            "string draft flag": ("wrong_type", lambda r: r.update(draft="false")),
            "integer confidence": ("wrong_type", lambda r: r["bootstrap"].update(confidence=1)),
            "table as panel": ("wrong_type", lambda r: r.update(panel={"name": "enc"})),
            "confidence out of range": ("out_of_range", lambda r: r["bootstrap"].update(confidence=1.5)),
            "nan alpha": ("out_of_range", lambda r: r.update(alpha=float("nan"))),
            "alpha disagrees with the interval": ("alpha_confidence_mismatch", lambda r: r.update(alpha=0.01)),
            # Levels: order carries the sign of a trend.
            "reversed primary levels": ("level_order", lambda r: r["primary"].update(levels=["L2", "L1", "L0"])),
            "duplicate level": ("duplicate_level", lambda r: r["primary"].update(levels=["L0", "L0", "L1"])),
            "empty levels": ("empty_levels", lambda r: r["exploratory"].update(levels=[])),
            "two-level linear trend": ("primary_levels_count", lambda r: r["primary"].update(levels=["L0", "L2"])),
            "level both primary and exploratory": ("overlapping_levels",
                                                   lambda r: r["exploratory"].update(levels=["L2", "L3"])),
            # Panel.
            "empty panel": ("empty_panel", lambda r: r.update(panel=[])),
            "duplicate system": ("duplicate_system", lambda r: r["panel"].append(dict(r["panel"][0]))),
            "bad system name": ("bad_name", lambda r: r["panel"][0].update(name="../enc")),
            "unknown family": ("unknown_family", lambda r: r["panel"][0].update(family="svm")),
            "unknown design": ("unknown_design", lambda r: r["panel"][0].update(design="both")),
            "unknown stream": ("unknown_stream", lambda r: r["panel"][0].update(streams=["judge"])),
            "no streams": ("empty_streams", lambda r: r["panel"][0].update(streams=[])),
            "duplicate stream": ("duplicate_stream", lambda r: r["panel"][0].update(streams=["stage1", "stage1"])),
            "matched llm": ("design_not_allowed", lambda r: r["panel"][1].update(family="llm")),
            # Member semantics.
            "h3 against a non-primary system": ("h3_reference", lambda r: r["family"][1].update(reference="enc")),
            "mismatch control on a genuine contrast": (
                "wrong_contrast_kind", add_member(name="mm", kind="mismatch_control", system="pipe",
                                                  endpoint="request_interpretation", contrast="full_minus_none")),
            "h1 under a mismatch condition": ("unknown_condition",
                                              lambda r: r["family"][0].update(condition="mismatched")),
            "unknown config version": ("unknown_version", lambda r: r.update(version="analysis-v2")),
            "unknown rules version": ("unknown_rules_version", lambda r: r.update(rules_version="auto-v9")),
        }
        for name, (code, change) in cases.items():
            with self.subTest(name), self.assertRaises(AnalysisConfigError) as caught:
                parse_config(edited(change))
            self.assertEqual(caught.exception.code, code, name)

    def test_h2_trend_on_another_endpoint_is_not_the_primary_test(self) -> None:
        raw = edited(add_member(name="h2-detection", kind="h2_trend", system="pipe",
                                endpoint="stage1_correct", contrast="full_minus_none"))
        self.assertEqual(parse_config(raw).family[-1].endpoint, "stage1_correct")

    def test_stage1_correct_primary_is_allowed_for_a_stage1_system(self) -> None:
        # The open fallback: a detection-only confirmatory test for a named encoder.
        raw = edited(lambda r: r["primary"].update(system="enc", endpoint="stage1_correct"))
        raw["family"] = [dict(name="h1", kind="h1_trend", system="enc", endpoint="stage1_correct", condition="none")]
        self.assertEqual(parse_config(raw).primary.system, "enc")

    def test_error_names_the_problem_without_echoing_unbounded_input(self) -> None:
        with self.assertRaises(AnalysisConfigError) as caught:
            parse_config(edited(lambda r: r["panel"][0].update(name="x" * 500)))
        self.assertLess(len(str(caught.exception)), 200)


class HashTest(TempFiles):
    def test_formatting_comments_and_key_order_leave_the_hash_unchanged(self) -> None:
        self.assertEqual(load_config(self.write(BASE)).sha256, load_config(self.write(REFORMATTED)).sha256)

    def test_any_value_change_moves_the_hash(self) -> None:
        reference = load_config(self.write(BASE)).sha256
        changes = {
            "draft": BASE.replace("draft = true", "draft = false"),
            "seed": BASE.replace("seed = 7\nconfidence", "seed = 8\nconfidence"),
            "samples": BASE.replace("samples = 200", "samples = 201"),
            "minimum cell": BASE.replace("min_dialogues = 30", "min_dialogues = 31"),
            "member condition": BASE.replace('condition = "none"', 'condition = "full"'),
            "system name": BASE.replace('name = "enc"', 'name = "enc2"').replace('system = "enc"', 'system = "enc2"'),
        }
        for name, text in changes.items():
            with self.subTest(name):
                self.assertNotEqual(load_config(self.write(text)).sha256, reference)

    def test_hash_is_reproducible_with_tomllib_and_json_alone(self) -> None:
        # The freeze writer (spec 008) or a reader of the paper can recompute it independently.
        canonical = json.dumps(tomllib.loads(BASE), sort_keys=True, separators=(",", ":"))
        self.assertEqual(load_config(self.write(BASE)).sha256, hashlib.sha256(canonical.encode()).hexdigest())

    def test_loading_twice_gives_the_same_hash(self) -> None:
        path = self.write(BASE)
        self.assertEqual(load_config(path).sha256, load_config(path).sha256)


class LoadTest(TempFiles):
    def test_file_level_failures_are_named(self) -> None:
        cases = [
            ("syntax error", "invalid_toml", self.write("version = \n")),
            ("not UTF-8", "invalid_toml", self.write(b"version = \"\xff\"\n")),
            ("nesting that exhausts the parser's stack", "invalid_toml", self.write("a = " + "[" * 50_000)),
            ("oversized", "file_too_large", self.write("#" * (MAX_CONFIG_BYTES + 1))),
        ]
        for name, code, path in cases:
            with self.subTest(name), self.assertRaises(AnalysisConfigError) as caught:
                load_config(path)
            self.assertEqual(caught.exception.code, code)

    def test_missing_path_and_directory_are_not_files(self) -> None:
        directory = self.write(BASE).parent
        for path in (directory / "absent.toml", directory):
            with self.subTest(str(path.name)), self.assertRaises(AnalysisConfigError) as caught:
                load_config(path)
            self.assertEqual(caught.exception.code, "not_a_file")


class DefaultConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config(Path(__file__).resolve().parents[1] / DEFAULT_CONFIG)

    def test_default_loads_as_a_draft(self) -> None:
        self.assertTrue(self.config.draft)
        self.assertEqual(self.config.rules_version, "auto-v1")

    def test_default_encodes_the_2026_10_20_decisions(self) -> None:
        primary = self.config.primary
        self.assertEqual((primary.endpoint, primary.contrast, primary.trend, primary.levels),
                         ("request_interpretation", "full_minus_none", "linear", ("L0", "L1", "L2")))
        self.assertEqual(primary.weights, (-1, 0, 1))
        self.assertEqual(self.config.exploratory_levels, ("L3", "INF"))
        self.assertEqual((self.config.alpha, self.config.bootstrap.samples, self.config.cells.min_dialogues),
                         (0.05, 10000, 30))
        self.assertEqual((self.config.error_audit.levels, self.config.error_audit.per_level),
                         (("L0", "L1", "L2", "L3"), 15))

    def test_default_family_matches_fr4(self) -> None:
        primary = self.config.primary.system
        kinds = [m.kind for m in self.config.family]
        for kind in ("h1_trend", "h2_trend", "h4_contrast", "mismatch_control"):
            self.assertEqual(kinds.count(kind), 1, kind)
        detection = next(m for m in self.config.family if m.kind == "h2_trend")
        self.assertEqual((detection.system, detection.endpoint), (primary, "stage1_correct"))
        h3_systems = {m.system for m in self.config.family if m.kind == "h3_difference"}
        self.assertEqual(h3_systems, {s.name for s in self.config.panel} - {primary})
        self.assertTrue(all(m.reference == primary for m in self.config.family if m.kind == "h3_difference"))

    def test_default_panel_names_todays_systems_and_placeholders(self) -> None:
        names = {s.name for s in self.config.panel}
        self.assertTrue({"tfidf-utterance", "tfidf-context", "deberta-v3-large", "roberta-large",
                         "llm", "hybrid"} <= names)
        self.assertEqual(self.config.system("llm").design, "test_time")


if __name__ == "__main__":
    unittest.main()
