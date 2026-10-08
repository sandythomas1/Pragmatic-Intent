"""Flag DIRECT rewrites that change a fact stated in their target utterance.

DIRECT's direct and indirect rewrites are meant to keep the target's meaning, but some
replace a stated value (target: "on Thursday", rewrite: "on Tuesday"). In the matched
context conditions that rewrite then contradicts its own dialogue history, which adds
noise to the context effect we want to measure. This audit lists such rewrites, so the
analysis can be re-run without them (sensitivity check). It does not change the data.

Run from the repository root (Python 3.11+, standard library only), after the builder::

    python -m src.data.audit_fact_drift
    python -m src.data.audit_fact_drift --items data/interim/direct/items.jsonl --out-dir data/interim/direct

Outputs in ``--out-dir`` (git-ignored, because they quote DIRECT values):

* ``fact_drift.jsonl``: one record per flagged ``(item_id, variant)``, with the slot
  types substituted and the values involved.
* ``fact_drift_summary.json``: per-variant, per-slot counts of kept / dropped /
  substituted values, plus counts of rewrites that start with a speaker prefix
  (``"USER: ..."``), a formatting artifact that a classifier could exploit.

Method (precision over recall, so a flag is worth a look):

* Six slot types: ``day``, ``time``, ``price``, ``area``, ``food``, ``place``. Days,
  times, prices and areas use fixed patterns; food and place names use a vocabulary
  built from the MultiWOZ user-act values of the items themselves.
* Place names, then food names, are matched longest first and masked, so the "centre"
  in "Cherry Hinton Village Centre" and the "north" in "north american" are not areas.
  Nested names match each other ("asian oriental" / "asian", "cambridge belfry" /
  "cambridge").
* A mention is *not* an assertion when a guard word appears within the preceding
  ``GUARD_WINDOW`` tokens of the same clause: negation ("not expensive", "non cheap"),
  comparison ("earlier than 21:36"), and, per slot, relative words ("the day after
  Monday", "far from the west"). A guard carries over coordination ("not cheap or
  moderate").
* A clock time without am/pm and an hour of 1-12 stands for both readings
  ("3.15" matches 03:15 and 15:15).
* A rewrite **substitutes** a slot when it asserts a value the target does not, *and*
  the target asserts a value the rewrite does not. Dropping a value is normal for
  hints and is only counted, never flagged. Only substitutions in ``FLAG_SLOTS`` flag a
  rewrite.
"""

from __future__ import annotations

import argparse
import collections
import functools
import json
import logging
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.data.direct_dataset import Item, load_items

logger = logging.getLogger(__name__)

DEFAULT_ITEMS = Path("data/interim/direct/items.jsonl")
DEFAULT_OUT_DIR = Path("data/interim/direct")

REWRITE_VARIANTS = ("direct", "indirect")
SLOT_TYPES = ("place", "day", "time", "price", "area", "food")
OUTCOMES = ("kept", "dropped", "substituted")
# Slots whose substitutions flag a rewrite. Area and price are counted but never flag:
# indirect rewrites state them by exclusion ("anything but the south", "non cheap"), so a
# string match there was mostly wrong in a hand check (see docs/data_sources.md).
FLAG_SLOTS = ("place", "day", "time", "food")

GUARD_WINDOW = 6
COMMON_GUARDS = frozenset({
    "not", "n't", "no", "non", "none", "nor", "neither", "never", "without", "except", "than",
    # contractions typed without the apostrophe
    "dont", "doesnt", "didnt", "cant", "cannot", "wont", "isnt", "arent", "wasnt", "wouldnt", "shouldnt",
})
SLOT_GUARDS = {
    "day": COMMON_GUARDS | {"after", "before"},
    "area": COMMON_GUARDS | {"from"},
    "price": COMMON_GUARDS | {"too", "less", "more"},
}
CLAUSE_BREAK = re.compile(r"[,;!?]|\.(?:\s|$)")
# Text allowed between two coordinated mentions of a slot ("not cheap or moderate",
# "other than north, east, west"); the second inherits the first one's guard.
COORDINATION = re.compile(r"[\s,]*(?:(?:or|nor|and|in|the|too|a|an|at|on)\b[\s,]*)*")
# "don't" -> "do", "n't"; a plain [a-z]+ would swallow it as "don" + "t".
TOKEN = re.compile(r"[a-z]+(?=n't)|n't|[a-z]+")
# DIRECT has curly quotes and some U+FFFD replacement characters where an apostrophe was ("don�t").
APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "`": "'", "�": "'"})

DAYS = {day: day for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")}
PRICES = {
    "cheap": "cheap", "inexpensive": "cheap",
    "moderate": "moderate", "moderately": "moderate",
    "expensive": "expensive", "pricey": "expensive", "upscale": "expensive", "luxurious": "expensive",
}
AREAS = {
    "centre": "centre", "center": "centre", "central": "centre",
    "north": "north", "northern": "north", "south": "south", "southern": "south",
    "east": "east", "eastern": "east", "west": "west", "western": "west",
}

# Clock times such as 18:30, 18;30, 13.00, 6:30pm, 7 p.m. A match with neither minutes nor
# am/pm ("at 7") is discarded in _time_readings: too easily a party size or a count of
# nights. A leading currency sign rules out prices such as £3.50.
TIME = re.compile(
    r"(?<![\d£$.:])(?P<hour>\d{1,2})(?:[:;.](?P<minute>\d{2}))?(?!\d)\s*(?:(?P<meridiem>[ap])\.?m\b\.?)?",
    re.IGNORECASE,
)
SPEAKER_PREFIX = re.compile(r"^\s*(?:USER|USR|SER|SYS|SYSTEM)\s*:")

# Act values that are not names of anything ("the place" is a real MultiWOZ value) or are
# also everyday words that would match ordinary text.
PLACE_STOPLIST = frozenset({
    "the place", "ask", "home", "no", "the", "do nt care", "dont care", "don't care", "any", "college", "museum",
})
FOOD_STOPLIST = frozenset({
    "do nt care", "dont care", "don't care", "any", "food", "creative", "traditional", "unusual", "world", "christmas",
    # broad categories: "Asian food" for "Chinese" generalizes rather than contradicts
    "asian", "european",
})
# Food names that MultiWOZ users treat as the same cuisine.
FOOD_SYNONYMS = {"english": "british", "australian": "australasian"}
# Slots whose names nest ("asian" / "asian oriental", "cambridge" / "cambridge belfry"):
# two values match if one's words contain the other's.
NESTED_NAME_SLOTS = frozenset({"place", "food"})
MIN_VOCAB_COUNT = 3
MIN_VOCAB_LENGTH = 3


@dataclass(frozen=True)
class Vocabulary:
    """Open-class names (places, cuisines) taken from the items' own user acts."""

    places: frozenset[str]
    foods: frozenset[str]


# A mention is the set of canonical values it could stand for (one value, except for
# ambiguous clock times). Extraction returns the mentions per slot type.
Mention = frozenset[str]
Mentions = dict[str, list[Mention]]


# ------------------------------------------------------------------ vocabulary


def build_vocabulary(items: Iterable[Item]) -> Vocabulary:
    """Collect place and food names that occur at least ``MIN_VOCAB_COUNT`` times in user acts."""
    places: collections.Counter[str] = collections.Counter()
    foods: collections.Counter[str] = collections.Counter()
    for item in items:
        for pairs in (item.get("user_acts") or {}).values():
            for slot, value in pairs:
                value = " ".join(str(value).lower().split())
                if slot in ("Dest", "Depart", "Name"):
                    places[value] += 1
                elif slot == "Food":
                    foods[value] += 1
    return Vocabulary(
        places=_frequent(places, PLACE_STOPLIST),
        foods=_frequent(foods, FOOD_STOPLIST) | frozenset(FOOD_SYNONYMS),
    )


def _frequent(counts: collections.Counter[str], stoplist: frozenset[str]) -> frozenset[str]:
    return frozenset(
        value
        for value, count in counts.items()
        if count >= MIN_VOCAB_COUNT and len(value) >= MIN_VOCAB_LENGTH and value not in stoplist
    )


# ------------------------------------------------------------------ extraction


def extract_mentions(text: str, vocab: Vocabulary) -> Mentions:
    """Return the values ``text`` asserts, per slot type (guarded mentions are left out)."""
    lowered = text.lower().translate(APOSTROPHES)
    mentions: Mentions = {slot: [] for slot in SLOT_TYPES}

    place_spans = _longest_matches(lowered, vocab.places)
    for start, end in _asserted(lowered, place_spans, "place"):
        mentions["place"].append(frozenset({_strip_article(lowered[start:end])}))
    masked = _mask(lowered, place_spans)

    food_spans = _longest_matches(masked, vocab.foods)
    for start, end in _asserted(masked, food_spans, "food"):
        food = masked[start:end]
        mentions["food"].append(frozenset({FOOD_SYNONYMS.get(food, food)}))
    masked = _mask(masked, food_spans)  # so "north american" food is not an area

    for slot, lexicon in (("day", DAYS), ("price", PRICES), ("area", AREAS)):
        for start, end in _asserted(masked, _longest_matches(masked, frozenset(lexicon)), slot):
            mentions[slot].append(frozenset({lexicon[masked[start:end]]}))
    times = [(match.span(), readings) for match in TIME.finditer(masked) if (readings := _time_readings(match))]
    asserted_times = set(_asserted(masked, [span for span, _ in times], "time"))
    mentions["time"] = [readings for span, readings in times if span in asserted_times]
    return mentions


def _asserted(text: str, spans: Sequence[tuple[int, int]], slot: str) -> list[tuple[int, int]]:
    """Keep the spans (in text order) that are not guarded, directly or through coordination."""
    kept: list[tuple[int, int]] = []
    previous: tuple[int, bool] | None = None  # (end, guarded) of the previous mention of this slot
    for start, end in spans:
        guarded = _is_guarded(text, start, slot)
        if not guarded and previous is not None:
            previous_end, previous_guarded = previous
            guarded = previous_guarded and COORDINATION.fullmatch(text[previous_end:start]) is not None
        if not guarded:
            kept.append((start, end))
        previous = (end, guarded)
    return kept


def _longest_matches(text: str, phrases: frozenset[str]) -> list[tuple[int, int]]:
    """Non-overlapping whole-word spans of ``phrases`` in ``text``, preferring the longer phrase at a position.

    A plural "s" is allowed after a phrase ("gastropubs") but is not part of the span.
    """
    pattern = _phrase_pattern(phrases)
    return [match.span("phrase") for match in pattern.finditer(text)] if pattern else []


@functools.lru_cache(maxsize=16)
def _phrase_pattern(phrases: frozenset[str]) -> re.Pattern[str] | None:
    if not phrases:
        return None
    # Regex alternation takes the first alternative that matches, so longest first.
    alternation = "|".join(re.escape(phrase) for phrase in sorted(phrases, key=lambda p: (-len(p), p)))
    return re.compile(r"(?<![a-z0-9])(?P<phrase>" + alternation + r")s?(?![a-z0-9])")


def _mask(text: str, spans: Sequence[tuple[int, int]]) -> str:
    chars = list(text)
    for start, end in spans:
        chars[start:end] = " " * (end - start)
    return "".join(chars)


def _strip_article(name: str) -> str:
    return name[4:] if name.startswith("the ") else name


def _is_guarded(text: str, start: int, slot: str) -> bool:
    """True if a guard word for ``slot`` precedes ``start`` within the same clause."""
    clause_start = 0
    for brk in CLAUSE_BREAK.finditer(text, 0, start):
        clause_start = brk.end()
    preceding = TOKEN.findall(text[clause_start:start])[-GUARD_WINDOW:]
    guards = SLOT_GUARDS.get(slot, COMMON_GUARDS)
    return any(token in guards for token in preceding)


def _time_readings(match: re.Match[str]) -> frozenset[str]:
    if match["minute"] is None and match["meridiem"] is None:
        return frozenset()
    hour, minute = int(match["hour"]), int(match["minute"] or 0)
    meridiem = (match["meridiem"] or "").lower()
    if hour > 24 or minute > 59 or (meridiem and not 1 <= hour <= 12):
        return frozenset()
    if meridiem == "p":
        return frozenset({f"{hour % 12 + 12:02d}:{minute:02d}"})
    if meridiem == "a":
        return frozenset({f"{hour % 12:02d}:{minute:02d}"})
    if 1 <= hour <= 12 and not match["hour"].startswith("0"):  # "06:00" is already 24-hour
        return frozenset({f"{hour % 12:02d}:{minute:02d}", f"{hour % 12 + 12:02d}:{minute:02d}"})
    return frozenset({f"{hour % 24:02d}:{minute:02d}"})


# ------------------------------------------------------------------ comparison


def compare_slot(target: Sequence[Mention], rewrite: Sequence[Mention], nested: bool = False) -> str | None:
    """Classify one slot type: ``kept``, ``dropped``, ``substituted``, or None if the target has no value.

    With ``nested``, two values also match when one's words contain the other's.
    """
    if not target:
        return None
    introduced = any(not _matches_any(mention, target, nested) for mention in rewrite)
    lost = any(not _matches_any(mention, rewrite, nested) for mention in target)
    if introduced and lost:
        return "substituted"
    return "dropped" if lost else "kept"


def _matches_any(mention: Mention, others: Sequence[Mention], nested: bool) -> bool:
    return any(_values_match(value, other_value, nested) for other in others for value in mention for other_value in other)


def _values_match(a: str, b: str, nested: bool) -> bool:
    if a == b:
        return True
    if not nested:
        return False
    a_words, b_words = set(a.split()), set(b.split())
    return a_words <= b_words or b_words <= a_words


def audit_item(item: Item, vocab: Vocabulary) -> dict[str, dict[str, str]]:
    """Map each rewrite variant to ``{slot: outcome}`` for the slots its target asserts."""
    target = extract_mentions(item["target_utterance"], vocab)
    outcomes: dict[str, dict[str, str]] = {}
    for variant in REWRITE_VARIANTS:
        rewrite = extract_mentions(item[f"{variant}_utterance"], vocab)
        outcomes[variant] = {
            slot: outcome
            for slot in SLOT_TYPES
            if (outcome := compare_slot(target[slot], rewrite[slot], slot in NESTED_NAME_SLOTS)) is not None
        }
    return outcomes


def has_speaker_prefix(text: str) -> bool:
    return bool(SPEAKER_PREFIX.match(text))


# ------------------------------------------------------------------ run


def run_audit(items: Sequence[Item], vocab: Vocabulary) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return the flagged records and the summary for ``items``."""
    flagged: list[dict[str, Any]] = []
    counts = {variant: {slot: dict.fromkeys(OUTCOMES, 0) for slot in SLOT_TYPES} for variant in REWRITE_VARIANTS}
    flagged_per_variant = dict.fromkeys(REWRITE_VARIANTS, 0)
    prefixed = {variant: 0 for variant in ("target", *REWRITE_VARIANTS)}

    for item in items:
        for variant in prefixed:
            prefixed[variant] += has_speaker_prefix(item[f"{variant}_utterance"])
        for variant, slots in audit_item(item, vocab).items():
            for slot, outcome in slots.items():
                counts[variant][slot][outcome] += 1
            substituted = sorted(
                slot for slot, outcome in slots.items() if outcome == "substituted" and slot in FLAG_SLOTS
            )
            if substituted:
                flagged_per_variant[variant] += 1
                flagged.append(_flag_record(item, variant, substituted, vocab))

    summary = {
        "schema_version": 1,
        "auditor": "src.data.audit_fact_drift",
        "items": len(items),
        "flag_slots": list(FLAG_SLOTS),
        "flagged": {
            variant: {"count": n, "fraction": round(n / len(items), 4) if items else 0.0}
            for variant, n in flagged_per_variant.items()
        },
        "slot_outcomes": counts,
        "speaker_prefix": prefixed,
        "vocabulary": {"places": len(vocab.places), "foods": len(vocab.foods)},
    }
    return flagged, summary


def _flag_record(item: Item, variant: str, slots: Sequence[str], vocab: Vocabulary) -> dict[str, Any]:
    target = extract_mentions(item["target_utterance"], vocab)
    rewrite = extract_mentions(item[f"{variant}_utterance"], vocab)
    return {
        "item_id": item["item_id"],
        "variant": variant,
        "split": item.get("split"),
        "slots": {
            slot: {"target": _values(target[slot]), "rewrite": _values(rewrite[slot])}
            for slot in slots
        },
    }


def _values(mentions: Sequence[Mention]) -> list[str]:
    return sorted({"|".join(sorted(mention)) for mention in mentions})


def load_flags(path: Path) -> set[tuple[str, str]]:
    """Read ``fact_drift.jsonl`` as a set of ``(item_id, variant)`` pairs to exclude."""
    with path.open(encoding="utf-8") as handle:
        return {(record["item_id"], record["variant"]) for record in map(json.loads, filter(str.strip, handle))}


def write_outputs(out_dir: Path, flagged: Sequence[dict[str, Any]], summary: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "fact_drift.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for record in flagged:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    (out_dir / "fact_drift_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.data.audit_fact_drift",
        description="Flag DIRECT rewrites that substitute a day, time, price, area, food or place stated in the target.",
    )
    parser.add_argument("--items", type=Path, default=DEFAULT_ITEMS)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        items = load_items(args.items)
    except (OSError, ValueError) as exc:
        logger.error("could not read items: %s", exc)
        return 1

    flagged, summary = run_audit(items, build_vocabulary(items))
    write_outputs(args.out_dir, flagged, summary)
    print(json.dumps({key: summary[key] for key in ("items", "flagged", "speaker_prefix")}, indent=2))
    logger.info("wrote %d flagged rewrites to %s", len(flagged), args.out_dir / "fact_drift.jsonl")
    return 0


if __name__ == "__main__":
    sys.exit(main())
