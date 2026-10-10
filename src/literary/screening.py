"""Assign literary pilot families, propose candidates, and export a validated screening log (spec 002).

Run from the repository root (Python 3.12, standard library only)::

    python -m src.literary.screening families draw   --source aesop_jones1912 --count 6 --seed 20261010
    python -m src.literary.screening families assign --source kjv_pg10 --family-id kjv:cana-wedding \\
        --episodes kjv:john:2 --reason "meeting candidate, 2026-10-08"
    python -m src.literary.screening families list
    python -m src.literary.screening propose           # fill data/interim/literary/screening_sheet.csv
    python -m src.literary.screening export --screener A1
    python -m src.literary.screening validate

Files:

* ``data/annotations/literary_families.csv`` (committed): split groups. A family is assigned to
  dev *before* anyone screens it, and an episode belongs to at most one family.
* ``data/interim/literary/proposals.jsonl`` (ignored, machine-owned): every mechanical proposal.
* ``data/interim/literary/screening_sheet.csv`` (ignored, human-edited in Excel; holds source text).
  Fill in ``target_text`` (copy the exact words), ``speaker``, ``addressee``, ``status``
  (include / exclude / blank = pending) and ``exclusion_reason``. **include means eligible**: an
  addressed exchange with prior context, whether or not it turns out to be a request. Add a missed
  utterance as a row with a blank ``candidate_id``, a dev ``family_id`` and its ``target_text``.
* ``data/annotations/literary_screening.csv`` (committed): the text-free log. It holds offsets,
  hashes, role names and enums, and every proposed candidate, including pending ones.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import json
import logging
import random
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from src.annotation.levels import AnnotationError, read_csv, write_csv
from src.data import download_sources
from src.literary import proposals as lp
from src.literary import sources as ls

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ANNOTATIONS_DIR = REPO_ROOT / "data" / "annotations"
DEFAULT_WORK_DIR = REPO_ROOT / "data" / "interim" / "literary"
FAMILIES_FILE = "literary_families.csv"
LOG_FILE = "literary_screening.csv"
SHEET_FILE = "screening_sheet.csv"
PROPOSALS_FILE = "proposals.jsonl"

PROTOCOL_VERSION = "lit-screen-v1"
SPLITS = ("dev",)  # untouched test families are drawn in WP-04 under a later protocol
ASSIGNMENTS = ("drawn", "assigned")
STATUSES = ("pending", "include", "exclude")
ORIGINS = ("proposed", "manual")
EXCLUSION_REASONS = (
    "no_addressed_speech",
    "no_context",
    "uncertain_reading",
    "out_of_scope",
    "duplicate_story",
    "rights_pending",
    "future_evidence_dependence",
    "narrator_moral",
)
_STATUS_ALIASES = {"": "pending", "pending": "pending", "include": "include", "included": "include",
                   "exclude": "exclude", "excluded": "exclude"}  # fmt: skip

FAMILY_FIELDS = (
    "family_id", "source", "episode_ids", "split", "assignment", "seed", "pool_size", "reason",
    "assigned_on", "protocol_version",
)  # fmt: skip
SHEET_FIELDS = (
    "candidate_id", "family_id", "locator", "flags", "unit_text", "target_text", "speaker", "addressee",
    "status", "exclusion_reason", "notes",
)  # fmt: skip
LOG_FIELDS = (
    "candidate_id", "source", "family_id", "episode_id", "split", "locator", "target_start", "target_end",
    "target_sha256", "source_sha256", "origin", "speaker", "addressee", "status", "exclusion_reason",
    "screener", "protocol_version",
)  # fmt: skip

MAX_ROLE_CHARS = 60
MAX_REASON_CHARS = 200
_FAMILY_ID_RE = re.compile(r"^[a-z0-9][a-z0-9:_-]{0,79}$")
_CANDIDATE_ID_RE = re.compile(r"^lit-[0-9a-f]{10}$")
_SCREENER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,15}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
# Spreadsheet formula triggers (OWASP CSV injection). Written cells starting with one get a "'".
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

logger = logging.getLogger(__name__)


class ScreeningError(Exception):
    """A command cannot proceed; the message says why and what to do."""


class ValidationFailed(ScreeningError):
    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__(f"{len(problems)} problem(s):\n  " + "\n  ".join(problems))
        self.problems = list(problems)


@dataclass(frozen=True)
class Dirs:
    raw_dir: Path
    manifest: Path
    annotations_dir: Path
    work_dir: Path

    @property
    def families(self) -> Path:
        return self.annotations_dir / FAMILIES_FILE

    @property
    def log(self) -> Path:
        return self.annotations_dir / LOG_FILE

    @property
    def sheet(self) -> Path:
        return self.work_dir / SHEET_FILE

    @property
    def proposals(self) -> Path:
        return self.work_dir / PROPOSALS_FILE


class Editions:
    """Lazily loaded, hash-verified editions, one per source."""

    def __init__(self, dirs: Dirs) -> None:
        self._dirs = dirs
        self._loaded: dict[str, ls.Edition] = {}

    def get(self, source: str) -> ls.Edition:
        if source not in self._loaded:
            self._loaded[source] = ls.load_edition(source, self._dirs.raw_dir, self._dirs.manifest)
        return self._loaded[source]


# --------------------------------------------------------------------------- shared helpers


def _read(path: Path) -> list[dict[str, str]]:
    """Rows as plain strings: short rows' missing cells become "", and overflow cells are dropped."""
    try:
        rows = read_csv(path)
    except AnnotationError as error:
        raise ScreeningError(str(error)) from None
    return [{key: value or "" for key, value in row.items() if key is not None} for row in rows]


def _write(path: Path, fields: Sequence[str], rows: Sequence[dict[str, object]], *, excel: bool = False) -> None:
    try:
        write_csv(path, fields, rows, excel=excel)
    except PermissionError:
        raise ScreeningError(f"cannot write {path}; close it in Excel and retry") from None


def escape_cell(value: str) -> str:
    """Prefix formula-like cells with "'" so a spreadsheet shows them as text."""
    return "'" + value if value.startswith(_FORMULA_PREFIXES) else value


def unescape_cell(value: str) -> str:
    return value[1:] if value.startswith("'") and value[1:].startswith(_FORMULA_PREFIXES) else value


def _check_header(path: Path, rows: list[dict[str, str]], fields: Sequence[str]) -> None:
    if rows and set(rows[0]) != set(fields):
        raise ScreeningError(f"{path}: columns {sorted(rows[0])} do not match the expected {list(fields)}")


def _single_line(value: str, limit: int, label: str) -> str | None:
    """An error message if ``value`` is not a short single-line printable string, else None."""
    if len(value) > limit:
        return f"{label} is longer than {limit} characters"
    if not value.isprintable():
        return f"{label} contains a newline or control character"
    if value.startswith(_FORMULA_PREFIXES):
        return f"{label} starts with a spreadsheet formula character"
    return None


# --------------------------------------------------------------------------- families


def load_families(dirs: Dirs) -> list[dict[str, str]]:
    if not dirs.families.exists():
        return []
    rows = _read(dirs.families)
    _check_header(dirs.families, rows, FAMILY_FIELDS)
    # Family IDs flow into the Excel sheet, so a malformed (e.g. formula-like) ID stops every command.
    bad = [row["family_id"] for row in rows if not _FAMILY_ID_RE.match(row["family_id"])]
    if bad:
        raise ScreeningError(f"{dirs.families}: malformed family id(s) {bad!r}; ids must match {_FAMILY_ID_RE.pattern}")
    return rows


def family_episodes(family: dict[str, str]) -> list[str]:
    return [episode for episode in family["episode_ids"].split(";") if episode]


def assigned_episodes(families: Iterable[dict[str, str]]) -> set[str]:
    return {episode for family in families for episode in family_episodes(family)}


def _today(value: str | None) -> str:
    if value is None:
        return datetime.date.today().isoformat()
    try:
        return datetime.date.fromisoformat(value).isoformat()
    except ValueError:
        raise ScreeningError(f"--date must be YYYY-MM-DD, not {value!r}") from None


def draw_families(dirs: Dirs, editions: Editions, source: str, count: int, seed: int, date: str | None) -> list[str]:
    """Draw ``count`` dev families uniformly from unassigned episodes that have ≥1 proposal."""
    if count < 1:
        raise ScreeningError("--count must be at least 1")
    families = load_families(dirs)
    edition = editions.get(source)
    taken = assigned_episodes(families)
    pool = [
        episode
        for episode in edition.episode_ids
        if episode not in taken and lp.propose_episode(edition, episode, family_id=episode)
    ]
    if count > len(pool):
        raise ScreeningError(f"{source}: only {len(pool)} unassigned episode(s) with proposals; asked for {count}")
    drawn = random.Random(seed).sample(pool, count)
    assigned_on = _today(date)
    new_rows = [
        _family_row(episode, source, [episode], "drawn", str(seed), str(len(pool)), "seeded uniform draw", assigned_on)
        for episode in drawn
    ]
    _write(dirs.families, FAMILY_FIELDS, [*families, *new_rows])
    logger.info("drew %d dev famil%s from a pool of %d: %s", count, "y" if count == 1 else "ies", len(pool), ", ".join(drawn))
    return drawn


def assign_family(
    dirs: Dirs, editions: Editions, source: str, family_id: str, episodes: Sequence[str], reason: str, date: str | None
) -> None:
    if not _FAMILY_ID_RE.match(family_id):
        raise ScreeningError(f"family id {family_id!r} must match {_FAMILY_ID_RE.pattern}")
    problem = _single_line(reason.strip(), MAX_REASON_CHARS, "--reason")
    if not reason.strip() or problem:
        raise ScreeningError(problem or "--reason is required for an explicit assignment")
    families = load_families(dirs)
    if any(family["family_id"] == family_id for family in families):
        raise ScreeningError(f"family {family_id!r} already exists")
    edition = editions.get(source)
    known = set(edition.episode_ids)
    unknown = [episode for episode in episodes if episode not in known]
    if unknown:
        raise ScreeningError(f"{source} has no episode(s) {', '.join(unknown)}")
    if len(set(episodes)) != len(episodes):
        raise ScreeningError("an episode is listed twice")
    clash = sorted(set(episodes) & assigned_episodes(families))
    if clash:
        raise ScreeningError(f"episode(s) already in another family: {', '.join(clash)}")
    row = _family_row(family_id, source, list(episodes), "assigned", "", "", reason.strip(), _today(date))
    _write(dirs.families, FAMILY_FIELDS, [*families, row])
    logger.info("assigned dev family %s: %s", family_id, ", ".join(episodes))


def _family_row(
    family_id: str, source: str, episodes: list[str], assignment: str, seed: str, pool_size: str, reason: str, date: str
) -> dict[str, str]:
    return {
        "family_id": family_id, "source": source, "episode_ids": ";".join(episodes), "split": "dev",
        "assignment": assignment, "seed": seed, "pool_size": pool_size, "reason": reason, "assigned_on": date,
        "protocol_version": PROTOCOL_VERSION,
    }  # fmt: skip


# --------------------------------------------------------------------------- propose


def load_proposals(dirs: Dirs) -> dict[str, lp.Proposal]:
    if not dirs.proposals.exists():
        return {}
    proposals: dict[str, lp.Proposal] = {}
    for number, line in enumerate(dirs.proposals.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            proposal = lp.Proposal(**{**record, "flags": tuple(record["flags"])})
        except (json.JSONDecodeError, TypeError, KeyError):
            raise ScreeningError(f"{dirs.proposals} line {number} is corrupt; it is machine-owned, do not edit it") from None
        proposals[proposal.candidate_id] = proposal
    return proposals


def propose(dirs: Dirs, editions: Editions) -> int:
    """Append proposals for every dev family not yet proposed. Existing sheet rows are kept as they are."""
    families = load_families(dirs)
    if not families:
        raise ScreeningError(f"no families in {dirs.families}; run 'families draw' or 'families assign' first")
    existing = load_proposals(dirs)
    proposed_families = {proposal.family_id for proposal in existing.values()}
    sheet_rows = _read(dirs.sheet) if dirs.sheet.exists() else []
    _check_header(dirs.sheet, sheet_rows, SHEET_FIELDS)

    new: list[lp.Proposal] = []
    for family in families:
        if family["family_id"] in proposed_families:
            continue
        edition = editions.get(family["source"])
        found = [p for episode in family_episodes(family) for p in lp.propose_episode(edition, episode, family["family_id"])]
        if not found:
            logger.warning("family %s has no mechanical proposals; add manual rows if it has addressed speech", family["family_id"])
        new.extend(proposal for proposal in found if proposal.candidate_id not in existing)
    if not new:
        logger.info("nothing new to propose")
        return 0

    new_rows = [_sheet_row(editions.get(proposal.source), proposal) for proposal in new]
    _write(dirs.sheet, SHEET_FIELDS, [*sheet_rows, *new_rows], excel=True)
    dirs.proposals.parent.mkdir(parents=True, exist_ok=True)
    with dirs.proposals.open("a", encoding="utf-8", newline="\n") as handle:
        for proposal in new:
            handle.write(json.dumps({**asdict(proposal), "flags": list(proposal.flags)}, sort_keys=True) + "\n")
    logger.info("proposed %d candidate(s); screen them in %s (save as CSV UTF-8)", len(new), dirs.sheet)
    return len(new)


def _sheet_row(edition: ls.Edition, proposal: lp.Proposal) -> dict[str, str]:
    unit_text = " ".join(
        edition.unit_text(unit) for unit in edition.units_overlapping(proposal.episode_id, proposal.start, proposal.end)
    )
    target = edition.text[proposal.start : proposal.end]
    return {
        "candidate_id": proposal.candidate_id, "family_id": escape_cell(proposal.family_id),
        "locator": escape_cell(proposal.locator), "flags": ";".join(proposal.flags), "unit_text": escape_cell(ls.collapse_whitespace(unit_text)),
        "target_text": escape_cell(ls.collapse_whitespace(target)), "speaker": "", "addressee": "", "status": "",
        "exclusion_reason": "", "notes": "",
    }  # fmt: skip


# --------------------------------------------------------------------------- export


def export(dirs: Dirs, editions: Editions, screener: str) -> int:
    if not _SCREENER_RE.match(screener):
        raise ScreeningError(f"screener id {screener!r} must be a short pseudonym such as A1")
    families = {family["family_id"]: family for family in load_families(dirs)}
    proposals = load_proposals(dirs)
    if not dirs.sheet.exists():
        raise ScreeningError(f"no sheet at {dirs.sheet}; run 'propose' first")
    sheet = _read(dirs.sheet)
    _check_header(dirs.sheet, sheet, SHEET_FIELDS)

    # Collect every problem in one pass, so a screener can fix the whole sheet at once.
    problems: list[str] = []
    rows: list[dict[str, str]] = []
    seen: dict[str, int] = {}
    for line_number, raw in enumerate(sheet, start=2):
        cells = {key: unescape_cell(value.strip()) for key, value in raw.items()}
        label = f"sheet line {line_number} ({cells.get('candidate_id') or 'manual'})"
        if cells.get("candidate_id") in proposals:
            seen.setdefault(cells["candidate_id"], line_number)
        try:
            row = _export_row(cells, families, proposals, editions, screener)
        except ScreeningError as error:
            problems.append(f"{label}: {error}")
            continue
        first_line = seen.setdefault(row["candidate_id"], line_number)
        if first_line != line_number:
            problems.append(f"{label}: duplicates the candidate on sheet line {first_line}")
            continue
        problems.extend(f"{label}: {problem}" for problem in _label_problems(row))
        rows.append(row)
    missing = sorted(set(proposals) - set(seen))
    problems.extend(f"{candidate}: proposed but missing from the sheet (rows must not be deleted)" for candidate in missing)
    if not problems:
        problems = validate_rows(rows, families, editions)
    if problems:
        raise ValidationFailed(problems)

    rows.sort(key=lambda row: _log_order(row, editions))
    _write(dirs.log, LOG_FIELDS, rows)
    counts = {status: sum(row["status"] == status for row in rows) for status in STATUSES}
    logger.info("exported %d candidate(s) to %s: %s", len(rows), dirs.log, ", ".join(f"{n} {s}" for s, n in counts.items()))
    return len(rows)


def _export_row(
    cells: dict[str, str],
    families: dict[str, dict[str, str]],
    proposals: dict[str, lp.Proposal],
    editions: Editions,
    screener: str,
) -> dict[str, str]:
    candidate = cells.get("candidate_id", "")
    if candidate:
        proposal = proposals.get(candidate)
        if proposal is None:
            raise ScreeningError("unknown candidate_id; proposed rows must keep their ID, and manual rows leave it blank")
        if cells.get("family_id") != proposal.family_id:
            raise ScreeningError(f"family_id was changed from {proposal.family_id!r}")
        family = families.get(proposal.family_id)
        if family is None:
            raise ScreeningError(f"family {proposal.family_id!r} is no longer in {FAMILIES_FILE}")
        episodes, origin = [proposal.episode_id], "proposed"
    else:
        family = families.get(cells.get("family_id", ""))
        if family is None:
            raise ScreeningError(f"manual row's family_id {cells.get('family_id', '')!r} is not an assigned dev family")
        episodes, origin = family_episodes(family), "manual"

    edition = editions.get(family["source"])
    episode_id, start, end = _resolve_in_episodes(edition, episodes, cells.get("target_text", ""))
    if origin == "manual":
        candidate = lp.candidate_id(edition.source, start, end)
        if candidate in proposals:
            raise ScreeningError(f"manual row duplicates proposed candidate {candidate}")

    status = _STATUS_ALIASES.get(cells.get("status", "").lower())
    if status is None:
        raise ScreeningError(f"status must be include, exclude or blank, not {cells.get('status')!r}")
    unit = next(unit for unit in edition.episode_units(episode_id) if unit.start < end and start < unit.end)
    return {
        "candidate_id": candidate, "source": edition.source, "family_id": family["family_id"],
        "episode_id": episode_id, "split": family["split"], "locator": unit.locator,
        "target_start": str(start), "target_end": str(end),
        "target_sha256": hashlib.sha256(edition.text[start:end].encode("utf-8")).hexdigest(),
        "source_sha256": edition.sha256, "origin": origin, "speaker": cells.get("speaker", ""),
        "addressee": cells.get("addressee", ""), "status": status,
        "exclusion_reason": cells.get("exclusion_reason", "").lower(), "screener": screener,
        "protocol_version": PROTOCOL_VERSION,
    }  # fmt: skip


def _resolve_in_episodes(edition: ls.Edition, episodes: Sequence[str], target: str) -> tuple[str, int, int]:
    """The single (episode, start, end) where ``target`` occurs across ``episodes``."""
    if not target.split():
        raise ScreeningError("target_text is empty")
    found: list[tuple[str, int, int]] = []
    ambiguous = False
    for episode in episodes:
        start, end = edition.episode_bounds(episode)
        try:
            found.append((episode, *ls.resolve_span(edition.text, start, end, target)))
        except ls.AmbiguousSpanError:
            ambiguous = True
        except ls.LiteraryError:
            continue  # not in this episode
    if ambiguous or len(found) > 1:
        raise ScreeningError("target_text occurs more than once in its family; add surrounding words")
    if not found:
        raise ScreeningError("target_text does not occur in its episode; copy the exact words from the source")
    return found[0]


def _log_order(row: dict[str, str], editions: Editions) -> tuple[str, int, int]:
    episode_index = editions.get(row["source"]).episode_ids.index(row["episode_id"])
    return row["source"], episode_index, int(row["target_start"])


# --------------------------------------------------------------------------- validate


def validate(dirs: Dirs, editions: Editions) -> int:
    """Re-derive and check the committed families file and screening log against the pinned sources."""
    families_list = load_families(dirs)
    problems = validate_families(families_list, editions)
    rows: list[dict[str, str]] = []
    if dirs.log.exists():
        rows = _read(dirs.log)
        _check_header(dirs.log, rows, LOG_FIELDS)
    families = {family["family_id"]: family for family in families_list}
    problems.extend(validate_rows(rows, families, editions))
    if problems:
        raise ValidationFailed(problems)
    logger.info("OK: %d famil%s and %d screening row(s) reconstruct from the pinned sources",
                len(families), "y" if len(families) == 1 else "ies", len(rows))  # fmt: skip
    return len(rows)


def validate_families(families: Sequence[dict[str, str]], editions: Editions) -> list[str]:
    problems: list[str] = []
    seen_ids: set[str] = set()
    owner: dict[str, str] = {}
    for family in families:
        family_id = family["family_id"]
        label = f"family {family_id!r}"
        if not _FAMILY_ID_RE.match(family_id):
            problems.append(f"{label}: malformed family id")
        if family_id in seen_ids:
            problems.append(f"{label}: duplicate family id")
        seen_ids.add(family_id)
        if family["split"] not in SPLITS:
            problems.append(f"{label}: split must be one of {SPLITS}")
        if family["assignment"] not in ASSIGNMENTS:
            problems.append(f"{label}: assignment must be one of {ASSIGNMENTS}")
        if family["protocol_version"] != PROTOCOL_VERSION:
            problems.append(f"{label}: unknown protocol version {family['protocol_version']!r}")
        try:
            known = set(editions.get(family["source"]).episode_ids)
        except ls.LiteraryError as error:
            problems.append(f"{label}: {error}")
            continue
        episodes = family_episodes(family)
        if not episodes:
            problems.append(f"{label}: no episodes")
        for episode in episodes:
            if episode not in known:
                problems.append(f"{label}: unknown episode {episode!r}")
            elif episode in owner:
                problems.append(f"{label}: episode {episode!r} is already in family {owner[episode]!r}")
            else:
                owner[episode] = family_id
    return problems


def validate_rows(rows: Sequence[dict[str, str]], families: dict[str, dict[str, str]], editions: Editions) -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()
    for row in rows:
        candidate = row.get("candidate_id", "")
        label = f"candidate {candidate or '?'}"
        if not _CANDIDATE_ID_RE.match(candidate):
            problems.append(f"{label}: malformed candidate id")
        if candidate in seen:
            problems.append(f"{label}: duplicate candidate id")
        seen.add(candidate)
        problems.extend(f"{label}: {problem}" for problem in _row_problems(row, families, editions))
    return problems


def _row_problems(row: dict[str, str], families: dict[str, dict[str, str]], editions: Editions) -> list[str]:
    problems = _label_problems(row)
    family = families.get(row["family_id"])
    if family is None:
        return [*problems, f"family {row['family_id']!r} is not in {FAMILIES_FILE}"]
    if row["source"] != family["source"] or row["split"] != family["split"]:
        problems.append("source/split disagree with its family")
    if row["episode_id"] not in family_episodes(family):
        problems.append(f"episode {row['episode_id']!r} is not in family {family['family_id']!r}")
        return problems
    try:
        edition = editions.get(row["source"])
        start, end = int(row["target_start"]), int(row["target_end"])
    except ls.LiteraryError as error:
        return [*problems, str(error)]
    except ValueError:
        return [*problems, "target offsets are not integers"]
    episode_start, episode_end = edition.episode_bounds(row["episode_id"])
    if not episode_start <= start < end <= episode_end:
        return [*problems, "target offsets fall outside its episode"]
    if row["source_sha256"] != edition.sha256:
        problems.append("source_sha256 does not match the pinned file (re-pin needs a migration)")
    if hashlib.sha256(edition.text[start:end].encode("utf-8")).hexdigest() != row["target_sha256"]:
        problems.append("target text no longer matches target_sha256")
    if row["origin"] == "manual" and row["candidate_id"] != lp.candidate_id(row["source"], start, end):
        problems.append("manual candidate id does not match its span")
    overlapping = edition.units_overlapping(row["episode_id"], start, end)
    if row["status"] == "include" and any(unit.kind in ls.NON_SPEECH_KINDS for unit in overlapping):
        problems.append("an included target overlaps a title or narrator moral; exclude it as narrator_moral")
    return problems


def _label_problems(row: dict[str, str]) -> list[str]:
    problems = []
    status, reason = row["status"], row["exclusion_reason"]
    if status not in STATUSES:
        problems.append(f"status {status!r} is not one of {STATUSES}")
    if row["origin"] not in ORIGINS:
        problems.append(f"origin {row['origin']!r} is not one of {ORIGINS}")
    if status == "exclude" and reason not in EXCLUSION_REASONS:
        problems.append(f"exclude needs an exclusion_reason from {', '.join(EXCLUSION_REASONS)}")
    if status != "exclude" and reason:
        problems.append("exclusion_reason is only allowed when status is exclude")
    for field in ("speaker", "addressee"):
        value = row[field]
        if status == "include" and not value:
            problems.append(f"include needs the {field}")
        problem = _single_line(value, MAX_ROLE_CHARS, field) if value else None
        if problem:
            problems.append(problem)
    if not _SHA256_RE.match(row["target_sha256"]) or not _SHA256_RE.match(row["source_sha256"]):
        problems.append("malformed sha256")
    if not _SCREENER_RE.match(row["screener"]):
        problems.append("malformed screener id")
    if row["protocol_version"] != PROTOCOL_VERSION:
        problems.append(f"unknown protocol version {row['protocol_version']!r}")
    return problems


# --------------------------------------------------------------------------- CLI


def list_families(dirs: Dirs) -> int:
    families = load_families(dirs)
    for family in families:
        print(f"{family['family_id']:<40} {family['source']:<16} {family['split']:<4} {family['assignment']:<8} {family['episode_ids']}")
    if not families:
        print(f"no families yet in {dirs.families}")
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--raw-dir", type=Path, default=ls.DEFAULT_RAW_DIR)
    parser.add_argument("--manifest", type=Path, default=download_sources.DEFAULT_MANIFEST)
    parser.add_argument("--annotations-dir", type=Path, default=DEFAULT_ANNOTATIONS_DIR)
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
    commands = parser.add_subparsers(dest="command", required=True)

    families = commands.add_parser("families", help="assign dev pilot families").add_subparsers(dest="action", required=True)
    draw = families.add_parser("draw", help="seeded uniform draw of single-episode families")
    draw.add_argument("--source", required=True, choices=sorted(ls.PARSERS))
    draw.add_argument("--count", type=int, required=True)
    draw.add_argument("--seed", type=int, required=True)
    draw.add_argument("--date", help="assignment date YYYY-MM-DD (default: today)")
    assign = families.add_parser("assign", help="explicit family, e.g. a meeting candidate or a multi-chapter account")
    assign.add_argument("--source", required=True, choices=sorted(ls.PARSERS))
    assign.add_argument("--family-id", required=True)
    assign.add_argument("--episodes", nargs="+", required=True)
    assign.add_argument("--reason", required=True)
    assign.add_argument("--date", help="assignment date YYYY-MM-DD (default: today)")
    families.add_parser("list", help="show assigned families")

    commands.add_parser("propose", help="append mechanical candidates for unproposed dev families to the sheet")
    export_parser = commands.add_parser("export", help="write the committed, text-free screening log")
    export_parser.add_argument("--screener", required=True, help="pseudonymous screener id, e.g. A1")
    commands.add_parser("validate", help="re-derive committed files from the pinned sources")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _parse_args(argv)
    dirs = Dirs(args.raw_dir, args.manifest, args.annotations_dir, args.work_dir)
    editions = Editions(dirs)
    try:
        if args.command == "families":
            if args.action == "draw":
                draw_families(dirs, editions, args.source, args.count, args.seed, args.date)
            elif args.action == "assign":
                assign_family(dirs, editions, args.source, args.family_id, args.episodes, args.reason, args.date)
            else:
                list_families(dirs)
        elif args.command == "propose":
            propose(dirs, editions)
        elif args.command == "export":
            export(dirs, editions, args.screener)
        else:
            validate(dirs, editions)
    except (ScreeningError, ls.LiteraryError, download_sources.DownloadSourcesError, csv.Error) as error:
        logger.error("%s", error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
