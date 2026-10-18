"""Provisional auto-v2 wording rules, frozen before the held-out round-2 check.

No per-item held-out errors are development inputs. auto-v1 remains the default.
CLI: freeze, validate (round 2 only), distribution, spotcheck, spotcheck-report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
from pathlib import Path

from src.data import auto_levels as v1
from src.data.audit_fact_drift import Vocabulary, build_vocabulary
from src.data.direct_dataset import Item, load_items

RULES_VERSION = "auto-v2"
DEFAULT_SEED = 20261018
_CLOSING = re.compile(
    r"^(?:(?:yes|okay|ok|great|perfect|thanks|thank you)[,.! ]+)*"
    r"(?:(?:that(?:'s| is| will be)|this is|it is)\s+(?:all|everything)"
    r"(?:\s+(?:i|we)\s+(?:need(?:ed)?|want(?:ed)?))?(?:\s+for\s+(?:now|today))?"
    r"|(?:i(?:'m| am)|we(?:'re| are))\s+all\s+set)"
    r"[,.! ]*(?:(?:thanks|thank you|goodbye|bye|cheers)[,.! ]*)*$"
)
_ANSWER = re.compile(
    r"^(?:yes[,! ]*)?(?:that|it|this)(?:'s| is)?\s+"
    r"(?:works?(?:\s+for\s+(?:me|us))?|sounds?\s+(?:good|great|fine|perfect)(?:\s+to\s+(?:me|us))?)"
    r"[.! ]*(?:(?:thanks|thank you)[.! ]*)?$"
)
_DETAIL = re.compile(
    r"\b(?:bistros?|eater(?:y|ies)|gastropubs?|pubs?|venues?|rides?|lifts?|transport|transportation|"
    r"lodgings?|hostels?|motels?|supper|brunch|fare|cost|budget|expensive|inexpensive|affordable)\b"
    r"|\b(?:around|after|before|by|at)\s+(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b"
)
_PLACE = re.compile(r"\b(?:to|from|near|at|in)\s+(?:the\s+)?[A-Z][a-z]+(?:[-'][A-Z]?[a-z]+)*\b")
_WH = re.compile(v1._SENTENCE_START + r"(?:what|how)\s+about\b")


def auto_level(text: str, social_only: bool, vocab: Vocabulary) -> v1.AutoLevel:
    """Apply v2 to wording only, retaining the disclosed v1 social-act exception."""
    if social_only:
        return v1.AutoLevel("NR", "social_acts")
    lowered = v1._normalize(text)
    # An anchored whole-turn closing cannot swallow a later independent request.
    if _CLOSING.fullmatch(lowered):
        return v1.AutoLevel("NR", "closing")
    l0 = [(name, pattern) for name, pattern in v1.L0_PATTERNS if name != "wh_question"]
    for name, pattern in l0:
        if pattern.search(lowered):
            return v1.AutoLevel("L0", name)
    # A what/how-about formula is L1; a genuine separate wh question remains L0.
    for match in v1.L0_PATTERNS[4][1].finditer(lowered):
        if not _WH.match(lowered, match.start()):
            return v1.AutoLevel("L0", "wh_question")
    for name, pattern in v1.L1_PATTERNS:
        if pattern.search(lowered):
            return v1.AutoLevel("L1", name)
    if _ANSWER.fullmatch(lowered):
        return v1.AutoLevel("INF", "confirmation")
    assigned = v1.auto_level(text, False, vocab)
    if assigned.level == "L3" and (_DETAIL.search(lowered) or _PLACE.search(text)):
        return v1.AutoLevel("L2", "extra_wording_detail")
    return assigned


def rules_sha256() -> str:
    """Hash normalized source for both rule modules, independent of checkout line endings."""
    digest = hashlib.sha256()
    for path in (Path(v1.__file__), Path(__file__)):
        digest.update(path.read_text(encoding="utf-8").encode("utf-8"))
    return digest.hexdigest()


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def freeze(path: Path) -> dict:
    """Seal a version's source; refuse to replace a different existing freeze."""
    record = {"rules_version": RULES_VERSION, "rules_sha256": rules_sha256()}
    if path.exists():
        return require_freeze(path)
    _write(path, record)
    return record


def require_freeze(path: Path) -> dict:
    """Fail if the source differs from the frozen version or no freeze exists."""
    if not path.exists():
        raise ValueError("freeze auto-v2 before validation or drawing a check")
    record = json.loads(path.read_text(encoding="utf-8"))
    if record != {"rules_version": RULES_VERSION, "rules_sha256": rules_sha256()}:
        raise ValueError("auto-v2 differs from its freeze; use a new rule version")
    return record


def fresh_spotcheck(items: list[Item], vocab: Vocabulary, historical: set[tuple[str, int]],
                    *, count: int, seed: int) -> tuple[list[dict], list[dict], dict]:
    """Reconstruct v1's original sample and exclude every sampled turn, across variants."""
    _, old_key = v1.draw_spotcheck(items, vocab, "L3", 40, v1.DEFAULT_SPOTCHECK_SEED, historical)
    by_id = {item["item_id"]: item for item in items}
    old_turns = {(by_id[row["item_id"]]["dialogue_id"], by_id[row["item_id"]]["turn_index"]) for row in old_key}
    excluded = historical | old_turns
    sheet, key = v1.draw_spotcheck(items, vocab, "L3", count, seed, excluded, version=RULES_VERSION)
    exclusion_bytes = json.dumps(sorted(excluded), separators=(",", ":")).encode()
    snapshot = {"rules_version": RULES_VERSION, "rules_sha256": rules_sha256(), "seed": seed,
                "old_v1_seed": v1.DEFAULT_SPOTCHECK_SEED, "old_v1_count": 40,
                "excluded_turns": len(excluded), "exclusions_sha256": hashlib.sha256(exclusion_bytes).hexdigest(),
                "items": [{"row_id": r["row_id"], "item_id": r["item_id"], "variant": r["variant"]} for r in key]}
    return sheet, key, snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "validate", "distribution", "spotcheck", "spotcheck-report"))
    parser.add_argument("--items", type=Path, default=v1.DEFAULT_ITEMS)
    parser.add_argument("--annotations", type=Path, default=v1.DEFAULT_ANNOTATIONS)
    parser.add_argument("--out-dir", type=Path, default=Path("outputs/auto_levels/auto-v2"))
    parser.add_argument("--spotcheck-dir", type=Path, default=Path("data/interim/auto_levels/auto-v2/spotcheck_L3"))
    parser.add_argument("--count", type=int, default=40)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        freeze_path = args.out_dir / "freeze.json"
        if args.command == "freeze":
            print(json.dumps(freeze(freeze_path), sort_keys=True))
            return 0
        sealed = require_freeze(freeze_path)
        if args.command == "spotcheck-report":
            snapshot = json.loads((args.spotcheck_dir / "snapshot.json").read_text(encoding="utf-8"))
            if snapshot["rules_sha256"] != sealed["rules_sha256"]:
                raise ValueError("spot-check rules differ from the freeze")
            key = v1.read_csv(args.spotcheck_dir / "key.csv")
            identities = [{k: row[k] for k in ("row_id", "item_id", "variant")} for row in key]
            if identities != snapshot["items"]:
                raise ValueError("spot-check key differs from its snapshot")
            result = v1.spotcheck_report(v1.read_csv(args.spotcheck_dir / "sheet.csv"), key, version=RULES_VERSION)
        else:
            items = load_items(args.items)
            vocab = build_vocabulary(items)
            if args.command == "validate":
                path = args.annotations / "levels_round2.csv"
                if not path.exists():
                    raise ValueError("held-out levels_round2.csv is missing")
                result = v1.validate(items, v1.load_human_labels([path]), vocab, version=RULES_VERSION)
                result["evaluation_role"] = "held_out_round2"
            elif args.command == "distribution":
                result = v1.distribution(items, vocab, version=RULES_VERSION)
            else:
                if any((args.spotcheck_dir / name).exists() for name in ("sheet.csv", "key.csv", "snapshot.json")):
                    raise ValueError("fresh spot-check files already exist; do not overwrite human work")
                sheet, key, snapshot = fresh_spotcheck(items, vocab, v1.labeled_turns(args.annotations),
                                                      count=args.count, seed=args.seed)
                snapshot["inputs_sha256"] = hashlib.sha256(args.items.read_bytes()).hexdigest()
                v1.write_csv(args.spotcheck_dir / "sheet.csv", v1.SPOTCHECK_FIELDS, sheet, excel=True)
                v1.write_csv(args.spotcheck_dir / "key.csv", v1.SPOTCHECK_KEY_FIELDS, key)
                _write(args.spotcheck_dir / "snapshot.json", snapshot)
                print(f"Prepared {len(sheet)} unlabeled L3 rows at {args.spotcheck_dir / 'sheet.csv'}")
                return 0
        result.update(sealed)
        if args.items.exists():
            result["inputs_sha256"] = hashlib.sha256(args.items.read_bytes()).hexdigest()
        _write(args.out_dir / f"{args.command}.json", result)
        print(json.dumps(result.get("agreement", {k: v for k, v in result.items() if k != "rows"}), sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, v1.AnnotationError) as error:
        logging.error("auto-v2 check failed: %s", error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
