"""LaTeX tables and prose numbers for the paper, from the committed test tables (spec 001 FR-12, AC-12).

Run from the repository root (Python 3.12, standard library only)::

    python -m src.analysis.paper_tables --tables results/analysis/test --out paper/generated

Every number the paper prints comes from ``results/analysis/test/*.csv``: the tables as ``.tex``
fragments, and the numbers quoted in the prose as macros in ``numbers.tex``. Nothing is typed by
hand. Each fragment opens with a comment naming its source files, their SHA-256 and the analysis
config hash, and ``provenance.tex`` lists the same for the paper's appendix (AC-12).

**Fail closed.** A missing column, a missing row, an unknown system name, a non-finite number or
two configs disagreeing stops the run with a named error. Text from the CSVs never reaches the
output: labels come from fixed maps here, so the fragments hold only these labels and numbers.
As a last guard, nothing resembling a dialogue ID is written (spec 006).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import math
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from src.analysis.files import AnalysisError, read_bounded
from src.analysis.report import _ID_PATTERN as DIALOGUE_ID_PATTERN
from src.analysis.report import write_atomic

MAX_TABLE_BYTES = 8 << 20
COMMAND = "python -m src.analysis.paper_tables --tables results/analysis/test --out paper/generated"
_CONFIG = re.compile(r"\(config ([0-9a-f]{12})\)")

SYSTEMS = {
    "tfidf-utterance": "TF-IDF (utterance)",
    "tfidf-context": "TF-IDF (context)",
    "deberta-v3-base": "DeBERTa-v3-base",
    "deberta-v3-large": "DeBERTa-v3-large",
    "qwen2.5-7b-instruct": "Qwen2.5-7B-Instruct",
    "hybrid": "Routed hybrid",
}
ENDPOINTS = {"stage1_correct": "detection", "type_exact": "type", "request_interpretation": "interp."}
CONDITIONS = ("none", "one", "full", "mismatched", "mismatched_one")
CONDITION_HEADS = ("none", "one", "full", "mism.", "mism.-one")
LEVELS = ("L0", "L1", "L2", "L3", "INF", "NR")
OVERALL_CONTRASTS = ("one_minus_none", "full_minus_none", "full_minus_one")  # the prose quotes all three
INTENTS = (("info_seeking", "Info-seeking"), ("booking", "Booking"), ("travel", "Travel"),
           ("recommendation", "Recommendation"))  # cat-v1 request categories, in the paper's order
HYBRID_RI = {"system": "hybrid", "line": "matched", "endpoint": "request_interpretation"}
FLAG = r"\textsuperscript{\dag}"


@dataclass(frozen=True)
class Source:
    """One parsed CSV and what identifies it: its path, SHA-256 and analysis config hash."""

    name: str
    sha256: str
    config: str | None
    rows: tuple[dict[str, str], ...]

    def find(self, **key: str) -> dict[str, str]:
        hits = [row for row in self.rows if all(row.get(k) == v for k, v in key.items())]
        if len(hits) != 1:
            raise AnalysisError("missing_row" if not hits else "ambiguous_row",
                                f"{self.name}: {len(hits)} rows match {dict(sorted(key.items()))}")
        return hits[0]


@dataclass(frozen=True)
class Fragment:
    name: str
    sources: tuple[Source, ...]
    body: str


def load_source(directory: Path, name: str, required: Sequence[str]) -> Source:
    """The table ``name``.csv, checked for its columns and for a single analysis config."""
    path = directory / f"{name}.csv"
    data = read_bounded(path, MAX_TABLE_BYTES)
    try:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""), strict=True)
        rows = tuple(dict(row) for row in reader)
    except (UnicodeDecodeError, csv.Error):
        raise AnalysisError("invalid_csv", f"{path.name} is not UTF-8 CSV") from None
    missing = [column for column in required if column not in (reader.fieldnames or ())]
    if missing:
        raise AnalysisError("missing_column", f"{path.name} lacks {missing}")
    configs = {match.group(1) for row in rows if (match := _CONFIG.search(row.get("provenance") or ""))}
    if len(configs) > 1:
        raise AnalysisError("mixed_config", f"{path.name} mixes analysis configs {sorted(configs)}")
    return Source(name=f"{name}.csv", sha256=hashlib.sha256(data).hexdigest(),
                  config=next(iter(configs), None), rows=rows)


# ------------------------------------------------------------------------------------- formatting


def _finite(value: str, label: str) -> float:
    try:
        number = float(value)
    except ValueError:
        raise AnalysisError("not_a_number", f"{label}: {value[:20]!r} is not a number") from None
    if not math.isfinite(number):
        raise AnalysisError("not_a_number", f"{label} is not finite")
    return number


def num(value: str, label: str = "value", places: int = 3, signed: bool = False) -> str:
    """A number in math-mode-safe text: a true minus sign, and ``--`` for an empty cell."""
    if value == "":
        return "--"
    number = round(_finite(value, label), places)
    if number == 0:
        number = 0.0  # never print -0.000
    text = f"{abs(number):.{places}f}"
    if number < 0:
        return f"$-${text}"
    return f"+{text}" if signed and number > 0 else text


def interval(row: Mapping[str, str], label: str) -> str:
    return f"[{num(row['ci_low'], label)}, {num(row['ci_high'], label)}]"


def p_value(value: str, label: str = "p") -> str:
    if value == "":
        return "--"
    number = _finite(value, label)
    return "$<$0.001" if number < 0.001 else f"{number:.3f}"


def flagged(row: Mapping[str, str], text: str) -> str:
    """Mark a statistic the analysis called sparse, unstable or empty."""
    return text if row.get("status", "ok") == "ok" else text + FLAG


def system_label(system: str) -> str:
    if system not in SYSTEMS:
        raise AnalysisError("unknown_system", f"no paper label for system {system[:40]!r}")
    return SYSTEMS[system]


def tabular(spec: str, head: Sequence[str], lines: Sequence[str]) -> str:
    rows = "\n".join(lines)
    return (f"\\begin{{tabular}}{{{spec}}}\n\\toprule\n{' & '.join(head)} \\\\\n\\midrule\n"
            f"{rows}\n\\bottomrule\n\\end{{tabular}}\n")


# ------------------------------------------------------------------------------------- tables

OVERALL_ROWS = (
    ("tfidf-utterance", "test_time", "stage1_correct"),
    ("tfidf-context", "test_time", "stage1_correct"),
    ("deberta-v3-base", "matched", "stage1_correct"),
    ("deberta-v3-large", "matched", "stage1_correct"),
    ("qwen2.5-7b-instruct", "test_time", "stage1_correct"),
    ("hybrid", "matched", "stage1_correct"),
    ("qwen2.5-7b-instruct", "test_time", "request_interpretation"),
    ("hybrid", "matched", "request_interpretation"),
)


def overall_rates(rates: Source, mismatch: Source) -> Fragment:
    """Seed-averaged rates by condition, plus the full − mismatched control, for each system."""
    lines = []
    for index, (system, line, endpoint) in enumerate(OVERALL_ROWS):
        if index and endpoint != OVERALL_ROWS[index - 1][2]:
            lines.append("\\midrule")
        cells = [system_label(system), ENDPOINTS[endpoint]]
        for condition in CONDITIONS:
            row = rates.find(system=system, line=line, endpoint=endpoint, condition=condition, level="overall")
            cells.append(flagged(row, num(row["point"], f"{system} {condition}")))
        control = mismatch.find(system=system, line="test_time", endpoint=endpoint,
                                contrast="full_minus_mismatched", level="overall")
        cells.append(flagged(control, num(control["point"], f"{system} control", signed=True)))
        lines.append(" & ".join(cells) + " \\\\")
    head = ("System", "Endpoint", *CONDITION_HEADS, "full$-$mism.")
    return Fragment("overall", (rates, mismatch), tabular("llrrrrrr", head, lines))


def confirmatory(primary: Source, holm: Source) -> Fragment:
    """The confirmatory H2 contrast, then the Holm family of secondary tests."""
    main = primary.find(system="hybrid", line="matched", endpoint="request_interpretation")
    lines = [
        "\\multicolumn{4}{l}{\\emph{Confirmatory (H2): routed hybrid, interpretation, L2$-$L0 of full$-$none}} \\\\",
        " & ".join(("Linear contrast", flagged(main, num(main["point"], "primary", signed=True)),
                    interval(main, "primary"), p_value(main["p"]))) + " \\\\",
        " & ".join(("Quadratic term (descriptive)", num(main["quadratic_point"], "quadratic", signed=True),
                    f"[{num(main['quadratic_ci_low'], 'quadratic')}, {num(main['quadratic_ci_high'], 'quadratic')}]",
                    "--")) + " \\\\",
        "\\midrule",
        "\\multicolumn{4}{l}{\\emph{Secondary family (Holm-adjusted $p$)}} \\\\",
    ]
    for row in holm.rows:
        label = HOLM_LABELS.get(row["name"]) or _h3_label(row)
        lines.append(" & ".join((label, flagged(row, num(row["point"], row["name"][:40], signed=True)),
                                 interval(row, row["name"][:40]), p_value(row["p_holm"]))) + " \\\\")
    head = ("Statistic", "Estimate", "95\\% CI", "$p$")
    return Fragment("confirmatory", (primary, holm), tabular("lrcr", head, lines))


HOLM_LABELS = {
    "h1-trend": "H1: interpretation trend L2$-$L0, none",
    "h2-detection-trend": "H2 (detection): L2$-$L0 of full$-$none",
    "h4-detection-vs-oracle": "H4: detection drop $-$ oracle drop",
    "full-minus-mismatched": "Control: full$-$mismatched (interp.)",
}
_H3 = re.compile(r"^h3-([a-z0-9.\-]+)$")


def _h3_label(row: Mapping[str, str]) -> str:
    """H3 members compare a system's full − none benefit with the hybrid's, on that system's endpoint."""
    match = _H3.match(row["name"])
    if not match or row.get("endpoint") not in ENDPOINTS:
        raise AnalysisError("unknown_family_member", f"no paper label for Holm member {row['name'][:40]!r}")
    return f"H3: {system_label(match.group(1))} $-$ hybrid ({ENDPOINTS[row['endpoint']]})"


def level_detail(rates: Source, benefits: Source) -> Fragment:
    """By rule level: interpretation and detection rates without and with full context, and the benefit."""
    head = ("Level", "$n$", "interp.\\ none", "interp.\\ full", "full$-$none [95\\% CI]",
            "detect.\\ none", "detect.\\ full")
    lines = []
    for level in LEVELS:
        interp = {c: rates.find(system="hybrid", line="matched", endpoint="request_interpretation",
                                condition=c, level=level) for c in ("none", "full")}
        detect = {c: rates.find(system="hybrid", line="matched", endpoint="stage1_correct",
                                condition=c, level=level) for c in ("none", "full")}
        gain = benefits.find(system="hybrid", line="matched", endpoint="request_interpretation",
                             contrast="full_minus_none", level=level)
        cells = (level, interp["none"]["examples"],
                 flagged(interp["none"], num(interp["none"]["point"], level)),
                 flagged(interp["full"], num(interp["full"]["point"], level)),
                 flagged(gain, f"{num(gain['point'], level, signed=True)} {interval(gain, level)}"),
                 flagged(detect["none"], num(detect["none"]["point"], level)),
                 flagged(detect["full"], num(detect["full"]["point"], level)))
        lines.append(" & ".join(cells) + " \\\\")
    return Fragment("levels", (rates, benefits), tabular("lrrrcrr", head, lines))


H4_MEASURES = (("detection", "Detection (gold requests)"), ("oracle", "Oracle interpretation"),
               ("routed", "Routed interpretation"))


def stages(h4: Source) -> Fragment:
    """Detection, oracle and routed interpretation for the hybrid, on gold requests, by condition."""
    lines = []
    for measure, label in H4_MEASURES:
        cells = [label]
        for condition in CONDITIONS:
            row = h4.find(system="hybrid", line="matched", condition=condition, level="overall", measure=measure)
            cells.append(flagged(row, num(row["point"], f"{measure} {condition}")))
        lines.append(" & ".join(cells) + " \\\\")
    return Fragment("stages", (h4,), tabular("lrrrrr", ("Measure", *CONDITION_HEADS), lines))


def intents(rates: Source, benefits: Source) -> Fragment:
    """H5 (exploratory): hybrid interpretation by intent category and condition, and the full − none benefit."""
    lines = []
    for category, label in INTENTS:
        rate = {c: rates.find(**HYBRID_RI, category=category, condition=c) for c in ("none", "one", "full")}
        gain = benefits.find(**HYBRID_RI, category=category, contrast="full_minus_none")
        cells = [label, rate["none"]["examples"]]
        cells += [flagged(rate[c], num(rate[c]["point"], f"{label} {c}")) for c in ("none", "one", "full")]
        cells.append(flagged(gain, f"{num(gain['point'], label, signed=True)} {interval(gain, label)}"))
        lines.append(" & ".join(cells) + " \\\\")
    head = ("Intent", "$n$", "none", "one", "full", "full$-$none [95\\% CI]")
    return Fragment("intents", (rates, benefits), tabular("lrrrrc", head, lines))


def transfer(table: Source) -> Fragment:
    """IndirectRequests transfer: its own table, labelled LLM-generated, never pooled (FR-15)."""
    lines = []
    for row in table.rows:
        gpt = {"true": "yes", "false": "no"}.get(row["gpt_family"])
        if gpt is None or row["data_kind"] != "llm_generated_transfer":
            raise AnalysisError("transfer_label", f"{table.name}: a row is not labelled as LLM-generated transfer")
        if not row["n"].isdigit() or not row["invalid_outputs"].isdigit():
            raise AnalysisError("not_a_number", f"{table.name}: counts must be whole numbers")
        cells = (system_label(row["system"]), gpt, row["n"], num(row["request_recall"], "recall"),
                 num(row["value_accuracy"], "value accuracy"), num(row["end_to_end"], "end to end"),
                 row["invalid_outputs"])
        lines.append(" & ".join(cells) + " \\\\")
    head = ("System", "GPT family", "$n$", "Request recall", "Value acc.", "End to end", "Invalid")
    return Fragment("transfer", (table,), tabular("lcrrrrr", head, lines))


# ------------------------------------------------------------------------------------- prose numbers


def _macro(name: str, value: str) -> str:
    if not re.fullmatch(r"[A-Za-z]+", name):
        raise AnalysisError("bad_macro", f"macro name {name!r} must be letters only")
    return f"\\newcommand{{\\{name}}}{{{value}}}"


def numbers(src: Mapping[str, Source]) -> Fragment:
    """Macros for every number quoted in the prose, so no figure in the text is typed by hand."""
    primary = src["primary_test"].find(system="hybrid", line="matched", endpoint="request_interpretation")
    holm = {row["name"]: row for row in src["holm"].rows}
    rates = src["h1_rates"]
    benefits = src["h2_benefits"]
    hybrid_ri = {c: rates.find(system="hybrid", line="matched", endpoint="request_interpretation",
                               condition=c, level="overall") for c in CONDITIONS}
    qwen_det = {c: rates.find(system="qwen2.5-7b-instruct", line="test_time", endpoint="stage1_correct",
                              condition=c, level="overall") for c in ("none", "full")}
    l3 = benefits.find(system="hybrid", line="matched", endpoint="request_interpretation",
                       contrast="full_minus_none", level="L3")
    oracle = src["h4_rates"].find(system="hybrid", line="matched", condition="full", level="overall", measure="oracle")
    detect = src["h4_rates"].find(system="hybrid", line="matched", condition="full", level="overall",
                                  measure="detection")
    sens = src["sensitivity"].find(system="hybrid", line="matched", endpoint="request_interpretation",
                                   contrast="full_minus_none", statistic="primary_linear_trend",
                                   sensitivity="primary_minus_dup")
    cue_free = src["sensitivity"].find(system="hybrid", line="test_time", endpoint="request_interpretation",
                                       contrast="full_minus_mismatched", statistic="overall_benefit",
                                       sensitivity="without_cue_donors")
    overall = {c: benefits.find(system="hybrid", line="matched", endpoint="request_interpretation",
                                contrast=c, level="overall") for c in OVERALL_CONTRASTS}
    moved = src["transfer"].find(system="qwen2.5-7b-instruct")
    h1 = _member(holm, "h1-trend")
    h4 = _member(holm, "h4-detection-vs-oracle")
    control = src["mismatch_controls"].find(system="hybrid", line="test_time", endpoint="request_interpretation",
                                            contrast="full_minus_mismatched", level="overall")
    configs = sorted({s.config for s in src.values() if s.config})
    if len(configs) != 1:
        raise AnalysisError("mixed_config", f"the tables carry analysis configs {configs}, not exactly one")
    values = [
        ("AnalysisConfig", configs[0]),
        ("PrimaryEst", num(primary["point"], "primary", signed=True)),
        ("PrimaryCI", interval(primary, "primary")),
        ("PrimaryP", p_value(primary["p"])),
        ("PrimaryExamples", _count(primary["examples"])),
        ("PrimaryDialogues", _count(primary["dialogues"])),
        ("QuadEst", num(primary["quadratic_point"], "quadratic", signed=True)),
        ("HoneEst", num(h1["point"], "h1", signed=True)),
        ("HoneCI", interval(h1, "h1")),
        ("HoneP", p_value(h1["p_holm"])),
        ("HfourEst", num(h4["point"], "h4", signed=True)),
        ("HfourCI", interval(h4, "h4")),
        ("HfourP", p_value(h4["p_holm"])),
        ("SensEst", num(sens["point"], "sensitivity", signed=True)),
        ("SensCI", interval(sens, "sensitivity")),
        ("CueFreeEst", num(cue_free["point"], "cue-free control", signed=True)),
        ("CueFreeCI", interval(cue_free, "cue-free control")),
        ("LthreeGain", num(l3["point"], "L3", signed=True)),
        ("LthreeCI", interval(l3, "L3")),
        ("LthreeExamples", _count(l3["examples"])),
        ("ControlEst", num(control["point"], "control", signed=True)),
        ("ControlCI", interval(control, "control")),
        ("OracleFull", num(oracle["point"], "oracle")),
        ("DetectFull", num(detect["point"], "detection")),
        ("QwenDetNone", num(qwen_det["none"]["point"], "qwen detection")),
        ("QwenDetFull", num(qwen_det["full"]["point"], "qwen detection")),
        ("TransferN", _count(moved["n"])),
        ("TransferRecall", num(moved["request_recall"], "recall")),
        ("TransferValue", num(moved["value_accuracy"], "value accuracy")),
        ("TransferEndToEnd", num(moved["end_to_end"], "end to end")),
    ]
    values += [(f"HybridInterp{_camel(c)}", num(hybrid_ri[c]["point"], c)) for c in CONDITIONS]
    for contrast, row in overall.items():
        name = "".join(_camel(part) for part in contrast.split("_minus_"))  # full_minus_none -> FullNone
        values += [(f"{name}Est", num(row["point"], contrast, signed=True)), (f"{name}CI", interval(row, contrast))]
    values += _intent_values(src["h5_rates"], src["h5_benefits"], src["h5_standardized"])
    body = "\n".join(_macro(name, value) for name, value in values) + "\n"
    return Fragment("numbers", tuple(src.values()), body)


def _intent_values(rates: Source, benefits: Source, standardized: Source) -> list[tuple[str, str]]:
    """Per-intent full rate and benefit, and the intent-standardized H2 trend (is the null a mix effect?)."""
    trend = standardized.find(**HYBRID_RI, level="trend", kind="standardized_linear_trend")
    values = [("StdTrendEst", num(trend["point"], "standardized trend", signed=True)),
              ("StdTrendCI", interval(trend, "standardized trend"))]
    for category, label in INTENTS:
        full = rates.find(**HYBRID_RI, category=category, condition="full")
        gain = benefits.find(**HYBRID_RI, category=category, contrast="full_minus_none")
        name = f"Intent{_camel(category)}"  # info_seeking -> IntentInfoSeeking
        values += [(f"{name}Full", num(full["point"], label)),
                   (f"{name}Est", num(gain["point"], label, signed=True)),
                   (f"{name}CI", interval(gain, label))]
    return values


def _member(holm: Mapping[str, dict[str, str]], name: str) -> dict[str, str]:
    if name not in holm:
        raise AnalysisError("missing_row", f"holm.csv has no member {name}")
    return holm[name]


def _count(value: str) -> str:
    if not value.isdigit():
        raise AnalysisError("not_a_number", f"count {value[:20]!r} is not a whole number")
    return f"{int(value):,}".replace(",", "{,}")


def _camel(condition: str) -> str:
    return "".join(part.capitalize() for part in condition.split("_"))


# ------------------------------------------------------------------------------------- output

REQUIRED = {
    "h1_rates": ("system", "line", "endpoint", "condition", "level", "point", "examples", "status", "provenance"),
    "h2_benefits": ("system", "line", "endpoint", "contrast", "level", "point", "ci_low", "ci_high", "status"),
    "mismatch_controls": ("system", "line", "endpoint", "contrast", "level", "point", "ci_low", "ci_high"),
    "primary_test": ("system", "line", "endpoint", "point", "ci_low", "ci_high", "p", "quadratic_point",
                     "quadratic_ci_low", "quadratic_ci_high", "examples", "dialogues", "status"),
    "holm": ("name", "endpoint", "point", "ci_low", "ci_high", "p_holm", "status"),
    "h4_rates": ("system", "line", "condition", "level", "measure", "point", "status"),
    "sensitivity": ("system", "line", "endpoint", "contrast", "statistic", "sensitivity", "point", "ci_low",
                    "ci_high"),
    "transfer": ("system", "gpt_family", "n", "request_recall", "value_accuracy", "end_to_end",
                 "invalid_outputs", "data_kind"),
    "h5_rates": ("system", "line", "endpoint", "category", "condition", "point", "examples", "status"),
    "h5_benefits": ("system", "line", "endpoint", "category", "contrast", "point", "ci_low", "ci_high", "status"),
    "h5_standardized": ("system", "line", "endpoint", "level", "kind", "point", "ci_low", "ci_high", "status"),
}
BUILDERS: tuple[tuple[str, Callable[[Mapping[str, Source]], Fragment]], ...] = (
    ("overall", lambda s: overall_rates(s["h1_rates"], s["mismatch_controls"])),
    ("confirmatory", lambda s: confirmatory(s["primary_test"], s["holm"])),
    ("levels", lambda s: level_detail(s["h1_rates"], s["h2_benefits"])),
    ("stages", lambda s: stages(s["h4_rates"])),
    ("intents", lambda s: intents(s["h5_rates"], s["h5_benefits"])),
    ("transfer", lambda s: transfer(s["transfer"])),
    ("numbers", numbers),
)


def header(fragment: Fragment, tables_dir: str) -> str:
    lines = ["% Generated; do not edit. Regenerate with:", f"%   {COMMAND}"]
    for source in fragment.sources:
        lines.append(f"% Source: {tables_dir}/{source.name} sha256={source.sha256}")
    configs = sorted({s.config for s in fragment.sources if s.config})
    lines.append(f"% Analysis config: {', '.join(configs) or 'not recorded'}")
    return "\n".join(lines) + "\n"


def provenance(fragments: Sequence[Fragment], tables_dir: str) -> str:
    """An appendix table: each generated fragment, its source files and their short hashes."""
    lines = []
    for fragment in fragments:
        sources = "; ".join(f"\\texttt{{{s.name.replace('_', chr(92) + '_')}}} ({s.sha256[:12]})"
                            for s in fragment.sources)
        lines.append(f"\\texttt{{{fragment.name}.tex}} & {sources} \\\\")
    body = tabular("lp{10cm}", ("Fragment", f"Sources under \\texttt{{{tables_dir.replace('_', chr(92) + '_')}}} (SHA-256 prefix)"),
                   lines)
    return body


def build(tables: Path) -> list[Fragment]:
    sources = {name: load_source(tables, name, columns) for name, columns in REQUIRED.items()}
    return [builder(sources) for _, builder in BUILDERS]


def write(fragments: Sequence[Fragment], out: Path, tables_dir: str) -> list[Path]:
    """Write every fragment and the provenance table; refuse all of it if any would carry an ID."""
    texts = {f"{f.name}.tex": header(f, tables_dir) + f.body for f in fragments}
    texts["provenance.tex"] = "% Generated; do not edit.\n" + provenance(fragments, tables_dir)
    for name, text in texts.items():
        if DIALOGUE_ID_PATTERN.search(text):
            raise AnalysisError("id_in_table", f"{name} would carry a dialogue ID; refusing to write")
    written = []
    for name, text in texts.items():
        path = out / name
        write_atomic(path, text.encode("utf-8"))
        written.append(path)
    return written


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Paper tables from the committed test analysis tables.")
    parser.add_argument("--tables", type=Path, default=Path("results/analysis/test"))
    parser.add_argument("--out", type=Path, default=Path("paper/generated"))
    args = parser.parse_args(argv)
    if args.out.resolve() == args.tables.resolve():
        print("error: --out must differ from --tables", file=sys.stderr)
        return 2
    try:
        written = write(build(args.tables), args.out, args.tables.as_posix())
    except AnalysisError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {len(written)} files to {args.out.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
