"""Stage 1 examples from DIRECT under an explicit, versioned weak-supervision policy.

DIRECT gives each MultiWOZ user turn a crowd-written direct and indirect
paraphrase. Those variant names are *weak* Stage 1 labels: they are not human
L0–L3 levels (about 15% of "indirect" paraphrases still use an L1 request
formula). Human levels enter only as an evaluation slice.

Policy ``direct_variants_v1`` (one example per paraphrase):

======================================  ===========================================
DIRECT row                              examples produced
======================================  ===========================================
target turn's user acts are all         direct and indirect paraphrases →
thanks / bye / greeting                 ``no_request``
any other user acts                     direct → ``direct``; indirect → ``indirect``
no user acts (MultiWOZ annotation gap)  excluded: request status is unknown
direct and indirect text identical      excluded: contradictory labels
original ``target`` utterance           never used: DIRECT gives it no directness label
test row, paraphrase marked             that paraphrase excluded
unacceptable by DIRECT's raters
======================================  ===========================================

Context always comes from the *original* dialogue (``build_context``); only the
target utterance is replaced by its paraphrase. Evaluation uses
``comparable`` items only, so every context condition scores the same examples;
training uses items whose contexts are all defined, so every training condition
fits the same examples.
"""

from __future__ import annotations

import collections
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from src.data.direct_dataset import Item, Turn, build_context, is_social_only

STAGE1_LABELS = ("direct", "indirect", "no_request")
POLICIES = ("direct_variants_v1",)
PARAPHRASE_VARIANTS = ("direct", "indirect")


@dataclass(frozen=True)
class Stage1Example:
    example_id: str  # "<item_id>:<variant>"
    item_id: str
    dialogue_id: str
    turn_index: int
    variant: str  # "direct" or "indirect": DIRECT provenance
    text: str
    label: str
    domain: str  # MultiWOZ target-turn domains; a proxy, not a Stage 2 intent


def contexts_defined(item: Item) -> bool:
    """True when every context condition is defined (turn 0 has empty context throughout)."""
    return item["turn_index"] == 0 or item.get("mismatch") is not None


def comparable(item: Item) -> bool:
    """True when all context conditions are defined and differ from ``none``."""
    return item["turn_index"] > 0 and contexts_defined(item)


def build_examples(
    items: Iterable[Item], split: str, policy: str = "direct_variants_v1",
    require_comparable: bool = False,
) -> tuple[list[Stage1Example], dict[str, int]]:
    """Apply ``policy`` to the items of ``split``; return examples and exclusion counts."""
    if policy not in POLICIES:
        raise ValueError(f"unknown policy {policy!r}; expected one of {POLICIES}")
    examples: list[Stage1Example] = []
    excluded: collections.Counter[str] = collections.Counter()
    for item in items:
        if item["split"] != split:
            continue
        if require_comparable and not comparable(item):
            excluded["not_comparable"] += 1
            continue
        if not item.get("user_acts"):
            excluded["no_user_acts"] += 1
            continue
        texts = {variant: item[f"{variant}_utterance"].strip() for variant in PARAPHRASE_VARIANTS}
        if " ".join(texts["direct"].lower().split()) == " ".join(texts["indirect"].lower().split()):
            excluded["identical_paraphrases"] += 1
            continue
        social = is_social_only(item)
        quality = item.get("quality_labels") or {}
        for variant in PARAPHRASE_VARIANTS:
            if quality.get(f"isacceptable_{variant}") is False:
                excluded[f"unacceptable_{variant}"] += 1
                continue
            examples.append(Stage1Example(
                example_id=f"{item['item_id']}:{variant}", item_id=item["item_id"],
                dialogue_id=item["dialogue_id"], turn_index=item["turn_index"], variant=variant,
                text=texts[variant], label="no_request" if social else variant,
                domain="+".join(sorted(item.get("turn_domains") or [])) or "(none)",
            ))
    if len({e.example_id for e in examples}) != len(examples):
        raise ValueError("duplicate example IDs; is an item repeated in the input?")
    return examples, dict(sorted(excluded.items()))


def render_context(turns: Sequence[Turn]) -> str:
    """Serialize context turns oldest first, one speaker-tagged line per turn."""
    return "\n".join(f"{turn.speaker.capitalize()}: {turn.text}" for turn in turns)


def model_inputs(
    examples: Sequence[Stage1Example], items_by_id: dict[str, Item],
    dialogues: dict[str, list[Turn]], condition: str,
) -> list[tuple[str, str] | None]:
    """(context text, utterance) per example, or ``None`` when the condition is undefined."""
    inputs: list[tuple[str, str] | None] = []
    for example in examples:
        turns = build_context(items_by_id[example.item_id], dialogues, condition)
        inputs.append(None if turns is None else (render_context(turns), example.text))
    return inputs
