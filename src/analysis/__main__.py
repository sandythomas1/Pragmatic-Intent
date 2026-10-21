"""Spec 007 analysis command line.

Run from the repository root (Python 3.12, standard library only)::

    python -m src.analysis run --split dev --inputs configs/analysis/inputs-dev.toml
    python -m src.analysis run --split test --inputs configs/analysis/inputs-test.toml --allow-test
    python -m src.analysis error-audit sample --on YYYY-MM-DD --inspector A1 --inputs configs/analysis/inputs-test.toml
    python -m src.analysis error-audit export      # after coding data/interim/error_audit/error_audit_sheet.csv
    python -m src.analysis error-audit report

**Test gates (FR21).** They run in this order, before any prediction file is opened:

1. ``--allow-test``;
2. a config with ``draft = false``;
3. a current spec 006 audit;
4. ``data/manifests/freeze.json`` recording this config's hash.

Claude runs dev only; Sandy runs test. The console shows counts, system names and paths, never
an example ID or any text.
"""

from __future__ import annotations

import argparse
import datetime
import sys
from collections.abc import Sequence
from pathlib import Path

from src.analysis import error_audit as ea
from src.analysis.config import DEFAULT_CONFIG, AnalysisConfig, load_config
from src.analysis.estimands import analyse
from src.analysis.files import AnalysisError, parse_json, read_bounded, read_verified
from src.analysis.freeze import FREEZE_FILE, require_frozen_config
from src.analysis.inputs import INPUTS_VERSION, AnalysisInputs, load_inputs
from src.analysis.outcomes import build_outcomes, load_evaluation_set
from src.analysis.report import (
    REPORT_NAME,
    assemble,
    check_outputs,
    json_bytes,
    output_locations,
    table_paths,
    tables,
    transfer_rows,
    write_atomic,
    write_tables,
)
from src.data import split_audit as sa
from src.data.contexts import RENDERER_VERSION
from src.data.direct_dataset import load_dialogues, load_items
from src.data.intent_categories import MAPPING_VERSION
from src.evaluation import interpretation as ip
from src.evaluation import stage2, transfer
from src.evaluation.test_audit import SplitAudit, audit_summary_path, require_test_audit
from src.stage1.provenance import git_state, sha256


def _at(root: Path, path: Path) -> Path:
    return (path if path.is_absolute() else root / path).resolve()


def _shown(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix()


def gate_test(args: argparse.Namespace, root: Path, config: AnalysisConfig) -> SplitAudit:
    """FR21, in order; nothing here opens a prediction file."""
    if not args.allow_test:
        raise AnalysisError("test_not_allowed", "a test analysis needs --allow-test, after the WP-08 freeze")
    if config.draft:
        raise AnalysisError("draft_config", "the analysis config is still a draft; the freeze sets draft = false")
    audit_path = _at(root, args.audit)
    audit = require_test_audit(_at(root, args.items), _at(root, args.dialogues), registry_path=_at(root, args.registry),
                               audit_path=audit_path, summary_path=audit_summary_path(audit_path))
    require_frozen_config(_at(root, args.freeze), config.sha256)
    return audit


def run(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    config_path = _at(root, args.config)
    config = load_config(config_path)
    audit = gate_test(args, root, config) if args.split == "test" else None
    inputs = load_inputs(_at(root, args.inputs), config, args.split, base=root)
    report_dir, tables_dir = output_locations(root, args.split)
    report_path = report_dir / REPORT_NAME
    check_outputs([report_path], _input_paths(args, root, config_path, inputs))
    items, dialogues = _at(root, args.items), _at(root, args.dialogues)
    evaluation = load_evaluation_set(items, dialogues, args.split, config.rules_version, audit)
    table = build_outcomes(evaluation, inputs)
    body = analyse(table, config, split=args.split)
    provenance = {
        "config_sha256": config.sha256, "config_file_sha256": sha256(config_path),
        "inputs_sha256": inputs.sha256, "files": inputs.files(root),
        "items_sha256": sha256(items), "dialogues_sha256": sha256(dialogues),
        "test_audit": audit.report(len(evaluation.examples)) if audit else None,
        "freeze_record_sha256": sha256(_at(root, args.freeze)) if audit else None,
        "versions": {"analysis_config": config.version, "inputs": INPUTS_VERSION, "rules": config.rules_version,
                     "category": MAPPING_VERSION, "renderer": RENDERER_VERSION, "stage2_scorer": stage2.SCORER_VERSION,
                     "transfer_scorer": transfer.SCORER_VERSION, "reference": ip.REFERENCE_VERSION,
                     "normalizer": ip.NORMALIZER_VERSION},
        **git_state(ignore=(report_dir, tables_dir)),
        "command": " ".join(["python -m src.analysis run", f"--split {args.split}",
                             f"--config {_shown(root, config_path)}", f"--inputs {_shown(root, inputs.path)}",
                             *(["--allow-test"] if args.split == "test" else [])]),
    }
    report = assemble(body, split=args.split, config=config, provenance=provenance)
    report["transfer"] = transfer_rows({name: read_verified(system.transfer)
                                        for name, system in inputs.systems.items() if system.transfer is not None})
    built = tables(report, report["transfer"])
    check_outputs(table_paths(tables_dir, built), _input_paths(args, root, config_path, inputs))
    write_atomic(report_path, json_bytes(report))
    write_tables(tables_dir, built, committed=args.split == "test")
    _log(report, inputs, evaluation_size=(len(evaluation.examples), len({e.dialogue_id for e in evaluation.examples})),
         report_path=_shown(root, report_path), tables_path=_shown(root, tables_dir))
    return 0


def _input_paths(args: argparse.Namespace, root: Path, config_path: Path, inputs: AnalysisInputs) -> list[Path]:
    paths = [config_path, inputs.path, _at(root, args.items), _at(root, args.dialogues), _at(root, args.registry),
             _at(root, args.audit), audit_summary_path(_at(root, args.audit)), _at(root, args.freeze)]
    return paths + [root / shown for shown in inputs.files(root)]


def _log(report: dict, inputs: AnalysisInputs, *, evaluation_size: tuple[int, int], report_path: str,
         tables_path: str) -> None:
    """Counts, system names and paths only (spec 007 NFR observability; no IDs or text)."""
    not_run = sorted(name for name, status in report["systems"].items() if status == "not_run")
    runs = sum(len(s.stage1) + len(s.stage2) for s in inputs.systems.values())
    print(f"analysis {report['split']} [{report['stamp']}]: {evaluation_size[0]} examples in "
          f"{evaluation_size[1]} dialogues; {len(report['systems']) - len(not_run)} systems run, "
          f"{len(not_run)} not run{(' (' + ', '.join(not_run) + ')') if not_run else ''}")
    for name, system in inputs.systems.items():
        for stream, runs_of in (("stage1", system.stage1), ("stage2", system.stage2)):
            if runs_of:
                seeds = sorted({(r.train_condition, r.seed) for r in runs_of})
                trains = sorted({t for t, _ in seeds})
                print(f"  {name} {stream}: train {', '.join(trains)}; seeds {sorted({s for _, s in seeds})}")
    statistics = report["statistics"]
    print(f"component check passed for {runs} runs; {statistics['count']} statistics "
          f"({statistics['sparse']} sparse, {statistics['unstable']} unstable)")
    primary = report["primary_test"]
    print(f"primary test ({primary['system']}): {primary['status']}"
          + (f", {primary['decision']}" if primary["status"] == "ok" else ""))
    print(f"report -> {report_path}; tables -> {tables_path}")


def _today() -> datetime.date:
    return datetime.date.today()


def audit_sample(args: argparse.Namespace) -> int:
    """FR23–FR25. Gates first; the registry gains rows before the sheet appears."""
    root = args.root.resolve()
    config = load_config(_at(root, args.config))
    gate = ea.check_gate(freeze_path=_at(root, args.freeze), on=args.on, inspector=args.inspector,
                         report_path=_at(root, args.report), config=config, today=_today())
    items_path, dialogues_path = _at(root, args.items), _at(root, args.dialogues)
    audit_path = _at(root, args.audit)
    audit = require_test_audit(items_path, dialogues_path, registry_path=_at(root, args.registry),
                               audit_path=audit_path, summary_path=audit_summary_path(audit_path))
    inputs = load_inputs(_at(root, args.inputs), config, "test", base=root)
    evaluation = load_evaluation_set(items_path, dialogues_path, "test", config.rules_version, audit)
    table = build_outcomes(evaluation, inputs)
    averaged, per_seed, line = ea.find_errors(table, config)
    errors = sorted(i for i, value in averaged.items() if value < ea.ERROR_BELOW)
    sampled, strata = ea.draw(errors, evaluation.slices["rule_level"], config)
    routed = ea.routed_outputs(table, inputs, config.primary.system, line, evaluation)
    items = {item["item_id"]: item for item in load_items(items_path)}
    rows = ea.sheet_rows(sampled, evaluation, per_seed, routed, items, load_dialogues(dialogues_path))
    design = config.error_audit
    summary = {"freeze_date": gate.freeze_date.isoformat(), "on": gate.on.isoformat(), "inspector": gate.inspector,
               "report_sha256": gate.report_sha256, "config_sha256": config.sha256, "seed": design.seed,
               "per_level": design.per_level, "levels": list(design.levels), "system": config.primary.system,
               "line": line, "condition": ea.CONDITION, "endpoint": ea.ENDPOINT,
               "error_definition": f"seed-averaged {ea.ENDPOINT} below {ea.ERROR_BELOW}", "strata": strata,
               "locked_sha256": {row["example_id"]: ea.locked_sha256(row) for row in rows}}
    sheet, _, added = ea.register_and_write(root=root, registry_path=_at(root, args.registry), items_path=items_path,
                                            rows=rows, summary=summary, gate=gate)
    drawn = ", ".join(f"{s['level']} {s['drawn']}/{s['quota']}" for s in strata)
    print(f"error audit sample: {len(errors)} errors; drawn {drawn}; "
          f"shortfall {sum(s['shortfall'] for s in strata)}; {added} registry rows added (post_scoring)")
    print(f"sheet -> {_shown(root, sheet)} (git-ignored; holds test text)")
    return 0


def _audit_summary(root: Path) -> dict:
    data = read_bounded(root / ea.SHEET_DIR / ea.SUMMARY_NAME, 16 << 20)
    summary = parse_json(data, ea.SUMMARY_NAME)
    if not isinstance(summary, dict) or not isinstance(summary.get("locked_sha256"), dict):
        raise AnalysisError("summary_malformed", f"{ea.SUMMARY_NAME} is not an error-audit sample summary")
    return summary


def audit_export(args: argparse.Namespace) -> int:
    """FR26: the validated, text-free codes file (example ID, level, code, flag)."""
    root = args.root.resolve()
    codes = ea.validate_sheet(ea.read_sheet(root / ea.SHEET_DIR / ea.SHEET_NAME), _audit_summary(root))
    write_atomic(root / ea.CODES_PATH, ea.sheet_bytes(codes, ea.CODES_FIELDS))
    print(f"error audit export: {len(codes)} coded rows -> {ea.CODES_PATH.as_posix()}")
    return 0


def audit_report(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    summary = _audit_summary(root)
    rows = ea.read_codes(root / ea.CODES_PATH, summary)
    counts = ea.code_counts(rows, summary)
    write_atomic((root / ea.REPORT_STEM).with_suffix(".json"), json_bytes(counts))
    write_atomic((root / ea.REPORT_STEM).with_suffix(".md"), ea.counts_markdown(counts))
    print(f"error audit report: {counts['n']} codes in {len(counts['counts'])} levels -> "
          f"{ea.REPORT_STEM.as_posix()}.{{json,md}}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m src.analysis", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", help="the H1–H5 analysis of one split")
    run_parser.add_argument("--split", choices=("dev", "test"), required=True)
    run_parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    run_parser.add_argument("--inputs", type=Path, required=True, help="configs/analysis/inputs-<split>.toml")
    run_parser.add_argument("--allow-test", action="store_true", help="test only, after the WP-08 freeze")
    _common_paths(run_parser)
    run_parser.set_defaults(handler=run)

    audit = commands.add_parser("error-audit", help="post-scoring error audit of the primary system (Sandy only)")
    audit_commands = audit.add_subparsers(dest="audit_command", required=True)
    sample = audit_commands.add_parser("sample", help="draw, register and write the sheet")
    sample.add_argument("--on", required=True, help="inspection date, YYYY-MM-DD (on or after the freeze date)")
    sample.add_argument("--inspector", required=True, help="pseudonymous annotator ID, e.g. A1")
    sample.add_argument("--report", type=Path, default=Path("outputs/analysis/test/report.json"),
                        help="the frozen_test analysis report")
    sample.add_argument("--inputs", type=Path, required=True, help="configs/analysis/inputs-test.toml")
    sample.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    _common_paths(sample)
    sample.set_defaults(handler=audit_sample)
    for name, handler, text in (("export", audit_export, "validate the filled sheet; write the codes file"),
                                ("report", audit_report, "count codes by level")):
        command = audit_commands.add_parser(name, help=text)
        command.add_argument("--root", type=Path, default=Path("."))
        command.set_defaults(handler=handler)
    return parser


def _common_paths(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", type=Path, default=Path("."), help="repository root; relative paths start here")
    parser.add_argument("--items", type=Path, default=sa.DEFAULT_ITEMS)
    parser.add_argument("--dialogues", type=Path, default=sa.DEFAULT_DIALOGUES)
    parser.add_argument("--registry", type=Path, default=sa.DEFAULT_REGISTRY)
    parser.add_argument("--audit", type=Path, default=sa.DEFAULT_AUDIT)
    parser.add_argument("--freeze", type=Path, default=FREEZE_FILE)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except KeyError:
        # A lookup failure would name the missing key, which could be an example ID.
        print("Analysis failed: an internal lookup failed (inputs and evaluation set disagree)", file=sys.stderr)
        return 1
    except sa.RegistryError as error:
        # Registry problems name dialogues; on test those are IDs, so only the count is shown.
        print(f"Analysis failed: the registry rejected the change ({len(error.problems)} problem(s)); "
              "run python -m src.data.split_audit register to see them", file=sys.stderr)
        return 1
    except (AnalysisError, ValueError, OSError) as error:
        print(f"Analysis failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
