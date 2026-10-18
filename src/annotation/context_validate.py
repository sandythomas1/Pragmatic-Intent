"""Integrity checks over the committed contextual-annotation data (spec 003 FR12).

``python -m src.annotation.context validate`` loads the workspace and passes it to the pure checks
here. Each check returns ``Finding``s that name a rule from ``RULES`` and a subject (an item, a
group or a file), so one run lists every problem at once.

Edited labels are caught through the local text file. Each text record carries the key of the
committed row it was exported with, so a label changed afterwards matches no record (``row-hash``).
That guards against accidents and stale copies. It is not a defence against someone who edits both
files consistently, and it can't be: the text file is local, not committed.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from src.annotation import context_items as ci
from src.annotation import context_passes as cp
from src.annotation import context_schema as cs
from src.annotation import context_taxonomy as ct

RULES = {
    "registry": "registry fields and formats",
    "duplicate-id": "an item registered twice, or more than one live row per item",
    "foreign-id": "a row, log entry or file that names an unknown item or annotator",
    "group-split": "a group spans splits, or its split differs from its source",
    "target-hash": "the registered target can't be rebuilt from its source with the same hash",
    "screening-log": "a literary item no longer matches an 'include' row of the screening log",
    "taxonomy": "the taxonomy file is invalid, or a version used by labels is missing or edited",
    "labels": "enums and the FR6 cross-field rules, including the intent's slots and stratum",
    "evidence": "n_segments or an evidence index disagrees with the rebuilt prior context",
    "prior-chain": "prior_sha256 matches no earlier-pass row it could have been built on",
    "corrections": "the corrections log disagrees with the superseded rows",
    "row-hash": "no local text record carries this committed row's key: labels or text changed",
    "local-text": "the local text file is missing or malformed, or its text hash doesn't match",
}


@dataclass(frozen=True, order=True)
class Finding:
    rule: str
    subject: str
    message: str

    def __post_init__(self) -> None:
        if self.rule not in RULES:
            raise ValueError(f"unknown validation rule {self.rule!r}")

    def __str__(self) -> str:
        return f"[{self.rule}] {self.subject}: {self.message}"


@dataclass(frozen=True)
class PassFile:
    """One annotator's committed rows for one pass, and the local text records for them.

    ``rows`` holds only rows that passed the structural checks; ``texts`` is None when the text
    file is missing or unreadable (already reported).
    """

    pass_name: str
    annotator: str
    rows: Sequence[Mapping[str, str]]
    texts: Mapping[tuple[str, str], Mapping[str, str]] | None

    def item_rows(self, item: str) -> list[Mapping[str, str]]:
        return [row for row in self.rows if row["item_id"] == item]


@dataclass(frozen=True)
class SourceFacts:
    """What validation needs from an item's rebuilt source."""

    stratum: str
    n_segments: int


PassFiles = Mapping[tuple[str, str], PassFile]  # (pass, annotator) → file


def shown(value: str | None) -> str:
    """An ID for a message: as is when well-formed, else its repr, so no raw cell reaches the terminal."""
    if value and (cs.DIALOGUE_ITEM_RE.fullmatch(value) or cs.LITERARY_ITEM_RE.fullmatch(value)):
        return value
    return repr(value)[:60]


# --------------------------------------------------------------------------- registry and sources


def check_registry(
    rows: Sequence[Mapping[str, str]],
    dialogue_splits: Mapping[str, set[str]] | None,
    families: Mapping[str, Mapping[str, str]],
) -> list[Finding]:
    """Row formats, duplicate items, and each group's split against its source.

    ``dialogue_splits`` maps a dialogue file name to the splits ``items.jsonl`` gives it (None when
    ``items.jsonl`` is unavailable, which the caller reports). Literary splits come from the
    spec 002 families file.
    """
    findings: list[Finding] = []
    seen: set[str] = set()
    group_splits: dict[str, set[str]] = defaultdict(set)
    for line, row in enumerate(rows, start=2):
        subject = shown(row.get("item_id")) if row.get("item_id") else f"registry line {line}"
        if set(row) != set(ci.REGISTRY_FIELDS) or any(value is None for value in row.values()):
            findings.append(Finding("registry", subject, "columns do not match the registry header"))
            continue
        if row["item_id"] in seen:
            findings.append(Finding("duplicate-id", subject, "registered more than once"))
        seen.add(row["item_id"])
        findings += [Finding("registry", subject, problem) for problem in ci.row_problems(row)]
        group_splits[row["group_id"]].add(row["split"])
        if row["stratum"] in cs.STRATA:
            findings += _source_split(row, dialogue_splits, families)
    findings += [Finding("group-split", f"group {group}", f"spans splits {sorted(splits)}")
                 for group, splits in sorted(group_splits.items()) if len(splits) > 1]  # fmt: skip
    return findings


def _source_split(
    row: Mapping[str, str], dialogue_splits: Mapping[str, set[str]] | None, families: Mapping[str, Mapping[str, str]]
) -> list[Finding]:
    subject = shown(row["item_id"])
    if row["stratum"] == "dialogue":
        if dialogue_splits is None:
            return []
        dialogue = row["source_ref"].split("#")[0]
        splits = dialogue_splits.get(dialogue)
        if splits is None:
            return [Finding("group-split", subject, f"{dialogue!r} is not in items.jsonl")]
        if splits != {row["split"]}:
            return [Finding("group-split", subject, f"registered as {row['split']!r}, but items.jsonl puts {dialogue!r} in {sorted(splits)}")]
        return []
    family = families.get(row["group_id"])
    if family is not None and family["split"] != row["split"]:
        return [Finding("group-split", subject, f"registered as {row['split']!r}, but family {row['group_id']!r} is {family['split']!r}")]
    return []


def check_screening(
    registry: Iterable[Mapping[str, str]], log: Mapping[str, Mapping[str, str]], families: Mapping[str, Mapping[str, str]]
) -> list[Finding]:
    """Every registered literary item must still be the same ``include`` row of the screening log."""
    findings: list[Finding] = []
    for row in registry:
        if row["stratum"] != "literary":
            continue
        subject, entry = row["item_id"], log.get(row["item_id"])
        if entry is None:
            findings.append(Finding("screening-log", subject, "is no longer in the screening log"))
            continue
        if entry["status"] != "include":
            findings.append(Finding("screening-log", subject, f"screening status changed to {entry['status']!r} after registration"))
        if row["group_id"] not in families:
            findings.append(Finding("screening-log", subject, f"family {row['group_id']!r} is not in the families file"))
        for registry_field, log_field in (("group_id", "family_id"), ("source_ref", "source"), ("target_sha256", "target_sha256")):
            if row[registry_field] != entry[log_field]:
                findings.append(Finding("screening-log", subject, f"registry {registry_field} differs from the log's {log_field}"))
    return findings


# --------------------------------------------------------------------------- committed pass files


def usable_rows(
    file_name: str, rows: Sequence[Mapping[str, str]], pass_name: str, annotator: str
) -> tuple[list[Mapping[str, str]], list[Finding]]:
    """Split a pass file into rows fit for the cross-file checks and findings for the rest."""
    fields = cp.COMMITTED_FIELDS[pass_name]
    if rows and tuple(rows[0]) != fields:
        return [], [Finding("labels", file_name, f"columns {list(rows[0])} do not match {list(fields)}")]
    usable, findings = [], []
    for line, row in enumerate(rows, start=2):
        problems = cp.committed_row_problems(row, pass_name, annotator)
        if problems:
            subject = f"{shown(row.get('item_id'))} ({file_name} line {line})"
            findings += [Finding("labels", subject, problem) for problem in problems]
        else:
            usable.append(row)
    return usable, findings


def check_pass_file(
    pass_file: PassFile,
    registry: Mapping[str, Mapping[str, str]],
    sources: Mapping[str, SourceFacts],
    taxonomy: ct.Taxonomy | None,
) -> list[Finding]:
    """Per-row checks of one pass file against the registry, rebuilt sources, taxonomy and local text."""
    findings: list[Finding] = []
    live = Counter(row["item_id"] for row in pass_file.rows if row["status"] == "")
    where = f"{pass_file.pass_name} {pass_file.annotator}"
    findings += [Finding("duplicate-id", f"{item} ({where})", f"{count} live rows") for item, count in sorted(live.items()) if count > 1]
    for row in pass_file.rows:
        item = row["item_id"]
        subject = f"{item} ({where}{', superseded' if row['status'] else ''})"
        if item not in registry:
            findings.append(Finding("foreign-id", subject, "item is not in the registry"))
            continue
        findings += _text_findings(pass_file, row, subject)
        if pass_file.pass_name == "context":
            findings += _context_findings(row, subject, registry[item]["stratum"], sources.get(item), taxonomy)
    if pass_file.texts is not None:
        findings += [Finding("foreign-id", f"{item} ({where} text)", "text record for an item that is not in the registry")
                     for item, _ in sorted(pass_file.texts) if item not in registry]  # fmt: skip
    return findings


def _text_findings(pass_file: PassFile, row: Mapping[str, str], subject: str) -> list[Finding]:
    if pass_file.texts is None:
        return []
    record = pass_file.texts.get((row["item_id"], cp.row_key(row)))
    if record is None:
        return [Finding("row-hash", subject, "no local text record carries this row's key: its labels or the text file changed after export")]
    if record.get("pass") != pass_file.pass_name or record.get("annotator") != pass_file.annotator:
        return [Finding("local-text", subject, "the text record belongs to another pass or annotator")]
    if pass_file.pass_name == "context":
        digest = cs.text_hash(row["item_id"], "context", pass_file.annotator, record.get("slots", ""), record.get("paraphrase", ""))
        if digest != row["text_sha256"]:
            return [Finding("local-text", subject, "slot values or paraphrase in the local text file no longer match text_sha256")]
    return []


def _context_findings(
    row: Mapping[str, str], subject: str, stratum: str, source: SourceFacts | None, taxonomy: ct.Taxonomy | None
) -> list[Finding]:
    findings: list[Finding] = []
    if source is not None:
        if int(row["n_segments"]) != source.n_segments:
            findings.append(Finding("evidence", subject, f"n_segments is {row['n_segments']}, but the prior context has {source.n_segments} segment(s)"))
        else:
            try:
                cp.parse_evidence(row["evidence"], source.n_segments)
            except cs.SchemaError as error:
                findings.append(Finding("evidence", subject, str(error)))
    if taxonomy is None:
        return findings
    version = row["taxonomy_version"]
    if version not in taxonomy.intents:
        return findings  # reported once per version by check_taxonomy_versions
    if taxonomy.sha256(version) != row["taxonomy_sha256"]:
        findings.append(Finding("taxonomy", subject, f"{version} was edited in place after this row was exported"))
    if row["function"] in ("request", "uncertain") and row["intent"]:
        findings += [Finding("labels", subject, problem) for problem in _intent_problems(row, stratum, taxonomy)]
    return findings


def _intent_problems(row: Mapping[str, str], stratum: str, taxonomy: ct.Taxonomy) -> list[str]:
    problems: list[str] = []
    version = row["taxonomy_version"]
    for label in ("intent", "alt_intent"):
        if not row[label]:
            continue
        try:
            intent = taxonomy.intent(version, row[label])
        except cs.SchemaError as error:
            problems.append(f"{label}: {error}")
            continue
        if not intent.allows(stratum):
            problems.append(f"{label} {row[label]!r} is a {intent.stratum} intent; this is a {stratum} item")
        if label == "intent":
            names = [name for name in row["slot_names"].split(";") if name]
            problems += ct.slot_problems(intent, [(name, cs.UNSTATED_SLOT_VALUE) for name in names])
    return problems


# --------------------------------------------------------------------------- chain and corrections


def logged_corrections(log: Iterable[Mapping[str, str]]) -> set[tuple[str, str, str, str]]:
    """(item, pass, annotator, old_sha256) of every logged correction: superseded rows later rows may build on."""
    return {(entry["item_id"], entry["pass"], entry["annotator"], entry["old_sha256"]) for entry in log}


def check_chain(files: PassFiles, registry: Mapping[str, Mapping[str, str]], logged: set[tuple[str, str, str, str]]) -> list[Finding]:
    """FR10: each row's prior_sha256 is the hash of its registry row or of a row of the previous pass.

    A row built on a since-superseded row is valid (FR9) when that correction is logged; coverage
    reports it as ``built_on_superseded``.
    """
    findings: list[Finding] = []
    for (pass_name, annotator), pass_file in sorted(files.items()):
        prior_pass = cp.PRIOR_PASS[pass_name]
        prior_file = files.get((prior_pass, annotator)) if prior_pass else None
        for row in pass_file.rows:
            item = row["item_id"]
            if item not in registry:
                continue
            subject = f"{item} ({pass_name} {annotator}{', superseded' if row['status'] else ''})"
            if prior_pass is None:
                if row["prior_sha256"] != cs.canonical_hash(registry[item]):
                    findings.append(Finding("prior-chain", subject, "prior_sha256 no longer matches the item's registry row"))
                continue
            problem = _prior_problem(row, prior_pass, prior_file, logged)
            if problem:
                findings.append(Finding("prior-chain", subject, problem))
    return findings


def _prior_problem(row: Mapping[str, str], prior_pass: str, prior_file: PassFile | None, logged: set[tuple[str, str, str, str]]) -> str:
    candidates = prior_file.item_rows(row["item_id"]) if prior_file else []
    if any(candidate["status"] == "" and cs.canonical_hash(candidate) == row["prior_sha256"] for candidate in candidates):
        return ""
    if any(cs.canonical_hash(candidate) == row["prior_sha256"] for candidate in candidates):
        if (row["item_id"], prior_pass, row["annotator"], row["prior_sha256"]) in logged:
            return ""
        return f"built on a superseded {prior_pass} row whose correction is not in {cp.CORRECTIONS_FILE}"
    return f"prior_sha256 matches no {prior_pass} row of {row['annotator']} for this item"


def check_corrections(log: Sequence[Mapping[str, str]], files: PassFiles, registry: Mapping[str, Mapping[str, str]]) -> list[Finding]:
    """The log and the superseded rows must tell the same story (FR9)."""
    findings: list[Finding] = []
    entries: Counter[tuple[str, str, str]] = Counter()
    for line, entry in enumerate(log, start=2):
        subject = f"{shown(entry.get('item_id'))} ({cp.CORRECTIONS_FILE} line {line})"
        problems = cp.correction_problems(entry)
        if problems:
            findings += [Finding("corrections", subject, problem) for problem in problems]
            continue
        key = (entry["item_id"], entry["pass"], entry["annotator"])
        entries[key] += 1
        if entry["item_id"] not in registry:
            findings.append(Finding("foreign-id", subject, "item is not in the registry"))
            continue
        pass_file = files.get((entry["pass"], entry["annotator"]))
        if pass_file is None:
            findings.append(Finding("corrections", subject, f"there is no {entry['pass']} file for {entry['annotator']}"))
            continue
        findings += [Finding("corrections", subject, problem) for problem in _entry_problems(entry, pass_file, files)]
    superseded = Counter(
        (row["item_id"], pass_name, annotator)
        for (pass_name, annotator), pass_file in files.items()
        for row in pass_file.rows
        if row["status"] == "superseded"
    )
    for key in sorted(set(superseded) | set(entries)):
        if superseded[key] != entries[key]:
            item, pass_name, annotator = key
            findings.append(Finding("corrections", f"{item} ({pass_name} {annotator})",
                                    f"{superseded[key]} superseded row(s) but {entries[key]} logged correction(s)"))  # fmt: skip
    return findings


def _entry_problems(entry: Mapping[str, str], pass_file: PassFile, files: PassFiles) -> list[str]:
    rows = pass_file.item_rows(entry["item_id"])
    problems = []
    if not any(row["status"] == "superseded" and cs.canonical_hash(row) == entry["old_sha256"] for row in rows):
        problems.append("old_sha256 matches no superseded row")
    if not any(cs.canonical_hash(row) == entry["new_sha256"] for row in rows):
        problems.append("new_sha256 matches no row")
    if entry["later_passes_sealed"] == "false":
        for later in cp.LATER_PASSES[entry["pass"]]:
            later_file = files.get((later, entry["annotator"]))
            built = later_file.item_rows(entry["item_id"]) if later_file else []
            if any(row["prior_sha256"] == entry["old_sha256"] for row in built):
                problems.append(f"says later passes were not sealed, but a {later} row was built on the corrected row")
                break
    return problems


def check_taxonomy_versions(taxonomy: ct.Taxonomy, files: PassFiles) -> list[Finding]:
    """FR3: a version that any committed label uses must still be in the taxonomy file."""
    referenced = {row["taxonomy_version"] for (pass_name, _), pass_file in files.items() if pass_name == "context" for row in pass_file.rows}
    return [Finding("taxonomy", ct.TAXONOMY_FILE, problem) for problem in ct.missing_versions(taxonomy, referenced)]
