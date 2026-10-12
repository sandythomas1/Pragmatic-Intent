"""Coverage tables for one batch, per annotator (spec 003 FR13, FR14).

Every table prints every cell, zeros included, so an empty cell is visible rather than missing.
Counts use each item's live (non-superseded) rows and are never pooled across annotators: each
annotator gets their own section. The data must already pass ``validate``.

Derived here, never stored:

* ``request_type`` from the live form label and the live context ``request_status`` (FR11).
* ``prior_exposure``: a literary item whose annotator screened it in spec 002 has read the target
  in context, ending included, so every one of their passes on it is exposed (FR14). This is a
  disclosed limitation, not an error.
* ``built_on_superseded``: a live row whose ``prior_sha256`` is a superseded row of the previous
  pass, i.e. the annotator corrected an earlier pass after building on it (FR9).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.annotation import context_passes as cp
from src.annotation import context_schema as cs
from src.annotation import context_taxonomy as ct
from src.annotation import context_validate as vd

FLAGS = ("true", "false")


@dataclass(frozen=True)
class Table:
    title: str
    rows: Sequence[str]
    columns: Sequence[str]
    counts: Mapping[tuple[str, str], int]

    def render(self) -> list[str]:
        width = max([len(row) for row in self.rows] + [1])
        widths = [max(len(column), 3) for column in self.columns]
        lines = [self.title, "  " + " " * width + "".join(f"  {column:>{w}}" for column, w in zip(self.columns, widths))]
        for row in self.rows:
            cells = "".join(f"  {self.counts.get((row, column), 0):>{w}}" for column, w in zip(self.columns, widths))
            lines.append(f"  {row:<{width}}{cells}")
        return lines


@dataclass(frozen=True)
class AnnotatorRows:
    """One annotator's live rows in the batch, by pass and item, plus every row (for superseded hashes)."""

    annotator: str
    live: Mapping[str, Mapping[str, Mapping[str, str]]]  # pass → item → row
    all_rows: Mapping[str, Sequence[Mapping[str, str]]]  # pass → rows, superseded included


def annotator_rows(files: Mapping[tuple[str, str], vd.PassFile], batch_items: set[str]) -> list[AnnotatorRows]:
    """Every annotator with at least one row in the batch, in name order."""
    annotators = sorted({annotator for (_, annotator), pass_file in files.items()
                         if any(row["item_id"] in batch_items for row in pass_file.rows)})  # fmt: skip
    result = []
    for annotator in annotators:
        all_rows = {
            pass_name: [row for row in files[(pass_name, annotator)].rows if row["item_id"] in batch_items]
            if (pass_name, annotator) in files else []
            for pass_name in cs.PASSES
        }  # fmt: skip
        live = {pass_name: dict(cp.live_rows(rows)) for pass_name, rows in all_rows.items()}
        result.append(AnnotatorRows(annotator, live, all_rows))
    return result


def tables(
    rows: AnnotatorRows,
    strata: Mapping[str, str],
    screeners: Mapping[str, str],
    taxonomy: ct.Taxonomy | None,
) -> list[Table]:
    """All FR13 tables for one annotator. ``strata``: item → stratum; ``screeners``: literary item → screener."""
    form, context, reveal = (rows.live[name] for name in cs.PASSES)
    request_types = {item: cs.request_type(form[item]["form"], row["request_status"]) for item, row in context.items() if item in form}
    intents = _intent_rows(context, taxonomy)
    return [
        Table("stratum by function (context pass)", cs.STRATA, cs.FUNCTIONS,
              Counter((strata[item], row["function"]) for item, row in context.items())),
        Table("form by function (form and context passes)", cs.FORM_LABELS, cs.FUNCTIONS,
              Counter((form[item]["form"], row["function"]) for item, row in context.items() if item in form)),
        Table("form by request type (derived, FR11)", cs.FORM_LABELS, cs.REQUEST_TYPES,
              Counter((form[item]["form"], kind) for item, kind in request_types.items())),
        Table("intent by stratum (request and uncertain rows)", [label for label, _ in intents], cs.STRATA,
              Counter((_intent_label(row), strata[item]) for item, row in context.items() if row["intent"])),
        Table("slots per intent: stated, unstated (?), absent", *_slot_table(context, intents)),
        Table("confidence (context pass)", ["rows"], cs.CONFIDENCES, Counter(("rows", row["confidence"]) for row in context.values())),
        Table("future dependence (reveal pass)", ["rows"], cs.FUTURE_DEPENDENCE,
              Counter(("rows", row["future_dependence"]) for row in reveal.values())),
        Table("needs_adjudication (reveal pass)", ["rows"], FLAGS, Counter(("rows", row["needs_adjudication"]) for row in reveal.values())),
        Table("prior_exposure (annotator screened the literary item, FR14)", cs.PASSES, FLAGS,
              Counter((name, _flag(screeners.get(item) == rows.annotator)) for name in cs.PASSES for item in rows.live[name])),
        Table("built_on_superseded (built on a since-corrected earlier pass, FR9)", cs.PASSES[1:], FLAGS,
              Counter((name, _flag(_built_on_superseded(rows, name, row))) for name in cs.PASSES[1:] for row in rows.live[name].values())),
    ]  # fmt: skip


def _intent_rows(context: Mapping[str, Mapping[str, str]], taxonomy: ct.Taxonomy | None) -> list[tuple[str, ct.Intent | None]]:
    """(label, intent) for every intent of every version the rows use (the newest if none), zeros included."""
    versions = sorted({row["taxonomy_version"] for row in context.values()})
    if not versions and taxonomy is not None:
        versions = [taxonomy.latest]
    labels: list[tuple[str, ct.Intent | None]] = []
    for version in versions:
        defined = taxonomy.intents.get(version, {}) if taxonomy else {}
        labels += [(f"{version} {intent_id}", defined[intent_id]) for intent_id in sorted(defined)]
        labels.append((f"{version} {cs.OUT_OF_TAXONOMY}", None))
    used = {_intent_label(row) for row in context.values() if row["intent"]}
    labels += [(label, None) for label in sorted(used - {label for label, _ in labels})]
    return labels


def _intent_label(row: Mapping[str, str]) -> str:
    return f"{row['taxonomy_version']} {row['intent']}"


def _slot_table(
    context: Mapping[str, Mapping[str, str]], intents: Sequence[tuple[str, ct.Intent | None]]
) -> tuple[list[str], tuple[str, ...], Counter[tuple[str, str]]]:
    row_labels: list[str] = []
    counts: Counter[tuple[str, str]] = Counter()
    for label, intent in intents:
        if intent is None:
            continue
        rows = [row for row in context.values() if _intent_label(row) == label]
        for slot in (*intent.required, *intent.optional):
            slot_label = f"{label}.{slot}{'*' if slot in intent.required else ''}"
            row_labels.append(slot_label)
            for row in rows:
                names, unstated = row["slot_names"].split(";"), row["unstated_slots"].split(";")
                state = "?" if slot in unstated else "stated" if slot in names else "absent"
                counts[(slot_label, state)] += 1
    return row_labels, ("stated", "?", "absent"), counts


def _built_on_superseded(rows: AnnotatorRows, pass_name: str, row: Mapping[str, str]) -> bool:
    prior_pass = cp.PRIOR_PASS[pass_name]
    live = rows.live[prior_pass].get(row["item_id"])
    if live is not None and cs.canonical_hash(live) == row["prior_sha256"]:
        return False
    return any(
        old["item_id"] == row["item_id"] and old["status"] == "superseded" and cs.canonical_hash(old) == row["prior_sha256"]
        for old in rows.all_rows[prior_pass]
    )


def _flag(value: bool) -> str:
    return "true" if value else "false"


def report(
    batch: str,
    batch_strata: Mapping[str, str],
    files: Mapping[tuple[str, str], vd.PassFile],
    screeners: Mapping[str, str],
    taxonomy: ct.Taxonomy | None,
) -> str:
    """The full plain-text coverage report for one batch."""
    strata = Counter(batch_strata.values())
    lines = [
        f"Coverage for batch {batch} ({cs.PROTOCOL_VERSION}): {len(batch_strata)} item(s), "
        f"{strata['dialogue']} dialogue and {strata['literary']} literary.",
        "Counts are per annotator from live rows. Never pool them across annotators.",
    ]
    people = annotator_rows(files, set(batch_strata))
    if not people:
        lines.append("No annotator has exported labels for this batch yet.")
    for rows in people:
        labeled = ", ".join(f"{name} {len(rows.live[name])}" for name in cs.PASSES)
        corrected = sum(row["status"] == "superseded" for name in cs.PASSES for row in rows.all_rows[name])
        lines += ["", f"== {rows.annotator} ==", f"labeled items: {labeled}; superseded rows: {corrected}"]
        for table in tables(rows, batch_strata, screeners, taxonomy):
            lines += ["", *table.render()]
    return "\n".join(lines) + "\n"
