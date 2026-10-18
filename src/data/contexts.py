"""Render every context condition the same way for every model (spec 004).

``build_context`` (``src.data.direct_dataset``) decides *which* turns a condition shows. This
module turns them into model input, applies the common D-06 budget, and is the only renderer
the TF-IDF, encoder, LLM, Stage 2 and hybrid code may use, so one example under one condition
is the same text everywhere.

Renderer ``render-v1``:

* Context turns are serialized oldest first, one ``"User: ..."`` / ``"System: ..."`` line per
  turn. The target (the example's own DIRECT paraphrase) is passed separately and never changed.
* Budget: under ``full`` and ``mismatched``, context plus target is at most ``BUDGET_WORDS``
  whitespace tokens (speaker tags count). The oldest whole turns are dropped first; when the
  target alone is over budget the context is empty. ``none`` and ``one``-turn conditions are
  never budgeted. The budget is part of the renderer version, not a run setting.

Example sets: the *genuine* set (``turn_index > 0``) is scored under none / one / full; the
*mismatch* set (genuine examples with a donor) under the two mismatch conditions.

Cue flags (disclosed, never used to exclude): ``donor_cue`` / ``donor_cue_one`` when the shown
``mismatched`` / ``mismatched_one`` donor context mentions a value of the target turn's user acts
(an accidental helpful cue); ``dropped_cue`` when a turn the budget removed from ``full``
mentions one. Mentions come from ``src.data.audit_fact_drift`` (precision first).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass

from src.data.audit_fact_drift import (AREAS, DAYS, FOOD_STOPLIST, FOOD_SYNONYMS, NESTED_NAME_SLOTS,
                                       PLACE_STOPLIST, PRICES, Vocabulary, extract_mentions, values_match)
from src.data.direct_dataset import CONDITIONS, Item, Turn, build_context

RENDERER_VERSION = "render-v1"
BUDGET_WORDS = 350
BUDGETED_CONDITIONS = ("full", "mismatched")
MISMATCH_CONDITIONS = ("mismatched", "mismatched_one")

# MultiWOZ user-act slots -> audit_fact_drift slot types. Other slots (People, Stay, Type ...)
# have no reliable mention extractor and are not cue-checked.
ACT_SLOT_TYPES = {"Day": "day", "Time": "time", "Leave": "time", "Arrive": "time", "Price": "price",
                  "Area": "area", "Food": "food", "Dest": "place", "Depart": "place", "Name": "place"}
LEXICONS = {"day": frozenset(DAYS.values()), "price": frozenset(PRICES.values()),
            "area": frozenset(AREAS.values())}
NO_VALUE = frozenset({"", "none", "any", "?", "dontcare", "dont care", "don't care", "do nt care", "do n't care"})


@dataclass(frozen=True)
class Rendered:
    turns: tuple[Turn, ...]  # the context turns actually shown, oldest first
    context: str
    target: str
    dropped: int  # oldest turns removed by the budget


def render_context(turns: Sequence[Turn]) -> str:
    """Serialize context turns oldest first, one speaker-tagged line per turn."""
    return "\n".join(_line(turn) for turn in turns)


def _line(turn: Turn) -> str:
    return f"{turn.speaker.capitalize()}: {turn.text}"


def word_count(text: str) -> int:
    return len(text.split())


def turn_words(turn: Turn) -> int:
    """Words a turn adds to the rendered context, speaker tag included."""
    return word_count(_line(turn))


def render(item: Item, target: str, dialogues: dict[str, list[Turn]], condition: str,
           budget: int = BUDGET_WORDS) -> Rendered | None:
    """Model input for ``target`` under ``condition``; ``None`` when the condition is undefined."""
    if budget < 1:
        raise ValueError("budget must be positive")
    turns = build_context(item, dialogues, condition)
    if turns is None:
        return None
    dropped = 0
    if condition in BUDGETED_CONDITIONS:
        room = budget - word_count(target)
        lengths = [turn_words(turn) for turn in turns]
        total = sum(lengths)
        while dropped < len(turns) and total > room:
            total -= lengths[dropped]
            dropped += 1
    shown = tuple(turns[dropped:])
    return Rendered(shown, render_context(shown), target, dropped)


def render_all(item: Item, target: str, dialogues: dict[str, list[Turn]],
               budget: int = BUDGET_WORDS) -> dict[str, Rendered | None]:
    """``render`` under every condition, keyed by condition."""
    return {condition: render(item, target, dialogues, condition, budget) for condition in CONDITIONS}


def input_sha256(rendered: Rendered) -> str:
    """Hash of exactly what a model is shown; any change to context or target changes it."""
    payload = json.dumps({"context": rendered.context, "target": rendered.target},
                         ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def target_sha256(target: str) -> str:
    return hashlib.sha256(target.encode("utf-8")).hexdigest()


def genuine(item: Item) -> bool:
    """True when the item has prior context, so none / one / full differ."""
    return item["turn_index"] > 0


def in_mismatch_set(item: Item) -> bool:
    """True when the item is genuine and has a mismatch donor."""
    return genuine(item) and item.get("mismatch") is not None


# ------------------------------------------------------------------ cue flags


@dataclass(frozen=True)
class CueFlags:
    donor_cue: bool  # the shown mismatched window mentions a target act value
    donor_cue_one: bool  # the shown mismatched_one turn does
    dropped_cue: bool  # a turn the budget removed from full does


def target_values(item: Item) -> dict[str, frozenset[str]]:
    """Canonical values of the target turn's user acts, per ``audit_fact_drift`` slot type."""
    values: dict[str, set[str]] = {}
    for pairs in (item.get("user_acts") or {}).values():
        for slot, raw in pairs:
            slot_type = ACT_SLOT_TYPES.get(slot)
            value = " ".join(str(raw).lower().split())
            if slot_type is None or value in NO_VALUE:
                continue
            if slot_type == "place":
                value = value[4:] if value.startswith("the ") else value
                if value in PLACE_STOPLIST:
                    continue
            elif slot_type == "food":
                if value in FOOD_STOPLIST:
                    continue
                value = FOOD_SYNONYMS.get(value, value)
            elif slot_type in LEXICONS and value not in LEXICONS[slot_type]:
                continue  # e.g. a Price of "2": not a value the extractor could ever find
            values.setdefault(slot_type, set()).add(value)
    return {slot_type: frozenset(found) for slot_type, found in values.items()}


def mentions_value(text: str, values: dict[str, frozenset[str]], vocab: Vocabulary) -> bool:
    """True if ``text`` asserts any of ``values`` (same slot type; nested match for names)."""
    if not values or not text:
        return False
    for slot_type, mentions in extract_mentions(text, vocab).items():
        wanted = values.get(slot_type)
        if wanted and any(values_match(found, value, slot_type in NESTED_NAME_SLOTS)
                          for mention in mentions for found in mention for value in wanted):
            return True
    return False


def cue_flags(item: Item, rendered: dict[str, Rendered | None], dialogues: dict[str, list[Turn]],
              vocab: Vocabulary) -> CueFlags:
    """Flags for one example from its renderings (``rendered[condition]``, as from ``render``)."""
    values = target_values(item)

    def shown(condition: str) -> str:
        result = rendered.get(condition)
        return result.context if result is not None else ""

    full = rendered.get("full")
    removed = dialogues[item["dialogue_id"]][: full.dropped] if full is not None else []
    return CueFlags(donor_cue=mentions_value(shown("mismatched"), values, vocab),
                    donor_cue_one=mentions_value(shown("mismatched_one"), values, vocab),
                    dropped_cue=mentions_value(render_context(removed), values, vocab))
