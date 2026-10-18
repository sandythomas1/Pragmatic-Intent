"""Check the spec 004 context invariants and write the text-free common-set manifest.

Run from the repository root (Python 3.12, standard library only)::

    python -m src.data.context_manifest check --split test
    python -m src.data.context_manifest manifest --split test            # writes data/manifests/
    python -m src.data.context_manifest manifest --split test --verify   # rebuild, compare bytes

``check`` verifies, for every example of the Stage 1 genuine set (``turn_index > 0``), the
rules in ``RULES`` and exits 1 if any fails, naming the first example per rule. It never trusts
the renderer: expected turns are sliced straight from ``dialogues.jsonl``. ``donor_domains``
sees per-turn act domains only (``dialogues.jsonl`` has no belief states); the builder already
enforces the stricter acts-plus-belief rule, so a hit here is always a real violation.

``manifest`` writes ``contexts_<split>.csv`` (one row per genuine example: IDs, set membership,
donor, budget drops, cue flags, SHA-256 of the target and of each condition's input; no text)
and ``contexts_<split>_summary.json`` (provenance and counts). Both are UTF-8 with LF line
endings on every OS, so ``--verify`` gives the same answer on Windows, WSL and macOS. The test
manifest is committed as the freeze object; the dev manifest is regenerated.
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import io
import json
import logging
import os
import statistics
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import cached_property
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.data.audit_fact_drift import build_vocabulary
from src.data.contexts import (BUDGET_WORDS, BUDGETED_CONDITIONS, MISMATCH_CONDITIONS, RENDERER_VERSION, Rendered,
                               cue_flags, genuine, in_mismatch_set, input_sha256, render_all, target_sha256,
                               turn_words, word_count)
from src.data.direct_dataset import CONDITIONS, Item, Turn, load_dialogues, load_items
from src.stage1.data import Stage1Example, build_examples

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "context-manifest-v1"
POLICY = "direct_variants_v1"
DEFAULT_ITEMS = Path("data/interim/direct/items.jsonl")
DEFAULT_DIALOGUES = Path("data/interim/direct/dialogues.jsonl")
DEFAULT_OUT_DIR = Path("data/manifests")
RULES = ("target_identical", "no_future", "budget", "donor_split", "donor_distinct", "donor_window",
         "donor_domains")
GENUINE_CONDITIONS = tuple(c for c in CONDITIONS if c not in MISMATCH_CONDITIONS)
FIELDS = ("example_id", "item_id", "dialogue_id", "turn_index", "variant", "mismatch_set", "exclusion",
          "donor_dialogue_id", "full_dropped", "mismatched_dropped", "donor_cue", "donor_cue_one", "dropped_cue",
          "target_sha256", *(f"sha256_{c}" for c in CONDITIONS))

Renderer = Callable[[Item, str, dict[str, list[Turn]]], dict[str, Rendered | None]]


@dataclass(frozen=True)
class Corpus:
    items: list[Item]
    dialogues: dict[str, list[Turn]]
    turn_domains: dict[str, list[list[str]]]  # per dialogue, per turn: act domains

    @cached_property
    def dialogue_split(self) -> dict[str, str]:
        return {item["dialogue_id"]: item["split"] for item in self.items}


def load_corpus(items_path: Path, dialogues_path: Path) -> Corpus:
    with dialogues_path.open(encoding="utf-8") as handle:
        turn_domains = {record["dialogue_id"]: [turn.get("domains") or [] for turn in record["turns"]]
                        for record in map(json.loads, filter(str.strip, handle))}
    return Corpus(load_items(items_path), load_dialogues(dialogues_path), turn_domains)


# ------------------------------------------------------------------ check


def _donor_problem(item: Item, corpus: Corpus) -> tuple[str, str] | None:
    """(rule, detail) for the first donor rule the item breaks, or None."""
    mismatch = item["mismatch"]
    donor, t = mismatch["donor_dialogue_id"], item["turn_index"]
    if donor not in corpus.dialogues:
        return "donor_window", f"donor {donor} is not in dialogues.jsonl"
    if corpus.dialogue_split.get(donor) != item["split"]:
        return "donor_split", f"donor {donor} is in {corpus.dialogue_split.get(donor)}, item in {item['split']}"
    if donor == item["dialogue_id"]:
        return "donor_distinct", "donor is the target dialogue"
    window = corpus.dialogues[donor][mismatch["start"]: mismatch["start"] + mismatch["length"]]
    if mismatch["start"] != 0 or mismatch["length"] != t or len(window) != t or window[-1].speaker != "system":
        return "donor_window", f"start {mismatch['start']}, length {mismatch['length']}, turn_index {t}"
    shared = {d for domains in corpus.turn_domains[donor][:t] for d in domains} & set(item["active_domains"])
    if shared:
        return "donor_domains", f"donor shares {sorted(shared)}"
    return None


def _is_suffix(shown: Sequence[Turn], source: Sequence[Turn]) -> bool:
    return len(shown) <= len(source) and list(shown) == list(source[len(source) - len(shown):])


def _rendering_problems(example: Stage1Example, item: Item, rendered: dict[str, Rendered | None],
                        corpus: Corpus, budget: int) -> list[tuple[str, str]]:
    problems: list[tuple[str, str]] = []
    t = item["turn_index"]
    sources = {condition: corpus.dialogues[item["dialogue_id"]][:t] for condition in GENUINE_CONDITIONS}
    if in_mismatch_set(item):
        sources.update(dict.fromkeys(MISMATCH_CONDITIONS, corpus.dialogues[item["mismatch"]["donor_dialogue_id"]][:t]))
    for condition, result in rendered.items():
        if result is None:
            if condition in sources:
                problems.append(("no_future", f"{condition} is undefined"))
            continue
        if result.target != example.text:
            problems.append(("target_identical", f"{condition} target differs"))
        source = sources.get(condition)
        expected_length = {"none": 0, "one": 1, "mismatched_one": 1}.get(condition)
        if source is None or not _is_suffix(result.turns, source) or (
                expected_length is not None and len(result.turns) != expected_length):
            problems.append(("no_future", f"{condition} context is not the allowed prior window"))
            continue
        if condition in BUDGETED_CONDITIONS:
            size = word_count(result.context) + word_count(result.target)
            # Minimal: putting back the newest dropped turn would break the budget.
            minimal = result.dropped == 0 or size + turn_words(source[result.dropped - 1]) > budget
            if result.dropped != len(source) - len(result.turns) or not minimal or (size > budget and result.turns):
                problems.append(("budget", f"{condition}: {size} words, {result.dropped} dropped"))
    return problems


def check_split(examples: Sequence[Stage1Example], corpus: Corpus, budget: int = BUDGET_WORDS,
                renderer: Renderer | None = None) -> dict[str, Any]:
    """Count failures per rule over ``examples`` (the genuine set); never raises on a bad example."""
    by_id = {item["item_id"]: item for item in corpus.items}
    render_fn = renderer or (lambda item, target, dialogues: render_all(item, target, dialogues, budget))
    failures: collections.Counter[str] = collections.Counter()
    first: dict[str, str] = {}

    def fail(example: Stage1Example, rule: str, detail: str) -> None:
        failures[rule] += 1
        first.setdefault(rule, f"{example.example_id}: {detail}")

    for example in examples:
        item = by_id[example.item_id]
        if not genuine(item):
            fail(example, "no_future", "turn 0 is not in the genuine set")
            continue
        problem = _donor_problem(item, corpus) if in_mismatch_set(item) else None
        if problem:
            fail(example, *problem)
            if problem[0] == "donor_window" and item["mismatch"]["donor_dialogue_id"] not in corpus.dialogues:
                continue  # cannot render the mismatch conditions at all
        for rule, detail in _rendering_problems(example, item, render_fn(item, example.text, corpus.dialogues),
                                                corpus, budget):
            fail(example, rule, detail)
    return {"examples": len(examples), "rules": list(RULES),
            "failures": {rule: failures[rule] for rule in RULES}, "first": dict(sorted(first.items())),
            "donor_domain_check": "acts_only"}


# ------------------------------------------------------------------ manifest


def _length_stats(lengths: Sequence[int], budget: int) -> dict[str, Any]:
    ordered = sorted(lengths)
    return {"n": len(ordered), "mean": round(statistics.fmean(ordered), 1), "median": statistics.median(ordered),
            "p95": ordered[int(0.95 * (len(ordered) - 1))], "max": ordered[-1],
            "over_budget": sum(length > budget for length in ordered)}


def build_manifest(examples: Sequence[Stage1Example], corpus: Corpus,
                   budget: int = BUDGET_WORDS) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Rows (sorted by example_id) and the count part of the summary."""
    by_id = {item["item_id"]: item for item in corpus.items}
    vocab = build_vocabulary(corpus.items)
    rows: list[dict[str, Any]] = []
    lengths: dict[str, list[int]] = {condition: [] for condition in CONDITIONS}
    dropped = {condition: collections.Counter() for condition in BUDGETED_CONDITIONS}
    flags_count: collections.Counter[str] = collections.Counter()
    target_over = 0
    for example in sorted(examples, key=lambda e: e.example_id):
        item = by_id[example.item_id]
        rendered = render_all(item, example.text, corpus.dialogues, budget)
        defined = {condition: result for condition, result in rendered.items() if result is not None}
        if {result.target for result in defined.values()} != {example.text}:
            raise ValueError(f"{example.example_id}: target differs between conditions")
        flags = cue_flags(item, rendered, corpus.dialogues, vocab)
        for name in ("donor_cue", "donor_cue_one", "dropped_cue"):
            flags_count[name] += getattr(flags, name)
        target_over += word_count(example.text) > budget
        for condition, result in defined.items():
            lengths[condition].append(word_count(result.context) + word_count(result.target))
            if condition in dropped and result.dropped:
                dropped[condition]["examples"] += 1
                dropped[condition]["turns"] += result.dropped
        mismatch = in_mismatch_set(item)
        rows.append({
            "example_id": example.example_id, "item_id": example.item_id, "dialogue_id": example.dialogue_id,
            "turn_index": example.turn_index, "variant": example.variant, "mismatch_set": int(mismatch),
            "exclusion": "" if mismatch else "no_donor",
            "donor_dialogue_id": item["mismatch"]["donor_dialogue_id"] if mismatch else "",
            "full_dropped": defined["full"].dropped,
            "mismatched_dropped": defined["mismatched"].dropped if mismatch else "",
            "donor_cue": int(flags.donor_cue), "donor_cue_one": int(flags.donor_cue_one),
            "dropped_cue": int(flags.dropped_cue), "target_sha256": target_sha256(example.text),
            **{f"sha256_{c}": input_sha256(defined[c]) if c in defined else "" for c in CONDITIONS},
        })
    n_mismatch = sum(row["mismatch_set"] for row in rows)
    counts = {
        "genuine": len(rows), "mismatch": n_mismatch,
        "mismatch_excluded": {"no_donor": len(rows) - n_mismatch},
        "dropped": {c: {"examples": dropped[c]["examples"], "turns": dropped[c]["turns"]} for c in BUDGETED_CONDITIONS},
        "target_over_budget": target_over, "cue_flags": dict(sorted(flags_count.items())),
        "lengths_words": {c: _length_stats(lengths[c], budget) for c in CONDITIONS if lengths[c]},
    }
    return rows, counts


def manifest_bytes(rows: Sequence[dict[str, Any]]) -> bytes:
    """CSV bytes, UTF-8 without BOM, LF line endings regardless of OS."""
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def summary_record(split: str, csv_bytes: bytes, counts: dict[str, Any], policy_excluded: dict[str, int],
                   items_path: Path, dialogues_path: Path, built_at: str, budget: int) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION, "split": split, "renderer_version": RENDERER_VERSION,
        "budget_words": budget, "policy": POLICY, "built_at": built_at,
        "inputs": {"items_sha256": _sha256_file(items_path), "dialogues_sha256": _sha256_file(dialogues_path)},
        "manifest_file": f"contexts_{split}.csv", "manifest_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "donor_domain_check": "acts_only", "policy_excluded": policy_excluded, **counts,
    }


# ------------------------------------------------------------------ CLI


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.data.context_manifest", description=__doc__.split("\n")[0])
    parser.add_argument("command", choices=("check", "manifest"))
    parser.add_argument("--split", choices=("dev", "test"), required=True)
    parser.add_argument("--items", type=Path, default=DEFAULT_ITEMS)
    parser.add_argument("--dialogues", type=Path, default=DEFAULT_DIALOGUES)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--verify", action="store_true", help="manifest: rebuild and compare with the file on disk")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        corpus = load_corpus(args.items, args.dialogues)
        examples, policy_excluded = build_examples(corpus.items, args.split, POLICY, require_context=True)
        if args.command == "check":
            report = check_split(examples, corpus)
            logger.info("checked %d %s examples: %s", report["examples"], args.split, report["failures"])
            for rule, detail in report["first"].items():
                logger.error("%s failed, first at %s", rule, detail)
            return 1 if any(report["failures"].values()) else 0
        rows, counts = build_manifest(examples, corpus)
        data = manifest_bytes(rows)
        csv_path = args.out_dir / f"contexts_{args.split}.csv"
        if args.verify:
            if not csv_path.exists() or csv_path.read_bytes() != data:
                logger.error("%s does not match a fresh build from the pinned inputs", csv_path)
                return 1
            logger.info("%s matches a fresh build (%d rows)", csv_path, len(rows))
            return 0
        built_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        summary = summary_record(args.split, data, counts, policy_excluded, args.items, args.dialogues,
                                 built_at, BUDGET_WORDS)
        _write_atomic(csv_path, data)
        _write_atomic(args.out_dir / f"contexts_{args.split}_summary.json",
                      (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        logger.info("%s: %d genuine, %d mismatch, %s no donor, dropped %s, target over budget %d, cue flags %s",
                    args.split, counts["genuine"], counts["mismatch"], counts["mismatch_excluded"]["no_donor"],
                    counts["dropped"], counts["target_over_budget"], counts["cue_flags"])
        logger.info("wrote %s and its summary", csv_path)
        return 0
    except (OSError, ValueError, KeyError) as exc:
        logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
