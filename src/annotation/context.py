"""Contextual annotation passes: draw, register, sheets, export and validation (spec 003).

Run from the repository root (Python 3.12, standard library only)::

    python -m src.annotation.context draw --batch pilot1 --count 40 --seed 20261011
    python -m src.annotation.context register-literary --batch pilot1   # after screening export
    python -m src.annotation.context sheet  --pass form --batch pilot1 --annotator A1
    python -m src.annotation.context export --pass form --batch pilot1 --annotator A1 --rubric v2
    python -m src.annotation.context taxonomy-check

Inputs: ``data/interim/direct/items.jsonl`` and ``dialogues.jsonl``
(``python -m src.data.build_direct_dataset``).

Committed output: ``data/annotations/context_items.csv`` (IDs, hashes and provenance; no text).
Local, git-ignored work files go under ``data/interim/context/``.

See ``specs/003-contextual-annotation/spec.md`` for the protocol and ``context_items`` for the
draw rule.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from src.annotation import context_items as ci
from src.annotation import context_passes as cp
from src.annotation import context_schema as cs
from src.annotation import context_taxonomy as ct
from src.annotation.levels import AnnotationError, labeled_dialogues, read_csv
from src.data import download_sources
from src.data.direct_dataset import load_dialogues, load_items
from src.literary import screening as sc
from src.literary import sources as ls

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ANNOTATIONS_DIR = REPO_ROOT / "data" / "annotations"
DEFAULT_WORK_DIR = REPO_ROOT / "data" / "interim" / "context"
DEFAULT_DIRECT_DIR = REPO_ROOT / "data" / "interim" / "direct"
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "raw"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Dirs:
    annotations_dir: Path
    work_dir: Path
    direct_dir: Path
    raw_dir: Path = DEFAULT_RAW_DIR
    manifest: Path = download_sources.DEFAULT_MANIFEST
    literary_work_dir: Path = sc.DEFAULT_WORK_DIR  # spec 002's sheet dir; this module never writes there

    @property
    def registry(self) -> Path:
        return self.annotations_dir / ci.REGISTRY_FILE

    @property
    def items(self) -> Path:
        return self.direct_dir / "items.jsonl"

    @property
    def dialogues(self) -> Path:
        return self.direct_dir / "dialogues.jsonl"

    @property
    def taxonomy(self) -> Path:
        return self.annotations_dir / ct.TAXONOMY_FILE

    @property
    def literary(self) -> sc.Dirs:
        """Spec 002's paths: its committed families file and screening log live in annotations_dir."""
        return sc.Dirs(self.raw_dir, self.manifest, self.annotations_dir, self.literary_work_dir)


def draw(dirs: Dirs, *, batch: str, count: int, seed: int, date: str | None) -> list[dict[str, str]]:
    """Draw ``count`` dev dialogues (one turn each) into ``batch`` and append them to the registry."""
    cs.batch_id(batch)
    registry = ci.load_registry(dirs.registry)
    if ci.batch_has_drawn_items(registry, batch):
        raise ci.RegistryError([f"batch {batch!r} already has drawn dialogue items; draw into a new batch name"])

    excluded = labeled_dialogues(dirs.annotations_dir)
    registered = {row["source_ref"].split("#")[0] for row in registry if row["stratum"] == "dialogue"}
    pool = ci.dialogue_pool(load_items(dirs.items), excluded, registered)
    rows = ci.draw_dialogues(
        pool,
        load_dialogues(dirs.dialogues),
        count=count,
        seed=seed,
        batch=batch,
        inputs_sha256=ci.file_sha256(dirs.items),
        registered_on=ci.today(date),
    )
    ci.write_registry(dirs.registry, [*registry, *rows])
    logger.info(
        "drew %d of %d eligible dev dialogues into batch %s (excluded %d already-labeled, %d already-registered); registry now has %d items",
        len(rows),
        len(pool),
        batch,
        len(excluded),
        len(registered),
        len(registry) + len(rows),
    )
    return rows


def register_literary(dirs: Dirs, *, batch: str, date: str | None) -> list[dict[str, str]]:
    """Register every screened-in literary candidate not yet in the registry (idempotent)."""
    registry = ci.load_registry(dirs.registry)
    try:
        log = sc.load_log(dirs.literary)
        families = {family["family_id"]: family for family in sc.load_families(dirs.literary)}
    except sc.ScreeningError as error:
        raise ci.RegistryError([str(error)]) from None
    rows = ci.literary_rows(log, families, registry, batch=batch, registered_on=ci.today(date))
    if rows:
        ci.write_registry(dirs.registry, [*registry, *rows])
    counts = {status: sum(entry["status"] == status for entry in log) for status in sc.STATUSES}
    logger.info(
        "registered %d new literary item(s) into batch %s; screening log has %s",
        len(rows),
        batch,
        ", ".join(f"{count} {status}" for status, count in counts.items()),
    )
    return rows


def target_texts(dirs: Dirs, registry: Sequence[dict[str, str]]) -> dict[str, str]:
    """Reconstruct each item's exact target from its source and check it against the registry hash.

    Dialogue targets come from ``dialogues.jsonl``; literary targets from the pinned edition at the
    screening log's offsets. A mismatch means a source or log changed after registration, so the
    sheet would show different text than the item was registered with: that is an error.
    """
    texts: dict[str, str] = {}
    problems: list[str] = []
    dialogue_rows = [row for row in registry if row["stratum"] == "dialogue"]
    literary_rows = [row for row in registry if row["stratum"] == "literary"]
    if dialogue_rows:
        dialogues = load_dialogues(dirs.dialogues)
        for row in dialogue_rows:
            dialogue_id, turn = row["source_ref"].split("#")
            turns = dialogues.get(dialogue_id, [])
            texts[row["item_id"]] = turns[int(turn)].text if int(turn) < len(turns) else ""
    if literary_rows:
        log = {entry["candidate_id"]: entry for entry in sc.load_log(dirs.literary)}
        editions = sc.Editions(dirs.literary)
        for row in literary_rows:
            entry = log.get(row["item_id"])
            if entry is None:
                problems.append(f"{row['item_id']}: no longer in the screening log")
                continue
            text = editions.get(entry["source"]).text
            texts[row["item_id"]] = text[int(entry["target_start"]) : int(entry["target_end"])]
    for row in registry:
        if row["item_id"] in texts and ci.target_sha256(texts[row["item_id"]]) != row["target_sha256"]:
            problems.append(f"{row['item_id']}: source text no longer matches the registered target_sha256")
    if problems:
        raise cp.PassError(problems)
    return texts


def _pass_state(dirs: Dirs, paths: cp.PassPaths) -> tuple[list[dict[str, str]], dict[str, str], dict]:
    """(registry, item → prior hash, this pass's live rows) for one annotator and pass."""
    registry = ci.load_registry(dirs.registry)
    prior_pass = cp.PRIOR_PASS[paths.pass_name]
    prior_live = cp.live_rows(cp.load_committed(paths.for_pass(prior_pass))) if prior_pass else {}
    prior = cp.prior_hashes(paths.pass_name, registry, prior_live)
    return registry, prior, cp.live_rows(cp.load_committed(paths))


def build_sheet(dirs: Dirs, paths: cp.PassPaths, *, seed: int) -> int:
    """Write the next sheet for one annotator and pass; return how many items it covers."""
    registry, prior, done = _pass_state(dirs, paths)
    pending = cp.pending_snapshot_items(paths, done)
    if pending:
        raise cp.PassError([f"{paths.sheet} still has {len(pending)} unexported item(s); export it before building a new sheet"])
    items = cp.eligible_items(paths.batch, registry, prior, done)
    if not items:
        logger.info("nothing to label: no item in batch %s is ready for the %s pass for %s", paths.batch, paths.pass_name, paths.annotator)
        return 0
    texts = target_texts(dirs, [row for row in registry if row["item_id"] in set(items)])
    sheet, snapshot_rows = cp.form_sheet(items, texts, prior, seed)
    cp.write_sheet(paths, sheet)
    cp.write_snapshot(paths, cp.build_snapshot(paths, snapshot_rows, seed=seed, registry_sha256=ci.file_sha256(dirs.registry)))
    logger.info("wrote %d %s item(s) for %s to %s", len(items), paths.pass_name, paths.annotator, paths.sheet)
    return len(items)


def export_pass(dirs: Dirs, paths: cp.PassPaths, *, rubric: str) -> int:
    """Validate the filled sheet against its snapshot and append it to the committed pass file."""
    _, prior, _ = _pass_state(dirs, paths)
    snapshot = cp.load_snapshot(paths)
    committed, texts = cp.parse_form_sheet(cp.read_sheet(paths), snapshot, prior, rubric=rubric)
    existing = cp.load_committed(paths)
    merged = cp.merge_export(existing, committed)
    cp.write_committed(paths, merged)
    cp.merge_text_records(paths, texts)
    added = len(merged) - len(existing)
    logger.info("exported %d new %s label(s) for %s to %s (%d already exported)", added, paths.pass_name, paths.annotator, paths.committed, len(committed) - added)
    logger.info("back up %s to Google Drive (it holds the only copy of the free text)", dirs.work_dir)
    return added


def referenced_taxonomy_versions(dirs: Dirs) -> set[str]:
    """Every taxonomy_version used by any annotator's committed context-pass labels."""
    versions: set[str] = set()
    for path in sorted(dirs.annotations_dir.glob("context_context_*.csv")):
        versions |= {row.get("taxonomy_version") or "" for row in read_csv(path)}
    return versions - {""}


def taxonomy_check(dirs: Dirs) -> ct.Taxonomy:
    """Validate the taxonomy file and that no version used by committed labels has been removed."""
    taxonomy = ct.load_taxonomy(dirs.taxonomy)
    problems = ct.missing_versions(taxonomy, referenced_taxonomy_versions(dirs))
    if problems:
        raise ct.TaxonomyError(problems)
    for version in taxonomy.versions:
        intents = taxonomy.intents[version].values()
        logger.info("OK %s: %d intent(s) (%d dialogue, %d literary, %d both)", version, len(intents),
                    *(sum(intent.stratum == stratum for intent in intents) for stratum in ct.INTENT_STRATA))  # fmt: skip
    return taxonomy


def _checked(validator, label: str):  # type: ignore[no-untyped-def]
    """Adapt a schema validator into an argparse ``type`` with a readable message."""

    def parse(value: str) -> str:
        try:
            return validator(value)
        except cs.SchemaError as error:
            raise argparse.ArgumentTypeError(str(error)) from None

    parse.__name__ = label
    return parse


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m src.annotation.context", description="Contextual annotation passes (spec 003).")
    parser.add_argument("--annotations-dir", type=Path, default=DEFAULT_ANNOTATIONS_DIR)
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
    parser.add_argument("--direct-dir", type=Path, default=DEFAULT_DIRECT_DIR)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--manifest", type=Path, default=download_sources.DEFAULT_MANIFEST)
    commands = parser.add_subparsers(dest="command", required=True)

    p_draw = commands.add_parser("draw", help="draw dev dialogues (one turn each) into a batch")
    p_draw.add_argument("--batch", type=_checked(cs.batch_id, "batch"), required=True)
    p_draw.add_argument("--count", type=int, required=True)
    p_draw.add_argument("--seed", type=int, default=ci.DEFAULT_DRAW_SEED)
    p_draw.add_argument("--date", help="registration date YYYY-MM-DD (default: today)")

    p_lit = commands.add_parser("register-literary", help="register screened-in literary candidates (idempotent)")
    p_lit.add_argument("--batch", type=_checked(cs.batch_id, "batch"), required=True)
    p_lit.add_argument("--date", help="registration date YYYY-MM-DD (default: today)")

    commands.add_parser("taxonomy-check", help="validate intent_taxonomy.csv and the versions labels use")

    for name, help_text in (("sheet", "build the next sheet for one annotator and pass"), ("export", "export a filled sheet")):
        p_pass = commands.add_parser(name, help=help_text)
        p_pass.add_argument("--pass", dest="pass_name", choices=cp.IMPLEMENTED_PASSES, required=True)
        p_pass.add_argument("--batch", type=_checked(cs.batch_id, "batch"), required=True)
        p_pass.add_argument("--annotator", type=_checked(cs.annotator_id, "annotator"), required=True)
        if name == "sheet":
            p_pass.add_argument("--seed", type=int, default=cp.DEFAULT_SHEET_SEED, help="row-order shuffle seed")
        else:
            p_pass.add_argument("--rubric", required=True, help="form rubric version the labels follow, e.g. v2")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    dirs = Dirs(args.annotations_dir, args.work_dir, args.direct_dir, args.raw_dir, args.manifest)
    try:
        if args.command == "draw":
            draw(dirs, batch=args.batch, count=args.count, seed=args.seed, date=args.date)
        elif args.command == "register-literary":
            register_literary(dirs, batch=args.batch, date=args.date)
        elif args.command == "taxonomy-check":
            taxonomy_check(dirs)
        else:
            paths = cp.PassPaths(dirs.work_dir, dirs.annotations_dir, args.batch, args.pass_name, args.annotator)
            if args.command == "sheet":
                build_sheet(dirs, paths, seed=args.seed)
            else:
                export_pass(dirs, paths, rubric=args.rubric)
        return 0
    except (ci.RegistryError, cp.PassError, ct.TaxonomyError, cs.SchemaError, sc.ScreeningError, ls.LiteraryError, AnnotationError, OSError, KeyError, ValueError) as error:
        logger.error("%s failed: %s", args.command, error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
