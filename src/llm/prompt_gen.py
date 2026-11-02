"""P2 few-shot examples: a seeded draw of train IDs and a byte-deterministic renderer (spec 009 T3, FR9, FR18).

``draw`` picks ``k`` train examples per route label and commits only their IDs, the seed and the
hashes of the source files. ``render`` rebuilds each example's text from the pinned, git-ignored
data and writes the filled P2 prompt under git-ignored ``outputs/``. Corpus text never enters a
committed file.

An example is usable when it is a DIRECT ``train`` paraphrase with prior context, labelled
``direct`` or ``indirect``, and its spec 005 reference (``acts-v1``) has a request category and no
conflicting values. Its answer must also parse under the T1 schema. ``no_request`` turns are not
drawn: the schema needs a request category, and a thanks/bye turn has none to show, so any
category would be invented. P1's instructions define that label in words instead.

Each example is shown under the ``full`` condition, using the shared ``render-v1`` renderer and
T2's data block, so its text is framed as data just as live inputs are.

    python -m src.llm.prompt_gen draw   [--out configs/llm/prompts/p2_examples.json]
    python -m src.llm.prompt_gen render [--out outputs/llm/prompts/p2.txt]

The draw uses CPython's ``random.Random(seed)``; the committed ID list, not a rerun, is the
record. Neither command prints corpus text or example IDs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.data.contexts import RENDERER_VERSION, render
from src.data.direct_dataset import Item, Turn, load_dialogues, load_items
from src.data.intent_categories import DEFAULT_ITEMS
from src.evaluation.interpretation import REFERENCE_VERSION, reference
from src.llm.prompt import fill, load_template, main_block
from src.llm.schema import REQUEST_CATEGORIES, MainAnswer, load_slot_keys, parse_main
from src.stage1.data import POLICIES, Stage1Example, build_examples

EXAMPLES_VERSION = "p2-examples-v1"
SEED = 20261102
K_PER_LABEL = 3
EXAMPLE_LABELS = ("direct", "indirect")
EXAMPLE_CONDITION = "full"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIALOGUES = Path("data/interim/direct/dialogues.jsonl")
DEFAULT_SLOT_KEYS = Path("configs/llm/slot_keys.json")
DEFAULT_EXAMPLES = Path("configs/llm/prompts/p2_examples.json")
DEFAULT_TEMPLATE = Path("configs/llm/prompts/p2.template.txt")
DEFAULT_OUT = Path("outputs/llm/prompts/p2.txt")
MAX_LIST_BYTES = 64_000
MAX_K_PER_LABEL = 20
_FIELDS = frozenset({"version", "split", "policy", "condition", "reference_version", "renderer_version",
                     "seed", "k_per_label", "labels", "items_sha256", "dialogues_sha256", "example_ids"})
_EXAMPLE_ID = re.compile(r"[A-Za-z0-9_]{1,64}:(?:direct|indirect)\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class Sources:
    """The pinned, git-ignored inputs and the hashes of their bytes."""

    items: list[Item]
    dialogues: dict[str, list[Turn]]
    items_sha256: str
    dialogues_sha256: str


def load_sources(items_path: Path, dialogues_path: Path) -> Sources:
    return Sources(load_items(items_path), load_dialogues(dialogues_path),
                   _file_sha256(items_path), _file_sha256(dialogues_path))


def example_text(example: Stage1Example, item: Item, dialogues: dict[str, list[Turn]],
                 slot_keys: Collection[str]) -> str | None:
    """One worked example (data block, then the reference answer), or None when unusable."""
    if example.label not in EXAMPLE_LABELS:
        return None
    gold = reference(item)
    if gold.exclusion is not None or gold.category not in REQUEST_CATEGORIES:
        return None
    rendered = render(item, example.text, dialogues, EXAMPLE_CONDITION)
    if rendered is None or not rendered.context.strip():
        return None
    answer = {"route": example.label, "category": gold.category,
              "slots": [{"slot": key, "value": value} for key, value in sorted(gold.slots.items())],
              "requested_slots": sorted(gold.requested_slots)}
    raw = json.dumps(answer, ensure_ascii=False, sort_keys=True)
    if not isinstance(parse_main(raw, "stop", slot_keys), MainAnswer):
        return None
    text = f"{main_block({'context': rendered.context, 'target': rendered.target})}\nAnswer:\n{raw}"
    return None if "{{" in text or "}}" in text else text


def draw(sources: Sources, slot_keys: Collection[str], *, seed: int = SEED,
         k_per_label: int = K_PER_LABEL) -> list[str]:
    """Seeded draw of usable train examples, ``k_per_label`` per label, at most one per dialogue
    within a label, interleaved by label (direct, indirect, direct, ...)."""
    if not 1 <= k_per_label <= MAX_K_PER_LABEL:
        raise ValueError(f"k_per_label must be between 1 and {MAX_K_PER_LABEL}")
    examples, _ = build_examples(sources.items, "train")
    by_item = {item["item_id"]: item for item in sources.items}
    rng = random.Random(seed)
    picked: dict[str, list[str]] = {}
    for label in EXAMPLE_LABELS:
        candidates = sorted((e for e in examples if e.label == label), key=lambda e: e.example_id)
        rng.shuffle(candidates)
        chosen: list[str] = []
        dialogues_used: set[str] = set()
        for example in candidates:
            if len(chosen) == k_per_label:
                break
            if example.dialogue_id in dialogues_used:
                continue
            if example_text(example, by_item[example.item_id], sources.dialogues, slot_keys) is not None:
                chosen.append(example.example_id)
                dialogues_used.add(example.dialogue_id)
        if len(chosen) < k_per_label:
            raise ValueError(f"only {len(chosen)} usable train '{label}' examples; "
                             "drop P2 and keep P1 as the only variant (FR9 fallback)")
        picked[label] = chosen
    return [picked[label][n] for n in range(k_per_label) for label in EXAMPLE_LABELS]


def examples_document(example_ids: Sequence[str], sources: Sources, *, seed: int, k_per_label: int) -> dict[str, Any]:
    """The committed ID list: IDs, seed, versions and source hashes; no corpus text."""
    document = {"version": EXAMPLES_VERSION, "split": "train", "policy": POLICIES[0],
                "condition": EXAMPLE_CONDITION, "reference_version": REFERENCE_VERSION,
                "renderer_version": RENDERER_VERSION, "seed": seed, "k_per_label": k_per_label,
                "labels": list(EXAMPLE_LABELS), "items_sha256": sources.items_sha256,
                "dialogues_sha256": sources.dialogues_sha256, "example_ids": list(example_ids)}
    validate_examples(document)
    return document


def load_examples(path: Path) -> dict[str, Any]:
    """Read and strictly validate a committed ID list."""
    with path.open("rb") as handle:
        raw = handle.read(MAX_LIST_BYTES + 1)
    if len(raw) > MAX_LIST_BYTES:
        raise ValueError("example list file is too large")
    document = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    validate_examples(document)
    return document


def validate_examples(document: Any) -> None:
    if not isinstance(document, dict) or set(document) != _FIELDS:
        raise ValueError("example list: unknown or missing fields")
    expected = {"version": EXAMPLES_VERSION, "split": "train", "policy": POLICIES[0],
                "condition": EXAMPLE_CONDITION, "reference_version": REFERENCE_VERSION,
                "renderer_version": RENDERER_VERSION, "labels": list(EXAMPLE_LABELS)}
    if any(document[name] != value for name, value in expected.items()):
        raise ValueError("example list: unsupported version, split, policy, condition or labels")
    for name in ("seed", "k_per_label"):
        if type(document[name]) is not int or document[name] < 0:
            raise ValueError(f"example list: {name} must be a non-negative integer")
    if not 1 <= document["k_per_label"] <= MAX_K_PER_LABEL:
        raise ValueError("example list: k_per_label out of range")
    for name in ("items_sha256", "dialogues_sha256"):
        if not isinstance(document[name], str) or not _SHA256.fullmatch(document[name]):
            raise ValueError(f"example list: {name} must be a lowercase SHA-256")
    ids = document["example_ids"]
    if not isinstance(ids, list) or len(ids) != document["k_per_label"] * len(EXAMPLE_LABELS):
        raise ValueError("example list: example_ids must hold k_per_label IDs per label")
    if any(not isinstance(example_id, str) or not _EXAMPLE_ID.fullmatch(example_id) for example_id in ids):
        raise ValueError("example list: malformed example ID")
    if len(set(ids)) != len(ids):
        raise ValueError("example list: duplicate example ID")
    labels = [example_id.rsplit(":", 1)[1] for example_id in ids]
    if labels != [label for _ in range(document["k_per_label"]) for label in EXAMPLE_LABELS]:
        raise ValueError("example list: IDs must interleave the labels in order")


def render_examples(document: dict[str, Any], sources: Sources, slot_keys: Collection[str]) -> str:
    """The examples text for ``{{examples}}``; refuses changed sources and any non-train ID."""
    validate_examples(document)
    if (document["items_sha256"], document["dialogues_sha256"]) != (sources.items_sha256, sources.dialogues_sha256):
        raise ValueError("source files differ from the hashes in the example list; redraw or restore the pinned data")
    examples, _ = build_examples(sources.items, "train")
    train = {example.example_id: example for example in examples}
    by_item = {item["item_id"]: item for item in sources.items}
    blocks = []
    for number, example_id in enumerate(document["example_ids"], 1):
        example = train.get(example_id)
        if example is None:  # never echo the ID: it may name a dev or test example
            raise ValueError(f"example {number} is not a usable train example")
        text = example_text(example, by_item[example.item_id], sources.dialogues, slot_keys)
        if text is None:
            raise ValueError(f"example {number} no longer yields a valid worked example")
        blocks.append(f"Example {number}\n{text}")
    return "\n\n".join(blocks)


def render_prompt(template_path: Path, examples_text: str) -> str:
    """P2 with its examples filled; ``{{slot_keys}}`` stays for ``main_instructions``."""
    return fill(load_template(template_path), {"examples": examples_text})


def write_prompt(text: str, out: Path, root: Path = REPO_ROOT) -> str:
    """Write under ``root/outputs/`` only (git-ignored), with ``\\n`` line ends; return its SHA-256."""
    target = out if out.is_absolute() else root / out
    if not target.resolve().is_relative_to((root / "outputs").resolve()):
        raise ValueError("the rendered prompt holds corpus text and must be written under git-ignored outputs/")
    data = text.encode("utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate JSON key")
    return dict(pairs)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("draw", "render"))
    parser.add_argument("--items", type=Path, default=DEFAULT_ITEMS)
    parser.add_argument("--dialogues", type=Path, default=DEFAULT_DIALOGUES)
    parser.add_argument("--slot-keys", type=Path, default=DEFAULT_SLOT_KEYS)
    parser.add_argument("--examples", type=Path, default=DEFAULT_EXAMPLES, help="ID list (draw writes it)")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="render: the P2 prompt, under outputs/")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--k-per-label", type=int, default=K_PER_LABEL)
    args = parser.parse_args(argv)
    try:
        slot_keys = frozenset(load_slot_keys(args.slot_keys))
        sources = load_sources(args.items, args.dialogues)
        if args.command == "draw":
            ids = draw(sources, slot_keys, seed=args.seed, k_per_label=args.k_per_label)
            document = examples_document(ids, sources, seed=args.seed, k_per_label=args.k_per_label)
            args.examples.parent.mkdir(parents=True, exist_ok=True)
            args.examples.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n",
                                     encoding="utf-8", newline="\n")
            print(f"P2 draw: {len(ids)} train examples ({args.k_per_label} per label) -> {args.examples}")
        else:
            document = load_examples(args.examples)
            text = render_prompt(args.template, render_examples(document, sources, slot_keys))
            digest = write_prompt(text, args.out)
            print(f"P2 render: {len(document['example_ids'])} examples, {len(text.split())} words, "
                  f"sha256 {digest} -> {args.out}")
        return 0
    except (OSError, ValueError, TypeError, KeyError, UnicodeDecodeError) as error:
        print(f"P2 {args.command} failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
