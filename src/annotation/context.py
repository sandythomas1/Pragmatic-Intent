"""Contextual annotation passes: draw, register, sheets, export and corrections (spec 003).

Run from the repository root (Python 3.12, standard library only)::

    python -m src.annotation.context draw --batch pilot1 --count 40 --seed 20261011
    python -m src.annotation.context register-literary --batch pilot1   # after screening export
    python -m src.annotation.context taxonomy-check
    python -m src.annotation.context sheet  --pass form    --batch pilot1 --annotator A1
    python -m src.annotation.context export --pass form    --batch pilot1 --annotator A1 --rubric v2
    python -m src.annotation.context sheet  --pass context --batch pilot1 --annotator A1
    python -m src.annotation.context export --pass context --batch pilot1 --annotator A1
    python -m src.annotation.context sheet  --pass reveal  --batch pilot1 --annotator A1
    python -m src.annotation.context export --pass reveal  --batch pilot1 --annotator A1
    python -m src.annotation.context correct --pass form --annotator A1 --item d:PMUL1234:t06 --prepare
    python -m src.annotation.context correct --pass form --annotator A1 --item d:PMUL1234:t06 --reason typo
    python -m src.annotation.context validate
    python -m src.annotation.context coverage --batch pilot1

Inputs: ``data/interim/direct/items.jsonl`` and ``dialogues.jsonl``
(``python -m src.data.build_direct_dataset``), the pinned literary editions and spec 002's
committed screening log.

Committed output (IDs, enums and hashes; no text): ``data/annotations/context_items.csv``,
``context_<pass>_<annotator>.csv`` and ``context_corrections.csv``. Sheets, snapshots and free
text go under git-ignored ``data/interim/context/``; back that folder up to Google Drive.

See ``specs/003-contextual-annotation/spec.md`` for the protocol and ``docs/context_supplement.md``
for the annotator rubric.
"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from src.annotation import context_coverage as cov
from src.annotation import context_items as ci
from src.annotation import context_passes as cp
from src.annotation import context_schema as cs
from src.annotation import context_taxonomy as ct
from src.annotation import context_validate as vd
from src.annotation import context_views as cv
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
DIALOGUE_SPEAKERS = "user → assistant"

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
    def corrections(self) -> Path:
        return self.annotations_dir / cp.CORRECTIONS_FILE

    @property
    def literary(self) -> sc.Dirs:
        """Spec 002's paths: its committed families file and screening log live in annotations_dir."""
        return sc.Dirs(self.raw_dir, self.manifest, self.annotations_dir, self.literary_work_dir)


# --------------------------------------------------------------------------- items


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


@dataclass(frozen=True)
class ItemSource:
    """One item's text, rebuilt from its source and checked against the registered target hash."""

    stratum: str
    target: str
    speakers: str
    prior: tuple[cv.Segment, ...]
    continuation: tuple[cv.Segment, ...]


def item_sources(dirs: Dirs, registry: Sequence[dict[str, str]]) -> dict[str, ItemSource]:
    """Reconstruct each item's target, seg-v1 prior and continuation, and verify the target hash.

    A hash mismatch means a source or log changed after registration, so a sheet would show
    different text than the item was registered with: that is an error.
    """
    sources, problems = collect_item_sources(dirs, registry)
    if problems:
        raise cp.PassError([f"{subject}: {message}" for subject, message in problems])
    return sources


def collect_item_sources(dirs: Dirs, registry: Sequence[dict[str, str]]) -> tuple[dict[str, ItemSource], list[tuple[str, str]]]:
    """Every item source that can be rebuilt, and (subject, message) for every one that can't.

    Dialogue text comes from ``dialogues.jsonl``; literary text from the pinned edition at the
    screening log's offsets. ``registry`` rows must already be well-formed (``ci.row_problems``).
    An item whose target hash doesn't match is still returned, alongside its problem.
    """
    sources: dict[str, ItemSource] = {}
    problems: list[tuple[str, str]] = []
    dialogue_rows = [row for row in registry if row["stratum"] == "dialogue"]
    literary_rows = [row for row in registry if row["stratum"] == "literary"]
    if dialogue_rows:
        try:
            dialogues = load_dialogues(dirs.dialogues)
        except (OSError, ValueError) as error:
            problems.append((dirs.dialogues.name, f"cannot be read ({error}); rebuild it with python -m src.data.build_direct_dataset"))
            dialogues = None
        for row in dialogue_rows if dialogues is not None else ():
            dialogue_id, turn = row["source_ref"].split("#")
            turns, index = dialogues.get(dialogue_id, []), int(turn)
            if index >= len(turns):
                problems.append((row["item_id"], f"turn {index} of {dialogue_id} is not in {dirs.dialogues.name}"))
                continue
            prior, continuation = cv.dialogue_prior(turns, index), cv.dialogue_continuation(turns, index)
            sources[row["item_id"]] = ItemSource("dialogue", turns[index].text, DIALOGUE_SPEAKERS, tuple(prior), tuple(continuation))
    if literary_rows:
        try:
            log = {entry["candidate_id"]: entry for entry in sc.load_log(dirs.literary)}
        except sc.ScreeningError as error:
            problems.append((dirs.literary.log.name, str(error)))
            log = None
        editions = sc.Editions(dirs.literary)
        for row in literary_rows if log is not None else ():
            entry = log.get(row["item_id"])
            if entry is None:
                problems.append((row["item_id"], "no longer in the screening log"))
                continue
            try:
                edition, start, end = editions.get(entry["source"]), int(entry["target_start"]), int(entry["target_end"])
                prior = cv.literary_prior(edition, entry["episode_id"], start)
                continuation = cv.literary_continuation(edition, entry["episode_id"], end)
            except (ls.LiteraryError, ValueError) as error:
                problems.append((row["item_id"], f"cannot be rebuilt from its edition ({error})"))
                continue
            speakers = f"{entry['speaker']} → {entry['addressee']}"
            sources[row["item_id"]] = ItemSource("literary", edition.text[start:end], speakers, tuple(prior), tuple(continuation))
    for row in registry:
        source = sources.get(row["item_id"])
        if source is not None and ci.target_sha256(source.target) != row["target_sha256"]:
            problems.append((row["item_id"], "source text no longer matches the registered target_sha256"))
    return sources, problems


def target_texts(dirs: Dirs, registry: Sequence[dict[str, str]]) -> dict[str, str]:
    """Item ID → exact, hash-verified target text."""
    return {item: source.target for item, source in item_sources(dirs, registry).items()}


# --------------------------------------------------------------------------- sheets and exports


def _pass_state(dirs: Dirs, paths: cp.PassPaths) -> tuple[list[dict[str, str]], dict[str, str], dict]:
    """(registry, item → prior hash, this pass's live rows) for one annotator and pass."""
    registry = ci.load_registry(dirs.registry)
    prior_pass = cp.PRIOR_PASS[paths.pass_name]
    prior_live = cp.live_rows(cp.load_committed(paths.for_pass(prior_pass))) if prior_pass else {}
    prior = cp.prior_hashes(paths.pass_name, registry, prior_live)
    return registry, prior, cp.live_rows(cp.load_committed(paths))


def _displays(dirs: Dirs, paths: cp.PassPaths, registry: Sequence[dict[str, str]], items: Sequence[str]) -> dict[str, cp.Display]:
    """What the ``paths.pass_name`` sheet shows for each item, and nothing more."""
    wanted = set(items)
    sources = item_sources(dirs, [row for row in registry if row["item_id"] in wanted])
    if paths.pass_name == "form":
        return {item: cp.Display(source.stratum, source.target) for item, source in sources.items()}
    if paths.pass_name == "context":
        return {
            item: cp.Display(source.stratum, source.target, source.speakers, cv.render(source.prior), len(source.prior))
            for item, source in sources.items()
        }
    context_paths = paths.for_pass("context")
    readings = cp.live_rows(cp.load_committed(context_paths))
    texts = cp.load_text_records(context_paths)
    return {
        item: cp.Display(
            source.stratum,
            source.target,
            source.speakers,
            continuation=cv.render(source.continuation) or "(nothing follows)",
            reading=cp.reading(readings[item], texts.get((item, cp.row_key(readings[item])))),
        )
        for item, source in sources.items()
    }


def _taxonomy_snapshot(dirs: Dirs, version: str | None) -> dict[str, str]:
    """The taxonomy version (default: newest) and its hash, recorded in a context sheet's snapshot."""
    taxonomy = ct.load_taxonomy(dirs.taxonomy)
    version = version or taxonomy.latest
    if version not in taxonomy.intents:
        raise ct.TaxonomyError([f"taxonomy_version {version!r} is not in {dirs.taxonomy.name}"])
    return {"taxonomy_version": version, "taxonomy_sha256": taxonomy.sha256(version)}


def build_sheet(dirs: Dirs, paths: cp.PassPaths, *, seed: int, taxonomy_version: str | None = None) -> int:
    """Write the next sheet for one annotator and pass; return how many items it covers."""
    registry, prior, done = _pass_state(dirs, paths)
    pending = cp.pending_snapshot_items(paths, done)
    if pending:
        raise cp.PassError([f"{paths.sheet} still has {len(pending)} unexported item(s); export it before building a new sheet"])
    items = cp.eligible_items(paths.batch, registry, prior, done)
    if not items:
        logger.info("nothing to label: no item in batch %s is ready for the %s pass for %s", paths.batch, paths.pass_name, paths.annotator)
        return 0
    extra = _taxonomy_snapshot(dirs, taxonomy_version) if paths.pass_name == "context" else {}
    sheet, snapshot_rows = cp.build_rows(paths.pass_name, items, _displays(dirs, paths, registry, items), prior, seed)
    cp.write_sheet(paths, sheet)
    snapshot = cp.build_snapshot(paths, snapshot_rows, seed=seed, registry_sha256=ci.file_sha256(dirs.registry), extra=extra)
    cp.write_snapshot(paths, snapshot)
    logger.info("wrote %d %s item(s) for %s to %s%s", len(items), paths.pass_name, paths.annotator, paths.sheet,
                f" (taxonomy {extra['taxonomy_version']})" if extra else "")  # fmt: skip
    return len(items)


def _parse(
    dirs: Dirs, paths: cp.PassPaths, snapshot: dict, prior: dict[str, str], rubric: str | None
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Parse the filled sheet (or correction sheet) at ``paths`` with its pass's rules."""
    sheet = cp.read_sheet(paths)
    if paths.pass_name == "form":
        if not rubric:
            raise cp.PassError(["--rubric is required to export the form pass (e.g. --rubric v2)"])
        return cp.parse_form_sheet(sheet, snapshot, prior, rubric=rubric)
    if paths.pass_name == "reveal":
        return cp.parse_reveal_sheet(sheet, snapshot, prior)
    taxonomy = ct.load_taxonomy(dirs.taxonomy)
    version = snapshot["taxonomy_version"]
    if version not in taxonomy.intents:
        raise cp.PassError([f"taxonomy_version {version!r} used by this sheet is no longer in {dirs.taxonomy.name}"])
    if taxonomy.sha256(version) != snapshot["taxonomy_sha256"]:
        raise cp.PassError([f"taxonomy {version} was edited in place after this sheet was built; restore it and add changes as a new version"])
    return cp.parse_context_sheet(sheet, snapshot, prior, taxonomy=taxonomy)


def export_pass(dirs: Dirs, paths: cp.PassPaths, *, rubric: str | None = None) -> int:
    """Validate the filled sheet against its snapshot and append it to the committed pass file."""
    _, prior, _ = _pass_state(dirs, paths)
    snapshot = cp.load_snapshot(paths)
    committed, texts = _parse(dirs, paths, snapshot, prior, rubric)
    existing = cp.load_committed(paths)
    merged = cp.merge_export(existing, committed)
    cp.write_committed(paths, merged)
    cp.merge_text_records(paths, texts)
    added = len(merged) - len(existing)
    logger.info("exported %d new %s label(s) for %s to %s (%d already exported)", added, paths.pass_name, paths.annotator, paths.committed, len(committed) - added)
    logger.info("back up %s to Google Drive (it holds the only copy of the free text)", dirs.work_dir)
    return added


# --------------------------------------------------------------------------- corrections


def _correction_paths(dirs: Dirs, registry: Sequence[dict[str, str]], pass_name: str, annotator: str, item: str) -> cp.PassPaths:
    row = next((row for row in registry if row["item_id"] == item), None)
    if row is None:
        raise cp.PassError([f"{item}: unknown item (not in {ci.REGISTRY_FILE})"])
    return cp.PassPaths(dirs.work_dir, dirs.annotations_dir, row["batch"], pass_name, annotator, correction=True)


def _current_row(paths: cp.PassPaths, done: dict, item: str) -> dict[str, str]:
    current = done.get(item)
    if current is None:
        raise cp.PassError([f"{item}: {paths.annotator} has no exported {paths.pass_name} row to correct"])
    return dict(current)


def prepare_correction(dirs: Dirs, *, pass_name: str, annotator: str, item: str, taxonomy_version: str | None = None) -> Path:
    """Write a one-row correction sheet prefilled with the item's current labels (FR9, step 1)."""
    registry = ci.load_registry(dirs.registry)
    paths = _correction_paths(dirs, registry, pass_name, annotator, cs.item_id(item))
    _, prior, done = _pass_state(dirs, paths)
    current = _current_row(paths, done, item)
    extra = _taxonomy_snapshot(dirs, taxonomy_version or current["taxonomy_version"]) if pass_name == "context" else {}
    display = _displays(dirs, paths, registry, [item])[item]
    labels = cp.label_cells(pass_name, current, cp.load_text_records(paths).get((item, cp.row_key(current))))
    sheet, snapshot_rows = cp.build_rows(pass_name, [item], {item: dataclasses.replace(display, labels=labels)}, prior, seed=0)
    snapshot_rows[0]["old_row_key"] = cp.row_key(current)
    cp.write_sheet(paths, sheet)
    cp.write_snapshot(paths, cp.build_snapshot(paths, snapshot_rows, seed=0, registry_sha256=ci.file_sha256(dirs.registry), extra=extra))
    logger.info("wrote a correction sheet for %s (%s, %s) to %s; edit it, then rerun correct with --reason", item, pass_name, annotator, paths.sheet)
    return paths.sheet


def later_passes_seen(paths: cp.PassPaths, item: str) -> bool:
    """Had the annotator already seen later evidence for ``item``: an exported row or a built sheet?"""
    for later in cp.LATER_PASSES[paths.pass_name]:
        later_paths = paths.for_pass(later)
        if any(row["item_id"] == item for row in cp.load_committed(later_paths)) or item in cp.snapshot_items(later_paths):
            return True
    return False


def apply_correction(
    dirs: Dirs, *, pass_name: str, annotator: str, item: str, reason: str, date: str | None = None, rubric: str | None = None
) -> dict[str, str]:
    """Supersede the item's live row with the edited correction sheet and log both hashes (FR9, step 2)."""
    cs.require_enum(reason, cs.CORRECTION_REASONS, "reason")
    corrected_on = ci.today(date)
    registry = ci.load_registry(dirs.registry)
    paths = _correction_paths(dirs, registry, pass_name, annotator, cs.item_id(item))
    snapshot = cp.load_snapshot(paths)
    if [entry["item_id"] for entry in snapshot["rows"]] != [item]:
        raise cp.PassError([f"the pending correction sheet {paths.sheet} is not for {item}; prepare one with --prepare"])
    _, prior, done = _pass_state(dirs, paths)
    current = _current_row(paths, done, item)
    if cp.row_key(current) != snapshot["rows"][0].get("old_row_key"):
        raise cp.PassError([f"{item}: the {pass_name} row changed after the correction sheet was prepared; prepare it again"])
    committed, texts = _parse(dirs, paths, snapshot, prior, rubric or current.get("rubric_version"))
    new = committed[0]
    if cp.row_key(new) == cp.row_key(current):
        raise cp.PassError([f"{item}: the correction sheet changes no label; nothing to correct"])
    log_row = {
        "item_id": item,
        "pass": pass_name,
        "annotator": annotator,
        "old_sha256": cs.canonical_hash(current),
        "new_sha256": cs.canonical_hash(new),
        "reason": reason,
        "corrected_on": corrected_on,
        "later_passes_sealed": "true" if later_passes_seen(paths, item) else "false",
    }
    rows = [dict(row, status="superseded") if row["item_id"] == item and row["status"] == "" else row for row in cp.load_committed(paths)]
    cp.write_committed(paths, cp.sort_rows([*rows, new]))
    cp.merge_text_records(paths, texts)
    cp.append_correction(dirs.corrections, log_row)
    paths.sheet.unlink()
    paths.snapshot.unlink()
    logger.info("corrected %s (%s, %s, %s); later passes sealed: %s", item, pass_name, annotator, reason, log_row["later_passes_sealed"])
    logger.info("back up %s to Google Drive (it holds the only copy of the free text)", dirs.work_dir)
    return log_row


# --------------------------------------------------------------------------- taxonomy


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


# --------------------------------------------------------------------------- validation (FR12)

_FILES_BATCH = "all"  # committed and text files are per pass and annotator, not per batch; sheet paths go unused


class ValidationFailed(Exception):
    def __init__(self, findings: Sequence[vd.Finding]) -> None:
        super().__init__(f"{len(findings)} problem(s):\n  " + "\n  ".join(map(str, findings)))
        self.findings = list(findings)


def _read_committed_csv(path: Path, fields: Sequence[str], rule: str, findings: list[vd.Finding]) -> list[dict[str, str]]:
    """A committed CSV's rows, or [] with a finding when it is missing a header or unreadable."""
    if not path.exists():
        return []
    try:
        rows = read_csv(path)
    except AnnotationError as error:
        findings.append(vd.Finding(rule, path.name, str(error)))
        return []
    if rows and tuple(rows[0]) != tuple(fields):
        findings.append(vd.Finding(rule, path.name, f"columns {list(rows[0])} do not match {list(fields)}"))
        return []
    return rows


def _dialogue_splits(dirs: Dirs, findings: list[vd.Finding]) -> dict[str, set[str]] | None:
    try:
        items = load_items(dirs.items)
    except (OSError, ValueError) as error:
        findings.append(vd.Finding("group-split", dirs.items.name, f"cannot be read ({error}); dialogue splits are unchecked"))
        return None
    splits: dict[str, set[str]] = {}
    for item in items:
        splits.setdefault(item["dialogue_id"], set()).add(item["split"])
    return splits


def _screening(dirs: Dirs, findings: list[vd.Finding]) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    """(candidate → screening log row, family → families row); empty with a finding if unreadable."""
    try:
        log = {entry["candidate_id"]: entry for entry in sc.load_log(dirs.literary)}
        families = {family["family_id"]: family for family in sc.load_families(dirs.literary)}
    except sc.ScreeningError as error:
        findings.append(vd.Finding("screening-log", dirs.literary.log.name, str(error)))
        return {}, {}
    return log, families


def _taxonomy(dirs: Dirs, findings: list[vd.Finding]) -> ct.Taxonomy | None:
    if not dirs.taxonomy.exists():
        return None
    try:
        return ct.load_taxonomy(dirs.taxonomy)
    except ct.TaxonomyError as error:
        findings += [vd.Finding("taxonomy", dirs.taxonomy.name, problem) for problem in error.problems]
        return None


def _pass_files(dirs: Dirs, findings: list[vd.Finding]) -> dict[tuple[str, str], vd.PassFile]:
    """Every committed pass file with its usable rows and local text records."""
    files: dict[tuple[str, str], vd.PassFile] = {}
    for pass_name in cs.PASSES:
        for path in sorted(dirs.annotations_dir.glob(f"context_{pass_name}_*.csv")):
            annotator = path.stem.removeprefix(f"context_{pass_name}_")
            if cs.ANNOTATOR_RE.fullmatch(annotator) is None:
                findings.append(vd.Finding("foreign-id", repr(path.name), "file name does not end in a valid annotator ID"))
                continue
            rows, row_findings = vd.usable_rows(path.name, _read_committed_csv(path, cp.COMMITTED_FIELDS[pass_name], "labels", findings), pass_name, annotator)
            findings += row_findings
            files[(pass_name, annotator)] = vd.PassFile(pass_name, annotator, rows, _text_records(dirs, pass_name, annotator, bool(rows), findings))
    return files


def _text_records(dirs: Dirs, pass_name: str, annotator: str, needed: bool, findings: list[vd.Finding]) -> dict | None:
    paths = cp.PassPaths(dirs.work_dir, dirs.annotations_dir, _FILES_BATCH, pass_name, annotator)
    if not paths.text.exists():
        if needed:
            findings.append(vd.Finding("local-text", paths.text.name, f"is missing; restore {dirs.work_dir} from the Google Drive backup"))
        return None
    try:
        return cp.load_text_records(paths)
    except (cp.PassError, UnicodeDecodeError) as error:
        findings.append(vd.Finding("local-text", paths.text.name, str(error)))
        return None


def validate(dirs: Dirs) -> list[vd.Finding]:
    """Recompute every FR12 check from the sources, committed files and local text; return all findings."""
    findings: list[vd.Finding] = []
    registry = _read_committed_csv(dirs.registry, ci.REGISTRY_FIELDS, "registry", findings)
    log, families = _screening(dirs, findings)
    dialogue_splits = _dialogue_splits(dirs, findings) if any(row.get("stratum") == "dialogue" for row in registry) else {}
    findings += vd.check_registry(registry, dialogue_splits, families)
    complete = [row for row in registry if set(row) == set(ci.REGISTRY_FIELDS) and None not in row.values()]
    by_id = {row["item_id"]: row for row in complete}  # registered, even if a field is invalid (reported above)
    sound = [row for row in complete if not ci.row_problems(row)]  # safe to rebuild from source
    findings += vd.check_screening(sound, log, families)
    sources, problems = collect_item_sources(dirs, sound)
    findings += [vd.Finding("target-hash", subject, message) for subject, message in problems]
    facts = {item: vd.SourceFacts(source.stratum, len(source.prior)) for item, source in sources.items()}

    files = _pass_files(dirs, findings)
    taxonomy = _taxonomy(dirs, findings)
    if taxonomy is not None:
        findings += vd.check_taxonomy_versions(taxonomy, files)
    elif any(name == "context" and pass_file.rows for (name, _), pass_file in files.items()) and not dirs.taxonomy.exists():
        findings.append(vd.Finding("taxonomy", dirs.taxonomy.name, "is missing, but context labels reference it"))
    for pass_file in files.values():
        findings += vd.check_pass_file(pass_file, by_id, facts, taxonomy)
    corrections = _read_committed_csv(dirs.corrections, cp.CORRECTION_FIELDS, "corrections", findings)
    findings += vd.check_chain(files, by_id, vd.logged_corrections(entry for entry in corrections if not cp.correction_problems(entry)))
    findings += vd.check_corrections(corrections, files, by_id)
    return sorted(set(findings))


def validate_command(dirs: Dirs) -> int:
    """Run ``validate``; log a summary and raise ``ValidationFailed`` listing every finding."""
    findings = validate(dirs)
    if findings:
        rules = Counter(finding.rule for finding in findings)
        logger.error("validate found problems under: %s", ", ".join(f"{rule} ({count})" for rule, count in sorted(rules.items())))
        raise ValidationFailed(findings)
    registry = ci.load_registry(dirs.registry)
    strata = Counter(row["stratum"] for row in registry)
    labels = {path.stem.removeprefix("context_"): len(read_csv(path)) for pass_name in cs.PASSES
              for path in sorted(dirs.annotations_dir.glob(f"context_{pass_name}_*.csv"))}  # fmt: skip
    logger.info("OK: %d item(s) (%d dialogue, %d literary); rows per pass file: %s; %d correction(s)",
                len(registry), strata["dialogue"], strata["literary"],
                ", ".join(f"{name} {count}" for name, count in labels.items()) or "none",
                len(cp.load_corrections(dirs.corrections)))  # fmt: skip
    return 0


# --------------------------------------------------------------------------- coverage (FR13, FR14)


def coverage(dirs: Dirs, batch: str) -> str:
    """The plain-text coverage report for ``batch``; refuses data that does not pass ``validate``."""
    cs.batch_id(batch)
    findings = validate(dirs)
    if findings:
        logger.error("coverage reads only validated data; fix these first")
        raise ValidationFailed(findings)
    registry = ci.load_registry(dirs.registry)
    batch_strata = {row["item_id"]: row["stratum"] for row in registry if row["batch"] == batch}
    if not batch_strata:
        raise cp.PassError([f"batch {batch!r} has no registered items"])
    log, _ = _screening(dirs, [])
    screeners = {item: log[item]["screener"] for item, stratum in batch_strata.items() if stratum == "literary" and item in log}
    return cov.report(batch, batch_strata, _pass_files(dirs, []), screeners, _taxonomy(dirs, []))


# --------------------------------------------------------------------------- CLI


def _checked(validator, label: str):  # type: ignore[no-untyped-def]
    """Adapt a schema validator into an argparse ``type`` with a readable message."""

    def parse(value: str) -> str:
        try:
            return validator(value)
        except cs.SchemaError as error:
            raise argparse.ArgumentTypeError(str(error)) from None

    parse.__name__ = label
    return parse


def _taxonomy_version(value: str) -> str:
    return cs.require_match(cs.TAXONOMY_VERSION_RE, value, "taxonomy")


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
    commands.add_parser("validate", help="recompute every check over the registry, labels, corrections and local text")
    p_cov = commands.add_parser("coverage", help="print per-annotator coverage tables for one batch")
    p_cov.add_argument("--batch", type=_checked(cs.batch_id, "batch"), required=True)

    for name, help_text in (("sheet", "build the next sheet for one annotator and pass"), ("export", "export a filled sheet")):
        p_pass = commands.add_parser(name, help=help_text)
        p_pass.add_argument("--pass", dest="pass_name", choices=cp.IMPLEMENTED_PASSES, required=True)
        p_pass.add_argument("--batch", type=_checked(cs.batch_id, "batch"), required=True)
        p_pass.add_argument("--annotator", type=_checked(cs.annotator_id, "annotator"), required=True)
        if name == "sheet":
            p_pass.add_argument("--seed", type=int, default=cp.DEFAULT_SHEET_SEED, help="row-order shuffle seed")
            p_pass.add_argument("--taxonomy", type=_checked(_taxonomy_version, "taxonomy"), help="context pass: taxonomy version (default: newest)")
        else:
            p_pass.add_argument("--rubric", help="form pass: the rubric version the labels follow, e.g. v2")

    p_fix = commands.add_parser("correct", help="correct one exported row: --prepare a sheet, edit it, then apply it with --reason")
    p_fix.add_argument("--pass", dest="pass_name", choices=cp.IMPLEMENTED_PASSES, required=True)
    p_fix.add_argument("--annotator", type=_checked(cs.annotator_id, "annotator"), required=True)
    p_fix.add_argument("--item", type=_checked(cs.item_id, "item"), required=True)
    mode = p_fix.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true", help="write a one-row correction sheet holding the current labels")
    mode.add_argument("--reason", choices=cs.CORRECTION_REASONS, help="apply the edited correction sheet")
    p_fix.add_argument("--date", help="correction date YYYY-MM-DD (default: today)")
    p_fix.add_argument("--rubric", help="form pass: rubric version (default: the corrected row's)")
    p_fix.add_argument("--taxonomy", type=_checked(_taxonomy_version, "taxonomy"), help="context pass: taxonomy version (default: the corrected row's)")
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
        elif args.command == "validate":
            validate_command(dirs)
        elif args.command == "coverage":
            sys.stdout.write(coverage(dirs, args.batch))
        elif args.command == "correct":
            if args.prepare:
                prepare_correction(dirs, pass_name=args.pass_name, annotator=args.annotator, item=args.item, taxonomy_version=args.taxonomy)
            else:
                apply_correction(dirs, pass_name=args.pass_name, annotator=args.annotator, item=args.item, reason=args.reason,
                                 date=args.date, rubric=args.rubric)  # fmt: skip
        else:
            paths = cp.PassPaths(dirs.work_dir, dirs.annotations_dir, args.batch, args.pass_name, args.annotator)
            if args.command == "sheet":
                build_sheet(dirs, paths, seed=args.seed, taxonomy_version=args.taxonomy)
            else:
                export_pass(dirs, paths, rubric=args.rubric)
        return 0
    except (ValidationFailed, ci.RegistryError, cp.PassError, ct.TaxonomyError, cs.SchemaError, sc.ScreeningError, ls.LiteraryError, AnnotationError, OSError, KeyError, ValueError) as error:
        logger.error("%s failed: %s", args.command, error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
