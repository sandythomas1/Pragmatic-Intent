"""Assign rubric-v2 directness levels to DIRECT utterances with fixed wording rules (option A).

Option A (2026-10-13) replaces most hand labeling with mechanical levels. The rules transcribe
[rubric v2](../../docs/annotation_guidelines.md) and read the wording only (R1). They are *not*
human gold: validate them against the hand-labeled calibration rounds before using them, and
report their agreement next to every result that uses them.

Rules ``auto-v1``, applied in order (the first that fires wins, so the most direct request in
the utterance decides the level, as in the rubric's step 2):

==========  ==================================================================================
``NR``      the target turn's MultiWOZ user acts are all thanks / bye / greeting
``L0``      a need/want statement ("I need", "I'd like", "I'm looking for" per R5), a command
            at the start of a clause ("Book it", "Please send ..."), or a plain question
            (wh-question, or a yes/no question about the thing wanted, per R2)
``L1``      a conventional request formula (R7): can/could/would/will you, can/could/may I,
            would you mind, is it possible / would it be possible, are you able, how/what about
``NR``      turning down an offer (R4): "I don't need ...", "no need", "no thanks", "not now"
``INF``     a "no preference" answer (R4), a bare yes/no/okay, or a fragment with no verb (R3)
``L2``      a hint that names a detail of what's wanted (R6): a day, time, price, area, cuisine,
            place name, party size, or a service/attribute word (train, table, phone number ...)
``L3``      anything else
==========  ==================================================================================

Run from the repository root (Python 3.12, standard library only)::

    python -m src.data.auto_levels validate      # agreement with data/annotations/levels_round*.csv
    python -m src.data.auto_levels distribution  # level counts per split and DIRECT variant
    python -m src.data.auto_levels spotcheck --level L3          # blinded OK/wrong sheet from dev
    python -m src.data.auto_levels spotcheck-report --level L3   # precision once the sheet is filled

``validate`` and ``distribution`` write JSON with IDs and counts only (no utterance text) to
``outputs/auto_levels/``. Spot-check sheets hold DIRECT text, so they live in git-ignored
``data/interim/auto_levels/spotcheck_<level>/``; the report writes counts only.

Spot checks draw from **dev** only: anything a researcher reads stays out of the test split.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import logging
import random
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.annotation.levels import AnnotationError, labeled_turns, normalize_label, read_csv, write_csv
from src.data.audit_fact_drift import APOSTROPHES, Vocabulary, build_vocabulary, extract_mentions
from src.data.direct_dataset import Item, is_social_only, load_items
from src.evaluation.metrics import classification_metrics, cohen_kappa

logger = logging.getLogger(__name__)

RULES_VERSION = "auto-v1"
LEVELS = ("L0", "L1", "L2", "L3", "INF", "NR")
VARIANTS = ("target", "direct", "indirect")

DEFAULT_ITEMS = Path("data/interim/direct/items.jsonl")
DEFAULT_ANNOTATIONS = Path("data/annotations")
DEFAULT_OUT_DIR = Path("outputs/auto_levels")
DEFAULT_SPOTCHECK_DIR = Path("data/interim/auto_levels")
DEFAULT_SPOTCHECK_SEED = 20261013
SPOTCHECK_FIELDS = ("row_id", "utterance", "rule_level", "verdict", "better_level", "notes")
SPOTCHECK_KEY_FIELDS = ("row_id", "item_id", "variant", "rule")
VERDICTS = ("ok", "wrong")
_FORMULA_PREFIXES = ("=", "+", "-", "@")

# Words that may open a clause before its main verb ("Yes, please book it", "Great. Also, find ...").
_OPENER = r"(?:(?:yes|yeah|yea|yep|sure|ok|okay|great|perfect|thanks|thank you|no|nope|well|so|and|also|then|"
_OPENER += r"actually|alright|awesome|excellent|good|fine|cool|oh|hi|hello|hmm|um|umm|now|first|next|lastly|finally)"
_OPENER += r"[\s,.!]+)*"
_CLAUSE_START = r"(?:^|[.!?;:]\s*|,\s*)" + _OPENER

_COMMAND_VERBS = (
    "book", "find", "give", "tell", "send", "get", "show", "reserve", "make", "help", "check", "search",
    "look", "provide", "recommend", "suggest", "list", "pick", "choose", "let", "call", "arrange",
    "confirm", "email", "text", "schedule", "locate", "please",
)
_WH = r"(?:what|whats|where|when|which|who|whom|whose|how(?!\s+about))"
_YES_NO = (r"(?:(?:is|are|was|were|does|do|did|has|have|had)\s+(?:there|it|that|this|they|the|any|its|their|these|those)"
           r"|(?:do|does|did)\s+(?:you|they)\s+(?:have|know|offer|serve|happen|provide))")
_SENTENCE_START = r"(?:^|[.!?;:]\s*)" + _OPENER

L0_PATTERNS = (
    ("want_statement", re.compile(
        r"\b(?:i|we)(?:'ll|'d)?\s+(?:(?:will|would|do|really|also|just|still|definitely|actually|only|now|absolutely)\s+)*"
        r"(?:need|want|require)s?\b"
    )),
    ("would_like", re.compile(r"\b(?:(?:i|we)(?:'d|\s+would)|id)\s+(?:also\s+|really\s+|just\s+)?(?:like|love|prefer)\b")),
    ("looking_for", re.compile(r"\b(?:i|we)\s*(?:'m|am|are|'re)\s+(?:also\s+|now\s+|just\s+)?(?:looking|searching)\s+(?:for|to)\b")),
    ("command", re.compile(_CLAUSE_START + r"(?:" + "|".join(_COMMAND_VERBS) + r")\b")),
    ("wh_question", re.compile(_SENTENCE_START + _WH + r"\b(?!\s+(?:i|we)\b)")),
    ("yes_no_question", re.compile(_SENTENCE_START + _YES_NO + r"\b[^.!]*\?")),
)
L1_PATTERNS = (
    ("you_formula", re.compile(r"\b(?:can|could|would|will|wo?n't|cant|couldn't|wouldn't)\s+(?:you|u|ya)\b")),
    ("i_formula", re.compile(r"\b(?:can|could|may|might)\s+(?:i|we)\b")),
    ("would_you_mind", re.compile(r"\b(?:would|do)\s+you\s+mind\b")),
    ("possible", re.compile(r"\b(?:is\s+it|would\s+it\s+be|will\s+it\s+be|it\s+is|it's)\s+possible\b")),
    ("able", re.compile(r"\b(?:are|would|will)\s+you\s+(?:be\s+)?able\b")),
    ("if_you_could", re.compile(r"\b(?:if|whether)\s+(?:you|it)\s+(?:could|can|would|might)\b")),
    ("how_about", re.compile(r"\b(?:how|what)\s+about\b")),
)
INF_PATTERNS = (
    ("no_preference", re.compile(
        r"\b(?:no|any)\s+(?:particular\s+)?preference\b|\bdo(?:n't|nt|\s+not)\s+(?:really\s+)?(?:care|mind)\b"
        r"|\b(?:does|doesn't|doesnt|does\s+not)\s+(?:really\s+)?matter\b|\beither\s+(?:one\s+)?(?:is|would\s+be)\s+fine\b"
        r"|\b(?:whatever|anything|any|either)\s+(?:is|will\s+do|works)\b|\bnot\s+picky\b"
    )),
    ("bare_answer", re.compile(
        r"^(?:(?:yes|yeah|yea|yep|sure|ok|okay|no|nope|that\s+works|sounds\s+good|that's\s+fine|fine|great|perfect)[\s,.!]*)+$"
    )),
)
NR_PATTERNS = (
    ("decline", re.compile(
        r"\b(?:don't|dont|do\s+not)\s+(?:really\s+|actually\s+)?need\b|\bno\s+need\b"
        r"|^(?:no|nope)[\s,.!]+(?:thanks?|thank\s+you)\b|\bnot\s+(?:right\s+)?(?:now|today|yet)\b"
    )),
)
# R3: a fragment that only lists details has no verb. A token from this list (or one ending in
# -ing/-ed) counts as a verb; anything else is treated as a fragment.
_VERB = re.compile(
    r"\b(?:is|are|am|was|were|be|been|being|'s|'re|'m|'ll|'d|'ve|have|has|had|do|does|did|will|would|can|could|"
    r"should|shall|may|might|must|need|needs|want|wants|go|goes|leave|leaves|arrive|arrives|travel|stay|come|"
    r"get|eat|take|book|find|like|prefer|think|know|see|work|works|sounds?|plan|hope|matter|care|"
    r"\w+ing|\w+ed)\b|'(?:s|re|m|ll|d|ve)\b"
)
_NUMBER_WORDS = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
DETAIL_PATTERNS = (
    ("party_or_stay", re.compile(
        _NUMBER_WORDS + r"\s+(?:of\s+us|people|persons|person|guests|adults|tickets?|nights?|days?|rooms?|seats?)\b"
        r"|\b(?:just\s+)?(?:me|myself)\s+and\b|\bby\s+myself\b|\bjust\s+(?:me|myself)\b"
    )),
    ("clock_word", re.compile(r"\b" + _NUMBER_WORDS + r"\s*(?:o'?clock|am|pm|a\.m\.|p\.m\.)|\b(?:noon|midnight|morning|afternoon|evening)\b")),
    ("service_word", re.compile(
        r"\b(?:trains?|taxis?|cabs?|hotels?|guest\s*houses?|guesthouses?|b\s*&\s*b|restaurants?|tables?|rooms?|"
        r"tickets?|reservations?|booking|phone|number|address|postcode|post\s+code|reference|ref|fee|entrance|"
        r"attractions?|museums?|colleges?|parks?|theatres?|theaters?|cinemas?|pools?|churches|church|gallery|"
        r"wifi|wi-fi|internet|parking|stars?|food|cuisine|dinner|lunch|breakfast|departure|destination|arrive|"
        r"arrival|leave|leaving|depart|departing|travel\s+time|hospital|police|lodging|accommodations?|place\s+to\s+stay)\b"
    )),
)


@dataclass(frozen=True)
class AutoLevel:
    level: str
    rule: str  # which pattern fired, for audits


def _normalize(text: str) -> str:
    return " ".join(text.lower().translate(APOSTROPHES).split())


def auto_level(text: str, social_only: bool, vocab: Vocabulary) -> AutoLevel:
    """Return the ``auto-v1`` level of ``text``; ``social_only`` comes from the turn's user acts."""
    if social_only:
        return AutoLevel("NR", "social_acts")
    lowered = _normalize(text)
    for level, patterns in (("L0", L0_PATTERNS), ("L1", L1_PATTERNS), ("NR", NR_PATTERNS), ("INF", INF_PATTERNS)):
        for name, pattern in patterns:
            if pattern.search(lowered):
                return AutoLevel(level, name)
    if not _VERB.search(lowered):
        return AutoLevel("INF", "fragment")
    if any(extract_mentions(text, vocab).values()):
        return AutoLevel("L2", "slot_value")
    for name, pattern in DETAIL_PATTERNS:
        if pattern.search(lowered):
            return AutoLevel("L2", name)
    return AutoLevel("L3", "no_detail")


def level_item(item: Item, variant: str, vocab: Vocabulary) -> AutoLevel:
    return auto_level(item[f"{variant}_utterance"], is_social_only(item), vocab)


# ------------------------------------------------------------------ validation


@dataclass(frozen=True)
class HumanLabel:
    round_name: str
    item_id: str
    dialogue_id: str
    turn_index: int
    variant: str
    initial: str
    final: str


def load_human_labels(paths: Iterable[Path], annotator: str = "A1") -> list[HumanLabel]:
    """Read every ``levels_round*.csv`` row by ``annotator``; ``?`` labels are kept (they count as misses)."""
    labels: list[HumanLabel] = []
    for path in paths:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if row["annotator"] != annotator:
                    continue
                initial, final = normalize_label(row["label_initial"]), normalize_label(row["label_final"])
                if initial is None or final is None or row["variant"] not in VARIANTS:
                    raise ValueError(f"invalid row {row.get('item_id')!r} in {path}")
                labels.append(HumanLabel(
                    path.stem.removeprefix("levels_"), row["item_id"], row["dialogue_id"],
                    int(row["turn_index"]), row["variant"], initial, final,
                ))
    return labels


def validate(items: Sequence[Item], labels: Sequence[HumanLabel], vocab: Vocabulary) -> dict[str, Any]:
    """Agreement of ``auto-v1`` with the human labels, per round and pooled (IDs and counts only)."""
    by_turn = {(item["dialogue_id"], item["turn_index"]): item for item in items}
    rows: list[dict[str, Any]] = []
    for label in labels:
        item = by_turn.get((label.dialogue_id, label.turn_index))
        if item is None:
            raise ValueError(f"{label.item_id}: no DIRECT item for {label.dialogue_id} turn {label.turn_index}")
        auto = level_item(item, label.variant, vocab)
        rows.append({"round": label.round_name, "item_id": label.item_id, "variant": label.variant,
                     "initial": label.initial, "final": label.final, "auto": auto.level, "rule": auto.rule})

    groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in rows:
        groups[row["round"]].append(row)
        groups["all"].append(row)
    report = {name: _agreement(group) for name, group in sorted(groups.items())}
    return {"rules_version": RULES_VERSION, "agreement": report, "rows": rows}


def _agreement(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    labels = LEVELS + ("?",)
    out: dict[str, Any] = {"n": len(rows)}
    for reference in ("final", "initial"):
        pairs = [(row[reference], row["auto"]) for row in rows]
        metrics = classification_metrics(pairs, labels)
        out[reference] = {
            "accuracy": round(metrics["accuracy"], 4),
            "kappa": round(cohen_kappa(pairs), 4),
            "confusion": {gold: {p: n for p, n in row.items() if n} for gold, row in metrics["confusion"].items()
                          if any(row.values())},
        }
    out["by_variant_final"] = {
        variant: round(sum(r["final"] == r["auto"] for r in group) / len(group), 4)
        for variant in VARIANTS if (group := [r for r in rows if r["variant"] == variant])
    }
    return out


def distribution(items: Sequence[Item], vocab: Vocabulary) -> dict[str, Any]:
    """Level and rule counts per split and DIRECT variant, over items that have user acts."""
    counts: dict[str, dict[str, collections.Counter[str]]] = {}
    rules: collections.Counter[str] = collections.Counter()
    for item in items:
        if not item.get("user_acts"):
            continue
        for variant in VARIANTS:
            auto = level_item(item, variant, vocab)
            counts.setdefault(item["split"], {}).setdefault(variant, collections.Counter())[auto.level] += 1
            rules[f"{auto.level}:{auto.rule}"] += 1
    return {
        "rules_version": RULES_VERSION,
        "levels": {split: {variant: {level: c[level] for level in LEVELS} for variant, c in sorted(by_v.items())}
                   for split, by_v in sorted(counts.items())},
        "rules": dict(sorted(rules.items())),
    }


# ------------------------------------------------------------------ spot check


def draw_spotcheck(
    items: Sequence[Item], vocab: Vocabulary, level: str, count: int, seed: int,
    exclude_turns: set[tuple[str, int]] = frozenset(),
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Seeded uniform draw of ``count`` dev utterances the rules put at ``level``: (sheet rows, key rows).

    Turns in ``exclude_turns`` (already hand-labeled) are skipped. Rows are shuffled and carry
    opaque IDs, so the DIRECT variant is not visible.
    """
    if level not in LEVELS:
        raise ValueError(f"unknown level {level!r}")
    pool: list[tuple[Item, str, AutoLevel]] = []
    for item in items:
        if item["split"] != "dev" or (item["dialogue_id"], item["turn_index"]) in exclude_turns:
            continue
        for variant in VARIANTS:
            auto = level_item(item, variant, vocab)
            if auto.level == level:
                pool.append((item, variant, auto))
    if len(pool) < count:
        raise ValueError(f"only {len(pool)} dev utterances are {level}; asked for {count}")
    drawn = random.Random(seed).sample(pool, count)
    sheet, key = [], []
    for index, (item, variant, auto) in enumerate(drawn, start=1):
        row_id = f"s-{index:03d}"
        text = " ".join(item[f"{variant}_utterance"].split())
        sheet.append({"row_id": row_id, "utterance": "'" + text if text.startswith(_FORMULA_PREFIXES) else text,
                      "rule_level": level, "verdict": "", "better_level": "", "notes": ""})
        key.append({"row_id": row_id, "item_id": item["item_id"], "variant": variant, "rule": auto.rule})
    return sheet, key


def spotcheck_report(sheet: Sequence[dict[str, str]], key: Sequence[dict[str, str]]) -> dict[str, Any]:
    """Precision of the rule level from a filled sheet; every row needs a verdict."""
    rules = {row["row_id"]: row["rule"] for row in key}
    problems: list[str] = []
    verdicts: collections.Counter[str] = collections.Counter()
    better: collections.Counter[str] = collections.Counter()
    for row in sheet:
        row_id = row.get("row_id", "")
        verdict = (row.get("verdict") or "").strip().lower()
        if row_id not in rules:
            problems.append(f"{row_id or '(blank)'}: not in the key")
            continue
        if verdict not in VERDICTS:
            problems.append(f"{row_id}: verdict must be ok or wrong, got {verdict!r}")
            continue
        verdicts[verdict] += 1
        if verdict == "wrong":
            raw = (row.get("better_level") or "").strip()
            label = normalize_label(raw) if raw else None
            if label is None:
                problems.append(f"{row_id}: a wrong row needs better_level (L0 L1 L2 L3 INF NR ?)")
                continue
            better[label] += 1
    if len(sheet) != len(rules):
        problems.append(f"sheet has {len(sheet)} rows, key has {len(rules)}")
    if problems:
        raise ValueError("spot-check sheet has problems:\n  " + "\n  ".join(problems))
    total = sum(verdicts.values())
    return {"rules_version": RULES_VERSION, "n": total, "ok": verdicts["ok"], "wrong": verdicts["wrong"],
            "precision": round(verdicts["ok"] / total, 4), "better_level_when_wrong": dict(better.most_common())}


# ------------------------------------------------------------------ CLI


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.data.auto_levels", description=__doc__.split("\n")[0])
    parser.add_argument("command", choices=("validate", "distribution", "spotcheck", "spotcheck-report"))
    parser.add_argument("--items", type=Path, default=DEFAULT_ITEMS)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--annotator", default="A1")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--level", default="L3", help="spot check: the rule level to check")
    parser.add_argument("--count", type=int, default=40, help="spot check: rows to draw")
    parser.add_argument("--seed", type=int, default=DEFAULT_SPOTCHECK_SEED)
    parser.add_argument("--spotcheck-dir", type=Path, default=DEFAULT_SPOTCHECK_DIR)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    folder = args.spotcheck_dir / f"spotcheck_{args.level}"

    try:
        if args.command == "spotcheck-report":
            result = spotcheck_report(read_csv(folder / "sheet.csv"), read_csv(folder / "key.csv"))
            summary: Any = result
        else:
            items = load_items(args.items)
            vocab = build_vocabulary(items)
            if args.command == "spotcheck":
                if (folder / "sheet.csv").exists():
                    raise ValueError(f"{folder / 'sheet.csv'} exists; move it away to draw again")
                sheet, key = draw_spotcheck(items, vocab, args.level, args.count, args.seed,
                                            labeled_turns(args.annotations))
                write_csv(folder / "sheet.csv", SPOTCHECK_FIELDS, sheet, excel=True)
                write_csv(folder / "key.csv", SPOTCHECK_KEY_FIELDS, key)
                logger.info("wrote %d rows to %s", len(sheet), folder / "sheet.csv")
                return 0
            if args.command == "validate":
                paths = sorted(args.annotations.glob("levels_round*.csv"))
                if not paths:
                    raise ValueError(f"no levels_round*.csv in {args.annotations}")
                result = validate(items, load_human_labels(paths, args.annotator), vocab)
                summary = {name: {k: v for k, v in group.items() if k != "rows"}
                           for name, group in result["agreement"].items()}
            else:
                result = distribution(items, vocab)
                summary = result["levels"]
    except (OSError, ValueError, AnnotationError) as exc:
        logger.error("%s", exc)
        return 1

    args.out_dir.mkdir(parents=True, exist_ok=True)
    name = f"spotcheck_{args.level}" if args.command == "spotcheck-report" else args.command
    out = args.out_dir / f"{name}.json"
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    logger.info("wrote %s", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
