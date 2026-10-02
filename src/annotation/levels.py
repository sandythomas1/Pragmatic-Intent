"""Sample, label, and export request-directness annotation rounds (rubric: docs/annotation_guidelines.md).

Run from the repository root (Python 3.11+, standard library only)::

    python -m src.annotation.levels sample --round 2 --split dev --triples 10
    python -m src.annotation.levels label  --round 2 --annotator A1   # terminal, or:
    python -m src.annotation.levels sheet  --round 2 --annotator A1   # a CSV to fill in Excel
    python -m src.annotation.levels export --round 2 --annotator A1 --rubric v1

Input: ``data/interim/direct/items.jsonl`` (``python -m src.data.build_direct_dataset``).

Files per round, in ``data/interim/labeling/round<N>/`` (git-ignored, because they hold DIRECT text):

* ``sheet.csv``: the blinded items: ``item_id`` and ``utterance`` only, shuffled so that the three
  variants of a DIRECT row are not adjacent and the variant is not visible.
* ``key.csv``: ``item_id`` → ``dialogue_id``, ``turn_index``, ``variant``. Annotators don't open it.
* ``sample_info.json``: seed, split, eligibility counts, and the items.jsonl checksum.
* ``labels_<annotator>.csv``: one annotator's labels. ``label`` saves it after every item; ``sheet``
  pre-fills it with the utterances so it can be filled in Excel instead (save it as "CSV UTF-8").

``export`` writes ``data/annotations/levels_round<N>.csv`` (committed): IDs and labels, no text, no
notes (notes often quote the utterance).

Sampling rules: whole DIRECT rows (all three variants) are drawn uniformly without replacement from
the chosen split. Rows are skipped if ``turn_index == 0`` (every context condition is empty, so the
row carries no context signal), if no mismatch donor exists, or if any earlier round already labeled
that turn.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import random
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.data.direct_dataset import load_items

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ITEMS = REPO_ROOT / "data" / "interim" / "direct" / "items.jsonl"
DEFAULT_LABELING_DIR = REPO_ROOT / "data" / "interim" / "labeling"
DEFAULT_ANNOTATIONS_DIR = REPO_ROOT / "data" / "annotations"
DEFAULT_SEED = 20261001

VARIANTS = ("target", "direct", "indirect")
LABELS = ("L0", "L1", "L2", "L3", "INF", "NR", "?")
KEY_TO_LABEL = {"0": "L0", "1": "L1", "2": "L2", "3": "L3", "i": "INF", "n": "NR", "?": "?"}
SHEET_FIELDS = ("item_id", "utterance")
KEY_FIELDS = ("item_id", "dialogue_id", "turn_index", "variant")
LABEL_FIELDS = ("item_id", "label", "fragment", "notes")
EXCEL_FIELDS = ("item_id", "utterance", "label", "fragment", "notes")
EXPORT_FIELDS = (
    "item_id",
    "dialogue_id",
    "turn_index",
    "variant",
    "label_initial",
    "label_final",
    "fragment",
    "annotator",
    "rubric_version",
)
_ANNOTATOR_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,15}$")
_ROUND_FILE_RE = re.compile(r"^levels_round(\d+)\.csv$")

HELP = """\
  0 = L0 direct        command, need/want, plain question for exactly the info
  1 = L1 conventional  can/could/would you, can I get, is it possible, how about
  2 = L2 strong hint   no formula, but names what is wanted
  3 = L3 mild hint     no formula, does not name what is wanted
  i = INF              asks nothing new, gives task info (incl. "no preference")
  n = NR               thanks / bye / greeting / declining an offer
  ? = undecidable      say why in the note

  Add f for a fragment (no main clause), e.g. "if". Anything after the key is a note: "2 vague 'it'".
  b = back (redo the previous item)   h = help   q = save and quit
"""

logger = logging.getLogger(__name__)


class AnnotationError(Exception):
    """A round's files are missing, inconsistent, or would be overwritten."""


@dataclass(frozen=True)
class Paths:
    round_dir: Path
    export_csv: Path

    @property
    def sheet(self) -> Path:
        return self.round_dir / "sheet.csv"

    @property
    def key(self) -> Path:
        return self.round_dir / "key.csv"

    @property
    def sample_info(self) -> Path:
        return self.round_dir / "sample_info.json"

    def labels(self, annotator: str) -> Path:
        return self.round_dir / f"labels_{annotator}.csv"


def round_paths(round_number: int, labeling_dir: Path, annotations_dir: Path) -> Paths:
    return Paths(labeling_dir / f"round{round_number}", annotations_dir / f"levels_round{round_number}.csv")


# --------------------------------------------------------------------------- CSV helpers


def read_csv(path: Path) -> list[dict[str, str]]:
    """Read UTF-8 with or without a byte-order mark (Excel's "CSV UTF-8" adds one)."""
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    except UnicodeDecodeError as exc:
        raise AnnotationError(f"{path} is not UTF-8; in Excel use File > Save As > CSV UTF-8") from exc


def write_csv(path: Path, fields: Sequence[str], rows: Sequence[dict[str, Any]], *, excel: bool = False) -> None:
    """Write atomically, so a crash mid-save never truncates a labels file.

    ``excel=True`` adds a byte-order mark so Excel decodes the file as UTF-8.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8-sig" if excel else "utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, path)


# --------------------------------------------------------------------------- sample


def labeled_turns(annotations_dir: Path) -> set[tuple[str, int]]:
    """Every (dialogue_id, turn_index) that any committed round already labeled."""
    seen: set[tuple[str, int]] = set()
    for path in sorted(annotations_dir.glob("levels_round*.csv")):
        for row in read_csv(path):
            seen.add((row["dialogue_id"], int(row["turn_index"])))
    return seen


def eligible_items(items: Sequence[dict[str, Any]], split: str, exclude: set[tuple[str, int]]) -> list[dict[str, Any]]:
    eligible = [
        item
        for item in items
        if item["split"] == split
        and item["turn_index"] > 0
        and item["mismatch_status"] == "ok"
        and (item["dialogue_id"], item["turn_index"]) not in exclude
    ]
    return sorted(eligible, key=lambda item: item["item_id"])


def draw_round(
    items: Sequence[dict[str, Any]], round_number: int, triples: int, seed: int
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Draw ``triples`` rows and return (sheet rows, key rows), shuffled and numbered."""
    if triples > len(items):
        raise AnnotationError(f"asked for {triples} triples but only {len(items)} are eligible")
    rng = random.Random(f"{seed}:round{round_number}")
    chosen = rng.sample(list(items), triples)
    utterances = [(item, variant) for item in chosen for variant in VARIANTS]
    rng.shuffle(utterances)

    width = max(2, len(str(len(utterances))))
    sheet, key = [], []
    for index, (item, variant) in enumerate(utterances, start=1):
        item_id = f"r{round_number}-{index:0{width}d}"
        sheet.append({"item_id": item_id, "utterance": item[f"{variant}_utterance"]})
        key.append({"item_id": item_id, "dialogue_id": item["dialogue_id"], "turn_index": item["turn_index"], "variant": variant})
    return sheet, key


def sample(args: argparse.Namespace) -> int:
    paths = round_paths(args.round, args.labeling_dir, args.annotations_dir)
    if paths.sheet.exists() or paths.export_csv.exists():
        raise AnnotationError(f"round {args.round} already exists ({paths.round_dir} or {paths.export_csv}); pick a new round number")

    exclude = labeled_turns(args.annotations_dir)
    eligible = eligible_items(load_items(args.items), args.split, exclude)
    sheet, key = draw_round(eligible, args.round, args.triples, args.seed)

    write_csv(paths.sheet, SHEET_FIELDS, sheet)
    write_csv(paths.key, KEY_FIELDS, key)
    info = {
        "round": args.round,
        "split": args.split,
        "triples": args.triples,
        "utterances": len(sheet),
        "seed": args.seed,
        "eligible_triples": len(eligible),
        "excluded_already_labeled_turns": len(exclude),
        "items_sha256": _sha256(args.items),
    }
    paths.sample_info.write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    logger.info("wrote %d utterances (%d triples from %d eligible %s rows) to %s", len(sheet), args.triples, len(eligible), args.split, paths.round_dir)
    return 0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------- label


@dataclass(frozen=True)
class Answer:
    label: str
    fragment: bool
    notes: str


def parse_answer(text: str) -> Answer | str | None:
    """Parse one input line into an Answer, a command ("b", "h", "q"), or None if invalid."""
    text = text.strip()
    if text in ("b", "h", "q"):
        return text
    head, _, notes = text.partition(" ")
    fragment = len(head) == 2 and head.endswith("f")
    key = head[0] if fragment else head
    if key not in KEY_TO_LABEL:
        return None
    return Answer(KEY_TO_LABEL[key], fragment, notes.strip())


def label(args: argparse.Namespace, read_line: Callable[[str], str] = input, write: Callable[[str], None] = print) -> int:
    paths = round_paths(args.round, args.labeling_dir, args.annotations_dir)
    if not paths.sheet.exists():
        raise AnnotationError(f"no sheet at {paths.sheet}; run the sample command first")
    sheet = read_csv(paths.sheet)
    labels_path = paths.labels(args.annotator)
    existing = {row["item_id"]: row for row in read_csv(labels_path)} if labels_path.exists() else {}
    rows = [{field: existing.get(item["item_id"], {}).get(field, "") for field in LABEL_FIELDS} | {"item_id": item["item_id"]} for item in sheet]

    write(HELP)
    index = _next_unlabeled(rows, 0)
    while index is not None:
        done = sum(1 for row in rows if row["label"])
        write(f"\n[{sheet[index]['item_id']}]  {done}/{len(rows)} labeled\n  {sheet[index]['utterance']}")
        try:
            answer = parse_answer(read_line("label> "))
        except EOFError:
            answer = "q"
        if answer is None:
            write("  ? not a label. Type h for help.")
        elif answer == "h":
            write(HELP)
        elif answer == "q":
            break
        elif answer == "b":
            previous = _previous_labeled(rows, index)
            if previous is None:
                write("  nothing to go back to")
            else:
                rows[previous].update(label="", fragment="", notes="")
                write_csv(labels_path, LABEL_FIELDS, rows)
                index = previous
        else:
            rows[index].update(label=answer.label, fragment="1" if answer.fragment else "0", notes=answer.notes)
            write_csv(labels_path, LABEL_FIELDS, rows)
            index = _next_unlabeled(rows, index)

    done = sum(1 for row in rows if row["label"])
    write(f"\nsaved {done}/{len(rows)} labels to {labels_path}")
    return 0


def _next_unlabeled(rows: Sequence[dict[str, str]], start: int) -> int | None:
    order = list(range(start, len(rows))) + list(range(0, start))
    return next((i for i in order if not rows[i]["label"]), None)


def _previous_labeled(rows: Sequence[dict[str, str]], index: int) -> int | None:
    return next((i for i in range(index - 1, -1, -1) if rows[i]["label"]), None)


# --------------------------------------------------------------------------- sheet


def excel_sheet(args: argparse.Namespace) -> int:
    paths = round_paths(args.round, args.labeling_dir, args.annotations_dir)
    if not paths.sheet.exists():
        raise AnnotationError(f"no sheet at {paths.sheet}; run the sample command first")
    labels_path = paths.labels(args.annotator)
    if labels_path.exists():
        raise AnnotationError(f"{labels_path} already exists; keep labeling in it")
    rows = [{**item, "label": "", "fragment": "", "notes": ""} for item in read_csv(paths.sheet)]
    write_csv(labels_path, EXCEL_FIELDS, rows, excel=True)
    logger.info("wrote %s: fill in label (L0 L1 L2 L3 INF NR ?), fragment (1 or blank), notes; save as CSV UTF-8", labels_path)
    return 0


# --------------------------------------------------------------------------- export


def normalize_label(value: str) -> str | None:
    """Accept a label as written (any case) or as its labeler key; None if it is neither."""
    value = value.strip()
    if value.upper() in LABELS:
        return value.upper()
    return KEY_TO_LABEL.get(value.lower())


def normalize_fragment(value: str) -> str | None:
    return {"": "0", "0": "0", "1": "1"}.get(value.strip())



def export(args: argparse.Namespace) -> int:
    paths = round_paths(args.round, args.labeling_dir, args.annotations_dir)
    labels_path = paths.labels(args.annotator)
    if not labels_path.exists():
        raise AnnotationError(f"no labels at {labels_path}")
    key = {row["item_id"]: row for row in read_csv(paths.key)}
    labels = read_csv(labels_path)

    missing = [row["item_id"] for row in labels if not row["label"]]
    if missing or len(labels) != len(key) or {row["item_id"] for row in labels} != set(key):
        raise AnnotationError(f"labels are incomplete or don't match the key ({len(missing)} unlabeled); finish labeling first")
    bad = [row["item_id"] for row in labels if normalize_label(row["label"]) is None or normalize_fragment(row["fragment"] or "") is None]
    if bad:
        raise AnnotationError(f"invalid label or fragment for {bad}; labels are {', '.join(LABELS)} and fragment is 1 or blank")

    existing = read_csv(paths.export_csv) if paths.export_csv.exists() else []
    if any(row["annotator"] == args.annotator for row in existing):
        raise AnnotationError(f"{paths.export_csv} already has rows from {args.annotator}; edit label_final there instead")

    new_rows = [
        {
            **{field: key[row["item_id"]][field] for field in KEY_FIELDS},
            "label_initial": normalize_label(row["label"]),
            "label_final": normalize_label(row["label"]),
            "fragment": normalize_fragment(row["fragment"] or ""),
            "annotator": args.annotator,
            "rubric_version": args.rubric,
        }
        for row in labels
    ]
    write_csv(paths.export_csv, EXPORT_FIELDS, existing + new_rows)
    logger.info("wrote %d rows for %s to %s", len(new_rows), args.annotator, paths.export_csv)
    return 0


# --------------------------------------------------------------------------- CLI


def _annotator(value: str) -> str:
    if not _ANNOTATOR_RE.match(value):
        raise argparse.ArgumentTypeError("annotator must be a short pseudonymous ID such as A1")
    return value


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m src.annotation.levels", description="Request-directness annotation rounds.")
    parser.add_argument("--labeling-dir", type=Path, default=DEFAULT_LABELING_DIR)
    parser.add_argument("--annotations-dir", type=Path, default=DEFAULT_ANNOTATIONS_DIR)
    commands = parser.add_subparsers(dest="command", required=True)

    p_sample = commands.add_parser("sample", help="draw a new blinded round")
    p_sample.add_argument("--round", type=int, required=True)
    p_sample.add_argument("--split", choices=("train", "dev", "test"), required=True)
    p_sample.add_argument("--triples", type=int, required=True, help="DIRECT rows to draw; each gives 3 utterances")
    p_sample.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p_sample.add_argument("--items", type=Path, default=DEFAULT_ITEMS)

    p_label = commands.add_parser("label", help="label a round interactively (resumable)")
    p_label.add_argument("--round", type=int, required=True)
    p_label.add_argument("--annotator", type=_annotator, required=True)

    p_sheet = commands.add_parser("sheet", help="write an Excel-ready labels CSV to fill in by hand")
    p_sheet.add_argument("--round", type=int, required=True)
    p_sheet.add_argument("--annotator", type=_annotator, required=True)

    p_export = commands.add_parser("export", help="write finished labels to data/annotations/")
    p_export.add_argument("--round", type=int, required=True)
    p_export.add_argument("--annotator", type=_annotator, required=True)
    p_export.add_argument("--rubric", required=True, help="rubric version the labels follow, e.g. v1")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    command = {"sample": sample, "label": label, "sheet": excel_sheet, "export": export}[args.command]
    try:
        return command(args)
    except (AnnotationError, OSError, KeyError, ValueError) as exc:
        logger.error("%s failed: %s", args.command, exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
