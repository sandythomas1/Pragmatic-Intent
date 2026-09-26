"""Load the joined DIRECT + MultiWOZ dataset and derive context conditions on demand.

The builder (``src.data.build_direct_dataset``) stores each dialogue once and one
record per DIRECT row. The context shown to a model is derived here, at load time,
from ``turn_index`` and the stored mismatch pairing:

======================  ===========================================================
condition               turns returned for an item at ``turn_index = t``
======================  ===========================================================
``none``                ``[]``
``one``                 ``[turns[t-1]]``: the system turn right before the target
``full``                ``turns[0:t]``: every prior turn
``mismatched``          ``t`` turns from a donor dialogue (same split, no shared
                        active domain), ending on a system turn: control for ``full``
``mismatched_one``      the last turn of that donor window (a system turn):
                        control for ``one``
======================  ===========================================================

For ``t == 0`` every condition is ``[]``. ``build_context`` returns ``None`` only
when a mismatch was needed but no valid donor existed (``mismatch_status ==
"unavailable"``).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONDITIONS = ("none", "one", "full", "mismatched", "mismatched_one")
SOCIAL_ACTS = frozenset({"general-thank", "general-bye", "general-greet"})

Item = dict[str, Any]


@dataclass(frozen=True)
class Turn:
    speaker: str  # "user" or "system"
    text: str


def _read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def load_dialogues(path: Path) -> dict[str, list[Turn]]:
    """Map ``dialogue_id`` to its turns from ``dialogues.jsonl``."""
    return {
        record["dialogue_id"]: [Turn(turn["speaker"], turn["text"]) for turn in record["turns"]]
        for record in _read_jsonl(path)
    }


def load_items(path: Path) -> list[Item]:
    """Read ``items.jsonl`` (one record per DIRECT row)."""
    return list(_read_jsonl(path))


def build_context(item: Item, dialogues: dict[str, list[Turn]], condition: str) -> list[Turn] | None:
    """Return the context turns shown before ``item``'s target utterance under ``condition``."""
    if condition not in CONDITIONS:
        raise ValueError(f"unknown condition {condition!r}; expected one of {CONDITIONS}")
    turn_index = item["turn_index"]
    if condition == "none" or turn_index == 0:
        return []
    if condition == "one":
        return [dialogues[item["dialogue_id"]][turn_index - 1]]
    if condition == "full":
        return dialogues[item["dialogue_id"]][:turn_index]

    mismatch = item.get("mismatch")
    if mismatch is None:
        return None
    start, length = mismatch["start"], mismatch["length"]
    window = dialogues[mismatch["donor_dialogue_id"]][start : start + length]
    return window if condition == "mismatched" else window[-1:]


def is_social_only(item: Item) -> bool:
    """True if the target turn has user acts and all of them are thanks, bye, or greeting."""
    acts = item.get("user_acts") or {}
    return bool(acts) and set(acts) <= SOCIAL_ACTS
