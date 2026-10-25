"""A tiny, internally consistent repository for the spec 008 freeze tests (invented IDs, no text).

Two test dialogues (PMUL9001 inspected before the freeze, PMUL9002 primary) and one dev dialogue.
The split audit, its summary, the context manifest summary and the ``auto-v2`` seal agree with the
files they describe, so ``compute_pins`` and ``require_test_audit`` pass until a test breaks them.
"""

from __future__ import annotations

import csv
import datetime
import hashlib
import io
import json
from pathlib import Path
from typing import Any

from src.data import freeze
from src.data import split_audit as sa
from tests.analysis_fixtures import Workspace, config_dict, config_toml, toml_value

COMMIT = "0123456789abcdef0123456789abcdef01234567"
INPUTS = Path("configs/freeze/freeze-v1.toml")
INSPECTED = "PMUL9001.json"
PRIMARY = "PMUL9002.json"
FREEZE_ON = datetime.date(2026, 11, 7)
TODAY = datetime.date(2026, 11, 8)

ENCODER_TOML = f"""[run]
name = "enc"
kind = "encoder"

[data]
train_condition = "full"

[encoder]
pretrained = "org/model"
revision = "{COMMIT}"
"""

TFIDF_TOML = """[run]
name = "tfidf"
kind = "tfidf"

[data]
train_condition = "full"

[tfidf]
use_context = true
"""


def inputs_toml(raw: dict[str, Any]) -> str:
    """Top-level scalars and arrays, then one [systems.<name>] table each."""
    lines = [f"{key} = {toml_value(value)}" for key, value in raw.items() if key != "systems"]
    for name, table in raw.get("systems", {}).items():
        lines.append(f"[systems.{name}]")
        lines.extend(f"{key} = {toml_value(value)}" for key, value in table.items())
    return "\n".join(lines) + "\n"


def registry_row(dialogue_id: str, inspected_on: str, phase: str = "pre_freeze") -> dict[str, str]:
    return {"dialogue_id": dialogue_id, "source": "manual", "reason": "viewed_text", "inspector": "A1",
            "inspected_on": inspected_on, "phase": phase, "registry_version": sa.REGISTRY_VERSION}


class FreezeRepo:
    """A fixture repository; ``build()`` writes a state that is ready to freeze."""

    def __init__(self) -> None:
        self.ws = Workspace()
        self.root = self.ws.root

    def cleanup(self) -> None:
        self.ws.cleanup()

    def write(self, relative: str | Path, text: str) -> Path:
        self.ws.write(Path(relative).as_posix(), text)
        return self.root / relative

    def build(self, *, draft: bool = False, rules_version: str = "auto-v1") -> FreezeRepo:
        self.write("data/sources.toml", "schema_version = 1\n")
        self.write("uv.lock", "version = 1\n")
        self.write("src/data/auto_levels.py", "RULES_VERSION = 'auto-v1'\n")
        self.write("src/data/auto_levels_v2.py", "RULES_VERSION = 'auto-v2'\n")
        self.write("src/tool.py", "VALUE = 1\n")
        self.seal_auto_v2()
        self.write_corpus()
        self.write_registry([registry_row(INSPECTED, "2026-10-01")])
        self.write_context_manifest("example_id\nPMUL9002_t1:direct\n")
        self.write_audit()
        self.write_analysis_config(draft=draft, rules_version=rules_version)
        self.write("configs/stage1/enc.toml", ENCODER_TOML)
        self.write("configs/stage1/tfidf.toml", TFIDF_TOML)
        self.write("prompts/llm.txt", "Classify the request.\n")
        self.write("prompts/pipe.txt", "Route, then interpret.\n")
        self.write_inputs()
        return self

    # ------------------------------------------------------------------ pieces

    def inputs_raw(self) -> dict[str, Any]:
        return {
            "version": freeze.INPUTS_VERSION,
            "analysis_config": "configs/analysis/analysis-v1.toml",
            "code": ["src/data/*.py", "src/tool.py"],
            "systems": {
                "enc": {"stage1": "configs/stage1/enc.toml", "seeds": [13, 42]},
                "tfidf": {"stage1": "configs/stage1/tfidf.toml", "seeds": [13]},
                "llm": {"files": ["prompts/llm.txt"], "seeds": [0], "llm_model": "model-2026-01-01"},
                "pipe": {"files": ["prompts/pipe.txt"], "seeds": [13]},
            },
        }

    def write_inputs(self, raw: dict[str, Any] | None = None) -> None:
        self.write(INPUTS, inputs_toml(self.inputs_raw() if raw is None else raw))

    def write_analysis_config(self, *, draft: bool = False, rules_version: str = "auto-v1") -> None:
        raw = config_dict(draft=draft)
        raw["rules_version"] = rules_version
        self.write("configs/analysis/analysis-v1.toml", "# the plan\n" + config_toml(raw))

    def seal_auto_v2(self) -> None:
        digest = hashlib.sha256()
        for module in freeze.AUTO_LEVEL_MODULES:
            digest.update((self.root / module).read_text(encoding="utf-8").encode("utf-8"))
        self.write(freeze.AUTO_V2_FREEZE, json.dumps({"rules_sha256": digest.hexdigest(), "rules_version": "auto-v2"}))

    def write_corpus(self) -> None:
        items = [{"item_id": "PMUL9001_t1", "dialogue_id": INSPECTED, "split": "test"},
                 {"item_id": "PMUL9002_t1", "dialogue_id": PRIMARY, "split": "test"},
                 {"item_id": "SNG9003_t1", "dialogue_id": "SNG9003.json", "split": "dev"}]
        self.ws.write_jsonl(sa.DEFAULT_ITEMS.as_posix(), items)
        self.ws.write_jsonl(sa.DEFAULT_DIALOGUES.as_posix(), [{"dialogue_id": i["dialogue_id"], "turns": []} for i in items])

    def write_registry(self, rows: list[dict[str, str]]) -> None:
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(sa.REGISTRY_FIELDS), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        (self.root / sa.DEFAULT_REGISTRY).parent.mkdir(parents=True, exist_ok=True)
        (self.root / sa.DEFAULT_REGISTRY).write_bytes(buffer.getvalue().encode("utf-8"))

    def write_context_manifest(self, text: str) -> None:
        path = self.write(sa.DEFAULT_CONTEXT_MANIFEST, text)
        summary = {"manifest_sha256": sa.file_sha256(path), "renderer_version": "render-v1", "budget_words": 350,
                   "built_at": "2026-10-15T00:00:00Z"}
        self.write(freeze.CONTEXT_SUMMARY, json.dumps(summary, sort_keys=True, indent=2) + "\n")

    def write_audit(self, *, post_scoring_dialogues: int = 0) -> None:
        """A valid spec 006 audit of the fixture test set against the current files."""
        rows = []
        for item_id, dialogue_id, exclusion in (("PMUL9001_t1", INSPECTED, "inspected:viewed_text"),
                                                ("PMUL9002_t1", PRIMARY, "")):
            for variant in ("direct", "indirect"):
                rows.append({"example_id": f"{item_id}:{variant}", "item_id": item_id, "dialogue_id": dialogue_id,
                             "variant": variant, "mismatch_set": "0", "primary": "0" if exclusion else "1",
                             "exclusion": exclusion, "dup_exact": "0", "donor_inspected": "0"})
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=sa.AUDIT_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        audit = self.root / sa.DEFAULT_AUDIT
        audit.write_bytes(buffer.getvalue().encode("utf-8"))
        index = sa.load_corpus_index(self.root / sa.DEFAULT_ITEMS)
        registry = sa.load_registry(self.root / sa.DEFAULT_REGISTRY, index.dialogue_split)
        summary: dict[str, Any] = {
            "schema_version": sa.AUDIT_SCHEMA_VERSION, "split": "test", "audit_sha256": sa.file_sha256(audit),
            "inputs": {"items_sha256": sa.file_sha256(self.root / sa.DEFAULT_ITEMS),
                       "dialogues_sha256": sa.file_sha256(self.root / sa.DEFAULT_DIALOGUES),
                       "registry_pre_freeze_sha256": sa.pre_freeze_sha256(registry),
                       "context_manifest_sha256": sa.file_sha256(self.root / sa.DEFAULT_CONTEXT_MANIFEST)},
            "primary": {"genuine": 2, "mismatch": 0},
            "dup_exact": {"overall": {"flagged": 0}},
            "disclosure": {"post_scoring_dialogues": post_scoring_dialogues},
        }
        summary["content_sha256"] = sa.audit_content_sha256(summary)
        self.write(sa.DEFAULT_AUDIT_SUMMARY, json.dumps(summary, sort_keys=True, indent=2) + "\n")

    # ------------------------------------------------------------------ helpers

    def inputs(self) -> freeze.FreezeInputs:
        return freeze.load_inputs(INPUTS, root=self.root)

    def state(self) -> freeze.PinState:
        return freeze.compute_pins(self.inputs(), self.root)

    def freeze(self, on: datetime.date = FREEZE_ON) -> dict[str, Any]:
        """Write the record as ``freeze write --on`` would, with a clean (fake) git tree."""
        return freeze.write_freeze(self.inputs(), self.root, on=on, today=TODAY, git=clean_git)


def clean_git(root: Path) -> dict[str, Any]:
    return {"git_commit": "a" * 40, "git_dirty": False}
