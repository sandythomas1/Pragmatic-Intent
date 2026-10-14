"""Map MultiWOZ user acts onto the proposal's assistant-intent categories (option A, 2026-10-13).

The proposal lists general assistant categories ("information seeking, recommendation,
planning/scheduling, navigation, ... action/device requests"). MultiWOZ user turns carry only
``<Domain>-Inform`` and ``<Domain>-Request`` acts plus thanks / bye / greeting, so a fixed mapping
covers four of those categories. Troubleshooting, advice/support and device control are not in
this data and stay a stated limitation.

Mapping ``cat-v1`` (a turn can fall in several categories; ``primary`` takes the first that
applies, in this order):

====================  ===============================  =============================================
category              proposal name                    turn has
====================  ===============================  =============================================
``info_seeking``      information seeking              any ``*-Request`` act, or a hospital/police act
``booking``           action requests (booking)        an ``Inform`` with a ``People`` or ``Stay`` slot
``travel``            planning/scheduling, navigation  a ``Train-Inform`` or ``Taxi-Inform`` act
``recommendation``    recommendation                   a ``Hotel``/``Restaurant``/``Attraction-Inform`` act,
                                                       unless it holds only booking details
                                                       (``People``, ``Stay``, ``Day``, ``Time``)
``no_request``        (not a request)                  only thanks / bye / greeting
====================  ===============================  =============================================

Turns with no user acts get ``None``: their category is unknown, as in the Stage 1 policy.

Run from the repository root (Python 3.12, standard library only)::

    python -m src.data.intent_categories   # counts per split, primary and any-of
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from src.data.direct_dataset import SOCIAL_ACTS, Item, load_items

MAPPING_VERSION = "cat-v1"
CATEGORIES = ("info_seeking", "booking", "travel", "recommendation", "no_request")
PROPOSAL_NAMES = {
    "info_seeking": "information seeking",
    "booking": "action requests (booking)",
    "travel": "planning/scheduling, navigation",
    "recommendation": "recommendation",
    "no_request": "not a request",
}
BOOKING_SLOTS = frozenset({"People", "Stay"})
BOOKING_DETAIL_SLOTS = BOOKING_SLOTS | {"Day", "Time", "none"}
TRAVEL_DOMAINS = frozenset({"Train", "Taxi"})
SEARCH_DOMAINS = frozenset({"Hotel", "Restaurant", "Attraction"})
SERVICE_DOMAINS = frozenset({"Hospital", "Police"})
DEFAULT_ITEMS = Path("data/interim/direct/items.jsonl")


def turn_categories(item: Item) -> frozenset[str] | None:
    """Every ``cat-v1`` category of the item's target turn, or None when it has no user acts."""
    acts = item.get("user_acts") or {}
    if not acts:
        return None
    if set(acts) <= SOCIAL_ACTS:
        return frozenset({"no_request"})
    found: set[str] = set()
    for act, pairs in acts.items():
        if act in SOCIAL_ACTS:
            continue
        domain, _, kind = act.partition("-")
        if kind == "Request" or domain in SERVICE_DOMAINS:
            found.add("info_seeking")
        if kind != "Inform":
            continue
        slots = {slot for slot, _ in pairs}
        booking = bool(slots & BOOKING_SLOTS)
        if booking:
            found.add("booking")
        if domain in TRAVEL_DOMAINS:
            found.add("travel")
        elif domain in SEARCH_DOMAINS and (not booking or slots - BOOKING_DETAIL_SLOTS):
            found.add("recommendation")
    return frozenset(found)


def primary_category(item: Item) -> str | None:
    """The first category in ``CATEGORIES`` order that applies, or None when the turn has no acts."""
    found = turn_categories(item)
    if found is None:
        return None
    return next((category for category in CATEGORIES if category in found), None)


def category_counts(items: Sequence[Item]) -> dict[str, Any]:
    primary: dict[str, collections.Counter[str]] = {}
    any_of: dict[str, collections.Counter[str]] = {}
    for item in items:
        found = turn_categories(item)
        key = primary_category(item) or "(no acts)"
        primary.setdefault(item["split"], collections.Counter())[key] += 1
        for category in found or ():
            any_of.setdefault(item["split"], collections.Counter())[category] += 1
    return {
        "mapping_version": MAPPING_VERSION,
        "primary": {split: dict(counter.most_common()) for split, counter in sorted(primary.items())},
        "any_of": {split: dict(counter.most_common()) for split, counter in sorted(any_of.items())},
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.data.intent_categories", description=__doc__.split("\n")[0])
    parser.add_argument("--items", type=Path, default=DEFAULT_ITEMS)
    args = parser.parse_args(argv)
    try:
        items = load_items(args.items)
    except (OSError, ValueError) as exc:
        print(f"could not read items: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(category_counts(items), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
