"""Join DIRECT paraphrase triples to their MultiWOZ 2.1 dialogues and write a compact dataset.

Run from the repository root (Python 3.11+, standard library only)::

    python -m src.data.build_direct_dataset                      # defaults below
    python -m src.data.build_direct_dataset --seed 7 --out-dir data/interim/direct

Inputs (fetch them with ``python -m src.data.download_sources --only direct multiwoz``):
``data/raw/direct/{train,test}.csv`` and ``data/raw/multiwoz/MultiWOZ_2.1/``.

Outputs in ``data/interim/direct/`` (git-ignored, because DIRECT text can't be
redistributed):

* ``dialogues.jsonl``: each referenced MultiWOZ dialogue once (speaker, stripped
  text, and the domains from each turn's own dialogue acts).
* ``items.jsonl``: one record per DIRECT row with its three utterances, split,
  domains, user dialogue acts, DIRECT's quality labels (test rows), and the
  seeded mismatch pairing. Contexts are *not* stored;
  ``src.data.direct_dataset.build_context`` derives them.
* ``build_info.json``: input checksums, seed, join and split counts, and summary
  statistics. It has no timestamps, so identical inputs give identical bytes.

Rules:

* **Join:** DIRECT's ``turn_index`` indexes MultiWOZ's full turn list (user and
  system), so it must be even (a user turn). The target must equal the turn text
  exactly, after stripping outer whitespace, or after also collapsing inner
  whitespace and case. Anything else is rejected and counted.
* **Splits:** DIRECT test is MultiWOZ test. DIRECT train rows whose dialogue is in
  MultiWOZ's official ``valListFile.txt`` become ``dev``, so splits are grouped by
  dialogue by construction. A dialogue in more than one split is a fatal error.
* **Mismatch:** for a target at ``turn_index = t > 0``, the donor is a different
  dialogue in the same split whose first ``t`` turns (which end on a system turn)
  share no active domain with the target. The target's active domains are those
  in its history, the target turn, and the system reply that follows (its belief
  state records the target turn). Domains come from dialogue acts and belief
  states. The donor is drawn with ``random.Random(f"{seed}:{item_id}")`` from the
  sorted candidates, so pairing is deterministic.
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import logging
import random
import re
import statistics
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.data.direct_dataset import Item, Turn, build_context, is_social_only

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIRECT_DIR = REPO_ROOT / "data" / "raw" / "direct"
DEFAULT_MULTIWOZ_DIR = REPO_ROOT / "data" / "raw" / "multiwoz" / "MultiWOZ_2.1"
DEFAULT_OUT_DIR = REPO_ROOT / "data" / "interim" / "direct"
DEFAULT_SEED = 20260925
LONG_CONTEXT_TOKENS = 400  # whitespace tokens; leaves headroom under a 512-subword encoder limit

DOMAINS = ("attraction", "hospital", "hotel", "police", "restaurant", "taxi", "train")
_DOMAIN_BIT = {domain: 1 << index for index, domain in enumerate(DOMAINS)}
_EMPTY_SLOT_VALUES = frozenset({"", "not mentioned"})
_TRUE_FALSE = {"True": True, "False": False}

logger = logging.getLogger(__name__)


class BuildError(Exception):
    """The inputs are inconsistent in a way that makes the dataset untrustworthy."""


@dataclass(frozen=True)
class DirectRow:
    source_file: str
    source_row: int
    dialogue_id: str
    turn_index: int
    target_utterance: str
    direct_utterance: str
    indirect_utterance: str
    quality_labels: dict[str, Any] | None  # test rows only


@dataclass(frozen=True)
class Dialogue:
    dialogue_id: str
    turns: list[Turn]
    turn_domains: list[list[str]]  # from each turn's own dialogue acts
    turn_acts: list[dict[str, Any]]
    prefix_masks: list[int]  # prefix_masks[k] = domain bitmask of turns[0:k], acts plus belief states
    goal_domains: list[str]


# --------------------------------------------------------------------------- reading


def read_direct_csv(path: Path) -> list[DirectRow]:
    """Parse a DIRECT CSV. Test files carry three extra quality columns."""
    rows: list[DirectRow] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for record in csv.DictReader(handle):
            quality = None
            if "quality" in record:
                quality = {
                    "isacceptable_direct": _parse_bool(record["isacceptable_direct"], path),
                    "isacceptable_indirect": _parse_bool(record["isacceptable_indirect"], path),
                    "quality": record["quality"],
                }
            rows.append(
                DirectRow(
                    source_file=path.name,
                    source_row=int(record[""]),
                    dialogue_id=record["dialogue_id"],
                    turn_index=int(record["turn_index"]),
                    target_utterance=record["target_utterance"],
                    direct_utterance=record["direct_utterance"],
                    indirect_utterance=record["indirect_utterance"],
                    quality_labels=quality,
                )
            )
    return rows


def _parse_bool(value: str, path: Path) -> bool:
    try:
        return _TRUE_FALSE[value]
    except KeyError as exc:
        raise BuildError(f"{path.name}: expected True/False, got {value!r}") from exc


def read_id_list(path: Path) -> set[str]:
    return set(path.read_text(encoding="utf-8").split())


def load_multiwoz(data_json: Path, keep: set[str] | None = None) -> dict[str, Dialogue]:
    """Parse MultiWOZ 2.1 ``data.json``, keeping only dialogues in ``keep`` if given."""
    with data_json.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    return {
        dialogue_id: parse_multiwoz_dialogue(dialogue_id, dialogue)
        for dialogue_id, dialogue in raw.items()
        if keep is None or dialogue_id in keep
    }


def parse_multiwoz_dialogue(dialogue_id: str, raw: dict[str, Any]) -> Dialogue:
    turns, turn_domains, turn_acts, prefix_masks = [], [], [], [0]
    for index, turn in enumerate(raw["log"]):
        acts = turn.get("dialog_act") or {}
        act_domains = _act_domains(acts)
        mask = _mask(act_domains)
        if index % 2 == 1:  # system turns carry the cumulative belief state
            mask |= _mask(_belief_domains(turn.get("metadata") or {}))
        turns.append(Turn("user" if index % 2 == 0 else "system", turn["text"].strip()))
        turn_domains.append(sorted(act_domains))
        turn_acts.append(acts)
        prefix_masks.append(prefix_masks[-1] | mask)
    goal = raw.get("goal") or {}
    return Dialogue(
        dialogue_id=dialogue_id,
        turns=turns,
        turn_domains=turn_domains,
        turn_acts=turn_acts,
        prefix_masks=prefix_masks,
        goal_domains=sorted(domain for domain in DOMAINS if goal.get(domain)),
    )


def _act_domains(acts: dict[str, Any]) -> set[str]:
    # Act keys look like "Hotel-Inform"; "general-*" and "Booking-*" name no domain.
    return {key.split("-", 1)[0].lower() for key in acts} & set(DOMAINS)


def _belief_domains(metadata: dict[str, Any]) -> set[str]:
    active = set()
    for domain, state in metadata.items():
        if domain not in _DOMAIN_BIT:
            continue
        semi, book = state.get("semi", {}), state.get("book", {})
        filled = [value for value in semi.values() if value not in _EMPTY_SLOT_VALUES]
        filled += [value for key, value in book.items() if key != "booked" and value not in _EMPTY_SLOT_VALUES]
        if filled or book.get("booked"):
            active.add(domain)
    return active


def _mask(domains: Iterable[str]) -> int:
    mask = 0
    for domain in domains:
        mask |= _DOMAIN_BIT[domain]
    return mask


def _domains_of(mask: int) -> list[str]:
    return [domain for domain in DOMAINS if mask & _DOMAIN_BIT[domain]]


# --------------------------------------------------------------------------- join and splits


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def match_row(row: DirectRow, dialogues: dict[str, Dialogue]) -> tuple[str | None, str]:
    """Return ``(match_kind, reason)``. ``match_kind`` is None when the row can't be joined."""
    dialogue = dialogues.get(row.dialogue_id)
    if dialogue is None:
        return None, "dialogue_not_found"
    if not 0 <= row.turn_index < len(dialogue.turns):
        return None, "turn_index_out_of_range"
    if row.turn_index % 2 != 0:
        return None, "not_a_user_turn"
    stored = dialogue.turns[row.turn_index].text  # already stripped
    if row.target_utterance == stored:
        return "exact", "ok"
    if row.target_utterance.strip() == stored:
        return "stripped", "ok"
    if _normalize(row.target_utterance) == _normalize(stored):
        return "normalized", "ok"
    return None, "text_mismatch"


def assign_split(row: DirectRow, dev_dialogue_ids: set[str]) -> str:
    if row.source_file.startswith("test"):
        return "test"
    return "dev" if row.dialogue_id in dev_dialogue_ids else "train"


def check_split_grouping(items: Sequence[Item]) -> dict[str, str]:
    """Return ``dialogue_id -> split``, raising if any dialogue spans two splits."""
    dialogue_split: dict[str, str] = {}
    for item in items:
        previous = dialogue_split.setdefault(item["dialogue_id"], item["split"])
        if previous != item["split"]:
            raise BuildError(f"dialogue {item['dialogue_id']} appears in both {previous} and {item['split']}")
    return dialogue_split


def make_item(row: DirectRow, dialogue: Dialogue, split: str, match_kind: str) -> Item:
    t = row.turn_index
    target_active = dialogue.prefix_masks[min(t + 2, len(dialogue.turns))]
    return {
        "item_id": f"{row.dialogue_id.removesuffix('.json')}_t{t:02d}",
        "dialogue_id": row.dialogue_id,
        "turn_index": t,
        "split": split,
        "source": {"file": row.source_file, "row": row.source_row},
        "join_match": match_kind,
        "target_utterance": row.target_utterance,
        "direct_utterance": row.direct_utterance,
        "indirect_utterance": row.indirect_utterance,
        "turn_domains": dialogue.turn_domains[t],
        "active_domains": _domains_of(target_active),
        "dialogue_domains": dialogue.goal_domains,
        "user_acts": dialogue.turn_acts[t],
        "quality_labels": row.quality_labels,
        "mismatch": None,
        "mismatch_status": "not_needed" if t == 0 else "unassigned",
    }


# --------------------------------------------------------------------------- mismatch pairing


def pair_mismatches(items: Sequence[Item], dialogues: dict[str, Dialogue], dialogue_split: dict[str, str], seed: int) -> None:
    """Fill ``mismatch`` and ``mismatch_status`` on every item, in place and deterministically."""
    by_split: dict[str, list[str]] = collections.defaultdict(list)
    for dialogue_id in sorted(dialogue_split):
        by_split[dialogue_split[dialogue_id]].append(dialogue_id)

    candidate_cache: dict[tuple[str, int, int], list[str]] = {}
    for item in items:
        t = item["turn_index"]
        if t == 0:
            continue
        target_active = _mask(item["active_domains"])
        key = (item["split"], t, target_active)
        if key not in candidate_cache:
            candidate_cache[key] = [
                donor_id
                for donor_id in by_split[item["split"]]
                if len(dialogues[donor_id].turns) >= t and not dialogues[donor_id].prefix_masks[t] & target_active
            ]
        candidates = [donor_id for donor_id in candidate_cache[key] if donor_id != item["dialogue_id"]]
        if not candidates:
            item["mismatch_status"] = "unavailable"
            continue
        donor_id = random.Random(f"{seed}:{item['item_id']}").choice(candidates)
        item["mismatch"] = {"donor_dialogue_id": donor_id, "start": 0, "length": t}
        item["mismatch_status"] = "ok"


# --------------------------------------------------------------------------- build


def build(direct_dir: Path, multiwoz_dir: Path, seed: int) -> tuple[list[Item], dict[str, Dialogue], dict[str, Any]]:
    """Run the whole pipeline in memory. Returns ``(items, dialogues_used, report)``."""
    rows = read_direct_csv(direct_dir / "train.csv") + read_direct_csv(direct_dir / "test.csv")
    dialogues = load_multiwoz(multiwoz_dir / "data.json", keep={row.dialogue_id for row in rows})
    dev_ids = read_id_list(multiwoz_dir / "valListFile.txt")

    items, join_counts, rejects = [], collections.Counter(), collections.Counter()
    for row in rows:
        match_kind, reason = match_row(row, dialogues)
        if match_kind is None:
            rejects[reason] += 1
            logger.warning("rejected %s row %d (%s t=%d): %s", row.source_file, row.source_row, row.dialogue_id, row.turn_index, reason)
            continue
        join_counts[match_kind] += 1
        items.append(make_item(row, dialogues[row.dialogue_id], assign_split(row, dev_ids), match_kind))

    dialogue_split = check_split_grouping(items)
    pair_mismatches(items, dialogues, dialogue_split, seed)
    used = {dialogue_id: dialogues[dialogue_id] for dialogue_id in sorted(dialogue_split)}
    report = {
        "rows_read": len(rows),
        "join": dict(sorted(join_counts.items())),
        "rejected": dict(sorted(rejects.items())),
        "dialogue_split_overlap": 0,  # check_split_grouping raises otherwise
    }
    return items, used, report


def summarize(items: Sequence[Item], dialogue_turns: dict[str, list[Turn]]) -> dict[str, Any]:
    """Summary statistics for the report and ``build_info.json``."""
    per_split = collections.Counter(item["split"] for item in items)
    dialogues_per_split = collections.Counter(
        split for _, split in {(item["dialogue_id"], item["split"]) for item in items}
    )
    domain_counts = collections.Counter()
    for item in items:
        domain_counts.update(item["turn_domains"] or ["(none)"])
    history = [item["turn_index"] for item in items]

    context_tokens, input_tokens = [], []
    for item in items:
        context = build_context(item, dialogue_turns, "full") or []
        tokens = sum(len(turn.text.split()) for turn in context)
        longest_variant = max(len(item[key].split()) for key in ("target_utterance", "direct_utterance", "indirect_utterance"))
        context_tokens.append(tokens)
        input_tokens.append(tokens + longest_variant)

    total = len(items)
    social = sum(is_social_only(item) for item in items)
    no_acts = sum(not item["user_acts"] for item in items)
    return {
        "rows_per_split": dict(sorted(per_split.items())),
        "dialogues_per_split": dict(sorted(dialogues_per_split.items())),
        "target_turn_domain_counts": dict(domain_counts.most_common()),
        "social_only_targets": {"count": social, "fraction": round(social / total, 4)},
        "targets_without_user_acts": {"count": no_acts, "fraction": round(no_acts / total, 4)},
        "full_history_turns": {
            "mean": round(statistics.mean(history), 2),
            "median": statistics.median(history),
            "max": max(history),
            "zero_history_items": history.count(0),
        },
        "full_context_whitespace_tokens": {
            "mean": round(statistics.mean(context_tokens), 1),
            "max": max(context_tokens),
            f"items_over_{LONG_CONTEXT_TOKENS}": sum(tokens > LONG_CONTEXT_TOKENS for tokens in context_tokens),
            f"items_over_{LONG_CONTEXT_TOKENS}_with_longest_utterance": sum(
                tokens > LONG_CONTEXT_TOKENS for tokens in input_tokens
            ),
        },
        "mismatch_status": dict(sorted(collections.Counter(item["mismatch_status"] for item in items).items())),
    }


def write_outputs(out_dir: Path, items: Sequence[Item], dialogues: dict[str, Dialogue], build_info: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "dialogues.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for dialogue in dialogues.values():
            turns = [
                {"speaker": turn.speaker, "text": turn.text, "domains": domains}
                for turn, domains in zip(dialogue.turns, dialogue.turn_domains)
            ]
            record = {"dialogue_id": dialogue.dialogue_id, "goal_domains": dialogue.goal_domains, "turns": turns}
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    with (out_dir / "items.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    (out_dir / "build_info.json").write_text(json.dumps(build_info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------- CLI


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.data.build_direct_dataset",
        description="Join DIRECT to MultiWOZ 2.1 and write items/dialogues JSONL with seeded mismatch pairing.",
    )
    parser.add_argument("--direct-dir", type=Path, default=DEFAULT_DIRECT_DIR)
    parser.add_argument("--multiwoz-dir", type=Path, default=DEFAULT_MULTIWOZ_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="seed for mismatch donor choice")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        items, dialogues, report = build(args.direct_dir, args.multiwoz_dir, args.seed)
    except (BuildError, OSError, KeyError, ValueError) as exc:
        logger.error("build failed: %s", exc)
        return 1

    dialogue_turns = {dialogue_id: dialogue.turns for dialogue_id, dialogue in dialogues.items()}
    stats = summarize(items, dialogue_turns)
    build_info = {
        "schema_version": 1,
        "builder": "src.data.build_direct_dataset",
        "multiwoz_version": "2.1",
        "seed": args.seed,
        "inputs": {
            name: _sha256(path)
            for name, path in (
                ("direct/train.csv", args.direct_dir / "train.csv"),
                ("direct/test.csv", args.direct_dir / "test.csv"),
                ("multiwoz/data.json", args.multiwoz_dir / "data.json"),
                ("multiwoz/valListFile.txt", args.multiwoz_dir / "valListFile.txt"),
            )
        },
        "report": report,
        "stats": stats,
    }
    write_outputs(args.out_dir, items, dialogues, build_info)
    print(json.dumps({"report": report, "stats": stats}, indent=2))
    logger.info("wrote %d items and %d dialogues to %s", len(items), len(dialogues), args.out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
